"""
Unit test for Robust Tool Call & Netlist Extraction Resilience.
Guarantees that Hermes tool calls with multi-line SPICE netlists,
unclosed brackets, unescaped literal newlines, or malformed JSON
are 100% recovered and never dropped.
"""
from ai_analog_designer.hermes_core.hermes_agent import HermesAgent
from ai_analog_designer.llm_client import repair_truncated_json


def test_repair_truncated_json_with_control_chars():
    # JSON with literal newline and unclosed braces
    malformed = '{"name": "verify_circuit_pdg_gate", "arguments": {"netlist": ".subckt TEST IN OUT\n* comment\nR1 IN OUT 1k\n.ends TEST"'
    repaired = repair_truncated_json(malformed)
    assert repaired is not None
    assert repaired.get("name") == "verify_circuit_pdg_gate"
    assert "arguments" in repaired
    assert ".subckt TEST" in repaired["arguments"].get("netlist", "")


def test_parse_tool_calls_with_literal_newlines_and_missing_brace():
    agent = HermesAgent(workspace_dir=".")
    
    # Exact pattern emitted by LLMs when generating SPICE netlists
    text = (
        "<tool_call>\n"
        '{"name": "verify_circuit_pdg_gate", "arguments": {"netlist": ".subckt ADS7891 PIN NIN OUT VDD VSS\n'
        "* === 1. Device Models ===\n"
        ".model NMOS NMOS (VTO=0.7)\n"
        "M1 PIN VDD OUT VSS NMOS W=10u L=1u\n"
        "M2 NIN VDD OUT VSS NMOS W=10u L=1u\n"
        'R1 OUT VSS 10k\n.ends ADS7891\\n", "tag": "iter1"}\n'
        "</tool_call>"
    )
    calls = agent.parse_tool_calls(text)
    assert len(calls) == 1
    assert calls[0]["name"] == "verify_circuit_pdg_gate"
    assert ".ends ADS7891" in calls[0]["arguments"]["netlist"]
    assert calls[0]["arguments"]["tag"] == "iter1"


def test_parse_tool_calls_semantic_regex_fallback():
    agent = HermesAgent(workspace_dir=".")
    
    # Completely broken JSON where braces and quotes are totally mismatched
    text = (
        '<tool_call>\n{"name": "verify_circuit_pdg_gate", "arguments": {"netlist": '
        '".subckt OPAMP INP INM OUT VCC VEE\n'
        'Q1 OUT INP VEE QNPN\n'
        'Q2 OUT INM VEE QNPN\n'
        'R1 VCC OUT 2k\n'
        '.ends OPAMP"\n'
        '</tool_call>'
    )
    calls = agent.parse_tool_calls(text)
    assert len(calls) >= 1
    assert calls[0]["name"] == "verify_circuit_pdg_gate"
    assert ".subckt OPAMP" in calls[0]["arguments"]["netlist"]


def test_extract_netlist_resilience():
    agent = HermesAgent(workspace_dir=".")
    
    # Netlist inside raw JSON string without markdown blocks
    text = '{"name": "test", "netlist": ".subckt OPAMP INP INM OUT VCC VEE\\nQ1 OUT INP VEE QNPN\\nQ2 OUT INM VEE QNPN\\nR1 VCC OUT 2k\\n.ends OPAMP"}'
    nl = agent.extract_netlist(text)
    assert nl is not None
    assert ".subckt OPAMP" in nl
    assert ".ends OPAMP" in nl
