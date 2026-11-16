"""
Unit and Integration Tests for Hermes Agent wrapped and tuned by Harness² (C1-C8).
Verifies:
  1. Workspace layout adhering to NousResearch Hermes standards (SOUL.md, MEMORY.md, skills/)
  2. Tuning via Harness² (C1 Persona, C2 Guardrails, C3 Memory, C4 Tool Guidance, C5 Blueprint Skills)
  3. Strict physical guardrails in Hermes tools
  4. Subcircuit blueprint skill retrieval and persistent recording
  5. Memory management (convergence traps in MEMORY.md)
  6. Bidirectional synchronization back to HarnessTree & HarnessLibrary
"""
import os
import shutil
import sys
import tempfile

import pytest

# Ensure repository root in path
repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

from ai_analog_designer.autonomous_design_agent import AutonomousAnalogDesignAgent
from ai_analog_designer.circuit_synthesis.harness2.harness_tree import HarnessTree
from ai_analog_designer.hermes_core import (
    HarnessHermesTuner,
    HermesAgent,
    HermesAnalogTools,
)


@pytest.fixture
def temp_workspace():
    tmp = tempfile.mkdtemp(prefix="hermes_test_")
    yield tmp
    shutil.rmtree(tmp, ignore_errors=True)


def test_hermes_workspace_and_tuning(temp_workspace):
    """Verifies that HarnessHermesTuner configures Hermes workspace according to C1-C8."""
    tuner = HarnessHermesTuner(library_root=os.path.join(repo_root, "harness2_library"))

    # Mock HarnessTree with custom blueprints and traps
    tree = HarnessTree()
    tree.c1_system_prompt = "You are a Master BJT Analog IC Designer."
    tree.c2_guardrails = "STRICT INVARIANT: No B-sources or A-devices."
    tree.c3_memory = "TRAP: 500 Ohm mirror resistor causes 0V shutdown."
    tree.c4_tool_guidance = "Verify using verify_circuit_pdg_gate before finalizing."
    tree.c5_skills = {
        "lm393_comparator_core": ".subckt LM393_CH OUT INP INM VCC GND\nQ1 OUT INP INM QNPN\n.ends LM393_CH",
        "bandgap_ptat_cell": ".subckt PTAT_CELL VDD VREF GND\n.ends PTAT_CELL"
    }

    ws_dir = os.path.join(temp_workspace, "hermes_ws")
    pins = [{"name": "OUT"}, {"name": "INP"}, {"name": "INM"}, {"name": "VCC"}, {"name": "GND"}]
    specs = [{"symbol": "VOL", "min": 0.0, "max": 0.4, "unit": "V"}]

    tools = HermesAnalogTools(
        output_dir=temp_workspace,
        dut_name="LM393_TEST",
        pins=pins,
        specifications=specs,
        pdg_schedule={"VCC": 10e-6, "OUT": 50e-6},
        skills_dir=os.path.join(ws_dir, "skills"),
        memory_file=os.path.join(ws_dir, "memories", "MEMORY.md")
    )

    agent = HermesAgent(
        workspace_dir=ws_dir,
        tools=tools
    )

    tuner.tune_hermes(agent=agent, tree=tree, category="comparator", part_name="LM393_TEST")

    # 1. Check SOUL.md contains C1, C2, C4
    assert os.path.exists(agent.soul_path)
    soul = agent.load_soul()
    assert "Master BJT Analog IC Designer" in soul
    assert "STRICT INVARIANT: No B-sources or A-devices" in soul
    assert "verify_circuit_pdg_gate" in soul

    # 2. Check MEMORY.md contains C3
    assert os.path.exists(agent.memory_path)
    mem = agent.load_memory()
    assert "TRAP: 500 Ohm mirror resistor causes 0V shutdown" in mem

    # 3. Check skills/analog_blueprints/ contains C5 blueprints
    skills = agent.list_available_blueprint_skills()
    skill_names = [s["name"] for s in skills]
    assert "lm393_comparator_core" in skill_names
    assert "bandgap_ptat_cell" in skill_names

    bp_skill_path = os.path.join(agent.blueprints_dir, "lm393_comparator_core", "SKILL.md")
    assert os.path.exists(bp_skill_path)
    with open(bp_skill_path, "r", encoding="utf-8") as f:
        bp_content = f.read()
    assert ".subckt LM393_CH" in bp_content


def test_hermes_tools_guardrail_validation(temp_workspace):
    """Verifies that validate_netlist_syntax enforces C2 physical guardrails."""
    tools = HermesAnalogTools(
        output_dir=temp_workspace,
        dut_name="OPAMP_GUARD",
        pins=[{"name": "INP"}, {"name": "INN"}, {"name": "OUT"}, {"name": "VDD"}, {"name": "VSS"}],
        specifications=[],
        pdg_schedule={}
    )

    # 1. Behavioral B-source should be rejected
    bad_netlist = """.subckt OPAMP_GUARD INP INN OUT VDD VSS
B1 OUT 0 V = { if(V(INP) > V(INN), 5, 0) }
.ends OPAMP_GUARD
"""
    res = tools.validate_netlist_syntax(bad_netlist)
    assert not res["is_valid"]
    assert any("STRICT_ANALOG_VIOLATION" in e for e in res["errors"])

    # 2. Pure physical transistor circuit should pass
    good_netlist = """.subckt OPAMP_GUARD INP INN OUT VDD VSS
M1 N1 INP VSS VSS NMOS W=10u L=1u
M2 OUT INN VSS VSS NMOS W=10u L=1u
R1 VDD N1 10k
R2 VDD OUT 10k
.model NMOS NMOS (VTO=0.7 KP=100u)
.ends OPAMP_GUARD
"""
    res2 = tools.validate_netlist_syntax(good_netlist)
    assert res2["is_valid"]
    assert res2["guardrail_status"] == "PASS"


def test_compile_system_prompt_renders_tool_call_example(temp_workspace):
    """The tool-call JSON example must be escaped inside the f-string prompt."""
    tools = HermesAnalogTools(
        output_dir=temp_workspace,
        dut_name="PROMPT_TEST",
        pins=[{"name": "INP"}, {"name": "OUT"}],
        specifications=[],
        pdg_schedule={},
    )
    agent = HermesAgent(workspace_dir=os.path.join(temp_workspace, "prompt_ws"), tools=tools)

    prompt = agent.compile_system_prompt()

    assert '{"name": "<tool_name>", "arguments": {...}}' in prompt


def test_hermes_tools_blueprint_retrieval_and_saving(temp_workspace):
    """Verifies subcircuit blueprint retrieval and dynamic skill creation."""
    ws_dir = os.path.join(temp_workspace, "ws")
    skills_dir = os.path.join(ws_dir, "skills")
    os.makedirs(skills_dir, exist_ok=True)

    tools = HermesAnalogTools(
        output_dir=temp_workspace,
        dut_name="COMP_TEST",
        pins=[{"name": "OUT"}, {"name": "INP"}, {"name": "INM"}],
        specifications=[],
        pdg_schedule={},
        skills_dir=skills_dir
    )

    # Save a new blueprint skill via tool
    save_res = tools.save_subcircuit_blueprint(
        name="ti_8bjt_comparator",
        category="comparator",
        subckt_code=""".subckt COMP_CORE OUT INP INM VCC GND
Q1 N1 INP N_E QPNP
Q2 N2 INM N_E QPNP
.ends COMP_CORE""",
        description="TI 8-BJT Precision Comparator with PNP input and open-collector NPN output.",
        terminal_pins=["OUT", "INP", "INM", "VCC", "GND"]
    )
    assert save_res["status"] == "SUCCESS"

    # Query the blueprint via tool
    ret_res = tools.retrieve_subcircuit_blueprint(query="comparator", category="comparator")
    assert ret_res["matches_found"] >= 1
    found_titles = [b["title"] for b in ret_res["blueprints"]]
    assert "SKILL.md" in found_titles
    assert "TI 8-BJT Precision Comparator" in ret_res["blueprints"][0]["content"]


def test_hermes_memory_operations(temp_workspace):
    """Verifies Hermes's native memory tool for convergence traps (C3)."""
    mem_file = os.path.join(temp_workspace, "memories", "MEMORY.md")
    tools = HermesAnalogTools(
        output_dir=temp_workspace,
        dut_name="LM393B",
        pins=[],
        specifications=[],
        pdg_schedule={},
        memory_file=mem_file
    )

    # Add memory entry
    tools.manage_memory(action="add", content="Avoid 500 Ohm mirror bypass; use 50Meg bleed instead.")
    with open(mem_file, "r", encoding="utf-8") as f:
        content = f.read()
    assert "Avoid 500 Ohm mirror bypass" in content

    # View memory entry
    view_res = tools.manage_memory(action="view")
    assert view_res["status"] == "SUCCESS"
    assert "Avoid 500 Ohm mirror bypass" in view_res["memory_content"]


def test_bidirectional_sync_back_to_harness(temp_workspace):
    """Verifies that evolved Hermes skills and memories synchronize back into HarnessTree."""
    tuner = HarnessHermesTuner(library_root=os.path.join(temp_workspace, "lib"))
    tree = HarnessTree()

    ws_dir = os.path.join(temp_workspace, "sync_ws")
    tools = HermesAnalogTools(
        output_dir=temp_workspace,
        dut_name="TL431_EVOLVE",
        pins=[{"name": "CATHODE"}, {"name": "REF"}, {"name": "ANODE"}],
        specifications=[],
        pdg_schedule={},
        skills_dir=os.path.join(ws_dir, "skills"),
        memory_file=os.path.join(ws_dir, "memories", "MEMORY.md")
    )
    agent = HermesAgent(workspace_dir=ws_dir, tools=tools)

    # Simulate Hermes discovering a new blueprint and adding a trap in memory
    tools.save_subcircuit_blueprint(
        name="tl431_shunt_core",
        category="voltage_reference",
        subckt_code=".subckt TL431_CORE C R A\nQ1 C R A NPN\n.ends TL431_CORE",
        description="3-terminal precision shunt regulator core"
    )
    tools.manage_memory(action="add", content="TL431: Do not leak internal current to global node 0.")

    # Synchronize back
    evolved = tuner.sync_back_to_harness(
        agent=agent,
        tree=tree,
        task_id="TL431_EVOLVE",
        category="voltage_reference",
        score_before=0.0,
        score_after=100.0
    )

    # Verify HarnessTree contains new skill and memory
    assert "tl431_shunt_core" in evolved.c5_skills
    assert "TL431: Do not leak internal current to global node 0" in evolved.c3_memory


def test_autonomous_design_agent_with_hermes_integration(temp_workspace):
    """Verifies AutonomousAnalogDesignAgent initializes with Hermes enabled."""
    agent = AutonomousAnalogDesignAgent(
        output_dir=temp_workspace,
        use_hermes=True
    )
    assert agent.use_hermes is True
    assert agent.hermes_runner is not None
    assert agent.hermes_runner.output_dir == os.path.abspath(temp_workspace)


if __name__ == "__main__":
    pytest.main(["-v", __file__])
