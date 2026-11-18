"""
Harness² Contrastive Propose-Probe-Compose Engine.
Supports dual-LLM backend routing (NVIDIA NIM API and OpenRouter).
"""
from __future__ import annotations

import logging
import os
from typing import Any

from ai_analog_designer.llm_client import LLMClient

from .harness_tree import HarnessTree

logger = logging.getLogger("Harness2Proposer")


class Harness2Proposer:
    """
    Implements task-level recursion: Propose, Probe, and Compose.
    Coordinates between NVIDIA NIM API and OpenRouter for multi-model harness editing.
    """

    def __init__(
        self,
        nim_client: LLMClient | None = None,
        openrouter_client: LLMClient | None = None,
        groq_client: LLMClient | None = None,
        wusrouter_client: LLMClient | None = None,
        improver_provider: str = "nim",
        synthesizer_provider: str = "openrouter"
    ):
        # Improver (proposer/composer): Can use Groq, NVIDIA NIM, OpenRouter, or WusRouter
        self.nim_client = nim_client or (LLMClient(provider="nim") if os.environ.get("NVIDIA_API_KEY") else None)
        self.openrouter_client = openrouter_client or (LLMClient(provider="openrouter") if os.environ.get("OPENROUTER_API_KEY") else None)
        self.groq_client = groq_client or (LLMClient(provider="groq") if os.environ.get("GROQ_API_KEY") else None)
        self.wusrouter_client = wusrouter_client or (LLMClient(provider="wusrouter") if os.environ.get("WUSROUTER_API_KEY") else None)

        self.improver_provider = improver_provider.lower()
        self.synthesizer_provider = synthesizer_provider.lower()

    def get_improver_client(self) -> LLMClient:
        if self.improver_provider == "wusrouter" and self.wusrouter_client:
            return self.wusrouter_client
        if self.improver_provider == "groq" and self.groq_client:
            return self.groq_client
        if self.improver_provider == "nim" and self.nim_client:
            return self.nim_client
        return self.wusrouter_client or self.openrouter_client or self.groq_client or self.nim_client

    def get_synthesizer_client(self) -> LLMClient:
        if self.synthesizer_provider == "wusrouter" and self.wusrouter_client:
            return self.wusrouter_client
        if self.synthesizer_provider == "groq" and self.groq_client:
            return self.groq_client
        if self.synthesizer_provider == "openrouter" and self.openrouter_client:
            return self.openrouter_client
        return self.nim_client or self.groq_client or self.openrouter_client or self.wusrouter_client

    def propose_edits(
        self,
        current_tree: HarnessTree,
        part_name: str,
        specifications: list[dict[str, Any]],
        simulation_feedback: str,
        failed_specs: list[dict[str, Any]],
        compiler_errors: list[str]
    ) -> tuple[HarnessTree, HarnessTree]:
        """
        Generates two contrastive candidate harness trees:
          Candidate A: Invariant Edit (INV) - SPICE syntax, convergence, guardrails, ground isolation.
          Candidate B: Domain Edit (DOM) - Transistor sizing (W/L), topology selection, compensation.
        """
        client = self.get_improver_client()

        sys_prompt = """You are an Expert Harness² Meta-Architect for Analog SPICE Circuit Synthesis.
Your goal is to optimize the execution harness (System Prompt, Guardrails, Memory, Tool Guidance)
surrounding an AI circuit designer.
STRICT ANALOG RULE: Behavioral constructs (LTspice `B` sources `Bxxx`, `V=if(...)`, `table(...)`, `laplace(...)`, `VALUE={...}`, or digital `A` devices) are STRICTLY FORBIDDEN. Every circuit and blueprint must use physical transistor-level analog circuits (BJTs `Q`, MOSFETs `M`, JFETs `J`, Diodes `D`, and passive `R`/`C`/`L`).
Given simulation diagnostics from the latest iteration, propose concrete, targeted updates to the harness.
Never output prose or chat; return ONLY a JSON structure defining the edits.
"""

        failed_summary = "\n".join([
            f"  - Parameter '{s.get('symbol')}': Measured={s.get('measured')}, Expected Range=[{s.get('min')}, {s.get('max')}] {s.get('unit', '')} | Diagnostic: {s.get('diagnostic')}"
            for s in failed_specs[:8]
        ])

        errors_summary = "\n".join(compiler_errors[:5]) if compiler_errors else "None (SPICE netlist compiled cleanly)"

        user_prompt = f"""Task: Synthesize compliant SPICE subcircuit for {part_name}.

## SIMULATION SHORTFALLS & FAILURES:
### Compiler / Convergence Errors:
{errors_summary}

### Violated Specifications:
{failed_summary}

### Detailed Diagnostic Feedback:
{simulation_feedback[:2000]}

## TASK:
Generate TWO distinct, contrastive harness improvements:
1. `candidate_inv` (Invariant Edit):
   - Focus on SPICE syntax, numerical stability, avoiding singular matrix at high-impedance nodes, and strict subcircuit pin rules.
   - Propose additions to `c2_guardrails` or `c3_memory`.
2. `candidate_dom` (Domain Edit):
   - Focus on analog circuit topology, stage biasing, compensation capacitors (Cc), nulling resistors (Rz), and transistor aspect ratios (W/L) needed to hit the failed specs.
   - Propose additions to `c1_system_prompt`, `c3_memory`, or new domain blueprint in `c5_skills`.

Return JSON format:
{{
  "candidate_inv": {{
    "title": "<short description of fix>",
    "guardrails_addition": "<exact SPICE rules to append to C2 Guardrails, or empty>",
    "memory_addition": "<exact convergence lesson to append to C3 Memory, or empty>"
  }},
  "candidate_dom": {{
    "title": "<short description of fix>",
    "system_prompt_addition": "<exact synthesis directive to append to C1, or empty>",
    "memory_addition": "<exact sizing/topology lesson to append to C3, or empty>",
    "skill_addition": {{
      "name": "<e.g. low_dropout_biasing>",
      "content": "<compact blueprint text>"
    }}
  }}
}}
"""
        logger.info(f"Harness² Proposer querying improver ({self.improver_provider.upper()}) for contrastive edits...")
        try:
            resp = client.complete_json(user_prompt, system_prompt=sys_prompt, tag="harness2_propose", max_tokens=3500)
        except Exception as e:
            logger.warning(f"Improver call failed on {self.improver_provider}, falling back to alternative provider: {e}")
            alt_client = self.openrouter_client if self.improver_provider == "nim" else self.nim_client
            resp = alt_client.complete_json(user_prompt, system_prompt=sys_prompt, tag="harness2_propose_fallback", max_tokens=3500)

        # Build Candidate A (Invariant)
        tree_inv = current_tree.clone()
        inv_data = resp.get("candidate_inv", {})
        if inv_data.get("guardrails_addition"):
            tree_inv.c2_guardrails += f"\n\n### HARNESS² INVARIANT DIRECTIVE:\n{inv_data['guardrails_addition'].strip()}"
        if inv_data.get("memory_addition"):
            tree_inv.c3_memory += f"\n- {inv_data['memory_addition'].strip()}"

        # Build Candidate B (Domain)
        tree_dom = current_tree.clone()
        dom_data = resp.get("candidate_dom", {})
        if dom_data.get("system_prompt_addition"):
            tree_dom.c1_system_prompt += f"\n\n### HARNESS² DOMAIN DIRECTIVE:\n{dom_data['system_prompt_addition'].strip()}"
        if dom_data.get("memory_addition"):
            tree_dom.c3_memory += f"\n- {dom_data['memory_addition'].strip()}"
        skill = dom_data.get("skill_addition")
        if isinstance(skill, dict) and skill.get("name") and skill.get("content"):
            tree_dom.c5_skills[skill["name"]] = skill["content"].strip()

        return tree_inv, tree_dom

    def compose_harness(
        self,
        base_tree: HarnessTree,
        tree_a: HarnessTree,
        tree_b: HarnessTree,
        eval_base: dict[str, Any],
        eval_a: dict[str, Any],
        eval_b: dict[str, Any]
    ) -> tuple[HarnessTree, str, str]:
        """
        Contrasts the behavioral execution logs/diagnostics of Base vs Probe A vs Probe B
        using the Improver LLM (Harness² Behavioral Contrast) and composes the optimal
        unified harness tree even when pass rates are tied at 0%.
        """
        score_base = eval_base.get("pass_rate_percent", 0.0)
        score_a = eval_a.get("pass_rate_percent", 0.0)
        score_b = eval_b.get("pass_rate_percent", 0.0)

        passed_a = eval_a.get("passed_specs", 0)
        passed_b = eval_b.get("passed_specs", 0)
        passed_base = eval_base.get("passed_specs", 0)

        logger.info(f"Harness² Compose: Base={score_base:.1f}% ({passed_base}), Probe A={score_a:.1f}% ({passed_a}), Probe B={score_b:.1f}% ({passed_b})")

        def _summarize_eval(label: str, ev: dict[str, Any]) -> str:
            errs = (ev.get("simulation_errors") or ev.get("errors") or [])[:5]
            diag = str(ev.get("diagnostic_feedback", ""))[:1000]
            return (
                f"### {label}\n"
                f"- PassRate: {ev.get('pass_rate_percent', 0.0):.1f}% ({ev.get('passed_specs', 0)} passed)\n"
                f"- Errors: {errs}\n"
                f"- Diagnostic: {diag}\n"
            )

        adopt_inv = score_a > score_base or (not eval_a.get("simulation_errors") and bool(eval_base.get("simulation_errors")))
        adopt_dom = score_b > score_base or passed_b > passed_base
        contrast_evidence = f"Base Pass Rate: {score_base:.1f}% -> Composed Best Probe: {max(score_a, score_b):.1f}%."

        try:
            client = self.get_improver_client()
            compose_sys = (
                "You are the Harness² Behavioral Contrast Composer.\n"
                "Compare execution traces/diagnostics of Baseline (B), Probe A (Invariant edit), and Probe B (Domain edit) side-by-side.\n"
                "Even if all pass rates are 0%, detect whether Probe A or Probe B made meaningful causal progress "
                "(e.g., fixed syntax/rail errors, reached deeper simulation stage, reduced errors without regressions).\n"
                "Apply conservative evidence filtering: only adopt an edit if concrete log evidence supports it.\n"
                "Return ONLY JSON: {\"adopt_invariant\": bool, \"adopt_domain\": bool, \"evidence\": \"...\", \"summary\": \"...\"}"
            )
            compose_prompt = (
                f"{_summarize_eval('Baseline (B)', eval_base)}\n"
                f"{_summarize_eval('Probe A (Invariant Edit)', eval_a)}\n"
                f"{_summarize_eval('Probe B (Domain Edit)', eval_b)}\n"
                "Contrast B vs Probe A and B vs Probe B and decide which edits to compose."
            )
            c_res = client.complete_json(
                compose_prompt,
                system_prompt=compose_sys,
                temperature=0.1,
                max_tokens=1024,
                tag="harness2_compose",
            )
            if isinstance(c_res, dict) and str(c_res.get("evidence", "")).strip():
                adopt_inv = adopt_inv or bool(c_res.get("adopt_invariant", False))
                adopt_dom = adopt_dom or bool(c_res.get("adopt_domain", False))
                contrast_evidence = str(c_res.get("evidence", contrast_evidence))
                logger.info(f"Harness² Behavioral Contrast Compose: adopt_inv={adopt_inv}, adopt_dom={adopt_dom} | {contrast_evidence[:160]}")
        except Exception as ce:
            logger.warning(f"LLM Behavioral Contrast Compose skipped ({ce}); using deterministic comparison.")

        composed_tree = base_tree.clone()
        decision_summary = []

        if adopt_inv:
            composed_tree.c2_guardrails = tree_a.c2_guardrails
            decision_summary.append("Adopted Invariant (Candidate A) guardrails via Behavioral Contrast.")

        if adopt_dom:
            composed_tree.c1_system_prompt = tree_b.c1_system_prompt
            composed_tree.c5_skills.update(tree_b.c5_skills)
            decision_summary.append("Adopted Domain (Candidate B) topology/sizing via Behavioral Contrast.")

        # Merge memory additions from adopted candidates (or both if neither adopted yet)
        merged_memory = set(base_tree.c3_memory.splitlines())
        trees_to_merge = []
        if adopt_inv:
            trees_to_merge.append(tree_a)
        if adopt_dom:
            trees_to_merge.append(tree_b)
        for tree in trees_to_merge:
            for line in tree.c3_memory.splitlines():
                if line.strip() and line not in merged_memory:
                    composed_tree.c3_memory += f"\n{line}"
                    merged_memory.add(line)

        return composed_tree, " | ".join(decision_summary) or "Maintained baseline harness.", contrast_evidence
