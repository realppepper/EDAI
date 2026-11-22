"""
Hermes Autonomous Agent Core.
Implements the NousResearch Hermes Agent architecture (SOUL.md, MEMORY.md, skills/,
conversation loop, multi-turn tool dispatch, and self-improving reflection).
"""
from __future__ import annotations

import json
import logging
import os
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from ai_analog_designer.llm_client import LLMClient

from .hermes_tools import HermesAnalogTools

logger = logging.getLogger("HermesAgent")


@dataclass
class AgentTurnResult:
    """Represents the outcome of an agent execution turn."""
    turn_index: int
    raw_response: str
    thought: str = ""
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    tool_outputs: list[dict[str, Any]] = field(default_factory=list)
    netlist_extracted: str | None = None
    pass_rate: float = 0.0
    unique_pass_rate: float = 0.0
    passed_specs: int = 0
    total_specs: int = 0
    is_terminal: bool = False


class HermesAgent:
    """
    Hermes Agent Wrapper for Analog Circuit Synthesis.
    Integrates NousResearch Hermes Agent standards:
      - SOUL.md: Autonomous Persona & Physics Laws (tuned by Harness² C1)
      - memories/MEMORY.md: Persistent Convergence & Bug Traps (tuned by Harness² C3)
      - memories/USER.md: Target IC Mission & Datasheet Directives
      - skills/analog_blueprints/: Subcircuit Blueprint Skills (tuned by Harness² C5)
      - Tool Calling: Dynamic dispatch for simulation, syntax validation, memory & blueprint saving
    """

    def __init__(
        self,
        workspace_dir: str,
        tools: HermesAnalogTools | None = None,
        llm_client: LLMClient | None = None,
        model: str | None = None,
        temperature: float = 0.1,
    ):
        self.workspace_dir = os.path.abspath(workspace_dir)
        self.tools = tools
        self.llm_client = llm_client or LLMClient()
        # Keep None when no explicit model was requested so LLMClient can
        # select a tier per Hermes turn (and fall back on timeout).  Resolving
        # this to default_model here would turn it into an explicit override
        # and silently bypass the adaptive scheduler.
        self.model = model
        self.temperature = temperature

        # File paths inside Hermes workspace
        self.soul_path = os.path.join(self.workspace_dir, "SOUL.md")
        self.memory_dir = os.path.join(self.workspace_dir, "memories")
        self.memory_path = os.path.join(self.memory_dir, "MEMORY.md")
        self.user_context_path = os.path.join(self.memory_dir, "USER.md")
        self.skills_dir = os.path.join(self.workspace_dir, "skills")
        self.blueprints_dir = os.path.join(self.skills_dir, "analog_blueprints")

        self.messages: list[dict[str, str]] = []
        self.trajectory: list[AgentTurnResult] = []
        self._prev_tool_signatures: list[str] = []

        from ai_analog_designer.hermes_core.tool_decision_router import (
            ToolDecisionRouter,
        )
        dut_name = getattr(self.tools, "dut_name", "DUT") if self.tools else "DUT"
        self.router = ToolDecisionRouter(dut_name=dut_name)

        self._ensure_workspace()

    def _ensure_workspace(self):
        """Ensures the directory structure matching ~/.hermes layout exists."""
        os.makedirs(self.workspace_dir, exist_ok=True)
        os.makedirs(self.memory_dir, exist_ok=True)
        os.makedirs(self.blueprints_dir, exist_ok=True)

        if not os.path.exists(self.soul_path):
            with open(self.soul_path, "w", encoding="utf-8") as f:
                f.write("# Hermes Analog Agent Persona\nYou are an Expert Autonomous Analog IC Designer.")

        if not os.path.exists(self.memory_path):
            with open(self.memory_path, "w", encoding="utf-8") as f:
                f.write("# Hermes Long-Term Memory (MEMORY.md)\n\n## CONVERGENCE TRAPS & FAILURE MODES\n")

    def load_soul(self) -> str:
        """Reads SOUL.md persona."""
        if os.path.exists(self.soul_path):
            with open(self.soul_path, "r", encoding="utf-8") as f:
                return f.read()
        return ""

    def load_memory(self) -> str:
        """Reads active MEMORY.md snapshot."""
        if os.path.exists(self.memory_path):
            with open(self.memory_path, "r", encoding="utf-8") as f:
                return f.read()
        return ""

    def list_available_blueprint_skills(self) -> list[dict[str, str]]:
        """Scans skills/analog_blueprints/ for registered blueprint skills."""
        skills = []
        if os.path.exists(self.blueprints_dir):
            for entry in os.listdir(self.blueprints_dir):
                skill_file = os.path.join(self.blueprints_dir, entry, "SKILL.md")
                if os.path.exists(skill_file):
                    try:
                        with open(skill_file, "r", encoding="utf-8") as f:
                            lines = f.readlines()
                        desc = ""
                        for line in lines:
                            if line.lower().startswith("description:"):
                                desc = line.split(":", 1)[1].strip()
                                break
                        skills.append({"name": entry, "description": desc, "path": skill_file})
                    except Exception:
                        pass
        return skills

    def compile_system_prompt(self) -> str:
        """
        Assembles Hermes's comprehensive system prompt including:
          1. SOUL.md (Persona & Physical Laws)
          2. Active MEMORY.md snapshot (Convergence traps)
          3. Available Blueprint Skills list
          4. Tool schemas and usage instructions
        """
        soul = self.load_soul()
        memory = self.load_memory()
        skills = self.list_available_blueprint_skills()

        skills_summary = "\n".join([f"- `{s['name']}`: {s['description']}" for s in skills]) if skills else "No skills indexed yet."

        tools_schema_json = json.dumps(self.tools.get_tool_schemas(), indent=2)
        if hasattr(self.tools, "pins") and self.tools.pins:
            pins_line = " ".join([p.get("name", str(p)) if isinstance(p, dict) else str(p) for p in self.tools.pins])
        else:
            pins_line = "INP INM OUT VCC GND"

        prompt = f"""{soul}

=== PERSISTENT MEMORY SNAPSHOT (MEMORY.md) ===
{memory}

=== AVAILABLE SUBCIRCUIT BLUEPRINT SKILLS (skills/analog_blueprints/) ===
{skills_summary}
(Use tool `retrieve_subcircuit_blueprint` to fetch full schematics and SPICE code)

=== TOOL CALLING PROTOCOL ===
You have access to specialized tools. When you need to inspect blueprints, validate syntax, execute simulation, or update memory, invoke tools using the Hermes `<tool_call>` format:
<tool_call>
{{"name": "<tool_name>", "arguments": {{...}}}}
</tool_call>
IMPORTANT: You MUST write the closing `</tool_call>` tag immediately after the JSON!
CRITICAL: Execute ONLY ONE or TWO tool calls per turn. NEVER simulate future turns or write monologue text like '[ASSISTANCE]:' or '[USER]:'. Wait for tool results before proceeding.

Available Tools:
{tools_schema_json}

=== ORCHESTRATOR EXECUTION POLICY ===
You are a PURE ORCHESTRATOR (Supervisor). Delegate ALL circuit authoring, syntax repair, DC convergence, sizing, and simulation to your specialized tools and sub-agents:
1. FIRST, call `retrieve_subcircuit_blueprint` (or `search_web_circuit_reference`, `generate_topology_candidates`, `auto_size_gm_id`) to gather proven topology & sizing references.
2. ALWAYS invoke `synthesize_circuit_netlist` with clear high-level topology, biasing, and sizing directives.
   - NEVER hand-write raw SPICE netlists or `<spice_netlist>` blocks in your response or tool arguments.
   - `synthesize_circuit_netlist` runs CircuitBuilder IR + ERC + Syntax Repair + DC Operating Point Convergence Fixer automatically.
3. THEN call `verify_circuit_pdg_gate` (no `netlist` argument needed — it automatically verifies the latest sub-agent netlist). Inspect the 4-stage causal gate feedback:
   - Stage 0 failure: Signal path disconnected or illegal elements.
   - Stage 1 failure: DC bias current out of range (short circuit or cutoff).
   - Stage 2 failure: DC transfer gain/switching failed.
   - Stage 3 failure: Specific parametric spec failed (slew rate, VOL, PSRR, gain).
4. IF a failure reveals a new design trap or you need references, invoke `search_web_circuit_reference` or `manage_memory` (`action="add"`), then call `synthesize_circuit_netlist` again with revised directives.
5. ONCE 100% pass rate is achieved, call `save_subcircuit_blueprint` to record the winning topology into `skills/`.
"""
        return prompt.strip()

    @staticmethod
    def _parse_xml_tool_call(raw_call: str) -> dict[str, Any] | None:
        """Parses `<function=NAME><parameter=KEY>VALUE</parameter></function>` XML tool calls."""
        m_fn = re.search(r'<function=([a-zA-Z0-9_]+)>\s*([\s\S]*?)(?:</function>|$)', raw_call, re.IGNORECASE)
        if not m_fn:
            return None
        fn_name = m_fn.group(1).strip()
        body = m_fn.group(2)
        args: dict[str, Any] = {}
        for m_p in re.finditer(r'<parameter=([a-zA-Z0-9_]+)>\s*([\s\S]*?)\s*</parameter>', body, re.IGNORECASE):
            k = m_p.group(1).strip()
            v_raw = m_p.group(2).strip()
            if v_raw and v_raw[0] in ("{", "["):
                try:
                    args[k] = json.loads(v_raw, strict=False)
                    continue
                except Exception:
                    pass
            args[k] = v_raw
        return {"name": fn_name, "arguments": args}

    def parse_tool_calls(self, text: str) -> list[dict[str, Any]]:
        """
        Extracts tool calls from LLM response text with robust fault tolerance:
          - Handles missing </tool_call> closing tags
          - Recovers JSON blocks from unclosed tags using bracket matching / repair
          - Clamps hallucinated monologue loops (max 2 tool calls per turn)
        """
        calls: list[dict[str, Any]] = []

        # Step 0: Truncate hallucinated roleplay loops if the model started generating fake monologues
        # e.g., "\n[ASSISTANCE]:" or "\n[USER]:"
        clean_text = text
        m_fake = re.search(r'(?m)^\s*\[(?:ASSISTANCE|ASSISTANT|USER|SYSTEM)\]\s*:', text)
        if m_fake and m_fake.start() > 10:
            clean_text = text[:m_fake.start()].strip()

        # Pattern 1: Exact <tool_call> ... </tool_call>
        for m in re.finditer(r'<tool_call>\s*(.*?)\s*</tool_call>', clean_text, re.DOTALL | re.IGNORECASE):
            raw_call = m.group(1).strip()
            try:
                data = json.loads(raw_call, strict=False)
                if isinstance(data, dict) and "name" in data:
                    calls.append(data)
            except Exception:
                xml_parsed = self._parse_xml_tool_call(raw_call)
                if xml_parsed:
                    calls.append(xml_parsed)
                else:
                    from ai_analog_designer.llm_client import repair_truncated_json
                    repaired = repair_truncated_json(raw_call)
                    if repaired and isinstance(repaired, dict) and "name" in repaired:
                        calls.append(repaired)

        # Pattern 1b: Bare <function=...> ... </function> without <tool_call> wrapper
        if not calls:
            for m in re.finditer(r'<function=[a-zA-Z0-9_]+>[\s\S]*?</function>', clean_text, re.IGNORECASE):
                xml_parsed = self._parse_xml_tool_call(m.group(0))
                if xml_parsed:
                    calls.append(xml_parsed)

        # Pattern 2: Unclosed <tool_call> tags (model emitted <tool_call>\n{...} and omitted </tool_call>)
        if not calls:
            for m in re.finditer(r'<tool_call>\s*({[\s\S]*?})(?=\s*<tool_call>|\s*```|\s*$)', clean_text, re.IGNORECASE):
                raw_call = m.group(1).strip()
                try:
                    data = json.loads(raw_call, strict=False)
                    if isinstance(data, dict) and "name" in data:
                        calls.append(data)
                except Exception:
                    from ai_analog_designer.llm_client import repair_truncated_json
                    repaired = repair_truncated_json(raw_call)
                    if repaired and isinstance(repaired, dict) and "name" in repaired:
                        calls.append(repaired)

        # Pattern 3: ```tool_call ... ``` or ```json ... ```
        if not calls:
            for m in re.finditer(r'```(?:tool_call|json)\s*({[\s\S]*?"name"[\s\S]*?})\s*```', clean_text, re.DOTALL):
                raw_call = m.group(1).strip()
                try:
                    data = json.loads(raw_call, strict=False)
                    if isinstance(data, dict) and "name" in data:
                        calls.append(data)
                except Exception:
                    from ai_analog_designer.llm_client import repair_truncated_json
                    repaired = repair_truncated_json(raw_call)
                    if repaired and isinstance(repaired, dict) and "name" in repaired:
                        calls.append(repaired)

        # Pattern 4: Bare inline {"name": "...", "arguments": {...}}
        if not calls:
            for m in re.finditer(r'({[^{}]*"name"\s*:\s*"([a-zA-Z0-9_]+)"[^{}]*"arguments"\s*:\s*{[^{}]*}[^{}]*})', clean_text):
                try:
                    data = json.loads(m.group(1).strip(), strict=False)
                    if isinstance(data, dict) and "name" in data:
                        calls.append(data)
                except Exception:
                    pass

        # Pattern 5: Semantic regex fallback for circuit synthesis / verification / memory tools
        if not calls:
            m_name = re.search(r'"name"\s*:\s*"([a-zA-Z0-9_]+)"', clean_text)
            if m_name:
                tool_name = m_name.group(1)
                # Check if there is a netlist inside
                m_net = re.search(r'(\.subckt\b[\s\S]*?\.ends\b[^\r\n"\\]*)', clean_text, re.IGNORECASE)
                if m_net:
                    extracted_nl = m_net.group(1).replace(r'\n', '\n').replace(r'\"', '"').strip()
                    m_tag = re.search(r'"tag"\s*:\s*"([^"]+)"', clean_text)
                    calls.append({
                        "name": tool_name,
                        "arguments": {
                            "netlist": extracted_nl,
                            "tag": m_tag.group(1) if m_tag else "recovered_turn"
                        }
                    })
                elif tool_name == "manage_memory":
                    m_content = re.search(r'"content"\s*:\s*"([^"]+)"', clean_text)
                    m_target = re.search(r'"target"\s*:\s*"([^"]+)"', clean_text)
                    calls.append({
                        "name": tool_name,
                        "arguments": {
                            "action": "add",
                            "content": m_content.group(1) if m_content else "",
                            "target": m_target.group(1) if m_target else "memory"
                        }
                    })
                elif tool_name in ("retrieve_subcircuit_blueprint", "search_web_circuit_reference"):
                    m_query = re.search(r'"query"\s*:\s*"([^"]+)"', clean_text)
                    m_cat = re.search(r'"category"\s*:\s*"([^"]+)"', clean_text)
                    calls.append({
                        "name": tool_name,
                        "arguments": {
                            "query": m_query.group(1) if m_query else "",
                            "category": m_cat.group(1) if m_cat else ""
                        }
                    })
                elif tool_name == "save_subcircuit_blueprint":
                    m_subckt = re.search(r'"subcircuit_name"\s*:\s*"([^"]+)"', clean_text)
                    m_cat = re.search(r'"category"\s*:\s*"([^"]+)"', clean_text)
                    calls.append({
                        "name": tool_name,
                        "arguments": {
                            "subcircuit_name": m_subckt.group(1) if m_subckt else "",
                            "category": m_cat.group(1) if m_cat else "analog_ic"
                        }
                    })

        # Deduplicate and clamp to maximum 2 calls per turn to prevent hallucination floods
        unique_calls: list[dict[str, Any]] = []
        seen = set()
        for c in calls:
            call_sig = f"{c.get('name')}||{json.dumps(c.get('arguments', {}), sort_keys=True)}"
            if call_sig not in seen:
                seen.add(call_sig)
                unique_calls.append(c)
            if len(unique_calls) >= 2:
                break

        return unique_calls

    def _is_meaningful_netlist(self, netlist: str) -> bool:
        """Checks that netlist is not an empty stub with just ellipses, comments, or undefined X-placeholders."""
        if not netlist or ".subckt" not in netlist.lower() or ".ends" not in netlist.lower():
            return False
        # Reject literal placeholder netlists
        if re.search(r'\.\.\.', netlist) and len(netlist.strip().splitlines()) <= 5:
            return False
        if re.search(r'\([^\r\n]*placeholder[^\r\n]*\)', netlist, re.IGNORECASE):
            return False
        lines = [ln.strip() for ln in netlist.splitlines()]
        elem_lines = [ln for ln in lines if ln and ln[0].upper() in "RCLQMDJVI" and not ln.startswith(".")]
        return len(elem_lines) >= 3

    def extract_netlist(self, text: str) -> str | None:
        """Extracts SPICE netlist from response text with maximum resilience."""
        m_net = re.search(r'<spice_netlist>(.*?)</spice_netlist>', text, re.DOTALL | re.IGNORECASE)
        if m_net and self._is_meaningful_netlist(m_net.group(1).strip()):
            return m_net.group(1).strip()
        m_code = re.search(r'```(?:spice|cir)?\s*(\.subckt.*?\bend\w*)\s*```', text, re.DOTALL | re.IGNORECASE)
        if m_code and self._is_meaningful_netlist(m_code.group(1).strip()):
            return m_code.group(1).strip()
        # Require .subckt at beginning of a line to avoid matching error messages or text descriptions
        m_sub = re.search(r'(?m)^\s*(\.subckt\b[\s\S]*?^\s*\.ends\b[^\r\n]*)', text, re.IGNORECASE)
        if m_sub and self._is_meaningful_netlist(m_sub.group(1).strip()):
            return m_sub.group(1).strip()
        # Fallback: Match .subckt inside tool calls or quotes (with unescaping)
        m_json_nl = re.search(r'(\.subckt\b[\s\S]*?\.ends\b[^\r\n"\\]*)', text, re.IGNORECASE)
        if m_json_nl:
            candidate = m_json_nl.group(1).replace(r'\n', '\n').replace(r'\"', '"').strip()
            if self._is_meaningful_netlist(candidate):
                return candidate
        return None

    def run_turn(self, turn_idx: int) -> AgentTurnResult:
        """Executes a single conversational turn in the Hermes loop."""
        sys_prompt = self.compile_system_prompt()

        # Build native conversation messages with sliding window to stay safely within token quota
        native_messages = [{"role": "system", "content": sys_prompt}]
        if len(self.messages) <= 3:
            for msg in self.messages:
                native_messages.append({"role": msg["role"], "content": msg["content"]})
        else:
            # Preserve initial task instruction + most recent 2 turns
            native_messages.append({"role": self.messages[0]["role"], "content": self.messages[0]["content"]})
            for msg in self.messages[-2:]:
                native_messages.append({"role": msg["role"], "content": msg["content"]})

        logger.info(f"Hermes Agent executing turn {turn_idx}...")
        resp_text = self.llm_client.complete(
            prompt="",
            system_prompt=sys_prompt,
            messages=native_messages,
            model=self.model,
            temperature=self.temperature,
            max_tokens=2048,
            tag=f"hermes_turn_{turn_idx}"
        )
        logger.info(f"[Hermes Turn {turn_idx} Raw Response]:\n{resp_text}")
        try:
            turn_log_path = os.path.join(self.workspace_dir, f"turn_{turn_idx}.log")
            with open(turn_log_path, "w", encoding="utf-8") as f:
                f.write(resp_text)
        except Exception:
            pass

        thought = ""
        m_thought = re.search(r'<(?:thought|think)>(.*?)</(?:thought|think)>', resp_text, re.DOTALL | re.IGNORECASE)
        if m_thought:
            thought = m_thought.group(1).strip()

        tool_calls = self.parse_tool_calls(resp_text)
        current_nl = self.extract_netlist(resp_text)

        # Jev System-1 Decision: Evaluate state and get calibrated probability distribution
        prev_pass_rate = self.trajectory[-1].pass_rate if self.trajectory else 0.0
        history_names = [t.get("name", "") for tr in self.trajectory for t in tr.tool_calls]
        state_decision = self.router.evaluate_state(
            turn_idx=turn_idx,
            pass_rate=prev_pass_rate,
            has_netlist=bool(current_nl),
            syntax_valid=True,
            history_tool_names=history_names,
            unmet_specs_count=len(getattr(self.tools, "specifications", [])) if self.tools else 0,
            workflow_policy=getattr(getattr(self.tools, "harness_tree", None), "workflow_policy", None),
        )
        logger.info(f"[Jev Router] Selected: '{state_decision['selected_tool']}' (confidence: {state_decision['confidence']:.2f}, reason: {state_decision['reason']})")

        # Intercept and guardrail proposed tool calls
        tool_calls = self.router.intercept_and_guardrail(
            proposed_calls=tool_calls,
            state_decision=state_decision,
            has_extracted_netlist=bool(current_nl),
            current_netlist=current_nl
        )

        tool_outputs = []

        turn_result = AgentTurnResult(
            turn_index=turn_idx,
            raw_response=resp_text,
            thought=thought,
            tool_calls=tool_calls
        )

        # Store compact assistant response in history to avoid huge monologues exceeding TPM limits
        stored_resp = resp_text
        if len(stored_resp) > 1500 and "<spice_netlist>" not in stored_resp:
            stored_resp = stored_resp[:1200] + "\n... [analysis monologue trimmed for context limits]"
        self.messages.append({"role": "assistant", "content": stored_resp})

        # Execute any requested tool calls
        if tool_calls:
            for call in tool_calls:
                name = call.get("name", "")
                args = call.get("arguments", {})
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except Exception:
                        args = {}
                if isinstance(args, dict) and not args.get("netlist") and current_nl and name in ("verify_circuit_pdg_gate", "validate_netlist_syntax"):
                    args["netlist"] = current_nl

                logger.info(f"Hermes invoking tool: '{name}'")
                from ..tracing.phoenix_tracer import debug_breakpoint, set_span_output, trace_span

                with trace_span(
                    f"tool.{name}",
                    span_kind="TOOL",
                    attributes={"tool.name": name, "tool.parameters": args},
                    input_data=args,
                ) as tool_span:
                    output = self.tools.dispatch(name, args)
                    set_span_output(tool_span, output)
                debug_breakpoint("tool", name, {
                    "turn": turn_idx,
                    "tool": name,
                    "args": args,
                    "output": output,
                })
                tool_outputs.append({"tool": name, "output": output})

                # Check if netlist sub-agent, parameter sweep, validation, or verification was run
                if name in ("synthesize_circuit_netlist", "sweep_parameters_grid", "validate_netlist_syntax", "verify_circuit_pdg_gate"):
                    candidate_nl = output.get("cleaned_netlist") or (args.get("netlist") if isinstance(args, dict) else None)
                    if candidate_nl and self._is_meaningful_netlist(candidate_nl):
                        turn_result.netlist_extracted = candidate_nl
                        # Strict PDG Causal Gating: ONLY run full PDG AC/transient verification
                        # once syntax/ERC AND Stage-2 DC bias + unity-gain transfer have passed.
                        dc_ready = output.get("dc_converged", True) if name in ("synthesize_circuit_netlist", "sweep_parameters_grid") else True
                        if name in ("synthesize_circuit_netlist", "sweep_parameters_grid", "validate_netlist_syntax") and output.get("is_valid", False) and dc_ready:
                            eval_out = self.tools.verify_circuit_pdg_gate(candidate_nl, tag=f"turn{turn_idx}")
                            turn_result.pass_rate = eval_out.get("pass_rate_percent", 0.0)
                            turn_result.unique_pass_rate = eval_out.get("unique_kind_pass_rate_pct", 0.0)
                            turn_result.passed_specs = eval_out.get("passed_specs", 0)
                            turn_result.total_specs = eval_out.get("total_specs", 0)
                            tool_outputs.append({"tool": "auto_eval_physical_gate", "output": eval_out})
                        elif name == "synthesize_circuit_netlist" and output.get("is_valid", False) and not dc_ready:
                            tool_outputs.append({
                                "tool": "pdg_dc_gate_blocked",
                                "output": {
                                    "status": "DC_BIAS_GATE_FAILED_AC_SKIPPED",
                                    "dc_diagnostic": output.get("dc_diagnostic", ""),
                                    "directive": (
                                        "PDG Causal Rule: Full AC/transient verification SKIPPED because DC bias/signal transfer failed. "
                                        "Invoke `synthesize_circuit_netlist` with DC-bias-only directives until V_OUT(0V) is near 0V and dV_OUT >= 0.8V."
                                    ),
                                },
                            })

                # Check if simulation was run
                if name == "verify_circuit_pdg_gate":
                    turn_result.pass_rate = output.get("pass_rate_percent", 0.0)
                    turn_result.unique_pass_rate = output.get("unique_kind_pass_rate_pct", 0.0)
                    turn_result.passed_specs = output.get("passed_specs", 0)
                    turn_result.total_specs = output.get("total_specs", 0)

            turn_result.tool_outputs = tool_outputs
            # Append tool outputs to conversation messages for next turn
            def _format_tool_output(out: Any, tool_name: str = "") -> str:
                if isinstance(out, dict) and tool_name in ("auto_eval_physical_gate", "verify_circuit_pdg_gate"):
                    compact = {
                        "status": out.get("status"),
                        "pass_rate_percent": out.get("pass_rate_percent"),
                        "passed_specs": out.get("passed_specs"),
                        "failed_specs": out.get("failed_specs"),
                        "stage_status": out.get("stage_status"),
                        "failed_specs_summary": (out.get("failed_specs_summary") or [])[:12],
                        "diagnostic_feedback": str(out.get("diagnostic_feedback", ""))[:600],
                    }
                    return json.dumps(compact, indent=2)
                s = json.dumps(out, indent=2) if isinstance(out, (dict, list)) else str(out)
                if len(s) > 1200:
                    return s[:1200] + "\n... [output truncated for brevity]"
                return s

            tool_feedback = "\n\n".join([
                f"<tool_output name=\"{o['tool']}\">\n{_format_tool_output(o['output'], o['tool'])}\n</tool_output>"
                for o in tool_outputs
            ])

            guidance = []
            pins_line = " ".join([p.get("name", str(p)) if isinstance(p, dict) else str(p) for p in self.tools.pins]) if hasattr(self.tools, "pins") and self.tools.pins else "INP INM OUT VCC GND"

            # Check for repetition loops
            current_call_sigs = [f"{c.get('name')}||{json.dumps(c.get('arguments', {}), sort_keys=True)}" for c in tool_calls]
            is_repeating = (current_call_sigs == self._prev_tool_signatures) and not any(c.get("name") == "verify_circuit_pdg_gate" for c in tool_calls)
            self._prev_tool_signatures = current_call_sigs

            if is_repeating:
                guidance.append(
                    f"CRITICAL DIRECTIVE: You are repeating tool calls ({[c.get('name') for c in tool_calls]}) without progress. "
                    f"STOP calling read-only tools or manage_memory. You MUST immediately synthesize the full transistor-level SPICE netlist "
                    f"for '{self.tools.dut_name}' and evaluate it with `verify_circuit_pdg_gate`."
                )

            if any(o['tool'] in ('retrieve_subcircuit_blueprint', 'search_web_circuit_reference') for o in tool_outputs):
                guidance.append(
                    f"Reference & blueprint data retrieved. Synthesize your complete transistor-level SPICE netlist for '{self.tools.dut_name}'. "
                    f"Header signature: .subckt {self.tools.dut_name} {pins_line}. "
                    f"Write out every transistor (Q/M), passive component (R/C), and .model card without any X-placeholders. Verify using `verify_circuit_pdg_gate`."
                )
            if any(o['tool'] == 'manage_memory' for o in tool_outputs):
                guidance.append(
                    f"Memory operation complete. DO NOT call 'manage_memory' again. "
                    f"You must now synthesize your physical transistor-level SPICE netlist for '{self.tools.dut_name}' "
                    f"using real transistors (Q/M/D) and passives (R/C), and evaluate it with `verify_circuit_pdg_gate`."
                )
            if any(o['tool'] == 'save_subcircuit_blueprint' for o in tool_outputs):
                guidance.append(
                    "Blueprint operation processed. Now proceed to synthesize and verify your circuit netlist via `verify_circuit_pdg_gate`."
                )
            if any(o['tool'] in ('validate_netlist_syntax', 'verify_circuit_pdg_gate', 'auto_eval_physical_gate') for o in tool_outputs):
                if not turn_result.netlist_extracted:
                    guidance.append(
                        "CRITICAL REQUIREMENT: The netlist validated contains NO active or passive components. "
                        "An empty skeleton will fail all simulations! You MUST write out the complete transistor-level schematic "
                        "(differential pair Q..., current mirror Q..., gain stage Q..., load resistors R...) with explicit `.model` statements, "
                        "and test it using `verify_circuit_pdg_gate`."
                    )
                elif turn_result.pass_rate < 100.0:
                    guidance.append(
                        f"Current Pass Rate: {turn_result.pass_rate:.1f}% ({turn_result.passed_specs}/{turn_result.total_specs} specs passed). "
                        f"Inspect diagnostic feedback and adjust transistor sizing or bias currents to meet failing specifications."
                    )
                else:
                    guidance.append("Target achieved: 100% pass rate! Provide final <architecture_summary> and <spice_netlist> to terminate.")

            # Add Jev System-1 Calibrated Router Directive
            guidance.append(
                f"[Jev System-1 Router]: Recommended next action is `{state_decision['selected_tool']}` "
                f"({state_decision['confidence']*100:.0f}% confidence: {state_decision['reason']})."
            )

            guidance_str = "\n".join(guidance) if guidance else (
                f"Analyze these results. You must now produce or refine the transistor-level SPICE netlist "
                f"for '{self.tools.dut_name}' and test it using `verify_circuit_pdg_gate`."
            )
            self.messages.append({
                "role": "user",
                "content": f"[TOOL EXECUTION RESULTS]:\n{tool_feedback}\n\n[NEXT ACTION DIRECTIVE]:\n{guidance_str}"
            })

        # Check for extracted netlist
        netlist = self.extract_netlist(resp_text)
        if netlist:
            turn_result.netlist_extracted = netlist
            # If no tool calls in this turn and netlist exists, trigger automatic verification
            if not tool_calls:
                val_res = self.tools.validate_netlist_syntax(netlist)
                turn_result.netlist_extracted = val_res.get("cleaned_netlist", netlist)
                eval_out = self.tools.verify_circuit_pdg_gate(turn_result.netlist_extracted, tag=f"turn{turn_idx}")
                turn_result.pass_rate = eval_out.get("pass_rate_percent", 0.0)
                turn_result.unique_pass_rate = eval_out.get("unique_kind_pass_rate_pct", 0.0)
                turn_result.passed_specs = eval_out.get("passed_specs", 0)
                turn_result.total_specs = eval_out.get("total_specs", 0)
                turn_result.tool_outputs.append({"tool": "auto_verify_circuit_pdg_gate", "output": eval_out})

        self.trajectory.append(turn_result)
        from ..tracing.phoenix_tracer import debug_breakpoint
        debug_breakpoint(
            "turn",
            f"turn_{turn_idx}",
            {
                "turn_index": turn_idx,
                "pass_rate": turn_result.pass_rate,
                "passed_specs": turn_result.passed_specs,
                "total_specs": turn_result.total_specs,
                "state_decision": state_decision,
                "tool_calls": turn_result.tool_calls,
                "tool_outputs": turn_result.tool_outputs,
                "netlist_extracted": turn_result.netlist_extracted,
                "messages": self.messages,
            },
            snapshot_dir=os.path.join(self.workspace_dir, "debug_snapshots"),
        )
        return turn_result

    def run_autonomous_loop(
        self,
        task_prompt: str,
        max_turns: int = 12,
        target_pass_rate: float = 100.0,
        progress_callback: Callable[[int, str, str], None] | None = None
    ) -> dict[str, Any]:
        """
        Executes the full autonomous agentic loop:
          - Initializes with user task prompt.
          - Only counts invocations of the Netlist Synthesis Sub-Agent (`synthesize_circuit_netlist`)
            toward `max_turns` (default: 12, within 10-15 range).
          - Terminates early upon 100% pass rate.
        """
        self.messages = [{"role": "user", "content": task_prompt}]
        best_netlist = None
        best_pass_rate = 0.0
        best_syntax_valid = False
        best_turn = None

        logger.info(f"Starting Hermes Autonomous Design Loop (Max Netlist Sub-Agent Calls: {max_turns}, Target: {target_pass_rate}%)...")

        synthesis_turns = 0
        raw_turn = 0
        max_raw_turns = max(max_turns * 3, max_turns + 6)
        while synthesis_turns < max_turns and raw_turn < max_raw_turns:
            raw_turn += 1
            if progress_callback:
                progress_callback(
                    3,
                    f"Hermes Agent Loop (Netlist Sub-Agent {synthesis_turns}/{max_turns}, Step {raw_turn})",
                    "Agent reasoning, tool dispatching & verifying...",
                )

            from ..tracing.phoenix_tracer import set_span_output, trace_span
            with trace_span(
                f"hermes.turn_{raw_turn}",
                span_kind="AGENT",
                attributes={
                    "turn": raw_turn,
                    "netlist_subagent_calls": synthesis_turns,
                    "max_turns": max_turns,
                },
                input_data=self.messages[-1] if self.messages else None,
            ) as turn_span:
                turn_res = self.run_turn(raw_turn)
                called_subagent = any(
                    c.get("name") == "synthesize_circuit_netlist" for c in turn_res.tool_calls
                )
                if called_subagent or turn_res.netlist_extracted:
                    synthesis_turns += 1
                set_span_output(turn_span, {
                    "pass_rate": turn_res.pass_rate,
                    "passed_specs": turn_res.passed_specs,
                    "total_specs": turn_res.total_specs,
                    "netlist_subagent_calls": synthesis_turns,
                    "subagent_invoked": called_subagent,
                    "netlist_generated": bool(turn_res.netlist_extracted),
                    "tool_calls": [c.get("name") for c in turn_res.tool_calls],
                })

            turn_syntax_valid = not any(
                isinstance(o.get("output"), dict)
                and (
                    o["output"].get("is_valid") is False
                    or o["output"].get("status") == "REJECTED_BY_GUARDRAIL"
                )
                for o in (turn_res.tool_outputs or [])
            )
            if turn_res.netlist_extracted and (
                not best_netlist
                or turn_res.pass_rate > best_pass_rate
                or (turn_res.pass_rate == best_pass_rate and turn_syntax_valid and not best_syntax_valid)
            ):
                best_pass_rate = turn_res.pass_rate
                best_syntax_valid = turn_syntax_valid
                best_netlist = turn_res.netlist_extracted
                best_turn = turn_res

            logger.info(
                f"Step {raw_turn} Complete (Synthesis {synthesis_turns}/{max_turns}): "
                f"Pass Rate = {turn_res.pass_rate:.1f}% ({turn_res.passed_specs}/{turn_res.total_specs} specs)"
            )

            if turn_res.pass_rate >= target_pass_rate and turn_res.total_specs > 0:
                logger.info(f"Target pass rate ({target_pass_rate}%) reached at step {raw_turn}! Terminating loop.")
                turn_res.is_terminal = True
                break

        return {
            "best_netlist": best_netlist,
            "best_pass_rate": best_pass_rate,
            "best_turn": best_turn,
            "total_turns_executed": len(self.trajectory),
            "trajectory": [
                {
                    "turn": t.turn_index,
                    "pass_rate": t.pass_rate,
                    "unique_pass_rate": t.unique_pass_rate,
                    "tools_called": [c.get("name") for c in t.tool_calls],
                    "thought": t.thought[:200]
                }
                for t in self.trajectory
            ]
        }
