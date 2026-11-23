"""
Hermes Analog Workflow Runner.
Orchestrates the autonomous circuit synthesis and iterative verification loop
using the Harness²-tuned Hermes Agent.
"""
from __future__ import annotations

import logging
import os
import re
import time
from collections.abc import Callable
from typing import Any

from ai_analog_designer.circuit_synthesis.harness2.harness_tree import HarnessTree
from ai_analog_designer.llm_client import LLMClient

from .harness_hermes_tuner import HarnessHermesTuner
from .hermes_agent import HermesAgent
from .hermes_tools import HermesAnalogTools

logger = logging.getLogger("HermesAnalogWorkflowRunner")


class HermesAnalogWorkflowRunner:
    """
    High-level orchestrator that runs the Hermes Agent workflow tuned by Harness².
    """

    def __init__(
        self,
        output_dir: str = "output_design",
        llm_client: LLMClient | None = None,
        library_root: str = "harness2_library",
        max_turns: int = 12,
        target_pass_rate: float = 100.0,
    ):
        self.output_dir = os.path.abspath(output_dir)
        os.makedirs(self.output_dir, exist_ok=True)
        self.llm_client = llm_client or LLMClient()
        self.library_root = library_root
        self.max_turns = max_turns
        self.target_pass_rate = target_pass_rate
        self.tuner = HarnessHermesTuner(library_root=library_root)

    def run_design_flow(
        self,
        ic_info: dict[str, Any],
        pins: list[dict[str, Any]],
        specifications: list[dict[str, Any]],
        pdg_schedule: dict[str, float],
        measurement_plan: dict[str, Any] | None = None,
        user_prompt: str | None = None,
        verify_fn: Callable[..., dict[str, Any]] | None = None,
        progress_callback: Callable[[int, str, str], None] | None = None,
        base_harness_tree: HarnessTree | None = None,
    ) -> dict[str, Any]:
        """
        Executes the Hermes Agent circuit synthesis workflow:
          1. Bootstrap HarnessTree for device category.
          2. Initialize Hermes workspace and toolset.
          3. Tune Hermes (SOUL.md, MEMORY.md, blueprint skills).
          4. Execute autonomous agent loop with multi-turn tool interaction.
          5. Sync newly discovered skills and memories back into Harness² library.
        """
        part_name = ic_info.get("part_name") or ic_info.get("name") or "ANALOG_IC"
        subckt_name = re.sub(r'[^a-zA-Z0-9_]', '_', part_name).upper()
        category = ic_info.get("category", "analog_ic")

        logger.info(f"=== Starting Hermes Agent Workflow for {part_name} ({category}) ===")

        # 1. Bootstrap HarnessTree
        active_tree = self.tuner.bootstrap_tree(
            category=category,
            part_name=part_name,
            base_tree=base_harness_tree
        )

        # 2. Setup Hermes workspace
        workspace_dir = os.path.join(self.output_dir, "hermes_workspace")
        os.makedirs(workspace_dir, exist_ok=True)

        tools = HermesAnalogTools(
            output_dir=self.output_dir,
            dut_name=subckt_name,
            pins=pins,
            specifications=specifications,
            pdg_schedule=pdg_schedule,
            measurement_plan=measurement_plan,
            verify_fn=verify_fn,
            skills_dir=os.path.join(workspace_dir, "skills"),
            memory_file=os.path.join(workspace_dir, "memories", "MEMORY.md"),
            llm_client=self.llm_client,
            harness_tree=active_tree,
        )

        agent = HermesAgent(
            workspace_dir=workspace_dir,
            tools=tools,
            llm_client=self.llm_client
        )

        # 3. Tune Hermes with Harness² (C1-C8)
        self.tuner.tune_hermes(agent=agent, tree=active_tree, category=category, part_name=part_name)

        # 4. Formulate Task Prompt
        pins_summary = "\n".join([
            f"  - Pin '{p['name']}' (Role: {p.get('role', 'SIGNAL')}, Dir: {p.get('direction', 'INPUT')}, Desc: {p.get('description', '')})"
            for p in pins
        ])

        top_specs = specifications[:10]
        specs_summary = "\n".join([
            f"  - Parameter '{s.get('symbol') or s.get('name')}': Min={s.get('min')}, Typ={s.get('typ')}, Max={s.get('max')} {s.get('unit', '')} | Conditions: {s.get('test_conditions', '')}"
            for s in top_specs
        ])
        if len(specifications) > 10:
            specs_summary += f"\n  - ... and {len(specifications) - 10} additional electrical parameters."

        schedule_summary = "\n".join([
            f"  - Pin {p:10s} activation: {t*1e6:.2f} us"
            for p, t in pdg_schedule.items()
        ])

        measurement_section = ""
        if measurement_plan:
            try:
                from ai_analog_designer.neuro_symbolic_verifier.spec_planner import (
                    fixture_brief,
                )
                measurement_section = f"""
## HOW THIS CIRCUIT WILL BE MEASURED (LTspice Deterministic Testbench):
{fixture_brief(measurement_plan)}
The subcircuit must operate with its negative supply pin tied to 0 V (single supply), must not reference external node '0' directly, and must not contain analysis directives.
"""
            except Exception:
                pass

        user_prompt_section = f"\n## USER DIRECTIVES:\n{user_prompt}\n" if user_prompt else ""

        # 4b. Pre-fetch Web Circuit References via Tavily + Exa
        web_ref_section = ""
        try:
            web_res = tools.search_web_circuit_reference(
                query=f"{part_name} {category} internal schematic transistor circuit SPICE topology",
                ic_name=part_name,
                category=category
            )
            if web_res and web_res.get("formatted_markdown"):
                raw_md = web_res["formatted_markdown"]
                trimmed_md = raw_md[:1200] + ("\n... [references truncated]" if len(raw_md) > 1200 else "")
                web_ref_section = f"\n## IEEE ACADEMIC LITERATURE & CIRCUIT DESIGN REFERENCES:\n{trimmed_md}\n"
                logger.info(
                    f"Retrieved {web_res.get('references_count', 0)} circuit references "
                    f"(IEEE={web_res.get('ieee_ok')}, Tavily={web_res.get('tavily_ok')}, Exa={web_res.get('exa_ok')}) for {part_name}"
                )
        except Exception as e:
            logger.warning(f"Pre-synthesis web reference fetch skipped: {e}")

        task_prompt = f"""Synthesize a production-ready, pure transistor-level SPICE netlist for {part_name}.

## TARGET IC METADATA:
- Name: {part_name}
- Category: {category}
- Description: {ic_info.get('description', '')}

## MANDATORY PIN INTERFACE (Must match .subckt line in exact order):
{pins_summary}

## TARGET ELECTRICAL SPECIFICATIONS:
{specs_summary}

## PORT DEPENDENCY SCHEDULE (Settling time sequence):
{schedule_summary}
{measurement_section}
{web_ref_section}
{user_prompt_section}

### AGENT INSTRUCTIONS:
1. First, search available subcircuit blueprint skills using `retrieve_subcircuit_blueprint` (and `search_web_circuit_reference` if additional topology details are needed) to find the proven topology for this IC family.
2. Invoke the dedicated Netlist Synthesis Sub-Agent via `synthesize_circuit_netlist` with explicit `design_directives` (bias currents, differential pair, active load, gain stage, output buffer, and optional `blueprint_name`). Do NOT write raw SPICE netlists directly in chat; delegate synthesis to `synthesize_circuit_netlist`.
3. Run LTspice physical simulation via `verify_circuit_pdg_gate` on the synthesized netlist.
4. Examine any failed specifications or stage cutoffs. If a design trap or convergence issue occurs, record it in memory using `manage_memory`.
5. Call `synthesize_circuit_netlist` again with refined sizing directives until 100% pass rate is achieved.
6. Save your final verified circuit as a reusable blueprint using `save_subcircuit_blueprint`.
"""

        # 5. Run Hermes Agentic Loop
        t0 = time.time()
        loop_res = agent.run_autonomous_loop(
            task_prompt=task_prompt,
            max_turns=self.max_turns,
            target_pass_rate=self.target_pass_rate,
            progress_callback=progress_callback
        )
        elapsed_s = time.time() - t0

        best_netlist = loop_res.get("best_netlist")
        best_pass_rate = loop_res.get("best_pass_rate", 0.0)

        # 6. Final verification & Artifact Generation (with Harness² Blueprint Anchor)
        final_eval = {}
        if best_netlist:
            final_eval = tools.verify_circuit_pdg_gate(best_netlist, tag="final_hermes_harness2")
            best_pass_rate = final_eval.get("pass_rate_percent", best_pass_rate)
            # EDAI: a netlist blocked by the PDG gate is measured on only a handful of specs (e.g. 2/3 = 66.7 %),
            # which used to skip the blueprint fallback below. Treat a gate failure as 0 % so stored blueprints get evaluated.
            gate_failed = (not final_eval.get("stage0_passed", True) or not final_eval.get("stage1_passed", True)
                           or not final_eval.get("stage2_passed", True)
                           or any("PDG_STAGE" in str(e) for e in final_eval.get("simulation_errors", [])))
            if gate_failed:
                logger.info("Best agent netlist failed the PDG gate; treating it as 0% so the blueprint fallback runs.")
                best_pass_rate = 0.0

        if not best_netlist or best_pass_rate < 50.0:
            logger.info(f"Agent direct synthesis score ({best_pass_rate:.1f}%) < 50%. Activating Harness² Blueprint Adaptation...")
            cat_low = (category or "").lower()
            if "comp" in cat_low:
                fallback_cat = "comparator"
            elif any(k in cat_low for k in ["audio", "sound", "speaker", "btl"]):
                fallback_cat = "audio_amplifier"
            elif any(k in cat_low for k in ["ref", "tl431", "shunt", "bandgap"]):
                fallback_cat = "voltage_reference"
            elif any(k in cat_low for k in ["step", "buck", "dcdc", "converter", "regulat", "ldo", "power"]):
                fallback_cat = "power_management"
            elif any(k in cat_low for k in ["pll", "vco", "phase", "detector", "frequency", "clock"]):
                fallback_cat = "phase_locked_loop"
            else:
                fallback_cat = "operational_amplifier"

            all_blueprints = []
            seen_bps = set()
            for query_key in [part_name, category, fallback_cat]:
                if not query_key:
                    continue
                q_res = tools.retrieve_subcircuit_blueprint(query=query_key, category=category)
                for bp in q_res.get("blueprints", []):
                    bp_id = bp.get("file") or bp.get("title")
                    if bp_id not in seen_bps:
                        seen_bps.add(bp_id)
                        all_blueprints.append(bp)

            candidates: list[str] = []
            for bp in all_blueprints:
                raw_code = bp.get("content", "")
                # Extract all fenced SPICE/cir code blocks preserving models
                blocks = re.findall(r'```(?:spice|cir)?\s*([\s\S]*?)```', raw_code, re.IGNORECASE)
                for blk in blocks:
                    if ".subckt" in blk.lower() and ".ends" in blk.lower():
                        candidates.append(blk.strip())
                if not blocks and ".subckt" in raw_code.lower() and ".ends" in raw_code.lower():
                    candidates.append(raw_code.strip())

            # Also check web reference spice hints if available
            if web_res and web_res.get("spice_hints"):
                for hint in web_res["spice_hints"]:
                    if ".subckt" in hint.lower() and ".ends" in hint.lower():
                        candidates.append(hint)

            for cand_raw in candidates:
                if not agent._is_meaningful_netlist(cand_raw):
                    continue
                adapted = tools.adapt_blueprint_to_dut(cand_raw, subckt_name)
                eval_try = tools.verify_circuit_pdg_gate(adapted, tag="harness2_blueprint_anchor")
                cur_rate = eval_try.get("pass_rate_percent", 0.0)
                if cur_rate > best_pass_rate or (not best_netlist and cur_rate > 0.0):
                    logger.info(f"Harness² Blueprint Adaptation candidate passed with {cur_rate:.1f}% pass rate!")
                    best_netlist = adapted
                    best_pass_rate = cur_rate
                    final_eval = eval_try
                    if cur_rate >= 50.0:
                        break

        final_pass_rate = best_pass_rate
        if best_netlist:
            final_cir_path = os.path.join(self.output_dir, f"{subckt_name}_FINAL_HERMES_HARNESS2.cir")
            with open(final_cir_path, "w", encoding="utf-8") as f:
                f.write(best_netlist)
        else:
            final_cir_path = None

        # 7. Synchronize back to HarnessTree & HarnessLibrary
        evolved_tree = self.tuner.sync_back_to_harness(
            agent=agent,
            tree=active_tree,
            task_id=part_name,
            category=category,
            score_before=0.0,
            score_after=final_pass_rate
        )

        return {
            "subcircuit_name": subckt_name,
            "best_netlist": best_netlist,
            "final_cir_path": final_cir_path,
            "pass_rate_percent": final_pass_rate,
            "unique_kind_pass_rate_pct": final_eval.get("unique_kind_pass_rate_pct", 0.0),
            "passed_specs": final_eval.get("passed_specs", 0),
            "total_specs": len(specifications),
            "elapsed_seconds": round(elapsed_s, 1),
            "turns_executed": loop_res.get("total_turns_executed", 0),
            "trajectory": loop_res.get("trajectory", []),
            "harness_tree": evolved_tree.to_dict(),
            "workspace_dir": workspace_dir
        }
