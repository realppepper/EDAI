"""
End-to-End Verification Test for Autonomous Circuit Synthesis Success.
Tests that the integrated Hermes Agent x Harness2 workflow produces a valid,
simulatable, high pass rate analog circuit without human intervention.
"""

import os

from ai_analog_designer.hermes_core import HermesAnalogWorkflowRunner
from ai_analog_designer.neuro_symbolic_verifier.spec_planner import build_plan
from ai_analog_designer.neuro_symbolic_verifier.verification_flow import verify


def test_hermes_harness2_synthesizes_passing_comparator(tmp_path):
    output_dir = str(tmp_path / "test_out")
    os.makedirs(output_dir, exist_ok=True)

    pins = [
        {"name": "INP", "role": "SIGNAL", "direction": "INPUT", "description": "Non-inverting input"},
        {"name": "INM", "role": "SIGNAL", "direction": "INPUT", "description": "Inverting input"},
        {"name": "OUT", "role": "OUTPUT", "direction": "OUTPUT", "description": "Open collector output"},
        {"name": "VCC", "role": "POWER", "direction": "POWER", "description": "Positive supply"},
        {"name": "GND", "role": "GROUND", "direction": "GROUND", "description": "Ground"}
    ]
    specifications = [
        {"symbol": "I_Q", "name": "Quiescent Current", "min": None, "typ": 0.0008, "max": 0.002, "unit": "A", "category": "ELECTRICAL"},
        {"symbol": "V_OL", "name": "Output Low Voltage", "min": None, "typ": 0.15, "max": 0.4, "unit": "V", "category": "ELECTRICAL"},
        {"symbol": "V_IO", "name": "Input Offset Voltage", "min": None, "typ": 0.001, "max": 0.005, "unit": "V", "category": "ELECTRICAL"}
    ]
    pdg_schedule = {"VCC": 0.0, "GND": 0.0, "INP": 2e-6, "INM": 2e-6, "OUT": 5e-6}
    ic_info = {"part_name": "LM393_VERIFIED", "category": "comparator", "description": "Dual differential comparator"}
    mplan = build_plan(ic_info, pins, specifications)

    def probe_verify(netlist, tag):
        sched_us = {k: v * 1e6 for k, v in pdg_schedule.items()}
        res = verify(
            netlist=netlist,
            plan=mplan,
            schedule_us=sched_us,
            out_dir=output_dir,
            dut_name="LM393_VERIFIED",
            label=tag
        )
        return res

    lib_root = os.path.abspath("harness2_library") if os.path.exists("harness2_library") else os.path.abspath("analogverifier/harness2_library")
    runner = HermesAnalogWorkflowRunner(
        output_dir=output_dir,
        max_turns=3,
        target_pass_rate=100.0,
        library_root=lib_root
    )

    result = runner.run_design_flow(
        ic_info=ic_info,
        pins=pins,
        specifications=specifications,
        pdg_schedule=pdg_schedule,
        measurement_plan=mplan,
        user_prompt="Synthesize a high-speed BJT differential comparator based on LM393 architecture.",
        verify_fn=probe_verify
    )

    assert result["pass_rate_percent"] > 50.0, f"Expected pass rate > 50%, got {result['pass_rate_percent']}"
    assert result["final_cir_path"] is not None
    assert os.path.exists(result["final_cir_path"])

    with open(result["final_cir_path"], "r", encoding="utf-8") as f:
        netlist_content = f.read()

    assert ".subckt LM393_VERIFIED" in netlist_content
    assert ".ends LM393_VERIFIED" in netlist_content
    assert "..." not in netlist_content
    print(f"\n[TEST SUCCESS] Final Pass Rate: {result['pass_rate_percent']}% on {result['subcircuit_name']}")
