"""
Unit & Integration Tests for Jev-Compatible Tool Decision Router & Circuit Blueprint Reranker.
Verifies:
  1. ToolDecisionRouter calibrated probability calculations P(tool | state)
  2. Repetition trap breaking and safety guardrail interception
  3. BlueprintReranker multi-factor physical SPICE ranking
  4. Integration with HermesAnalogTools.retrieve_subcircuit_blueprint
"""
import os
import sys

# Ensure repository root in path
repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

from ai_analog_designer.hermes_core.blueprint_reranker import BlueprintReranker
from ai_analog_designer.hermes_core.hermes_tools import HermesAnalogTools
from ai_analog_designer.hermes_core.tool_decision_router import ToolDecisionRouter


def test_jev_router_turn1_blueprint_routing():
    router = ToolDecisionRouter(dut_name="LM393")
    decision = router.evaluate_state(
        turn_idx=1,
        pass_rate=0.0,
        has_netlist=False,
        syntax_valid=False,
        history_tool_names=[]
    )
    assert decision["selected_tool"] == "retrieve_subcircuit_blueprint"
    assert decision["confidence"] >= 0.70
    assert "retrieve_subcircuit_blueprint" in decision["probabilities"]


def test_jev_router_netlist_present_simulation_routing():
    router = ToolDecisionRouter(dut_name="LM393")
    decision = router.evaluate_state(
        turn_idx=2,
        pass_rate=0.0,
        has_netlist=True,
        syntax_valid=True,
        history_tool_names=["retrieve_subcircuit_blueprint"]
    )
    assert decision["selected_tool"] == "verify_circuit_pdg_gate"
    assert decision["confidence"] >= 0.70


def test_jev_router_repetition_trap_breaker():
    router = ToolDecisionRouter(dut_name="LM393")
    # Simulate agent getting trapped in repetitive manage_memory calls
    decision = router.evaluate_state(
        turn_idx=5,
        pass_rate=0.0,
        has_netlist=False,
        syntax_valid=False,
        history_tool_names=["manage_memory", "manage_memory", "manage_memory"]
    )
    assert "Repetition trap broken" in decision["reason"]
    assert decision["selected_tool"] == "verify_circuit_pdg_gate"

    # Test interception
    intercepted = router.intercept_and_guardrail(
        proposed_calls=[{"name": "manage_memory", "arguments": {"action": "add"}}],
        state_decision=decision,
        has_extracted_netlist=False
    )
    # The redundant manage_memory call must be suppressed
    assert not any(c.get("name") == "manage_memory" for c in intercepted)


def test_jev_router_goal_achievement_saving():
    router = ToolDecisionRouter(dut_name="LM393")
    decision = router.evaluate_state(
        turn_idx=4,
        pass_rate=100.0,
        has_netlist=True,
        syntax_valid=True,
        history_tool_names=["verify_circuit_pdg_gate"]
    )
    assert decision["selected_tool"] == "save_subcircuit_blueprint"
    assert decision["confidence"] >= 0.90


def test_blueprint_reranker_physical_vs_macro_scoring():
    reranker = BlueprintReranker(
        target_dut="LM393",
        target_category="comparator",
        target_pins=["INP", "INM", "OUT", "VCC", "GND"]
    )

    physical_cand = {
        "title": "lm393_transistor_level.md",
        "file": "comparator/LM393/EXPERIENCE.md",
        "content": (
            "```spice\n"
            ".subckt LM393 INP INM OUT VCC GND\n"
            ".model QNPN NPN (BF=100)\n"
            "Q1 N1 INP N3 QNPN\n"
            "Q2 N2 INM N3 QNPN\n"
            "R1 VCC N1 5k\n"
            "R2 VCC N2 5k\n"
            "Q3 OUT N2 GND QNPN\n"
            ".ends LM393\n"
            "```"
        )
    }

    macro_cand = {
        "title": "lm393_behavioral.md",
        "file": "comparator/LM393/macro.md",
        "content": (
            "```spice\n"
            ".subckt LM393 INP INM OUT VCC GND\n"
            "A1 INP INM 0 0 0 OUT 0 0 SCHMITT\n"
            ".ends LM393\n"
            "```"
        )
    }

    unrelated_cand = {
        "title": "tpa3116_audio.md",
        "file": "audio_amplifier/TPA3116/doc.md",
        "content": "Class-D audio power amplifier with BTL bridge output."
    }

    results = reranker.rerank([unrelated_cand, macro_cand, physical_cand], query="LM393 dual comparator", top_k=3)
    
    # Physical transistor candidate must rank #1
    assert len(results) == 3
    assert results[0]["title"] == "lm393_transistor_level.md"
    assert results[0]["rerank_score"] > results[1]["rerank_score"]
    assert results[0]["rerank_details"]["spice"] > results[1]["rerank_details"]["spice"]


def test_hermes_tools_reranker_integration(tmp_path):
    tools = HermesAnalogTools(
        output_dir=str(tmp_path),
        dut_name="LM393",
        pins=[{"name": "INP"}, {"name": "INM"}, {"name": "OUT"}, {"name": "VCC"}, {"name": "GND"}],
        specifications=[{"name": "VOS", "min": -5e-3, "max": 5e-3}],
        pdg_schedule={"OUT": 1.0}
    )

    res = tools.retrieve_subcircuit_blueprint(query="LM393 comparator internal schematic", category="comparator")
    assert "blueprints" in res
    assert isinstance(res["blueprints"], list)
    if res["blueprints"]:
        assert "rerank_score" in res["blueprints"][0]
