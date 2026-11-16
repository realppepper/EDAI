"""
Hermes Analog Tools: Domain-specific toolset exposed to the Hermes Agent.
Provides LTspice PDG 4-stage causal verification, SPICE physical guardrail validation,
subcircuit blueprint skill retrieval/persistence, and long-term memory operations.
"""
from __future__ import annotations

import logging
import os
import re
from collections.abc import Callable
from typing import Any

from ai_analog_designer.circuit_synthesis.netlist_validator import NetlistValidator
from ai_analog_designer.hermes_core.blueprint_reranker import BlueprintReranker
from ai_analog_designer.hermes_core.web_reference_search import (
    WebCircuitReferenceSearcher,
)

logger = logging.getLogger("HermesAnalogTools")


class HermesAnalogTools:
    """
    Tool registry and dispatcher for Hermes Agent during analog IC synthesis.
    """

    def __init__(
        self,
        output_dir: str,
        dut_name: str,
        pins: list[dict[str, Any]],
        specifications: list[dict[str, Any]],
        pdg_schedule: dict[str, float],
        measurement_plan: dict[str, Any] | None = None,
        verify_fn: Callable[..., dict[str, Any]] | None = None,
        skills_dir: str | None = None,
        memory_file: str | None = None,
    ):
        self.output_dir = os.path.abspath(output_dir)
        os.makedirs(self.output_dir, exist_ok=True)

        self.dut_name = re.sub(r'[^a-zA-Z0-9_]', '_', dut_name).upper()
        self.pins = pins
        self.specifications = specifications
        self.pdg_schedule = pdg_schedule
        self.measurement_plan = measurement_plan
        self.verify_fn = verify_fn

        self.skills_dir = os.path.abspath(skills_dir) if skills_dir else os.path.join(self.output_dir, "skills")
        os.makedirs(self.skills_dir, exist_ok=True)

        self.memory_file = os.path.abspath(memory_file) if memory_file else os.path.join(self.output_dir, "memories", "MEMORY.md")
        os.makedirs(os.path.dirname(self.memory_file), exist_ok=True)

        self.validator = NetlistValidator()
        self.web_searcher = WebCircuitReferenceSearcher()
        self.reranker = BlueprintReranker(
            target_dut=self.dut_name,
            target_pins=[p.get("name") if isinstance(p, dict) else str(p) for p in (self.pins or [])]
        )
        self.evaluation_history: list[dict[str, Any]] = []

    def get_tool_schemas(self) -> list[dict[str, Any]]:
        """Returns the list of tool JSON schemas in OpenAI / Hermes tool-calling format."""
        return [
            {
                "type": "function",
                "function": {
                    "name": "validate_netlist_syntax",
                    "description": "Validates SPICE syntax, subcircuit port alignment, and strict physical analog rules (zero behavioral B-sources, zero digital A-devices, zero undeclared rails, zero node 0 leakage).",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "netlist": {
                                "type": "string",
                                "description": "The complete SPICE netlist code containing the .subckt definition."
                            },
                            "subckt_name": {
                                "type": "string",
                                "description": "Optional subcircuit name override; defaults to current target IC."
                            }
                        },
                        "required": ["netlist"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "verify_circuit_pdg_gate",
                    "description": "Executes the 4-Stage PDG Causal Verification in LTspice: Stage 0 (Topology & signal path) -> Stage 1 (Power & DC bias current) -> Stage 2 (Causal DC transfer dVout >= 0.5V) -> Stage 3 (Staged spec fixtures). Returns exact row pass rate, unique kind pass rate, and diagnostic feedback.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "netlist": {
                                "type": "string",
                                "description": "The complete SPICE subcircuit netlist to simulate and measure."
                            },
                            "tag": {
                                "type": "string",
                                "description": "Diagnostic tag or iteration label, e.g. 'hermes_iter1'."
                            }
                        },
                        "required": ["netlist"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "retrieve_subcircuit_blueprint",
                    "description": "Queries Hermes's subcircuit blueprint skills library (C5 skills) for verified analog topologies (e.g. comparator cores, Darlington diff pairs, active current mirrors, bandgap references, op-amp Miller stages).",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "Search keyword or topology type, e.g. 'comparator', 'darlington', 'two_stage_opamp', 'bandgap', 'tl431'."
                            },
                            "category": {
                                "type": "string",
                                "description": "Optional category filter: 'comparator', 'operational_amplifier', 'voltage_reference', 'timer', 'ldo'."
                            }
                        },
                        "required": ["query"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "save_subcircuit_blueprint",
                    "description": "Persists a newly designed, high-performing subcircuit as a reusable blueprint skill in Hermes's skills directory (C5 skills) and the permanent Harness² library.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "name": {
                                "type": "string",
                                "description": "Blueprint name identifier, e.g. 'high_speed_bipolar_comparator_core'."
                            },
                            "category": {
                                "type": "string",
                                "description": "IC category, e.g. 'comparator', 'operational_amplifier', 'voltage_reference'."
                            },
                            "subckt_code": {
                                "type": "string",
                                "description": "Complete SPICE subcircuit netlist code of the blueprint."
                            },
                            "description": {
                                "type": "string",
                                "description": "Technical description of the architecture, operating points, and design equations."
                            },
                            "terminal_pins": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "Ordered pin names on the .subckt line."
                            }
                        },
                        "required": ["name", "category", "subckt_code", "description"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "manage_memory",
                    "description": "Hermes's native long-term memory tool (C3 memory). Records failure lessons, convergence traps (e.g. parallel mirror resistor trap), or patches existing heuristics in MEMORY.md.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "action": {
                                "type": "string",
                                "enum": ["add", "patch", "view"],
                                "description": "Memory operation to execute."
                            },
                            "content": {
                                "type": "string",
                                "description": "Lesson, convergence trap description, or note to record in MEMORY.md."
                            },
                            "target": {
                                "type": "string",
                                "description": "Optional section name or substring to target during patch."
                            }
                        },
                        "required": ["action"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "search_web_circuit_reference",
                    "description": "Searches IEEE academic literature (JSSC, TCAS), Exa neural database, and Tavily for peer-reviewed circuit design rationale, transistor-level schematics, SPICE subcircuit netlists (.subckt), and manufacturer application note references.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "Search query for circuit topology, SPICE subcircuit model, or internal schematic stages."
                            },
                            "ic_name": {
                                "type": "string",
                                "description": "Optional target IC part number (defaults to current DUT)."
                            },
                            "category": {
                                "type": "string",
                                "description": "Optional IC category, e.g. 'audio_amplifier', 'comparator', 'operational_amplifier', 'ldo'."
                            }
                        },
                        "required": ["query"]
                    }
                }
            }
        ]

    def dispatch(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """Dispatches an incoming tool call from Hermes."""
        if tool_name == "validate_netlist_syntax":
            return self.validate_netlist_syntax(**arguments)
        elif tool_name == "verify_circuit_pdg_gate":
            return self.verify_circuit_pdg_gate(**arguments)
        elif tool_name == "retrieve_subcircuit_blueprint":
            return self.retrieve_subcircuit_blueprint(**arguments)
        elif tool_name == "save_subcircuit_blueprint":
            return self.save_subcircuit_blueprint(**arguments)
        elif tool_name == "manage_memory":
            return self.manage_memory(**arguments)
        elif tool_name == "search_web_circuit_reference":
            return self.search_web_circuit_reference(**arguments)
        else:
            return {"error": f"Unknown tool: '{tool_name}'"}

    def validate_netlist_syntax(self, netlist: str = "", subckt_name: str | None = None, **kwargs) -> dict[str, Any]:
        """Executes NetlistValidator."""
        if not netlist or not netlist.strip():
            return {
                "is_valid": False,
                "errors": ["Empty netlist string."],
                "warnings": [],
                "device_counts": {},
                "cleaned_netlist": "",
                "guardrail_status": "FAIL_SYNTAX_OR_GUARDRAIL"
            }
        target_name = (subckt_name or self.dut_name).upper()
        res = self.validator.validate(netlist, expected_subckt_name=target_name, expected_pins=self.pins)
        return {
            "is_valid": res.get("is_valid", False),
            "errors": res.get("errors", []),
            "subcircuit_name": res.get("subcircuit_name", target_name),
            "device_counts": res.get("device_counts", {}),
            "cleaned_netlist": res.get("cleaned_netlist", netlist),
            "guardrail_status": "PASS" if res.get("is_valid") else "FAIL_SYNTAX_OR_GUARDRAIL"
        }

    def verify_circuit_pdg_gate(self, netlist: str = "", tag: str = "hermes_eval", **kwargs) -> dict[str, Any]:
        """Runs the 4-stage causal gate verifier."""
        if not netlist or not netlist.strip():
            return {
                "status": "REJECTED_EMPTY_NETLIST",
                "pass_rate_percent": 0.0,
                "unique_kind_pass_rate_pct": 0.0,
                "passed_specs": 0,
                "failed_specs": len(self.specifications),
                "errors": ["No netlist provided to verify_circuit_pdg_gate."],
                "diagnostic_feedback": "Cannot verify empty netlist."
            }
        # 1. First run syntax validation
        val_res = self.validate_netlist_syntax(netlist)
        cleaned_netlist = val_res.get("cleaned_netlist", netlist)
        if not val_res.get("is_valid", False):
            return {
                "status": "REJECTED_BY_GUARDRAIL",
                "pass_rate_percent": 0.0,
                "unique_kind_pass_rate_pct": 0.0,
                "passed_specs": 0,
                "failed_specs": len(self.specifications),
                "errors": val_res.get("errors", []),
                "diagnostic_feedback": "Netlist failed strict physical SPICE guardrail checks:\n" + "\n".join(val_res.get("errors", []))
            }

        # 2. Write netlist file
        netlist_file = os.path.join(self.output_dir, f"{self.dut_name}_{tag}.cir")
        with open(netlist_file, "w", encoding="utf-8") as f:
            f.write(cleaned_netlist)

        # 3. Execute verify function
        if self.verify_fn:
            eval_res = self.verify_fn(cleaned_netlist, tag)
        else:
            # Fallback to importing verify
            from ai_analog_designer.neuro_symbolic_verifier.verification_flow import (
                verify,
            )
            sched_us = {k: v * 1e6 if v < 1.0 else v for k, v in self.pdg_schedule.items()}
            eval_res = verify(
                netlist=cleaned_netlist,
                plan=self.measurement_plan,
                schedule_us=sched_us,
                out_dir=self.output_dir,
                dut_name=self.dut_name,
                label=tag
            )

        self.evaluation_history.append({
            "tag": tag,
            "pass_rate_percent": eval_res.get("pass_rate_percent", 0.0),
            "unique_kind_pass_rate_pct": eval_res.get("unique_kind_pass_rate_pct", 0.0),
            "passed_specs": eval_res.get("passed_specs", 0),
            "failed_specs": eval_res.get("failed_specs", 0),
            "stage_status": eval_res.get("stage_status", "UNKNOWN"),
            "simulation_errors": eval_res.get("simulation_errors", [])
        })

        # Return a structured, compact diagnostic summary
        failed_items = [
            {
                "symbol": e.get("symbol"),
                "measured": e.get("measured"),
                "expected": f"[{e.get('min')}, {e.get('max')}]",
                "unit": e.get("unit"),
                "reason": e.get("fail_reason", "Out of bounds")
            }
            for e in eval_res.get("spec_evaluations", []) if not e.get("passed")
        ]

        return {
            "status": "SIMULATION_COMPLETE",
            "pass_rate_percent": eval_res.get("pass_rate_percent", 0.0),
            "unique_kind_pass_rate_pct": eval_res.get("unique_kind_pass_rate_pct", 0.0),
            "passed_specs": eval_res.get("passed_specs", 0),
            "failed_specs": eval_res.get("failed_specs", 0),
            "stage_status": eval_res.get("stage_status", "STAGE3_COMPLETE"),
            "stage0_passed": eval_res.get("stage0_passed", True),
            "stage1_passed": eval_res.get("stage1_passed", True),
            "stage2_passed": eval_res.get("stage2_passed", True),
            "diagnostic_feedback": eval_res.get("diagnostic_feedback", ""),
            "failed_specs_summary": failed_items[:15],
            "simulation_errors": eval_res.get("simulation_errors", []),
            "total_specs": len(self.specifications)
        }

    def retrieve_subcircuit_blueprint(self, query: str, category: str | None = None) -> dict[str, Any]:
        """Searches blueprint skills in skills/analog_blueprints/ and harness2_library with Reranker scoring."""
        query_norm = query.lower().strip()
        cat_norm = category.lower().strip() if category else ""
        matches = []

        scan_roots = [os.path.join(self.skills_dir, "analog_blueprints")]
        # Also include global harness2_library if present
        repo_harness = os.path.abspath(os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "harness2_library"))
        if os.path.exists(repo_harness) and repo_harness not in scan_roots:
            scan_roots.append(repo_harness)

        for bp_root in scan_roots:
            if os.path.exists(bp_root):
                for root, dirs, files in os.walk(bp_root):
                    for f in files:
                        if f.endswith(".md") or f.endswith(".json"):
                            p = os.path.join(root, f)
                            try:
                                with open(p, "r", encoding="utf-8") as fp:
                                    content = fp.read()
                                # Allow broad candidate retrieval; the Reranker will rank by relevance
                                is_candidate = False
                                if any(t in content.lower() or t in f.lower() for t in query_norm.split()) or cat_norm and (cat_norm in content.lower() or cat_norm in root.lower()):
                                    is_candidate = True
                                if is_candidate:
                                    matches.append({
                                        "file": os.path.relpath(p, bp_root),
                                        "title": f,
                                        "content": content[:4000]
                                    })
                            except Exception:
                                pass

        # Deduplicate candidates by file path
        unique_matches = []
        seen = set()
        for m in matches:
            if m["file"] not in seen:
                seen.add(m["file"])
                unique_matches.append(m)

        # Apply Circuit Blueprint Reranker
        reranked_matches = self.reranker.rerank(unique_matches, query=query, top_k=5)

        web_refs: dict[str, Any] | None = None
        if len(reranked_matches) == 0:
            try:
                web_refs = self.search_web_circuit_reference(
                    query=query,
                    ic_name=self.dut_name,
                    category=category or ""
                )
            except Exception as e:
                logger.warning(f"Auto web reference fallback failed: {e}")

        res_dict: dict[str, Any] = {
            "query": query,
            "category": category,
            "matches_found": len(reranked_matches),
            "blueprints": reranked_matches
        }
        if web_refs:
            res_dict["web_references"] = web_refs
        return res_dict

    def search_web_circuit_reference(
        self,
        query: str,
        ic_name: str | None = None,
        category: str | None = None
    ) -> dict[str, Any]:
        """
        Queries IEEE academic literature, Exa, and Tavily for circuit topology references,
        SPICE netlists, peer-reviewed design rationale, and internal schematic descriptions.
        """
        target_ic = (ic_name or self.dut_name).strip()
        res = self.web_searcher.search_circuit_reference(
            ic_name=target_ic,
            category=category or "",
            extra_query=query
        )
        # Persist retrieved web reference into workspace skills for traceability
        try:
            web_dir = os.path.join(self.skills_dir, "web_references")
            os.makedirs(web_dir, exist_ok=True)
            safe_ic = re.sub(r'[^a-zA-Z0-9_-]', '_', target_ic).lower()
            ref_path = os.path.join(web_dir, f"{safe_ic}_web_reference.md")
            with open(ref_path, "w", encoding="utf-8") as f:
                f.write(res.get("formatted_markdown", ""))
        except Exception:
            pass
        return res

    def save_subcircuit_blueprint(
        self,
        name: str,
        category: str,
        subckt_code: str,
        description: str,
        terminal_pins: list[str] | None = None
    ) -> dict[str, Any]:
        """Saves a subcircuit blueprint skill to skills/analog_blueprints/<name>/SKILL.md."""
        # Strict Guardrail: Never save empty stubs without elements as reusable blueprints
        clean_code = subckt_code.strip()
        lines = [ln.strip() for ln in clean_code.splitlines()]
        elem_lines = [ln for ln in lines if ln and ln[0].upper() in "RCLQMDJVI" and not ln.startswith(".")]
        transistor_lines = [ln for ln in elem_lines if ln[0].upper() in "QMJ"]
        if len(elem_lines) == 0:
            logger.warning(f"Rejected save_subcircuit_blueprint for '{name}': lacks physical circuit elements (elems={len(elem_lines)})")
            return {
                "status": "REJECTED",
                "error": "Cannot save empty blueprint. Blueprint must contain real physical circuit elements.",
                "elem_count": len(elem_lines),
                "transistor_count": len(transistor_lines)
            }

        safe_name = re.sub(r'[^a-zA-Z0-9_-]', '_', name).lower()
        bp_dir = os.path.join(self.skills_dir, "analog_blueprints", safe_name)
        os.makedirs(bp_dir, exist_ok=True)

        pins_str = ", ".join(terminal_pins) if terminal_pins else "N/A"
        skill_md = f"""---
name: {safe_name}
category: {category}
description: {description[:120]}
pins: [{pins_str}]
---

# Subcircuit Blueprint: {name}

## Category
`{category}`

## Description
{description}

## Pin Interface
`{pins_str}`

## SPICE Subcircuit Implementation
```spice
{subckt_code.strip()}
```
"""
        skill_path = os.path.join(bp_dir, "SKILL.md")
        with open(skill_path, "w", encoding="utf-8") as f:
            f.write(skill_md)

        logger.info(f"Saved subcircuit blueprint skill: {skill_path}")
        return {
            "status": "SUCCESS",
            "name": safe_name,
            "path": os.path.relpath(skill_path, self.output_dir),
            "category": category
        }

    def manage_memory(self, action: str, content: str = "", target: str | None = None) -> dict[str, Any]:
        """Manages long-term memories in MEMORY.md."""
        action = action.lower().strip()
        current_memory = ""
        if os.path.exists(self.memory_file):
            with open(self.memory_file, "r", encoding="utf-8") as f:
                current_memory = f.read()

        if action == "view":
            return {"status": "SUCCESS", "memory_content": current_memory}

        elif action == "add":
            new_entry = f"\n- [{self.dut_name}] {content.strip()}\n"
            updated = current_memory + new_entry
            with open(self.memory_file, "w", encoding="utf-8") as f:
                f.write(updated)
            return {"status": "SUCCESS", "action": "added", "entry": new_entry}

        elif action == "patch":
            if target and target in current_memory:
                updated = current_memory.replace(target, content.strip())
            else:
                updated = current_memory + f"\n- {content.strip()}\n"
            with open(self.memory_file, "w", encoding="utf-8") as f:
                f.write(updated)
            return {"status": "SUCCESS", "action": "patched"}

        else:
            return {"status": "ERROR", "message": f"Unsupported action: '{action}'"}

    def adapt_blueprint_to_dut(self, blueprint_code: str, target_subckt: str | None = None) -> str:
        """Adapts a blueprint subcircuit netlist to match the target DUT name and pin interface,
        handling multi-channel mapping (e.g. dual comparators/opamps), substrate/thermal pad
        termination, and preserving all physical transistor model cards."""
        target_name = (target_subckt or self.dut_name).upper()
        pin_names = [p.get("name", str(p)) if isinstance(p, dict) else str(p) for p in self.pins]
        pins_line = " ".join(pin_names)

        # 1. Clean markdown fences or commentary
        code = re.sub(r"^\s*```[a-zA-Z]*\s*$", "", blueprint_code, flags=re.MULTILINE).strip()

        # 2. Extract and preserve all .model definitions
        models = re.findall(r'(?m)^\s*\.model\s+[^\r\n]+', code, re.IGNORECASE)

        # 3. Classify target pins
        vcc_pin = next((p for p in pin_names if p.upper() in ('VCC', 'VDD', 'VP', 'PVCC', 'AVCC')), 'Vcc')
        gnd_pin = next((p for p in pin_names if p.upper() in ('GND', 'VSS', '0')), 'GND')
        thermal_pins = [p for p in pin_names if any(k in p.upper() for k in ('THERMAL', 'POWERPAD', 'EPAD', 'TAB', 'SUB'))]

        def is_pos(p: str) -> bool:
            up = p.upper()
            return any(up.endswith(s) for s in ('_P', 'P', '+', 'PLUS')) and not any(up.endswith(s) for s in ('_N', 'N', '-', 'MINUS'))

        def is_neg(p: str) -> bool:
            up = p.upper()
            return any(up.endswith(s) for s in ('_N', 'N', '-', 'MINUS')) and not any(up.endswith(s) for s in ('_P', 'P', '+', 'PLUS'))

        ch1_inp = next((p for p in pin_names if '1IN' in p.upper() and is_pos(p)), None)
        ch1_inn = next((p for p in pin_names if '1IN' in p.upper() and is_neg(p)), None)
        ch1_out = next((p for p in pin_names if '1OUT' in p.upper()), None)
        ch2_inp = next((p for p in pin_names if '2IN' in p.upper() and is_pos(p)), None)
        ch2_inn = next((p for p in pin_names if '2IN' in p.upper() and is_neg(p)), None)
        ch2_out = next((p for p in pin_names if '2OUT' in p.upper()), None)

        # 4. Check for single-channel comparator/opamp core inside blueprint
        m_sub = re.search(r'(?m)^\s*\.subckt\s+([a-zA-Z0-9_]+)\s+[^\r\n]+([\s\S]*?)^\s*\.ends\b', code, re.IGNORECASE)
        if m_sub and ch1_inp and ch1_inn and ch1_out and ch2_inp and ch2_inn and ch2_out:
            core_body = m_sub.group(2).strip()
            # Strip hoisted models from core body
            core_body = re.sub(r'(?m)^\s*\.model\s+[^\r\n]+\n?', '', core_body).strip()
            th_lines = "\n".join([f"R_TP_{i} {tp} {gnd_pin} 10Meg" for i, tp in enumerate(thermal_pins)])
            models_block = "\n".join(models) + "\n\n" if models else ""

            return f"""* Adapted Multi-Channel Architecture for {target_name}
{models_block}.subckt {target_name} {pins_line}
{th_lines}
* Channel 1 Instantiation
XU1 {ch1_inp} {ch1_inn} {ch1_out} {vcc_pin} {gnd_pin} {target_name}_CORE
* Channel 2 Instantiation
XU2 {ch2_inp} {ch2_inn} {ch2_out} {vcc_pin} {gnd_pin} {target_name}_CORE
.ends {target_name}

.subckt {target_name}_CORE INP INM OUT VCC GND
{core_body}
.ends {target_name}_CORE
"""

        # 5. Fallback: single subcircuit header replacement
        m_head = re.search(r'(?m)^\s*\.subckt\s+([a-zA-Z0-9_]+)\s+.*$', code, re.IGNORECASE)
        if m_head:
            old_name = m_head.group(1)
            code = code[:m_head.start()] + f".subckt {target_name} {pins_line}" + code[m_head.end():]
            code = re.sub(r'(?m)^\s*\.ends\s+' + re.escape(old_name) + r'\b', f".ends {target_name}", code, flags=re.IGNORECASE)
        elif not re.search(r'(?m)^\s*\.subckt\b', code, re.IGNORECASE):
            code = f".subckt {target_name} {pins_line}\n" + code + f"\n.ends {target_name}\n"

        if models and not any(m in code for m in models):
            code = "\n".join(models) + "\n\n" + code

        return code

