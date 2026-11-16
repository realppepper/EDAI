"""
Tests for Tavily + Exa Web Circuit Reference Search integration,
HermesAnalogTools web reference retrieval, dynamic testbench sanitizer,
and placeholder rejection guardrails.
"""
import os
import tempfile

from ai_analog_designer.hermes_core.hermes_agent import HermesAgent
from ai_analog_designer.hermes_core.hermes_tools import HermesAnalogTools
from ai_analog_designer.hermes_core.web_reference_search import (
    WebCircuitReferenceSearcher,
)
from ai_analog_designer.neuro_symbolic_verifier.dynamic_testbench_harness import (
    DynamicTestbenchHarness,
)


def test_tavily_and_exa_web_circuit_reference_search():
    """Verifies live Tavily + Exa dual-engine web circuit reference search."""
    searcher = WebCircuitReferenceSearcher()
    res = searcher.search_circuit_reference(
        ic_name="TPA3116D2",
        category="audio_amplifier",
        extra_query="Class-D BTL output stage"
    )
    assert res["status"] == "SUCCESS"
    assert res["tavily_ok"] or res["exa_ok"]
    assert res["references_count"] > 0
    assert "### Web Circuit Design References" in res["formatted_markdown"]


def test_hermes_tools_web_reference_integration():
    """Verifies that HermesAnalogTools exposes search_web_circuit_reference and caches skills."""
    with tempfile.TemporaryDirectory() as tmpdir:
        pins = [
            {"name": "INP", "role": "SIGNAL", "direction": "INPUT"},
            {"name": "INM", "role": "SIGNAL", "direction": "INPUT"},
            {"name": "VCC", "role": "POWER", "direction": "INPUT"},
            {"name": "GND", "role": "GROUND", "direction": "INPUT"},
            {"name": "OUT", "role": "SIGNAL", "direction": "OUTPUT"},
        ]
        tools = HermesAnalogTools(
            output_dir=tmpdir,
            dut_name="LM393",
            pins=pins,
            specifications=[],
            pdg_schedule={"VCC": 0.0, "GND": 0.0, "INP": 1e-6, "INM": 1e-6, "OUT": 2e-6},
        )
        schema_names = [s["function"]["name"] for s in tools.get_tool_schemas()]
        assert "search_web_circuit_reference" in schema_names

        out = tools.dispatch("search_web_circuit_reference", {
            "query": "LM393 differential comparator schematic BJT",
            "ic_name": "LM393",
            "category": "comparator"
        })
        assert out.get("references_count", 0) > 0
        ref_file = os.path.join(tools.skills_dir, "web_references", "lm393_web_reference.md")
        assert os.path.exists(ref_file)


def test_dynamic_testbench_sanitizer_repairs_broken_spice_lines():
    """Verifies that malformed testbench lines (missing V prefix, bare pins, bad .meas param) are repaired."""
    broken_deck = """* Broken Testbench
.include "TPA3116D2_hermes_iter1.cir"
XDUT MODSEL SDZ GND PVCC AVCC PowerPAD OUTPL OUTNL TPA3116D2
GND GND 0
PowerPAD 0
PVCC PVCC 21
AVCC AVCC 5
SDZ SDZ 3.3V
AM0 AM0 V
.meas tran gain_20db param 20*log(V(OUTPL,OUTNL)/V(INP,INN)) from=15m to=20m
.end
"""
    pins = [
        {"name": "MODSEL"}, {"name": "SDZ"}, {"name": "GND"},
        {"name": "PVCC"}, {"name": "AVCC"}, {"name": "PowerPAD"},
        {"name": "OUTPL"}, {"name": "OUTNL"}, {"name": "AM0"}
    ]
    fixed = DynamicTestbenchHarness._sanitize_dynamic_testbench(broken_deck, pins)
    assert "V_GND GND 0 0" in fixed
    assert "V_PowerPAD PowerPAD 0 0" in fixed
    assert "V_PVCC PVCC 0 21" in fixed
    assert "V_AVCC AVCC 0 5" in fixed
    assert "V_SDZ SDZ 0 3.3V" in fixed
    assert "V_AM0 AM0 0 3.3" in fixed
    assert "* [Auto-commented invalid .meas param]" in fixed


def test_meaningful_netlist_rejects_x_placeholders():
    """Verifies that undefined X-subcircuit placeholder stubs are rejected by HermesAgent."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tools = HermesAnalogTools(
            output_dir=tmpdir,
            dut_name="TPA3116D2",
            pins=[{"name": "INP"}, {"name": "OUT"}, {"name": "VCC"}, {"name": "GND"}],
            specifications=[],
            pdg_schedule={},
        )
        agent = HermesAgent(workspace_dir=tmpdir, tools=tools)

        bad_netlist = """.subckt TPA3116D2 INP OUT VCC GND
XGVDD VCC GND QNPN (GVDD regulator - placeholder)
XPWM INP VCC QNPN (PWM modulator - placeholder)
XLOUT OUT GND QPMOS QNMOS (half-bridge - placeholder)
.ends TPA3116D2"""
        assert not agent._is_meaningful_netlist(bad_netlist)

        good_netlist = """.subckt TPA3116D2 INP OUT VCC GND
Q1 N1 INP GND QNPN
R1 VCC N1 10k
Q2 OUT N1 GND QNPN
R2 VCC OUT 4k
.model QNPN NPN (IS=1e-14 BF=100)
.ends TPA3116D2"""
        assert agent._is_meaningful_netlist(good_netlist)


def test_parse_tool_calls_recovers_unclosed_tags_and_clamps_monologues():
    """Verifies that missing </tool_call> closing tags and monologue hallucination loops are handled cleanly."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tools = HermesAnalogTools(
            output_dir=tmpdir,
            dut_name="TPS62160-Q1",
            pins=[{"name": "VIN"}, {"name": "GND"}],
            specifications=[],
            pdg_schedule={},
        )
        agent = HermesAgent(workspace_dir=tmpdir, tools=tools)

        # Case 1: Missing </tool_call> closing tag (exact Turn 1 failure reproduction)
        raw_turn1 = """<tool_call>
{"name": "retrieve_subcircuit_blueprint", "arguments": {"query": "TPS62160 step-down converter DCS-Control transistor topology", "category": "voltage_reference"}}"""

        calls1 = agent.parse_tool_calls(raw_turn1)
        assert len(calls1) == 1
        assert calls1[0]["name"] == "retrieve_subcircuit_blueprint"
        assert "TPS62160" in calls1[0]["arguments"]["query"]

        # Case 2: Monologue hallucination flood with [ASSISTANCE]: (exact Turn 5 failure reproduction)
        raw_turn5 = """<tool_call>
{"name": "search_web_circuit_reference", "arguments": {"query": "TPS62160 DCS-Control PWM step-down converter internal schematic", "ic_name": "TPS62160-Q1", "category": "voltage_reference"}}

[ASSISTANCE]: Let me search for more general PWM converter topologies and reference designs.</think>
<tool_call>
{"name": "search_web_circuit_reference", "arguments": {"query": "DCS-Control step-down converter transistor level topology", "ic_name": "TPS62160-Q1", "category": "voltage_reference"}}

[ASSISTANCE]: Let me search for general PWM converter topology references.</think>
<tool_call>
{"name": "retrieve_subcircuit_blueprint", "arguments": {"query": "synchronous buck converter transistor level", "category": "voltage_reference"}}
"""
        calls5 = agent.parse_tool_calls(raw_turn5)
        # Must be truncated before the fake [ASSISTANCE] monologue and clamped to 1 call
        assert len(calls5) == 1
        assert calls5[0]["name"] == "search_web_circuit_reference"
        assert "TPS62160" in calls5[0]["arguments"]["query"]


def test_native_messages_support_in_llm_client():
    """Verifies that LLMClient accepts native chat messages list."""
    from ai_analog_designer.llm_client import LLMClient
    client = LLMClient()
    native_msgs = [
        {"role": "system", "content": "You are a circuit test agent."},
        {"role": "user", "content": "Respond with OK."}
    ]
    # Verify complete method handles messages argument without error
    import inspect
    sig = inspect.signature(client.complete)
    assert "messages" in sig.parameters
    assert sig.parameters["messages"].default is None
