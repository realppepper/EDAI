"""
Harness²-Enhanced Circuit Architect for Recursive Analog Netlist Synthesis.
Integrates Google Research's Harness² framework (arXiv:2603.22472) with OpenRouter and NVIDIA NIM API.
"""
from __future__ import annotations

import logging
import os
import re
from collections.abc import Callable
from typing import Any

from ai_analog_designer.circuit_synthesis.netlist_validator import NetlistValidator
from ai_analog_designer.hermes_core.web_reference_search import (
    WebCircuitReferenceSearcher,
)
from ai_analog_designer.llm_client import LLMClient

from .harness_library import HarnessLibrary
from .harness_proposer import Harness2Proposer
from .harness_tree import HarnessTree

logger = logging.getLogger("Harness2CircuitArchitect")


class Harness2CircuitArchitect:
    """
    Harness² Recursive Analog Circuit Architect.
    Replaces static one-shot prompts with an evolutionary 8-component execution harness
    (C1-C8) refined via contrastive Propose-Probe-Compose cycles using NVIDIA NIM and OpenRouter.
    """

    def __init__(
        self,
        llm_client: LLMClient | None = None,
        nim_client: LLMClient | None = None,
        openrouter_client: LLMClient | None = None,
        library_root: str = "harness2_library",
        improver_provider: str | None = None,
        synthesizer_provider: str | None = None,
    ):
        # Preserve the application's selected provider.  The old defaults could
        # silently route synthesis to OpenRouter even when the web server was
        # configured solely with an NVIDIA NIM key.
        selected_provider = getattr(llm_client, "provider", "") or os.environ.get("LLM_PROVIDER", "nim")
        self.nim_client = nim_client or (
            llm_client if selected_provider == "nim" else (LLMClient(provider="nim") if os.environ.get("NVIDIA_API_KEY") else None)
        )
        self.openrouter_client = openrouter_client or (
            llm_client if selected_provider == "openrouter" else (LLMClient(provider="openrouter") if os.environ.get("OPENROUTER_API_KEY") else None)
        )
        self.groq_client = (
            llm_client if selected_provider == "groq" else (LLMClient(provider="groq") if os.environ.get("GROQ_API_KEY") else None)
        )
        self.wusrouter_client = (
            llm_client if selected_provider == "wusrouter" else (LLMClient(provider="wusrouter") if os.environ.get("WUSROUTER_API_KEY") else None)
        )
        improver_provider = (improver_provider or os.environ.get("HARNESS2_IMPROVER_PROVIDER") or selected_provider).lower()
        synthesizer_provider = (synthesizer_provider or os.environ.get("HARNESS2_SYNTHESIZER_PROVIDER") or selected_provider).lower()
        allowed_providers = {"nim", "openrouter", "groq", "wusrouter"}
        if improver_provider not in allowed_providers or synthesizer_provider not in allowed_providers:
            raise ValueError("Harness² providers must be 'nim', 'openrouter', 'groq', or 'wusrouter'")

        self.library = HarnessLibrary(root_dir=library_root)
        self.proposer = Harness2Proposer(
            nim_client=self.nim_client,
            openrouter_client=self.openrouter_client,
            groq_client=self.groq_client,
            wusrouter_client=self.wusrouter_client,
            improver_provider=improver_provider,
            synthesizer_provider=synthesizer_provider
        )
        self.validator = NetlistValidator()
        self.web_searcher = WebCircuitReferenceSearcher()

        # Active harness tree (initialized from library bootstrapping)
        self.active_tree = HarnessTree()

    def bootstrap_for_device(self, category: str, part_name: str) -> HarnessTree:
        """Bootstraps the harness tree from the persistent improvement library."""
        self.active_tree = self.library.bootstrap_harness(category=category, base_tree=self.active_tree)
        logger.info(f"Harness² bootstrapped for {part_name} ({category}) with accumulated library lessons.")
        return self.active_tree

    def synthesize_candidate(
        self,
        tree: HarnessTree,
        ic_info: dict[str, Any],
        pins: list[dict[str, Any]],
        specifications: list[dict[str, Any]],
        pdg_schedule: dict[str, float],
        measurement_plan: dict[str, Any] | None = None,
        user_prompt: str | None = None,
        prior_feedback: str | None = None
    ) -> dict[str, Any]:
        """Synthesizes a SPICE netlist under a specific harness tree."""
        part_name = ic_info.get("part_name") or ic_info.get("name") or "ANALOG_IC"
        subckt_name = re.sub(r'[^a-zA-Z0-9_]', '_', part_name).upper()

        pins_summary = "\n".join([
            f"  - Pin '{p['name']}' (Role: {p.get('role', 'SIGNAL')}, Dir: {p.get('direction', 'INPUT')}, Desc: {p.get('description', '')})"
            for p in pins
        ])

        specs_summary = "\n".join([
            f"  - Parameter '{s['symbol']}': Min={s.get('min')}, Typ={s.get('typ')}, Max={s.get('max')} {s.get('unit', '')} | Conditions: {s.get('test_conditions', '')}"
            for s in specifications
        ])

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
## HOW THIS CIRCUIT WILL BE MEASURED (DUT is instantiated with V- = ground, V+ = VS):
{fixture_brief(measurement_plan)}
The subcircuit must work with its negative supply pin tied to 0 V (single supply), must not reference external node '0' directly, and must not contain analysis directives.
"""
            except Exception:
                pass

        user_prompt_section = f"\n## USER DIRECTIVES:\n{user_prompt}\n" if user_prompt else ""
        try:
            web_ref = self.web_searcher.search_circuit_reference(
                ic_name=part_name,
                category=ic_info.get("category", "analog_ic")
            )
            if web_ref and web_ref.get("formatted_markdown"):
                user_prompt_section += f"\n## WEB CIRCUIT DESIGN REFERENCES (Tavily & Exa):\n{web_ref['formatted_markdown']}\n"
        except Exception as e:
            logger.debug(f"Web reference lookup in synthesize_candidate skipped: {e}")

        feedback_section = f"\n## PREVIOUS FEEDBACK & DIAGNOSTICS:\n{prior_feedback}\n" if prior_feedback else ""

        # Compile full structured prompt from the harness tree
        full_prompt = tree.compile_synthesis_prompt(
            part_name=subckt_name,
            pins_summary=pins_summary,
            specs_summary=specs_summary,
            schedule_summary=schedule_summary,
            measurement_section=measurement_section,
            user_prompt_section=user_prompt_section,
            feedback_section=feedback_section
        )

        synth_client = self.proposer.get_synthesizer_client()
        logger.info(f"Harness² Synthesizer querying {synth_client.provider.upper()} ({synth_client.default_model})...")

        raw_resp = synth_client.complete(
            full_prompt,
            system_prompt=tree.c1_system_prompt,
            temperature=0.1,
            max_tokens=8192,
            tag="harness2_synth"
        )

        # Parse XML tags
        arch_summary = ""
        m_arch = re.search(r'<architecture_summary>(.*?)</architecture_summary>', raw_resp, re.DOTALL | re.IGNORECASE)
        if m_arch:
            arch_summary = m_arch.group(1).strip()

        from ai_analog_designer.circuit_synthesis.circuit_builder import (
            CircuitBuilder,
        )

        netlist_code = ""
        built = CircuitBuilder.from_json(raw_resp, subckt_name=subckt_name, pins=pins)
        if built is not None:
            netlist_code = built["netlist"]
        else:
            m_net = re.search(r'<spice_netlist>(.*?)</spice_netlist>', raw_resp, re.DOTALL | re.IGNORECASE)
            if not m_net:
                m_net = re.search(r'<spice_netlist>(.*)', raw_resp, re.DOTALL | re.IGNORECASE)
            if m_net:
                netlist_code = m_net.group(1).strip()
            else:
                m_code = re.search(r'```(?:spice|cir)?\s*(.*?)\s*```', raw_resp, re.DOTALL | re.IGNORECASE)
                if m_code:
                    netlist_code = m_code.group(1).strip()
                elif ".subckt" in raw_resp.lower():
                    netlist_code = raw_resp.strip()

        if netlist_code.startswith("```"):
            netlist_code = re.sub(r'^```[a-zA-Z]*\n', '', netlist_code)
            netlist_code = re.sub(r'\n```$', '', netlist_code)

        val_res = self.validator.validate(netlist_code, expected_subckt_name=subckt_name, expected_pins=pins)
        cleaned_netlist = val_res.get("cleaned_netlist", netlist_code.strip())

        return {
            "subcircuit_name": subckt_name,
            "architecture_summary": arch_summary,
            "spice_netlist": cleaned_netlist,
            "raw_netlist": netlist_code,
            "design_rationale": {"summary": arch_summary},
            "harness_snapshot": tree.to_dict()
        }

    def execute_contrastive_iteration(
        self,
        ic_info: dict[str, Any],
        pins: list[dict[str, Any]],
        specifications: list[dict[str, Any]],
        pdg_schedule: dict[str, float],
        base_eval: dict[str, Any],
        eval_probe_fn: Callable[[str, str], dict[str, Any]],
        measurement_plan: dict[str, Any] | None = None,
        user_prompt: str | None = None,
        base_synth: dict[str, Any] | None = None,
        iteration_index: int = 2
    ) -> tuple[dict[str, Any], dict[str, Any], HarnessTree, str]:
        """
        Executes a full Harness² Propose–Probe–Compose step:
          1. Proposes Candidate A (Invariant) and Candidate B (Domain)
          2. Probes both candidates using the simulation evaluator probe function
          3. Contrasts behaviors and composes the evolved harness tree
          4. Returns (winning_res, winning_eval, composed_tree, decision_notes)
        """
        part_name = ic_info.get("part_name") or ic_info.get("name") or "ANALOG_IC"
        feedback = base_eval.get("diagnostic_feedback", "")
        failed_specs = [e for e in base_eval.get("spec_evaluations", []) if not e.get("passed")]
        compiler_errors = base_eval.get("simulation_errors", [])

        try:
            failed_syms = [str(e.get("symbol", "")) for e in failed_specs if e.get("symbol")]
            web_ref = self.web_searcher.search_circuit_reference(
                ic_name=part_name,
                category=ic_info.get("category", "analog_ic"),
                failed_specs=failed_syms
            )
            if web_ref and web_ref.get("formatted_markdown"):
                feedback = f"{feedback}\n\n{web_ref['formatted_markdown']}".strip()
        except Exception as e:
            logger.debug(f"Web reference lookup in execute_contrastive_iteration skipped: {e}")

        # 1. Propose
        tree_inv, tree_dom = self.proposer.propose_edits(
            current_tree=self.active_tree,
            part_name=part_name,
            specifications=specifications,
            simulation_feedback=feedback,
            failed_specs=failed_specs,
            compiler_errors=compiler_errors
        )

        # 2. Probe A (Invariant)
        tag_a = f"iter{iteration_index}_probe_a"
        logger.info(f"Executing Probe A ({tag_a}: Invariant Candidate)...")
        res_a = self.synthesize_candidate(
            tree=tree_inv,
            ic_info=ic_info,
            pins=pins,
            specifications=specifications,
            pdg_schedule=pdg_schedule,
            measurement_plan=measurement_plan,
            user_prompt=user_prompt,
            prior_feedback="Focus strictly on SPICE convergence, numerical stability, and syntax invariants."
        )
        eval_a = eval_probe_fn(res_a["spice_netlist"], tag_a)

        # 3. Probe B (Domain)
        tag_b = f"iter{iteration_index}_probe_b"
        logger.info(f"Executing Probe B ({tag_b}: Domain Candidate)...")
        res_b = self.synthesize_candidate(
            tree=tree_dom,
            ic_info=ic_info,
            pins=pins,
            specifications=specifications,
            pdg_schedule=pdg_schedule,
            measurement_plan=measurement_plan,
            user_prompt=user_prompt,
            prior_feedback="Focus strictly on circuit topology, stage biasing, and transistor sizing to satisfy unmet specifications."
        )
        eval_b = eval_probe_fn(res_b["spice_netlist"], tag_b)

        # 4. Compose
        composed_tree, decision_notes, evidence = self.proposer.compose_harness(
            base_tree=self.active_tree,
            tree_a=tree_inv,
            tree_b=tree_dom,
            eval_base=base_eval,
            eval_a=eval_a,
            eval_b=eval_b
        )

        # Robust Monotonic Selection
        def score_tuple(ev):
            if not ev:
                return (-1, -1.0, -999)
            return (
                ev.get("passed_specs", 0),
                ev.get("coverage_pct", 0.0),
                -len(ev.get("simulation_errors", []))
            )

        st_base = score_tuple(base_eval)
        st_a = score_tuple(eval_a)
        st_b = score_tuple(eval_b)

        candidates = []
        if base_synth is not None:
            candidates.append((st_base, base_synth, base_eval, "Base"))
        candidates.append((st_a, res_a, eval_a, "Probe A"))
        candidates.append((st_b, res_b, eval_b, "Probe B"))

        candidates.sort(key=lambda c: c[0], reverse=True)
        best_tuple, winning_res, winning_eval, winning_tag = candidates[0]

        score_base = base_eval.get("pass_rate_percent", 0.0)
        best_score = winning_eval.get("pass_rate_percent", 0.0)

        # If improvement was made, save to persistent library
        if best_score > score_base or winning_eval.get("passed_specs", 0) > base_eval.get("passed_specs", 0):
            cue = f"Unsatisfied specs on {part_name}: {[s.get('symbol') for s in failed_specs[:4]]}"
            self.library.record_experience(
                task_id=part_name,
                category=ic_info.get("category", "ANALOG"),
                cue=cue,
                lesson=decision_notes,
                evidence=evidence,
                tree=composed_tree,
                score_before=score_base,
                score_after=best_score
            )

        self.active_tree = composed_tree
        return winning_res, winning_eval, composed_tree, f"Winner: {winning_tag} | {decision_notes}" 

    def synthesize_netlist(
        self,
        ic_info: dict[str, Any],
        pins: list[dict[str, Any]],
        specifications: list[dict[str, Any]],
        pdg_schedule: dict[str, float],
        iteration: int = 1,
        prior_feedback: str | None = None,
        user_prompt: str | None = None,
        measurement_plan: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """
        Backward-compatible interface with AICircuitArchitect.
        Bootstraps on iteration 1 and synthesizes under the active Harness² tree.
        """
        part_name = ic_info.get("part_name") or ic_info.get("name") or "ANALOG_IC"
        if iteration == 1:
            self.bootstrap_for_device(category=ic_info.get("category", "ANALOG"), part_name=part_name)

        return self.synthesize_candidate(
            tree=self.active_tree,
            ic_info=ic_info,
            pins=pins,
            specifications=specifications,
            pdg_schedule=pdg_schedule,
            measurement_plan=measurement_plan,
            user_prompt=user_prompt,
            prior_feedback=prior_feedback
        )
