"""
Harness² Recursive Analog Circuit Netlist Generation & Refinement Loop.
Inspired by Google Research's Harness² (https://github.com/google-research/harness2.git).

Combines:
  - NVIDIA NIM API (Deep Reasoning Proposer / Harness Improver: nvidia/nemotron-3-ultra-550b-a55b)
  - OpenRouter API (Ultra-Fast Netlist Synthesis / Probe Generator: nvidia/nemotron-3.5-lightning:free)
  - 8-Component Modular Execution Harness (C1-C8: System Prompt, Guardrails, Memory, Tool Guidance, Skills, Scripts, Subagents, Plugins)
  - Task-Level Recursion (Contrastive Propose-Probe-Compose cycle across multiple iterations)
  - Harnessing-Level Recursion (Cross-Task Persistent Experience Library across multiple datasheets)
"""
from __future__ import annotationsimport argparseimport jsonimport osimport sysimport timefrom typing import Anyimport networkx as nxrepo_root = os.path.abspath(os.path.dirname(__file__))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

from ai_analog_designer.circuit_synthesis.harness2 import (    Harness2CircuitArchitect,)from ai_analog_designer.llm_client import LLMClientfrom ai_analog_designer.neuro_symbolic_verifier.harness2_verifier import (    DualHarness2Coordinator,)from ai_analog_designer.neuro_symbolic_verifier.verification_flow import (    plan_for,    verify,)from ai_analog_designer.pdf_to_graph.pdg_extractor import PortDependencyGraphExtractor# Supported Benchmark ICs and Default Categories
SUPPORTED_ICS = {
    "lm358": {"category": "operational_amplifier", "description": "Dual High-Gain Operational Amplifier"},
    "lm393": {"category": "comparator", "description": "Dual Differential Comparator"},
    "tl431": {"category": "shunt_reference", "description": "Adjustable Precision Shunt Regulator"},
    "ne555": {"category": "timer", "description": "Precision Timing Circuit / Timer"},
    "lm317": {"category": "ldo_regulator", "description": "3-Terminal Adjustable Positive Voltage Regulator"},
    "opa2134": {"category": "operational_amplifier", "description": "Dual SoundPlus High Performance Audio Operational Amplifier"},
    "ref30e": {"category": "voltage_reference", "description": "Low-Power Precision Series Voltage Reference"},
}


def load_device(ic_name: str, root_dir: str) -> tuple[str, dict[str, Any], list[dict[str, Any]], list[dict[str, Any]], dict[str, float]]:
    """
    Universal device loader for benchmark ICs and parsed datasheets.
    Returns: (part_name, ic_info, pins, specifications, pdg_schedule_us)
    """
    ic_key = ic_name.lower().strip()
    gt_dir = os.path.join(root_dir, "benchmarks", "pdg_groundtruth")
    gt_path = os.path.join(gt_dir, f"{ic_key}.json")

    if os.path.exists(gt_path):
        with open(gt_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        part_name = data.get("ic", ic_key.upper())
        cat_meta = SUPPORTED_ICS.get(ic_key, {})
        category = cat_meta.get("category", data.get("category", "analog_ic"))
        description = cat_meta.get("description", data.get("description", f"{part_name} Integrated Circuit"))
        ic_info = {"name": part_name, "category": category, "description": description}
        pins = data.get("pins", [])
        specs = data.get("specs", [])
        # Normalize spec format
        for s in specs:
            if "test_conditions" not in s and "conditions" in s:
                s["test_conditions"] = s["conditions"]
            if "value" in s and s.get("typ") is None:
                s["typ"] = s["value"]

        # Automatically compute PDG activation schedule from pins & specs
        hkg = nx.MultiDiGraph()
        hkg.graph["raw_extraction"] = {"pins": pins, "electrical_parameters": specs}
        for p in pins:
            hkg.add_node(p.get("name", "PIN"), node_type="PIN", data=p)
        _, sched_s, _ = PortDependencyGraphExtractor().extract_pdg(hkg)
        schedule_us = {k: round(v * 1e6, 2) for k, v in sched_s.items()}

    elif ic_key == "ref30e":
        kg_path = os.path.join(root_dir, "output_ref30e_pipeline", "ref30e_knowledge_graph.json")
        pdg_path = os.path.join(root_dir, "output_ref30e_pipeline", "ref30e_pdg.json")
        with open(kg_path, "r", encoding="utf-8") as f:
            kg_data = json.load(f)
        with open(pdg_path, "r", encoding="utf-8") as f:
            pdg_data = json.load(f)
        part_name = "REF30E"
        ic_info = kg_data.get("ic_device", {"name": part_name, "category": "voltage_reference"})
        ic_info["name"] = part_name
        pins = kg_data.get("pins", [])
        specs = kg_data.get("electrical_parameters", [])
        schedule_us = pdg_data.get("schedule_us", {"GND": 0.0, "IN": 20.0, "OUT": 120.0})
    else:
        raise ValueError(f"Device '{ic_key}' not found in benchmarks or pipelines. Supported: {list(SUPPORTED_ICS.keys())}")

    return part_name, ic_info, pins, specs, schedule_us


def run_harness2_for_ic(
    ic_key: str,
    architect: Harness2CircuitArchitect,
    out_dir: str,
    max_iterations: int = 3
) -> dict[str, Any]:
    """
    Executes multi-iteration Harness² Propose–Probe–Compose optimization for a single IC.
    """
    part_name, ic_info, pins, specs, schedule_us = load_device(ic_key, repo_root)

    print("\n==================================================================", flush=True)
    print(f"=== [HARNESS² RUN] Target Device: {part_name} ({ic_info['category']}) ===", flush=True)
    print("==================================================================", flush=True)
    print(f"-> Pins ({len(pins)}): {[p['name'] for p in pins]}", flush=True)
    print(f"-> Electrical Specifications: {len(specs)} rows", flush=True)
    print(f"-> PDG Activation Delays: {schedule_us}", flush=True)

    # 1. Dual-Harness² Verification Plan & Gatekeeper Calibration
    plan = plan_for(ic_info, pins, specs)
    coordinator = DualHarness2Coordinator(circuit_architect=architect)
    co_res = coordinator.prepare_dual_evolution_for_ic(ic_info, pins, specs, plan)
    if co_res.get("verifier_evolved"):
        plan = plan_for(ic_info, pins, specs)
        print(f"-> [Dual-Harness²] Verifier evolved {co_res['evolved_count']} new physical fixtures validated by Golden Oracle!", flush=True)

    planned_count = plan["summary"]["planned"]
    distinct_tests = plan["summary"]["distinct_fixtures"]
    print(f"-> Deterministic Verification Plan: {planned_count} planned fixtures across {distinct_tests} distinct tests", flush=True)

    # 2. Bootstrap Harness from Cross-Task Library
    active_tree = architect.bootstrap_for_device(category=ic_info["category"], part_name=part_name)
    print(f"-> Bootstrapped C1-C8 Harness Tree (System Prompt: {len(active_tree.c1_system_prompt)} chars, Guardrails: {len(active_tree.c2_guardrails)} chars)", flush=True)

    trajectory: list[dict[str, Any]] = []

    # 3. Iteration 1: Baseline Synthesis & Probe
    print(f"\n--- [Iteration 1/{max_iterations}] Baseline Netlist Synthesis under Bootstrapped Harness ---", flush=True)
    t0 = time.time()
    curr_synth = architect.synthesize_candidate(
        tree=active_tree,
        ic_info=ic_info,
        pins=pins,
        specifications=specs,
        pdg_schedule={k: v * 1e-6 for k, v in schedule_us.items()},
        measurement_plan=plan
    )
    dt_synth = time.time() - t0
    print(f"-> Baseline netlist generated in {dt_synth:.1f}s!", flush=True)

    base_netlist = curr_synth["spice_netlist"]
    base_file = os.path.join(out_dir, f"{part_name}_iter1_base.cir")
    with open(base_file, "w", encoding="utf-8") as f:
        f.write(base_netlist)

    print("-> Simulating Baseline in LTspice (settling per PDG schedule)...", flush=True)
    curr_eval = verify(
        netlist=base_netlist,
        plan=plan,
        schedule_us=schedule_us,
        out_dir=out_dir,
        dut_name=part_name,
        label=f"{part_name.lower()}_iter1_base"
    )

    pass_base = curr_eval["pass_rate_percent"]
    passed_base = curr_eval["passed_specs"]
    total_specs = curr_eval["total_specs"]
    cov_base = curr_eval["coverage_pct"]

    print(f"-> Iteration 1 Result: Pass Rate = {pass_base:.1f}% ({passed_base}/{total_specs} specs passed), Coverage = {cov_base:.1f}%", flush=True)
    if curr_eval.get("simulation_errors"):
        print(f"   Errors detected: {curr_eval['simulation_errors'][:2]}", flush=True)

    best_synth = curr_synth
    best_eval = curr_eval
    best_pass = pass_base
    best_passed = passed_base

    trajectory.append({
        "iteration": 1,
        "type": "baseline",
        "pass_rate_pct": pass_base,
        "passed_specs": passed_base,
        "total_specs": total_specs,
        "coverage_pct": cov_base,
        "errors_count": len(curr_eval.get("simulation_errors", [])),
        "decision": "Initial baseline under bootstrapped harness"
    })

    # Helper probe evaluator
    def probe_evaluator(netlist_code: str, probe_tag: str) -> dict[str, Any]:
        probe_cir = os.path.join(out_dir, f"{part_name}_{probe_tag}.cir")
        with open(probe_cir, "w", encoding="utf-8") as f:
            f.write(netlist_code)
        ev = verify(
            netlist=netlist_code,
            plan=plan,
            schedule_us=schedule_us,
            out_dir=out_dir,
            dut_name=part_name,
            label=f"{part_name.lower()}_{probe_tag}"
        )
        return ev

    # 4. Multi-Iteration Harness² Contrastive Loops
    for it in range(2, max_iterations + 1):
        print(f"\n--- [Iteration {it}/{max_iterations}] Harness² Task-Level Recursion (Propose–Probe–Compose) ---", flush=True)

        # Early exit if 100% specs satisfied
        if best_pass >= 100.0 and total_specs > 0:
            print(f"-> All {total_specs} specifications satisfied! Ending optimization loop early.", flush=True)
            break

        t_it = time.time()
        win_synth, win_eval, evolved_tree, decision_notes = architect.execute_contrastive_iteration(
            ic_info=ic_info,
            pins=pins,
            specifications=specs,
            pdg_schedule={k: v * 1e-6 for k, v in schedule_us.items()},
            base_eval=best_eval,
            eval_probe_fn=probe_evaluator,
            measurement_plan=plan,
            base_synth=best_synth,
            iteration_index=it
        )
        dt_it = time.time() - t_it

        pass_it = win_eval["pass_rate_percent"]
        passed_it = win_eval["passed_specs"]
        cov_it = win_eval["coverage_pct"]

        print(f"-> Iteration {it} finished in {dt_it:.1f}s!", flush=True)
        print(f"-> Decision: {decision_notes}", flush=True)
        print(f"-> Iteration {it} Winning Result: Pass Rate = {pass_it:.1f}% ({passed_it}/{total_specs} specs passed), Coverage = {cov_it:.1f}%", flush=True)

        if pass_it >= best_pass:
            best_synth = win_synth
            best_eval = win_eval
            best_pass = pass_it
            best_passed = passed_it

        trajectory.append({
            "iteration": it,
            "type": "contrastive_propose_probe_compose",
            "pass_rate_pct": pass_it,
            "passed_specs": passed_it,
            "total_specs": total_specs,
            "coverage_pct": cov_it,
            "errors_count": len(win_eval.get("simulation_errors", [])),
            "decision": decision_notes
        })

    # 5. Final Netlist and Evolved Tree Output
    final_file = os.path.join(out_dir, f"{part_name}_FINAL_HARNESS2.cir")
    with open(final_file, "w", encoding="utf-8") as f:
        f.write(best_synth["spice_netlist"])

    tree_file = os.path.join(out_dir, f"evolved_harness_tree_{ic_key}.json")
    with open(tree_file, "w", encoding="utf-8") as f:
        json.dump(architect.active_tree.to_dict(), f, indent=2, ensure_ascii=False)

    report_data = {
        "device": part_name,
        "category": ic_info["category"],
        "iterations_run": len(trajectory),
        "baseline_pass_rate_pct": pass_base,
        "final_pass_rate_pct": best_pass,
        "pass_rate_delta_pct": round(best_pass - pass_base, 2),
        "passed_specs_final": best_passed,
        "total_specs": total_specs,
        "trajectory": trajectory,
        "final_netlist_path": final_file,
        "evolved_harness_tree_path": tree_file
    }

    report_file = os.path.join(out_dir, f"harness2_run_report_{ic_key}.json")
    with open(report_file, "w", encoding="utf-8") as f:
        json.dump(report_data, f, indent=2, ensure_ascii=False)

    print(f"\n[SUMMARY for {part_name}]: Baseline {pass_base:.1f}% -> Final {best_pass:.1f}% ({'+' if best_pass >= pass_base else ''}{best_pass - pass_base:.1f}%)", flush=True)
    return report_data


def main():
    parser = argparse.ArgumentParser(description="Harness² Multi-Iteration Multi-Datasheet Netlist Loop")
    parser.add_argument("--ic", default="lm358,lm393,tl431", help="Target IC(s): comma-separated or 'all' (e.g. lm358,lm393,tl431,ne555,opa2134,ref30e)")
    parser.add_argument("--iterations", type=int, default=3, help="Number of Harness² iterations per IC (default: 3)")
    args = parser.parse_args()

    # Parse IC list
    if args.ic.strip().lower() == "all":
        target_ics = list(SUPPORTED_ICS.keys())
    else:
        target_ics = [x.strip().lower() for x in args.ic.split(",") if x.strip()]

    out_dir = os.path.join(repo_root, "output_harness2_netlist")
    os.makedirs(out_dir, exist_ok=True)
    lib_dir = os.path.join(repo_root, "harness2_library")
    os.makedirs(lib_dir, exist_ok=True)

    print("==================================================================", flush=True)
    print("=== Google Research Harness² Recursive Multi-Datasheet Runner ===", flush=True)
    print("==================================================================", flush=True)
    print(f"-> Target ICs ({len(target_ics)}): {target_ics}", flush=True)
    print(f"-> Iterations per IC: {args.iterations}", flush=True)
    print(f"-> Output Directory: {out_dir}", flush=True)
    print(f"-> Experience Library: {lib_dir}", flush=True)

    # Configure Dual LLM Engines
    nim_key = os.getenv("NVIDIA_API_KEY", "")
    openrouter_key = os.getenv("OPENROUTER_API_KEY", "")

    nim_client = LLMClient(
        api_key=nim_key,
        provider="nim",
        default_model="nvidia/nemotron-3-ultra-550b-a55b",
        request_timeout=120
    )
    nim_client.fallback_models = []

    openrouter_client = LLMClient(
        api_key=openrouter_key,
        provider="openrouter",
        default_model="nvidia/nemotron-3.5-lightning:free",
        request_timeout=120
    )
    openrouter_client.fallback_models = [
        "meta-llama/llama-3.3-70b-instruct:free",
        "google/gemini-2.0-flash-exp:free"
    ]

    architect = Harness2CircuitArchitect(
        nim_client=nim_client,
        openrouter_client=openrouter_client,
        library_root=lib_dir,
        improver_provider="nim",
        synthesizer_provider="openrouter"
    )

    t_suite = time.time()
    all_reports: list[dict[str, Any]] = []

    for idx, ic_name in enumerate(target_ics, 1):
        print(f"\n>>> Running Device [{idx}/{len(target_ics)}]: {ic_name.upper()} <<<", flush=True)
        try:
            rep = run_harness2_for_ic(
                ic_key=ic_name,
                architect=architect,
                out_dir=out_dir,
                max_iterations=args.iterations
            )
            all_reports.append(rep)
        except Exception as e:
            print(f"ERROR running {ic_name}: {e}", file=sys.stderr)
            import traceback
            traceback.print_exc()

    # Aggregate Multi-IC Summary Report
    summary_file = os.path.join(out_dir, "harness2_multi_ic_summary.json")
    with open(summary_file, "w", encoding="utf-8") as f:
        json.dump(all_reports, f, indent=2, ensure_ascii=False)

    print("\n==================================================================", flush=True)
    print(f"=== Harness² Multi-Datasheet Benchmark Suite Finished ({time.time() - t_suite:.1f}s) ===", flush=True)
    print("==================================================================", flush=True)
    print(f"{'Device':<10} | {'Category':<22} | {'Base Pass':<10} | {'Final Pass':<10} | {'Delta':<8} | {'Iterations'}")
    print("-" * 75)
    for r in all_reports:
        d_str = f"{'+' if r['pass_rate_delta_pct'] >= 0 else ''}{r['pass_rate_delta_pct']:.1f}%"
        print(f"{r['device']:<10} | {r['category']:<22} | {r['baseline_pass_rate_pct']:>8.1f}% | {r['final_pass_rate_pct']:>8.1f}% | {d_str:>8} | {r['iterations_run']}")

    print(f"\nSaved Multi-IC Benchmark Summary to: {summary_file}")


if __name__ == "__main__":
    main()
