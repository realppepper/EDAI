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
from ai_analog_designer.hermes_core.ieee_mcp_client import (
    IEEEMCPClient,
    extract_body_excerpts,
)
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
        llm_client: Any = None,
        harness_tree: Any = None,
    ):
        self.output_dir = os.path.abspath(output_dir)
        os.makedirs(self.output_dir, exist_ok=True)

        self.dut_name = re.sub(r'[^a-zA-Z0-9_]', '_', dut_name).upper()
        self.pins = pins
        self.specifications = specifications
        self.pdg_schedule = pdg_schedule
        self.measurement_plan = measurement_plan
        self.verify_fn = verify_fn
        self.llm_client = llm_client
        self.harness_tree = harness_tree

        self.skills_dir = os.path.abspath(skills_dir) if skills_dir else os.path.join(self.output_dir, "skills")
        os.makedirs(self.skills_dir, exist_ok=True)

        self.memory_file = os.path.abspath(memory_file) if memory_file else os.path.join(self.output_dir, "memories", "MEMORY.md")
        os.makedirs(os.path.dirname(self.memory_file), exist_ok=True)

        self.validator = NetlistValidator()
        self.web_searcher = WebCircuitReferenceSearcher()
        self.ieee_mcp_client = IEEEMCPClient()
        self.reranker = BlueprintReranker(
            target_dut=self.dut_name,
            target_pins=[p.get("name") if isinstance(p, dict) else str(p) for p in (self.pins or [])]
        )
        self.evaluation_history: list[dict[str, Any]] = []
        self.best_evaluation: dict[str, Any] | None = None
        self.dc_bias_achieved: bool = False
        self.last_dc_diagnostic: str = ""
        self.last_synthesized_netlist: str = ""
        self.ieee_literature_context: str = ""
        self._ieee_query_cache: dict[str, str] = {}

    def get_tool_schemas(self) -> list[dict[str, Any]]:
        """Returns the list of tool JSON schemas in OpenAI / Hermes tool-calling format."""
        return [
            {
                "type": "function",
                "function": {
                    "name": "synthesize_circuit_netlist",
                    "description": "Invokes the dedicated Netlist Synthesis Sub-Agent to generate or refine a pure transistor-level SPICE subcircuit (.subckt) based on topology directives, blueprint references, and prior simulation feedback.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "design_directives": {
                                "type": "string",
                                "description": "Concrete circuit topology, stage biasing, and component sizing directives for the Netlist Synthesis Sub-Agent."
                            },
                            "blueprint_name": {
                                "type": "string",
                                "description": "Optional blueprint skill name or topology template to adapt from."
                            }
                        },
                        "required": ["design_directives"]
                    }
                }
            },
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
                    "description": "Executes the 4-Stage PDG Causal Verification in LTspice on the latest netlist generated by `synthesize_circuit_netlist`, `auto_size_gm_id`, or `generate_base_circuit`. Do NOT hand-write raw SPICE netlists; omit `netlist` to verify the latest sub-agent output.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "tag": {
                                "type": "string",
                                "description": "Diagnostic tag or iteration label, e.g. 'hermes_iter1'."
                            }
                        },
                        "required": []
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
            },
            {
                "type": "function",
                "function": {
                    "name": "generate_topology_candidates",
                    "description": "Generates rule-validated CMOS op-amp topology structure tables using FLAN-T5 (when configured) and modular op-amp building blocks (folded cascode, telescopic, two-stage Miller, Class-AB).",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "prompt_hint": {
                                "type": "string",
                                "description": "Optional architecture or spec hint (e.g. 'low power rail-to-rail folded cascode')."
                            },
                            "max_candidates": {
                                "type": "integer",
                                "description": "Maximum candidates to return (default 6)."
                            },
                            "auto_size_preview": {
                                "type": "boolean",
                                "description": "If true, runs deterministic gm/ID sizing preview on each valid topology."
                            }
                        },
                        "required": []
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "auto_size_gm_id",
                    "description": "Computes deterministic transistor widths/lengths (W/L/m) for a structure table using the GF180 6V gm/ID lookup table and exports an LTspice/ngspice-ready physical .subckt netlist.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "structure_table": {
                                "type": "string",
                                "description": "Semicolon- or newline-separated structure table (e.g. 'PM1 D=N1 G=IN1 S=N3 B=VDD; ...')."
                            },
                            "unit_current_ua": {
                                "type": "number",
                                "description": "Unit tail/bias current in microamperes (default 20.0)."
                            },
                            "output_scale": {
                                "type": "number",
                                "description": "Output stage current scaling multiplier (default 1.0; try 5.0 or 20.0 for heavy load)."
                            },
                            "simulator": {
                                "type": "string",
                                "enum": ["auto", "ltspice", "ngspice"],
                                "description": "Target SPICE dialect/runner (default 'auto')."
                            }
                        },
                        "required": ["structure_table"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "generate_base_circuit",
                    "description": "Synthesizes an initial single-file base SPICE circuit and bounded parameter sweep settings from natural-language requirements and optional IEEE references, validated by NetlistValidator.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "instruction": {
                                "type": "string",
                                "description": "Circuit architecture and performance requirements."
                            },
                            "simulator": {
                                "type": "string",
                                "enum": ["ltspice", "ngspice"],
                                "description": "Target SPICE simulator (default 'ltspice')."
                            },
                            "ieee_context": {
                                "type": "string",
                                "description": "Optional IEEE paper summary or equations to ground the base topology."
                            }
                        },
                        "required": ["instruction"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "sweep_parameters_grid",
                    "description": (
                        "Runs a bounded LTspice/ngspice parameter optimization sweep (coordinate-descent feedback) "
                        "to tune bias/load resistors (e.g. RBIAS, RC1/RC2, RG2, RE3/RE4) for higher open-loop gain, "
                        "lower offset, and lower bias current WITHOUT breaking DC convergence. "
                        "When called with no arguments, it automatically optimizes the current best DC-convergent subcircuit."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "netlist": {
                                "type": "string",
                                "description": "Optional SPICE netlist; if omitted, uses the best DC-convergent subcircuit synthesized so far."
                            },
                            "settings": {
                                "type": "object",
                                "description": "Optional sweep settings object; if omitted, auto-parameterizes key bias/load resistors."
                            },
                            "simulator": {
                                "type": "string",
                                "enum": ["ltspice", "ngspice"],
                                "description": "Simulator backend (default 'ltspice')."
                            },
                            "max_runs": {
                                "type": "integer",
                                "description": "Maximum SPICE sweep runs (default 16)."
                            }
                        },
                        "required": []
                    }
                }
            }
        ]

    def dispatch(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """Dispatches an incoming tool call from Hermes."""
        if tool_name == "synthesize_circuit_netlist":
            return self.synthesize_circuit_netlist(**arguments)
        elif tool_name == "validate_netlist_syntax":
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
        elif tool_name == "generate_topology_candidates":
            return self.generate_topology_candidates(**arguments)
        elif tool_name == "auto_size_gm_id":
            return self.auto_size_gm_id(**arguments)
        elif tool_name == "generate_base_circuit":
            return self.generate_base_circuit(**arguments)
        elif tool_name == "sweep_parameters_grid":
            return self.sweep_parameters_grid(**arguments)
        else:
            return {"error": f"Unknown tool: '{tool_name}'"}

    def synthesize_circuit_netlist(
        self,
        design_directives: str = "",
        blueprint_name: str = "",
        **kwargs,
    ) -> dict[str, Any]:
        """Invokes the dedicated Netlist Synthesis Sub-Agent to generate a pure transistor-level SPICE netlist."""
        from ..llm_client import LLMClient
        from ..tracing.phoenix_tracer import set_span_output, trace_span

        client = self.llm_client or LLMClient()
        pin_names = [p.get("name") if isinstance(p, dict) else str(p) for p in (self.pins or [])]
        pins_line = " ".join(pin_names) if pin_names else "INP INM OUT VCC GND"
        pins_desc = "\n".join(
            f"  - {p.get('name')}: role={p.get('role', 'SIGNAL')}, dir={p.get('direction', 'IO')}, desc={p.get('description', '')}"
            for p in (self.pins or []) if isinstance(p, dict)
        )
        specs_desc = "\n".join(
            f"  - {s.get('symbol') or s.get('name')}: min={s.get('min')}, typ={s.get('typ')}, max={s.get('max')} {s.get('unit', '')}"
            for s in (self.specifications or [])[:12]
        )

        bp_context = ""
        bp_res = self.retrieve_subcircuit_blueprint(query=blueprint_name or self.dut_name)
        if bp_res.get("blueprints"):
            raw_bp = bp_res["blueprints"][0].get("content", "")
            adapted_seed = self.adapt_blueprint_to_dut(raw_bp, target_subckt=self.dut_name)
            seed_rule = (
                "CRITICAL: Keep the exact node connections of this DC-convergent skeleton intact; "
                "do NOT invent floating nodes—only tune W/L, R, and C values."
                if not self.evaluation_history
                else "Use this skeleton as structural reference and fix the failing specs below."
            )
            bp_context = (
                f"\n## PRE-ADAPTED DC-CONVERGENT SKELETON ({seed_rule}):\n"
                f"{adapted_seed[:3200]}\n"
            )

        prior_feedback = ""
        is_stagnating = (
            len(self.evaluation_history) >= 2
            and self.evaluation_history[-1].get("pass_rate_percent", 0.0)
            == self.evaluation_history[-2].get("pass_rate_percent", -1.0)
            and self.evaluation_history[-1].get("pass_rate_percent", 0.0) < 100.0
        )
        ieee_spec_context = ""
        if self.best_evaluation and self.best_evaluation.get("pass_rate_percent", 0.0) > 0:
            best_ev = self.best_evaluation
            failed_specs = best_ev.get("failed_specs_summary") or []
            failed_lines = "\n".join(
                f"  - {f.get('symbol')}: measured={f.get('measured')}, expected={f.get('expected')} {f.get('unit', '')} ({f.get('reason', '')})"
                for f in failed_specs[:12]
            )
            # Query IEEE MCP for peer-reviewed topology techniques + full-text body excerpts targeting failing specs
            if failed_specs and self.ieee_mcp_client.is_mcp_configured():
                unique_fail_names = list(dict.fromkeys(str(f.get("symbol") or "").strip() for f in failed_specs if f.get("symbol")))
                raw_ieee_q = f"operational amplifier active load {' '.join(unique_fail_names[:2])}"
                ieee_q = self.web_searcher.normalize_ieee_query(raw_ieee_q, max_terms=4)
                if ieee_q not in self._ieee_query_cache:
                    with trace_span(
                        "tool.ieee_mcp.search_and_read_body",
                        span_kind="TOOL",
                        attributes={"query": ieee_q},
                        input_data={"query": ieee_q, "failed_specs": unique_fail_names[:5]},
                    ) as ieee_span:
                        mcp_res = self.ieee_mcp_client.search_papers(
                            query=ieee_q,
                            max_results=4,
                            publication_title="IEEE Access",
                        )
                        papers = mcp_res.get("papers") or []
                        body_excerpts_lines: list[str] = []
                        full_text_count = 0
                        kw_list = ieee_q.split() + ["gain", "offset", "bias", "mirror", "differential", "compensation"]
                        for p in papers[:3]:
                            art_num = str(p.get("article_number") or "").strip()
                            if not art_num:
                                continue
                            body_res = self.ieee_mcp_client.read_paper(
                                article_number=art_num,
                                needed_reason=f"Retrieve full-text design equations and stage topology for failing specs: {', '.join(unique_fail_names[:3])}",
                            )
                            if body_res.get("full_text_retrieved") and body_res.get("blocks"):
                                full_text_count += 1
                                ex_list = extract_body_excerpts(body_res["blocks"], kw_list, budget=2400)
                                ex_text = "\n".join(
                                    f"    - [{ex.get('section', 'Body')} | {ex.get('excerpt_id')}] {ex.get('text', '')[:450]}"
                                    for ex in ex_list[:3]
                                )
                                body_excerpts_lines.append(
                                    f"  * [{p.get('year', '')}] {p.get('title', '')} (article_number={art_num}, full_text_retrieved=True, body_chars={body_res.get('body_characters', 0)}):\n{ex_text}"
                                )
                                if full_text_count >= 2:
                                    break
                        if not body_excerpts_lines:
                            body_excerpts_lines = [
                                f"  * [{p.get('year', '')}] {p.get('title', '')} ({p.get('venue', 'IEEE')}): {str(p.get('abstract', ''))[:320]}"
                                for p in papers[:3]
                            ]
                        self._ieee_query_cache[ieee_q] = "\n".join(body_excerpts_lines)
                        set_span_output(
                            ieee_span,
                            {
                                "provider": mcp_res.get("provider"),
                                "papers_found": len(papers),
                                "full_text_bodies_retrieved": full_text_count,
                                "titles": [p.get("title") for p in papers[:3]],
                            },
                        )
                if self._ieee_query_cache.get(ieee_q):
                    ieee_spec_context = (
                        "\n## IEEE MCP FULL-TEXT LITERATURE GUIDANCE (Targeted to Failing Specs):\n"
                        f"{self._ieee_query_cache[ieee_q]}\n"
                    )
            stagnation_note = (
                "\nCRITICAL ANTI-STAGNATION RULE: Your last 2 attempts repeated the EXACT same pass rate without structural change. "
                "DO NOT copy the previous netlist verbatim! You MUST make a concrete topology upgrade "
                "(e.g., replace resistive collector loads RC1/RC2 with a PNP current-mirror active load Q_M1/Q_M2, "
                "and reduce tail current by increasing RBIAS to 300k-500k and RE3/RE4 to 5k-10k) while preserving DC balance.\n"
                if is_stagnating
                else ""
            )
            prior_feedback += (
                f"\n## BEST WORKING CIRCUIT SO FAR (Pass Rate: {best_ev.get('pass_rate_percent', 0.0):.1f}% — "
                f"{best_ev.get('passed_specs', 0)}/{best_ev.get('total_specs', 0)} specs PASSED):\n"
                "CRITICAL: START FROM THIS WORKING DC-CONVERGENT NETLIST and make targeted analog topology/sizing improvements "
                "to fix the failing specs below WITHOUT breaking DC convergence or previously passing specs.\n"
                "TUNING PLAYBOOK:\n"
                "- Low Open-Loop Voltage Gain (e.g. 60dB -> >95dB): replace resistive collector loads (RC1/RC2, RG2) with active PNP/NPN current-mirror loads or higher output impedance stages.\n"
                "- High Input Offset Voltage (Vos): balance differential pair collector/load currents symmetrically using an active current-mirror load.\n"
                "- High Input Bias/Offset Current (Ibias/Ios): reduce differential pair tail current (e.g. increase RBIAS/RE3/RE4 so I_tail ~ 20uA-50uA) and/or increase input BJT BF (e.g. BF=250-400).\n"
                f"{stagnation_note}"
                f"### BEST WORKING NETLIST:\n{str(best_ev.get('netlist', ''))[:2400]}\n"
                f"### REMAINING FAILING SPECS TO FIX:\n{failed_lines or '  (see diagnostic below)'}\n"
                f"### DIAGNOSTIC:\n{str(best_ev.get('diagnostic_feedback', ''))[:1000]}\n"
                f"{ieee_spec_context}"
            )
            if self.evaluation_history and self.evaluation_history[-1] is not best_ev:
                last_ev = self.evaluation_history[-1]
                prior_feedback += (
                    f"\n### LAST ATTEMPT REGRESSED (Pass Rate: {last_ev.get('pass_rate_percent', 0.0):.1f}% — DO NOT REPEAT):\n"
                    f"Stage: {last_ev.get('stage_status')}, Errors: {last_ev.get('simulation_errors')}\n"
                    f"Diagnostic: {str(last_ev.get('diagnostic_feedback', ''))[:600]}\n"
                )
        elif self.evaluation_history:
            last_ev = self.evaluation_history[-1]
            failed_lines = "\n".join(
                f"  - {f.get('symbol')}: measured={f.get('measured')}, expected={f.get('expected')} {f.get('unit', '')}"
                for f in (last_ev.get("failed_specs_summary") or [])[:10]
            )
            prior_feedback = (
                f"\n## PRIOR SIMULATION FEEDBACK (Pass Rate: {last_ev.get('pass_rate_percent', 0.0):.1f}%):\n"
                f"Stage: {last_ev.get('stage_status')}\n"
                f"Errors: {last_ev.get('errors') or last_ev.get('simulation_errors')}\n"
                f"Failed Specs:\n{failed_lines}\n"
                f"Diagnostic: {str(last_ev.get('diagnostic_feedback', ''))[:1500]}\n"
            )

        from ..circuit_synthesis.circuit_builder import CircuitBuilder

        schema_guide = CircuitBuilder.schema_guide()
        sys_prompt = (
            "You are the dedicated Netlist Synthesis Sub-Agent for pure transistor-level SPICE circuit design.\n"
            "Output ONLY a structured JSON circuit inside <circuit_json>...</circuit_json> tags so CircuitBuilder compiles it into guaranteed-valid SPICE.\n\n"
            f"{schema_guide}\n\n"
            "STRICT RULES:\n"
            "- ONLY physical kinds: bjt, mos, res, cap, ind, diode (NEVER v, i, b, a sources).\n"
            "- Connect EVERY required pin in PIN INTERFACE (POWER, GROUND, SIGNAL inputs, OUTPUT) using their EXACT pin names.\n"
            "- Optional auxiliary pins like OFFSET_NULL or NC may be left unconnected if not needed.\n"
            "- Ensure a continuous transistor/passive signal path from BOTH SIGNAL inputs to OUTPUT.\n"
            "- Every internal node MUST connect to >= 2 device terminals (no floating nodes), with a DC bias path between supply rails.\n"
            "- NEVER spam dummy 100k resistors to silence ERC; design a clean, physically meaningful topology.\n"
            "- PRECEDENCE: If ORCHESTRATOR DESIGN DIRECTIVES conflict with these rules, ALWAYS obey these rules."
        )
        if self.dc_bias_achieved or (self.best_evaluation and self.best_evaluation.get("pass_rate_percent", 0.0) > 0):
            stage_objective_section = (
                f"## CURRENT PDG STAGE: FULL SPEC OPTIMIZATION (DC bias already verified)\n"
                f"## KEY SPECIFICATIONS:\n{specs_desc}\n\n"
                f"## ORCHESTRATOR DESIGN DIRECTIVES:\n{design_directives}\n"
            )
        else:
            dc_prev_note = (
                f"\nPrevious DC bias failure to fix: {self.last_dc_diagnostic}\n"
                if self.last_dc_diagnostic
                else ""
            )
            stage_objective_section = (
                "## CURRENT PDG STAGE: STAGE 2 — DC BIAS & UNITY-GAIN SIGNAL TRANSFER ONLY\n"
                "STRICT PDG CAUSAL RULE: IGNORE AC gain, slew rate, bandwidth, CMRR, and noise specs for now.\n"
                "Your ONLY goal right now is a clean, DC-convergent 2-stage op-amp where in unity-gain feedback (+/-15V rails):\n"
                "  1. Quiescent supply current |I(V_POS)| is between 100uA and 10mA (no cutoff, no short).\n"
                "  2. DC output V_OUT(V_INP=0V) is centered near 0V (|V_OUT(0V)| <= 2.5V, NOT saturated near +/-14V).\n"
                "  3. Signal transfer is alive with correct negative-feedback polarity: V_OUT(+1V) - V_OUT(-1V) >= 1.5V.\n"
                "  4. Base terminals of input differential pair Q1/Q2 connect to NONINVERTING_INPUT and INVERTING_INPUT (never swap collector/base).\n"
                f"{dc_prev_note}"
            )

        user_prompt = (
            f"Synthesize the complete transistor-level circuit for `{self.dut_name}`.\n"
            f"Exact subcircuit pins: `{pins_line}`.\n\n"
            f"## PIN INTERFACE:\n{pins_desc}\n\n"
            f"{stage_objective_section}"
            f"{bp_context}{self.ieee_literature_context}{prior_feedback}\n"
            "Return ONLY the `<circuit_json>...</circuit_json>` block."
        )

        def _extract_and_validate(raw_out: str) -> tuple[str, dict[str, Any]]:
            built = CircuitBuilder.from_json(raw_out, subckt_name=self.dut_name, pins=self.pins)
            if built is not None:
                nl = built["netlist"]
                vr = self.validate_netlist_syntax(nl)
                if built["erc_errors"]:
                    vr = dict(vr)
                    vr["errors"] = list(built["erc_errors"]) + list(vr.get("errors") or [])
                    vr["is_valid"] = False
                return nl, vr
            m_nl = re.search(r"<spice_netlist>(.*?)</spice_netlist>", raw_out, re.DOTALL | re.IGNORECASE)
            if not m_nl:
                m_nl = re.search(r"(\.subckt\b[\s\S]*?\.ends\b[^\r\n]*)", raw_out, re.IGNORECASE)
            nl = m_nl.group(1).strip() if m_nl else raw_out.strip()
            return nl, self.validate_netlist_syntax(nl)

        with trace_span(
            "subagent.netlist_synthesizer",
            span_kind="AGENT",
            attributes={"dut_name": self.dut_name, "blueprint_name": blueprint_name},
            input_data={"design_directives": design_directives, "blueprint_name": blueprint_name},
        ) as sub_span:
            raw = client.complete(
                prompt=user_prompt,
                system_prompt=sys_prompt,
                temperature=0.35 if is_stagnating else 0.15,
                max_tokens=4096,
                tag="harness2_synth",
            )
            netlist, val_res = _extract_and_validate(raw)
            repair_attempts = 0
            wp = getattr(self.harness_tree, "workflow_policy", {}) or {}
            max_syntax_repairs = int(wp.get("max_syntax_repairs", 2))
            while not val_res.get("is_valid", False) and repair_attempts < max_syntax_repairs:
                repair_attempts += 1
                with trace_span(
                    f"subagent.syntax_verifier.attempt_{repair_attempts}",
                    span_kind="AGENT",
                    attributes={"attempt": repair_attempts, "errors_count": len(val_res.get("errors", []))},
                    input_data={"errors": val_res.get("errors", []), "netlist": val_res.get("cleaned_netlist", netlist)},
                ) as sv_span:
                    err_lines = "\n".join(f"- {e}" for e in val_res.get("errors", []))
                    sv_sys = (
                        "You are a dedicated SPICE Syntax & ERC Repair Sub-Agent.\n"
                        "Fix ALL ERC and SPICE syntax errors below while preserving or replacing with a clean, physically connected circuit topology.\n"
                        "Output ONLY `<circuit_json>...</circuit_json>`.\n\n"
                        f"{schema_guide}\n\n"
                        "MANDATORY RULES:\n"
                        "- NEVER output raw SPICE text; ALWAYS output `<circuit_json>...</circuit_json>`.\n"
                        "- Connect EVERY required POWER, GROUND, SIGNAL, and OUTPUT pin in the subcircuit header.\n"
                        "- Every internal node MUST connect to at least 2 device terminals (no floating nodes).\n"
                        "- NEVER add meaningless resistor meshes (e.g. R3..R60 100k) to silence ERC — remove dead/floating stubs or wire real transistor stages.\n"
                        "- Ensure a continuous DC bias current path between supply rails and signal path from SIGNAL inputs to OUTPUT."
                    )
                    sv_prompt = (
                        f"Target `.subckt {self.dut_name} {pins_line}`\n\n"
                        f"## ERC / SYNTAX ERRORS TO FIX:\n{err_lines}\n\n"
                        f"## CURRENT NETLIST:\n{val_res.get('cleaned_netlist', netlist)}\n\n"
                        "Return ONLY the repaired `<circuit_json>...</circuit_json>` block."
                    )
                    repaired_raw = client.complete(
                        prompt=sv_prompt,
                        system_prompt=sv_sys,
                        temperature=0.0,
                        max_tokens=4096,
                        tag="harness2_synth",
                    )
                    netlist, val_res = _extract_and_validate(repaired_raw)
                    set_span_output(sv_span, {"is_valid": val_res.get("is_valid", False), "errors": val_res.get("errors", [])})

            # Stage 3: DC Operating Point Convergence Fixer Sub-Agent
            dc_repair_attempts = 0
            dc_check: dict[str, Any] = {"converged": False, "skipped": True, "diagnostic": "Syntax invalid; DC .op skipped."}
            if val_res.get("is_valid", False):
                from ..circuit_synthesis.dc_convergence_fixer import run_quick_dc_op_check
                dc_check = run_quick_dc_op_check(
                    val_res.get("cleaned_netlist", netlist),
                    subckt_name=self.dut_name,
                    pins=self.pins,
                    timeout_s=15,
                )
                max_dc_repairs = int(wp.get("max_dc_repairs", 2))
                while not dc_check.get("converged", False) and dc_repair_attempts < max_dc_repairs:
                    dc_repair_attempts += 1
                    with trace_span(
                        f"subagent.dc_convergence_fixer.attempt_{dc_repair_attempts}",
                        span_kind="AGENT",
                        attributes={"attempt": dc_repair_attempts, "dc_diagnostic": dc_check.get("diagnostic", "")},
                        input_data={"dc_check": dc_check, "netlist": val_res.get("cleaned_netlist", netlist)},
                    ) as dc_span:
                        dc_sys = (
                            "You are the dedicated DC Bias & Signal-Transfer Convergence Fixer Sub-Agent (PDG Stage 2).\n"
                            "Your ONLY job is to fix DC operating point convergence, rail saturation (|V_OUT(0V)| > 2.5V), "
                            "cutoff (~0A), short-circuit (>0.5A), inverted feedback polarity, or stuck output (dV_OUT < 0.8V).\n"
                            "IGNORE AC gain/slew/bandwidth specs — ONLY achieve valid DC bias and unity-gain signal transfer.\n"
                            "Output ONLY `<circuit_json>...</circuit_json>`.\n\n"
                            f"{schema_guide}\n\n"
                            "DC CONVERGENCE BEST PRACTICES:\n"
                            "- Ensure a proper DC tail current bias path from positive supply to negative supply (e.g., 100uA-5mA).\n"
                            "- Wire differential pair bases to NONINVERTING_INPUT and INVERTING_INPUT (never collectors!).\n"
                            "- If DC_POLARITY_INVERTED is reported, swap which differential pair collector drives the 2nd gain stage (or swap INP/INN bases).\n"
                            "- Keep unity-gain DC output V_OUT(0V) within +/-2.5V and V_OUT(+1V) - V_OUT(-1V) >= 1.5V."
                        )
                        dc_prompt = (
                            f"Target `.subckt {self.dut_name} {pins_line}`\n\n"
                            f"## LTSPICE DC SWEEP FAILURE DIAGNOSTIC:\n{dc_check.get('diagnostic', '')}\n"
                            f"Log excerpt:\n{dc_check.get('log_excerpt', '')}\n\n"
                            f"## CURRENT NETLIST:\n{val_res.get('cleaned_netlist', netlist)}\n\n"
                            "Return ONLY the DC-convergent `<circuit_json>...</circuit_json>` block."
                        )
                        dc_raw = client.complete(
                            prompt=dc_prompt,
                            system_prompt=dc_sys,
                            temperature=0.05,
                            max_tokens=4096,
                            tag="harness2_synth",
                        )
                        cand_nl, cand_vr = _extract_and_validate(dc_raw)
                        if cand_vr.get("is_valid", False):
                            netlist, val_res = cand_nl, cand_vr
                            dc_check = run_quick_dc_op_check(
                                val_res.get("cleaned_netlist", netlist),
                                subckt_name=self.dut_name,
                                pins=self.pins,
                                timeout_s=15,
                            )
                        else:
                            dc_check = {
                                "converged": False,
                                "diagnostic": "DC fixer output failed ERC/syntax: " + "; ".join(cand_vr.get("errors", [])[:3]),
                                "log_excerpt": "",
                            }
                        set_span_output(dc_span, {"converged": dc_check.get("converged", False), "diagnostic": dc_check.get("diagnostic", "")})

            cleaned_out = val_res.get("cleaned_netlist", netlist)
            if cleaned_out and cleaned_out.strip():
                self.last_synthesized_netlist = cleaned_out
            dc_ok = bool(dc_check.get("converged", False))
            if dc_ok:
                self.dc_bias_achieved = True
                self.last_dc_diagnostic = ""
            else:
                self.last_dc_diagnostic = str(dc_check.get("diagnostic", ""))
            out = {
                "status": (
                    "SYNTHESIZED_DC_PASSED"
                    if (val_res.get("is_valid") and dc_ok)
                    else ("SYNTHESIZED_DC_FAILED" if val_res.get("is_valid") else "SYNTHESIZED_WITH_SYNTAX_ERRORS")
                ),
                "subagent_invoked": True,
                "syntax_repair_attempts": repair_attempts,
                "dc_repair_attempts": dc_repair_attempts,
                "dc_converged": dc_ok,
                "dc_diagnostic": dc_check.get("diagnostic", ""),
                "is_valid": val_res.get("is_valid", False),
                "errors": val_res.get("errors", []),
                "device_counts": val_res.get("device_counts", {}),
                "cleaned_netlist": cleaned_out,
            }
            set_span_output(sub_span, out)
            return out

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
        """Runs the 4-stage causal gate verifier on the latest sub-agent synthesized netlist."""
        effective_netlist = (netlist or "").strip() or (self.last_synthesized_netlist or "").strip()
        if self.last_synthesized_netlist and netlist and "Synthesized via CircuitBuilder IR" not in netlist:
            # Prefer sub-agent synthesized CircuitBuilder output over hand-written orchestrator SPICE
            effective_netlist = self.last_synthesized_netlist
        if not effective_netlist:
            return {
                "status": "REJECTED_EMPTY_NETLIST",
                "pass_rate_percent": 0.0,
                "unique_kind_pass_rate_pct": 0.0,
                "passed_specs": 0,
                "failed_specs": len(self.specifications),
                "errors": ["No synthesized netlist available. Call `synthesize_circuit_netlist` first."],
                "diagnostic_feedback": "No synthesized netlist yet. Invoke `synthesize_circuit_netlist` before `verify_circuit_pdg_gate`."
            }
        netlist = effective_netlist
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

        # Return a structured, compact diagnostic summary
        failed_items = [
            {
                "symbol": e.get("symbol") or e.get("name"),
                "measured": e.get("measured"),
                "expected": f"[{e.get('min_target', e.get('min'))}, {e.get('max_target', e.get('max'))}]",
                "unit": e.get("unit"),
                "reason": e.get("diagnostic") or e.get("fail_reason") or "Out of bounds"
            }
            for e in eval_res.get("spec_evaluations", [])
            if not e.get("passed") and e.get("status") != "NOT_TESTABLE_ABS_MAX" and e.get("measured") is not None
        ]

        eval_record = {
            "tag": tag,
            "pass_rate_percent": eval_res.get("pass_rate_percent", 0.0),
            "unique_kind_pass_rate_pct": eval_res.get("unique_kind_pass_rate_pct", 0.0),
            "passed_specs": eval_res.get("passed_specs", 0),
            "failed_specs": eval_res.get("failed_specs", 0),
            "total_specs": eval_res.get("total_specs", len(self.specifications)),
            "stage_status": eval_res.get("pdg_gate_stage") or eval_res.get("stage_status", "UNKNOWN"),
            "simulation_errors": eval_res.get("simulation_errors", []),
            "diagnostic_feedback": eval_res.get("diagnostic_feedback", ""),
            "failed_specs_summary": failed_items[:15],
            "netlist": cleaned_netlist,
        }
        self.evaluation_history.append(eval_record)
        if (
            self.best_evaluation is None
            or eval_record["pass_rate_percent"] > self.best_evaluation.get("pass_rate_percent", -1.0)
        ):
            self.best_evaluation = eval_record
            if eval_record["pass_rate_percent"] > 0:
                self.dc_bias_achieved = True
                try:
                    self.save_subcircuit_blueprint(
                        name=f"{self.dut_name.lower()}_verified_dc_seed",
                        category="opamp",
                        netlist=cleaned_netlist,
                        description=(
                            f"Auto-persisted DC-convergent seed for {self.dut_name} "
                            f"(PDG pass_rate={eval_record['pass_rate_percent']:.1f}%, "
                            f"passed={eval_record['passed_specs']}/{eval_record['total_specs']})."
                        ),
                        verified_metrics={"pass_rate_percent": eval_record["pass_rate_percent"]},
                    )
                except Exception as exc:
                    logger.debug(f"Auto-save partial seed blueprint skipped: {exc}")

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
        mcp_res: dict[str, Any] | None = None
        body_excerpts_summary: list[dict[str, Any]] = []
        if self.ieee_mcp_client.is_mcp_configured():
            compact_mcp_q = self.web_searcher.normalize_ieee_query(f"{category or 'operational amplifier'} {query}", max_terms=4)
            mcp_res = self.ieee_mcp_client.search_papers(
                query=compact_mcp_q,
                max_results=4,
                publication_title="IEEE Access",
            )
            kw_list = compact_mcp_q.split() + ["amplifier", "gain", "bias", "offset", "differential", "compensation"]
            for p in (mcp_res.get("papers") or [])[:3]:
                art_num = str(p.get("article_number") or "").strip()
                if not art_num:
                    continue
                body_res = self.ieee_mcp_client.read_paper(
                    article_number=art_num,
                    needed_reason=f"Extract circuit stage topology and biasing body excerpts for {target_ic} ({compact_mcp_q})",
                )
                p["full_text_retrieved"] = bool(body_res.get("full_text_retrieved"))
                if body_res.get("full_text_retrieved") and body_res.get("blocks"):
                    ex_list = extract_body_excerpts(body_res["blocks"], kw_list, budget=2500)
                    p["body_characters"] = body_res.get("body_characters", 0)
                    p["body_excerpts"] = ex_list
                    body_excerpts_summary.append({
                        "article_number": art_num,
                        "title": p.get("title", ""),
                        "body_characters": body_res.get("body_characters", 0),
                        "excerpts": ex_list,
                    })
                    if len(body_excerpts_summary) >= 2:
                        break

        res = self.web_searcher.search_circuit_reference(
            ic_name=target_ic,
            category=category or "",
            extra_query=query
        )
        if mcp_res and mcp_res.get("papers"):
            res["ieee_mcp_papers"] = mcp_res["papers"]
            res["ieee_full_text_retrieved"] = len(body_excerpts_summary) > 0
            res["ieee_body_excerpts"] = body_excerpts_summary
            if not res.get("ieee_papers"):
                res["ieee_papers"] = mcp_res["papers"]
                res["ieee_ok"] = True
                res["status"] = "SUCCESS"
                res["references_count"] = len(res.get("references", [])) + len(mcp_res["papers"])
            if body_excerpts_summary:
                lines = []
                for b_item in body_excerpts_summary:
                    ex_str = "\n".join(
                        f"    - [{ex.get('section', 'Body')} | {ex.get('excerpt_id')}] {ex.get('text', '')[:450]}"
                        for ex in (b_item.get("excerpts") or [])[:3]
                    )
                    lines.append(
                        f"  * {b_item['title']} (article_number={b_item['article_number']}, full_text_retrieved=True, body_chars={b_item['body_characters']}):\n{ex_str}"
                    )
                self.ieee_literature_context = (
                    "\n## RETRIEVED IEEE MCP FULL-TEXT ARTICLE BODY EXCERPTS:\n" + "\n".join(lines) + "\n"
                )
            else:
                summary_lines = [
                    f"  * [{p.get('year', '')}] {p.get('title', '')} ({p.get('venue', 'IEEE')}): {str(p.get('abstract', ''))[:260]}"
                    for p in mcp_res["papers"][:3]
                ]
                self.ieee_literature_context = (
                    "\n## RETRIEVED IEEE MCP PAPERS:\n" + "\n".join(summary_lines) + "\n"
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

    def generate_topology_candidates(
        self,
        prompt_hint: str = "",
        max_candidates: int = 6,
        auto_size_preview: bool = False,
        **kwargs,
    ) -> dict[str, Any]:
        """Generates rule-validated op-amp structure candidates via FLAN-T5 & modular blocks."""
        from ai_analog_designer.circuit_synthesis.flan_t5_topology import (
            generate_topology_candidates as _gen_topo,
        )
        from ai_analog_designer.circuit_synthesis.gm_id_sizer import check_opamp_pdg

        pin_names = [p.get("name") if isinstance(p, dict) else str(p) for p in (self.pins or [])]
        pdg_fit = check_opamp_pdg(self.pins or [])
        res = _gen_topo(
            specifications=self.specifications,
            prompt_hint=prompt_hint,
            max_candidates=max_candidates,
            auto_size_preview=auto_size_preview,
            subckt_name=self.dut_name,
            pin_names=pin_names or None,
        )
        res["opamp_5pin_fit"] = pdg_fit
        return res

    def auto_size_gm_id(
        self,
        structure_table: str,
        unit_current_ua: float = 20.0,
        output_scale: float = 1.0,
        simulator: str = "auto",
        **kwargs,
    ) -> dict[str, Any]:
        """Computes GF180 gm/ID transistor sizing and validates the resulting physical .subckt."""
        from ai_analog_designer.circuit_synthesis.gm_id_sizer import (
            auto_size,
            parse_table_text,
        )

        pin_names = [p.get("name") if isinstance(p, dict) else str(p) for p in (self.pins or [])]
        tbl = parse_table_text(structure_table)
        sized = auto_size(
            tbl,
            unit_current=float(unit_current_ua) * 1e-6,
            output_scale=float(output_scale),
            simulator=simulator,
            subckt_name=self.dut_name,
            pin_names=pin_names or None,
        )
        subckt = sized.get("subckt_ltspice") or sized.get("subckt_ngspice") or ""
        if subckt:
            sized["validator"] = self.validate_netlist_syntax(subckt, subckt_name=self.dut_name)
        return sized

    def generate_base_circuit(
        self,
        instruction: str,
        simulator: str = "ltspice",
        ieee_context: str = "",
        **kwargs,
    ) -> dict[str, Any]:
        """Generates a single-file base SPICE circuit & sweep config using seungcheol's bridge + LLMClient."""
        from ai_analog_designer.hermes_core.base_circuit_generator import (
            generate_base_circuit as _gen_base,
        )
        from ai_analog_designer.llm_client import LLMClient

        client = self.llm_client or LLMClient()
        return _gen_base(
            instruction=instruction,
            simulator=simulator,
            ieee_context=ieee_context,
            llm_client=client,
        )

    @staticmethod
    def _parse_spice_num(raw_val: str) -> float | None:
        s = str(raw_val or "").strip().lower()
        m = re.match(r"^([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:e[+-]?\d+)?)\s*(meg|[kmunpf]|g|t)?", s)
        if not m:
            return None
        num = float(m.group(1))
        suf = m.group(2) or ""
        mult = {
            "t": 1e12, "g": 1e9, "meg": 1e6, "k": 1e3,
            "m": 1e-3, "u": 1e-6, "n": 1e-9, "p": 1e-12, "f": 1e-15,
        }.get(suf, 1.0)
        return num * mult

    @staticmethod
    def _format_spice_ohm(val: float) -> str:
        if val >= 1e6:
            return f"{val / 1e6:.3g}Meg"
        if val >= 1e3:
            return f"{val / 1e3:.3g}k"
        return f"{val:.3g}"

    def _auto_sweep_subcircuit(
        self,
        subckt_netlist: str,
        simulator: str = "ltspice",
        max_runs: int = 16,
    ) -> dict[str, Any]:
        """Automatically parameterizes key bias/load resistors and optimizes Gain/Vos/Ibias in LTspice."""
        from pathlib import Path
        from ai_analog_designer.circuit_synthesis.dc_convergence_fixer import (
            _classify_pin,
            run_quick_dc_op_check,
        )
        from ai_analog_designer.neuro_symbolic_verifier.spice_sweep_engine import (
            optimize,
            render_netlist,
            resolve_simulator,
        )

        lines = subckt_netlist.splitlines()
        subckt_hdr_idx = next((i for i, ln in enumerate(lines) if ln.strip().lower().startswith(".subckt")), None)
        if subckt_hdr_idx is None:
            return {"status": "SWEEP_SKIPPED", "is_valid": False, "error": "No .subckt header found."}
        hdr_parts = lines[subckt_hdr_idx].split()
        sub_name = hdr_parts[1] if len(hdr_parts) > 1 else self.dut_name
        hdr_pins = hdr_parts[2:]

        # Map pins for testbench instantiation
        pin_lookup = {
            (str(p.get("name")) if isinstance(p, dict) else str(p)).upper(): p
            for p in (self.pins or [])
        }
        node_list: list[str] = []
        has_vpos = has_vneg = has_inp = has_inn = has_out = False
        ctrl_nodes: list[str] = []
        for idx, pname in enumerate(hdr_pins):
            _, kind = _classify_pin(pin_lookup.get(pname.upper(), pname))
            if kind == "NC":
                node_list.append(f"NC_{idx}")
            elif kind == "VPOS":
                node_list.append("N_VPOS")
                has_vpos = True
            elif kind == "VNEG":
                node_list.append("N_VNEG")
                has_vneg = True
            elif kind == "OUT":
                node_list.append("N_OUT")
                has_out = True
            elif kind == "INP" and not has_inp:
                node_list.append("N_INP")
                has_inp = True
            elif kind in ("INN", "INP"):
                node_list.append("N_INN")
                has_inn = True
            else:
                cn = f"N_CTRL_{idx}"
                node_list.append(cn)
                ctrl_nodes.append(cn)

        if not (has_vpos and has_vneg and has_inp and has_inn and has_out):
            return {"status": "SWEEP_SKIPPED", "is_valid": False, "error": "Subcircuit missing required 5 op-amp ports for auto-sweep."}

        # Collect resistors & group symmetric pairs (e.g., RC1/RC2 -> p_rc, RE3/RE4 -> p_re)
        param_defs: list[dict[str, float | str]] = []
        param_lines: list[str] = []
        param_map: dict[str, str] = {}
        new_sub_lines: list[str] = []
        for ln in lines:
            s = ln.strip()
            m_r = re.match(r"^(R[A-Za-z0-9_]*)\s+(\S+)\s+(\S+)\s+(\S+)(.*)$", s, re.IGNORECASE)
            if m_r:
                rname, n1, n2, rval, rest = m_r.groups()
                num_val = self._parse_spice_num(rval)
                if num_val and 100.0 <= num_val <= 1e6 and "OFFSET" not in rname.upper():
                    group_key = re.sub(r"\d+$", "", rname.upper()) or rname.upper()
                    pname = f"p_{group_key.lower()}"
                    if pname not in param_map and len(param_defs) < 5:
                        p_min = max(200.0, round(num_val * 0.25, 1))
                        p_max = min(500_000.0, max(num_val * 6.0, p_min * 4.0))
                        p_step = max(200.0, round((p_max - p_min) / 6.0, 1))
                        param_map[pname] = pname
                        param_defs.append({
                            "name": pname,
                            "min": p_min,
                            "max": p_max,
                            "initial": min(max(num_val, p_min), p_max),
                            "step": p_step,
                        })
                        param_lines.append(f".param {pname}={num_val}")
                    if pname in param_map:
                        new_sub_lines.append(f"{rname} {n1} {n2} {{{pname}}}{rest}")
                        continue
            new_sub_lines.append(ln)

        if not param_defs:
            return {"status": "SWEEP_SKIPPED", "is_valid": False, "error": "No tunable resistors found in subcircuit."}

        param_subckt = "\n".join(new_sub_lines)
        tb_lines = [
            f"* Auto-Sweep DC Gain/Offset/Bias Optimization for {sub_name}",
            *param_lines,
            param_subckt,
            f"XDUT {' '.join(node_list)} {sub_name}",
            "V_POS N_VPOS 0 DC 15",
            "V_NEG N_VNEG 0 DC -15",
            "V_INP N_INP 0 DC 0",
            "R_FB N_OUT N_INN 10k",
            "R_LOAD N_OUT 0 10k",
            *[f"R_CTRL_{idx} {cn} 0 100k" for idx, cn in enumerate(ctrl_nodes)],
            ".dc V_INP -1 1 1",
            ".meas dc v_id_p1 FIND V(N_INP,N_INN) AT 1",
            ".meas dc v_id_m1 FIND V(N_INP,N_INN) AT -1",
            ".meas dc v_out_0 FIND abs(V(N_OUT)) AT 0",
            ".meas dc i_bias_na FIND abs(I(V_INP))*1e9 AT 0",
            ".meas dc aol_lin PARAM '2.0/max(1e-9,abs(v_id_p1-v_id_m1))'",
            ".end",
        ]
        deck = "\n".join(tb_lines) + "\n"
        settings = {
            "method": "feedback",
            "max_runs": max(4, min(32, int(max_runs))),
            "timeout_s": 15,
            "parameters": param_defs,
            "goals": [
                {"measure": "v_out_0", "op": "<=", "value": 0.5},
                {"measure": "i_bias_na", "op": "<=", "value": 500.0},
                {"measure": "aol_lin", "op": ">=", "value": 3000.0},
            ],
            "objective": {"measure": "aol_lin", "sense": "max"},
        }
        sweep_dir = Path(self.output_dir) / f"sweep_{len(self.evaluation_history) + 1:02d}"
        cfg = {"simulator": simulator}
        resolve_simulator(cfg)
        res = optimize(deck, settings, cfg, sweep_dir)

        runs = res.get("runs") or []
        best_it = res.get("best_iteration")
        best_run = next((r for r in runs if r.get("iteration") == best_it), None)
        if best_run is None:
            valid_runs = [r for r in runs if r.get("valid") and isinstance(r.get("metrics", {}).get("aol_lin"), (int, float))]
            if valid_runs:
                best_run = max(valid_runs, key=lambda r: float(r["metrics"]["aol_lin"]))
        if best_run is None:
            return {"status": "SWEEP_NO_VALID_RUN", "is_valid": False, "error": "No valid sweep run converged."}

        best_params = best_run.get("parameters") or {}
        tuned_subckt = param_subckt
        for pname, val in best_params.items():
            tuned_subckt = tuned_subckt.replace(f"{{{pname}}}", self._format_spice_ohm(float(val)))

        val_res = self.validate_netlist_syntax(tuned_subckt)
        cleaned = val_res.get("cleaned_netlist", tuned_subckt)
        dc_check = run_quick_dc_op_check(cleaned, subckt_name=self.dut_name, pins=self.pins, timeout_s=15)
        if val_res.get("is_valid") and dc_check.get("converged"):
            self.last_synthesized_netlist = cleaned
        return {
            "status": "SWEEP_COMPLETE",
            "is_valid": bool(val_res.get("is_valid")),
            "dc_converged": bool(dc_check.get("converged")),
            "dc_diagnostic": dc_check.get("diagnostic", ""),
            "best_params": best_params,
            "best_metrics": best_run.get("metrics", {}),
            "feasible_count": res.get("feasible_count", 0),
            "runs_count": len(runs),
            "cleaned_netlist": cleaned,
        }

    def sweep_parameters_grid(
        self,
        netlist: str = "",
        settings: dict[str, Any] | None = None,
        simulator: str = "ltspice",
        max_runs: int = 16,
        **kwargs,
    ) -> dict[str, Any]:
        """Runs bounded LTspice/ngspice parameter optimization sweep on a SPICE deck or auto-tunes the current subcircuit."""
        from pathlib import Path
        from ai_analog_designer.neuro_symbolic_verifier.spice_sweep_engine import optimize

        is_full_sweep_project = (
            isinstance(settings, dict)
            and all(k in settings for k in ("parameters", "goals", "objective"))
            and bool(netlist and re.search(r"(?im)^\s*\.end\s*$", netlist))
        )
        if is_full_sweep_project:
            try:
                sweep_dir = Path(self.output_dir) / f"sweep_{len(self.evaluation_history) + 1:02d}"
                cfg = {"simulator": simulator}
                return optimize(netlist, settings, cfg, sweep_dir)
            except Exception as exc:
                logger.warning(f"Standalone sweep_parameters_grid failed ({exc}); falling back to auto-subcircuit sweep.")

        base_subckt = (
            (self.best_evaluation or {}).get("netlist", "").strip()
            or (netlist or "").strip()
            or (self.last_synthesized_netlist or "").strip()
        )
        if not base_subckt:
            return {"status": "SWEEP_SKIPPED", "is_valid": False, "error": "No DC-convergent subcircuit available to sweep."}
        return self._auto_sweep_subcircuit(base_subckt, simulator=simulator, max_runs=max_runs)

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

        # 3. Classify target pins (prefer explicit roles from HKG, fallback to name heuristics)
        vcc_pin = next(
            (p["name"] for p in self.pins if isinstance(p, dict) and str(p.get("role", "")).upper() == "POWER"),
            None,
        ) or next((p for p in pin_names if p.upper() in ('VCC', 'VDD', 'VP', 'V_P', 'PVCC', 'AVCC')), 'Vcc')
        gnd_pin = next(
            (p["name"] for p in self.pins if isinstance(p, dict) and str(p.get("role", "")).upper() == "GROUND"),
            None,
        ) or next((p for p in pin_names if p.upper() in ('GND', 'VSS', 'V', '0')), 'GND')
        thermal_pins = [p for p in pin_names if any(k in p.upper() for k in ('THERMAL', 'POWERPAD', 'EPAD', 'TAB', 'SUB'))]

        def is_pos(p: str) -> bool:
            up = p.upper()
            return any(up.endswith(s) for s in ('_P', 'P', '+', 'PLUS')) and not any(up.endswith(s) for s in ('_N', 'N', '-', 'MINUS'))

        def is_neg(p: str) -> bool:
            up = p.upper()
            return any(up.endswith(s) for s in ('_N', 'N', '-', 'MINUS')) and not any(up.endswith(s) for s in ('_P', 'P', '+', 'PLUS'))

        ch1_inp = next((p for p in pin_names if ('1IN' in p.upper() or 'IN1' in p.upper()) and is_pos(p)), None)
        ch1_inn = next((p for p in pin_names if ('1IN' in p.upper() or 'IN1' in p.upper()) and (is_neg(p) or p.upper() == 'IN1')), None)
        ch1_out = next((p for p in pin_names if '1OUT' in p.upper() or 'OUT1' in p.upper()), None)
        ch2_inp = next((p for p in pin_names if ('2IN' in p.upper() or 'IN2' in p.upper()) and is_pos(p)), None)
        ch2_inn = next((p for p in pin_names if ('2IN' in p.upper() or 'IN2' in p.upper()) and (is_neg(p) or p.upper() == 'IN2')), None)
        ch2_out = next((p for p in pin_names if '2OUT' in p.upper() or 'OUT2' in p.upper()), None)

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

