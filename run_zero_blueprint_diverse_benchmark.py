"""
Diverse Zero-Blueprint Benchmark with Expanded 15-20 Turn Budget.

Evaluates autonomous analog circuit synthesis from first physical principles across
diverse analog IC classes with ZERO blueprint contamination:
  1. Voltage Comparator (LM311)
  2. Operational Amplifier (LM741)
  3. Precision Timer / Multivibrator (NE555)

All runs strictly verify 0 existing blueprints in harness2_library prior to execution.
"""

import json
import logging
import os
import sys
import time
from typing import Any

# Ensure analogverifier is in sys.path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from ai_analog_designer import AutonomousAnalogDesignAgent

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("ZeroBlueprintBenchmark")

BENCHMARK_ICS = [
    {
        "name": "LM311",
        "category": "Voltage Comparator",
        "pdf": os.path.abspath("testcases/lm311.pdf"),
        "library_key": "LM311",
        "description": "High-speed voltage comparator with open-collector output and strobe/balance pins"
    },
    {
        "name": "LM741",
        "category": "Operational Amplifier",
        "pdf": os.path.abspath("testcases/lm741.pdf"),
        "library_key": "LM741",
        "description": "General-purpose BJT operational amplifier with offset null and internal compensation"
    },
    {
        "name": "NE555",
        "category": "Precision Timer",
        "pdf": os.path.abspath("testcases/ne555.pdf"),
        "library_key": "NE555",
        "description": "Classic precision timer with dual comparators, SR flip-flop, and discharge transistor"
    }
]

def check_zero_blueprint_contamination(library_dir: str, ic_key: str) -> bool:
    """Verifies that no prior blueprint or experience exists for this IC in harness2_library."""
    if not os.path.exists(library_dir):
        return True
    for root, dirs, files in os.walk(library_dir):
        for d in dirs:
            if ic_key.lower() in d.lower():
                return False
        for f in files:
            if ic_key.lower() in f.lower() and f.endswith((".json", ".cir", ".md")):
                return False
    return True

def run_single_ic_benchmark(ic_cfg: dict[str, Any], max_turns: int = 15, base_out_dir: str = "benchmark_results/zero_blueprint_diverse") -> dict[str, Any]:
    ic_name = ic_cfg["name"]
    pdf_path = ic_cfg["pdf"]
    out_dir = os.path.abspath(os.path.join(base_out_dir, f"eval_{ic_name.lower()}"))
    os.makedirs(out_dir, exist_ok=True)

    print("\n" + "=" * 80)
    print(f"BENCHMARKING FRESH IC (ZERO-BLUEPRINT): {ic_name} ({ic_cfg['category']})")
    print(f"Max Turns Budget: {max_turns}")
    print(f"Datasheet PDF: {pdf_path}")
    print(f"Output Directory: {out_dir}")
    print("=" * 80)

    # 1. Blueprint Contamination Check
    lib_path = os.path.abspath("harness2_library")
    is_clean = check_zero_blueprint_contamination(lib_path, ic_cfg["library_key"])
    print(f"[*] Clean-Room Verification: Zero Pre-existing Blueprints in Library = {is_clean}")
    if not is_clean:
        print(f"[!] WARNING: Found existing files matching {ic_cfg['library_key']} in {lib_path}!")

    # 2. Execute Autonomous Design Agent
    t_start = time.time()
    def cb(phase_num, phase_title, msg):
        print(f"  [{time.strftime('%H:%M:%S')}] [P{phase_num}: {phase_title}] {msg}")

    agent = AutonomousAnalogDesignAgent(
        output_dir=out_dir,
        max_iterations=max_turns
    )

    result = agent.run(
        datasheet_pdf_path=pdf_path,
        progress_callback=cb
    )
    elapsed = round(time.time() - t_start, 1)

    summary = result.get("summary", {})
    pass_rate = summary.get("pass_rate_percent", 0.0)
    final_netlist_path = summary.get("final_netlist_path")

    # Trajectory Analysis
    iterations = summary.get("iterations", [])
    turns_executed = len(iterations)
    tools_used = []
    for it in iterations:
        t_data = it.get("design_rationale", {}).get("hermes_turn", {})
        for tc in t_data.get("tools_called", []):
            if tc not in tools_used:
                tools_used.append(tc)

    # Inspect synthesized netlist
    netlist_code = ""
    device_counts = {}
    if final_netlist_path and os.path.exists(final_netlist_path):
        with open(final_netlist_path, "r", encoding="utf-8") as f:
            netlist_code = f.read()
        lines = [ln.strip() for ln in netlist_code.splitlines()]
        elem_lines = [ln for ln in lines if ln and ln[0].upper() in "RCLQMDJVI" and not ln.startswith(".")]
        device_counts = {
            "transistors": len([l for l in elem_lines if l[0].upper() in "QM"]),
            "resistors": len([l for l in elem_lines if l[0].upper() == "R"]),
            "capacitors": len([l for l in elem_lines if l[0].upper() == "C"]),
            "diodes": len([l for l in elem_lines if l[0].upper() == "D"]),
            "total_elements": len(elem_lines)
        }

    res_record = {
        "ic": ic_name,
        "category": ic_cfg["category"],
        "clean_room_zero_blueprint": is_clean,
        "max_turns_budget": max_turns,
        "turns_executed": turns_executed,
        "elapsed_seconds": elapsed,
        "pass_rate_percent": pass_rate,
        "spec_count": summary.get("spec_count", 0),
        "tools_used": tools_used,
        "final_netlist_path": final_netlist_path,
        "device_counts": device_counts,
        "has_transistor_synthesis": device_counts.get("transistors", 0) > 0,
        "trajectory": [
            {
                "iteration": it.get("iteration"),
                "pass_rate": it.get("pass_rate_percent", 0.0),
                "tools": it.get("design_rationale", {}).get("hermes_turn", {}).get("tools_called", [])
            }
            for it in iterations
        ]
    }

    print("\n" + "-" * 60)
    print(f"RESULT FOR {ic_name}:")
    print(f"  Turns Executed: {turns_executed}/{max_turns}")
    print(f"  Elapsed: {elapsed}s")
    print(f"  Pass Rate: {pass_rate:.1f}%")
    print(f"  Transistors Synthesized: {device_counts.get('transistors', 0)}")
    print(f"  Passives Synthesized: {device_counts.get('resistors', 0)} resistors, {device_counts.get('capacitors', 0)} caps")
    print(f"  Tools Dispatched: {tools_used}")
    print("-" * 60 + "\n")

    return res_record

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Diverse Zero-Blueprint Benchmark with 15-20 Turns")
    parser.add_argument("--ics", default="LM311,LM741,NE555", help="Comma-separated list of ICs")
    parser.add_argument("--max-turns", type=int, default=15, help="Max turn budget for Hermes autonomous loop")
    args = parser.parse_args()

    selected_ics = [s.strip().upper() for s in args.ics.split(",") if s.strip()]
    target_cfgs = [c for c in BENCHMARK_ICS if c["name"].upper() in selected_ics]

    if not target_cfgs:
        print(f"No matching ICs found for {selected_ics}. Available: {[c['name'] for c in BENCHMARK_ICS]}")
        sys.exit(1)

    out_base = "benchmark_results/zero_blueprint_diverse"
    os.makedirs(out_base, exist_ok=True)

    all_results = []
    for cfg in target_cfgs:
        rec = run_single_ic_benchmark(cfg, max_turns=args.max_turns, base_out_dir=out_base)
        all_results.append(rec)

    json_path = os.path.join(out_base, "zero_blueprint_benchmark_results.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(all_results, f, indent=2)
    print(f"\n[+] Full benchmark results saved to: {json_path}")

if __name__ == "__main__":
    main()
