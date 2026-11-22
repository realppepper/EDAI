"""
Jev-Compatible System-1 Tool Decision Router & Guardrail Interceptor.
Decouples action classification from generation: computes calibrated
probabilities P(tool | state), intercepts invalid calls, and breaks repetition loops.
Inspired by TypeSafe AI's Jev model for deterministic agent routing.
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any

logger = logging.getLogger("ToolDecisionRouter")


class ToolDecisionRouter:
    """
    Evaluates agent workflow state and outputs calibrated decision probabilities
    for the available tool space:
      - verify_circuit_pdg_gate
      - validate_netlist_syntax
      - retrieve_subcircuit_blueprint
      - search_web_circuit_reference
      - manage_memory
      - save_subcircuit_blueprint
    """

    SUPPORTED_TOOLS = [
        "synthesize_circuit_netlist",
        "verify_circuit_pdg_gate",
        "validate_netlist_syntax",
        "retrieve_subcircuit_blueprint",
        "search_web_circuit_reference",
        "manage_memory",
        "save_subcircuit_blueprint",
        "generate_topology_candidates",
        "auto_size_gm_id",
        "generate_base_circuit",
        "sweep_parameters_grid",
    ]

    def __init__(
        self,
        dut_name: str = "DUT",
        jev_endpoint: str | None = None,
        jev_api_key: str | None = None
    ):
        self.dut_name = dut_name
        self.jev_endpoint = jev_endpoint or os.environ.get("JEV_ENDPOINT")
        self.jev_api_key = jev_api_key or os.environ.get("JEV_API_KEY")

    def evaluate_state(
        self,
        turn_idx: int,
        pass_rate: float,
        has_netlist: bool,
        syntax_valid: bool,
        history_tool_names: list[str],
        unmet_specs_count: int = 0,
        workflow_policy: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Computes a calibrated probability distribution over tools
        based on the physical circuit synthesis state.
        """
        # If external Jev endpoint is configured, try calling it
        if self.jev_endpoint and self.jev_api_key:
            try:
                import urllib.request
                payload = json.dumps({
                    "state": {
                        "turn": turn_idx,
                        "pass_rate": pass_rate,
                        "has_netlist": has_netlist,
                        "syntax_valid": syntax_valid,
                        "history": history_tool_names[-5:],
                        "unmet_specs": unmet_specs_count
                    },
                    "choices": self.SUPPORTED_TOOLS
                }).encode("utf-8")
                req = urllib.request.Request(
                    self.jev_endpoint,
                    data=payload,
                    headers={
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {self.jev_api_key}"
                    }
                )
                with urllib.request.urlopen(req, timeout=3.0) as resp:
                    if resp.status == 200:
                        data = json.loads(resp.read().decode("utf-8"))
                        if "selected_tool" in data:
                            return data
            except Exception as e:
                logger.debug(f"Jev remote call skipped ({e}), falling back to System-1 local router.")

        # System-1 Calibrated Decision Logic
        probs: dict[str, float] = {t: 0.05 for t in self.SUPPORTED_TOOLS}

        # Hard Guardrail 1: Goal achieved (pass_rate >= 100%) -> save blueprint immediately
        if pass_rate >= 100.0:
            probs = {t: 0.01 for t in self.SUPPORTED_TOOLS}
            probs["save_subcircuit_blueprint"] = 0.95
            return self._format_decision("save_subcircuit_blueprint", probs, "Target 100% pass rate achieved.")

        # Hard Guardrail 2: Repetition trap breaker (agent repeatedly calling manage_memory)
        recent_memory_calls = sum(1 for t in history_tool_names[-3:] if t == "manage_memory")
        if recent_memory_calls >= 2:
            probs = {t: 0.01 for t in self.SUPPORTED_TOOLS}
            probs["synthesize_circuit_netlist"] = 0.85
            probs["verify_circuit_pdg_gate"] = 0.10
            probs["manage_memory"] = 0.00
            return self._format_decision(
                "synthesize_circuit_netlist",
                probs,
                "Repetition trap broken: invoking Netlist Synthesis Sub-Agent."
            )

        # Soft Priors (no forced early return): guide without blocking active LLM tool choice
        wp = workflow_policy or {}
        strategy = wp.get("initial_strategy", "blueprint_first")
        if turn_idx == 1 and not has_netlist:
            if strategy == "gm_id_first":
                probs["auto_size_gm_id"] = 0.45
                probs["generate_topology_candidates"] = 0.30
                probs["retrieve_subcircuit_blueprint"] = 0.15
                reason = "Initial turn prior (Harness² gm_id_first): prioritize gm/ID sizing & topology."
            elif strategy == "topology_first":
                probs["generate_topology_candidates"] = 0.45
                probs["auto_size_gm_id"] = 0.25
                probs["retrieve_subcircuit_blueprint"] = 0.15
                reason = "Initial turn prior (Harness² topology_first): prioritize topology candidates."
            else:
                probs["retrieve_subcircuit_blueprint"] = 0.45
                probs["search_web_circuit_reference"] = 0.25
                probs["generate_topology_candidates"] = 0.15
                reason = "Initial turn prior: explore blueprints, IEEE references, or topology candidates."
        elif has_netlist:
            probs["verify_circuit_pdg_gate"] = 0.45
            probs["validate_netlist_syntax"] = 0.20
            probs["sweep_parameters_grid"] = 0.25 if pass_rate > 0 else 0.05
            reason = "Netlist present prior: favor verification, syntax check, or parameter sweep."
        elif (
            pass_rate > 0
            and pass_rate < 100.0
            and len(history_tool_names) >= 2
            and history_tool_names[-1] == "synthesize_circuit_netlist"
        ):
            probs["sweep_parameters_grid"] = 0.50
            probs["synthesize_circuit_netlist"] = 0.35
            reason = "DC-convergent partial pass prior: favor LTspice parameter sweep to tune Gain/Vos/Ibias."
        else:
            probs["synthesize_circuit_netlist"] = 0.40
            probs["generate_topology_candidates"] = 0.20
            probs["auto_size_gm_id"] = 0.15
            probs["search_web_circuit_reference"] = 0.10
            reason = "No candidate netlist yet prior: favor synthesis, topology, or gm/ID sizing."

        for t, override_p in (wp.get("tool_priors") or {}).items():
            if t in probs and isinstance(override_p, (int, float)):
                probs[t] = max(0.0, min(1.0, float(override_p)))

        if os.environ.get("ANALOG_ENABLE_LLM_ROUTER", "1") == "1" and os.environ.get("ANALOG_DISABLE_LLM_PLANNER") != "1":
            try:
                from ..llm_client import LLMClient
                llm = LLMClient()
                if getattr(llm, "provider", "none") != "none":
                    prompt = (
                        "You are a System-1 probabilistic tool router for an analog IC synthesis agent.\n"
                        f"DUT: {self.dut_name}, Turn: {turn_idx}, PassRate: {pass_rate}%, HasNetlist: {has_netlist}, "
                        f"SyntaxValid: {syntax_valid}, RecentTools: {history_tool_names[-4:]}, UnmetSpecs: {unmet_specs_count}.\n"
                        f"Available tools: {self.SUPPORTED_TOOLS}\n"
                        "Return JSON: {\"probabilities\": {<tool>: float, ...}, \"reason\": \"...\"}"
                    )
                    res = llm.complete_json(
                        prompt,
                        system="Return only valid JSON with tool probability distribution.",
                        temperature=0.0,
                        max_tokens=300,
                        stage="probabilistic_tool_router",
                    )
                    if isinstance(res, dict) and isinstance(res.get("probabilities"), dict):
                        llm_p = res["probabilities"]
                        for t in self.SUPPORTED_TOOLS:
                            if isinstance(llm_p.get(t), (int, float)) and float(llm_p[t]) >= 0:
                                probs[t] = 0.5 * probs[t] + 0.5 * float(llm_p[t])
                        if res.get("reason"):
                            reason = str(res["reason"])
            except Exception:
                pass

        best_tool = max(probs, key=probs.get)
        return self._format_decision(best_tool, probs, reason)

    def _format_decision(self, selected_tool: str, probs: dict[str, float], reason: str) -> dict[str, Any]:
        # Normalize probabilities
        total = sum(probs.values()) or 1.0
        norm_probs = {k: round(v / total, 3) for k, v in probs.items()}
        return {
            "selected_tool": selected_tool,
            "confidence": norm_probs.get(selected_tool, 0.0),
            "probabilities": norm_probs,
            "reason": reason
        }

    def intercept_and_guardrail(
        self,
        proposed_calls: list[dict[str, Any]],
        state_decision: dict[str, Any],
        has_extracted_netlist: bool,
        current_netlist: str | None = None
    ) -> list[dict[str, Any]]:
        """
        Guards against invalid actions:
          - If the agent calls 'manage_memory' while a valid netlist is waiting to be simulated,
            injects or prioritizes 'verify_circuit_pdg_gate'.
          - Strips redundant consecutive manage_memory calls.
        """
        if not proposed_calls:
            # If agent emitted no tool calls but emitted a netlist, auto-inject the recommended tool
            if has_extracted_netlist:
                args = {"tag": "auto_routed_jev"}
                if current_netlist and state_decision["selected_tool"] in ("verify_circuit_pdg_gate", "validate_netlist_syntax"):
                    args["netlist"] = current_netlist
                return [{
                    "name": state_decision["selected_tool"],
                    "arguments": args
                }]
            return proposed_calls

        filtered: list[dict[str, Any]] = []
        for call in proposed_calls:
            name = call.get("name")
            # If Jev decided repetition trap breaker, suppress redundant manage_memory
            if "Repetition trap" in state_decision.get("reason", "") and name == "manage_memory":
                logger.info("Jev Router intercepted redundant manage_memory call.")
                continue
            # Enforce pure-orchestrator rule: redirect direct verify_circuit_pdg_gate without sub-agent synthesis
            if name == "verify_circuit_pdg_gate" and not has_extracted_netlist:
                logger.info("Jev Router redirected premature verify_circuit_pdg_gate to synthesize_circuit_netlist.")
                filtered.append({
                    "name": "synthesize_circuit_netlist",
                    "arguments": {
                        "design_directives": "Synthesize a DC-convergent physical transistor-level circuit matching all DUT pins and specs."
                    },
                })
                continue
            filtered.append(call)

        if not filtered and "Repetition trap" in state_decision.get("reason", ""):
            return []
        return filtered or proposed_calls
