"""
Unit Tests for Dual-Harness² Architecture and Strict Physical Analog Rules.
"""
import os
import sys

# Ensure repository root in path
sys.path.insert(0, os.path.abspath("."))

from ai_analog_designer.circuit_synthesis.netlist_validator import NetlistValidator
from ai_analog_designer.neuro_symbolic_verifier.harness2_verifier import (
    DualHarness2Coordinator,
    GoldenOracleAnchor,
)


def test_validator_rejects_behavioral_b_sources():
    validator = NetlistValidator()
    behavioral_netlist = """
.subckt BAD_OPAMP INP INN OUT VDD VSS
* Prohibited behavioral source shortcut
B1 OUT 0 V = { if(V(INP) > V(INN), 5, 0) }
.ends BAD_OPAMP
"""
    pins = [{"name": "INP"}, {"name": "INN"}, {"name": "OUT"}, {"name": "VDD"}, {"name": "VSS"}]
    res = validator.validate(behavioral_netlist, expected_subckt_name="BAD_OPAMP", expected_pins=pins)
    assert not res["is_valid"], "Validator must reject netlists with behavioral B-sources!"
    assert any("STRICT_ANALOG_VIOLATION" in err for err in res["errors"])
    print("[PASS] NetlistValidator successfully blocked behavioral B-source!")


def test_validator_rejects_logic_a_devices():
    validator = NetlistValidator()
    behavioral_netlist = """
.subckt BAD_GATE IN1 IN2 OUT
* Prohibited digital logic pseudo-device
A1 IN1 IN2 0 0 0 0 OUT 0 AND
.ends BAD_GATE
"""
    pins = [{"name": "IN1"}, {"name": "IN2"}, {"name": "OUT"}]
    res = validator.validate(behavioral_netlist, expected_subckt_name="BAD_GATE", expected_pins=pins)
    assert not res["is_valid"], "Validator must reject netlists with digital A-devices!"
    assert any("STRICT_ANALOG_VIOLATION" in err for err in res["errors"])
    print("[PASS] NetlistValidator successfully blocked digital logic A-device!")


def test_validator_accepts_pure_physical_analog():
    validator = NetlistValidator()
    physical_netlist = """
.subckt PURE_DIFF_PAIR INP INN OUT VDD VSS
* Differential input stage using real transistors
M1 N_DRAIN1 INP N_TAIL VSS NMOS W=20u L=1u
M2 OUT INN N_TAIL VSS NMOS W=20u L=1u
* Active current mirror load
M3 N_DRAIN1 N_DRAIN1 VDD VDD PMOS W=40u L=1u
M4 OUT N_DRAIN1 VDD VDD PMOS W=40u L=1u
* Tail current bias
M5 N_TAIL N_BIAS VSS VSS NMOS W=20u L=1u
R_BIAS VDD N_BIAS 50k
M_BIAS N_BIAS N_BIAS VSS VSS NMOS W=10u L=1u
* Output load capacitor
C_LOAD OUT VSS 10p
.ends PURE_DIFF_PAIR
"""
    pins = [{"name": "INP"}, {"name": "INN"}, {"name": "OUT"}, {"name": "VDD"}, {"name": "VSS"}]
    res = validator.validate(physical_netlist, expected_subckt_name="PURE_DIFF_PAIR", expected_pins=pins)
    assert res["is_valid"], f"Physical analog netlist should be valid! Errors: {res['errors']}"
    print("[PASS] NetlistValidator accepted pure physical transistor-level analog netlist!")


def test_golden_oracle_gatekeeper_rejection_of_behavioral_fixtures():
    anchor = GoldenOracleAnchor()
    bad_fixture = """* Bad fixture with B-source
B1 OUT 0 V = { V(IN) * 100 }
.end
"""
    audit = anchor.audit_fixture_candidate(
        target_kind="thd_n",
        target_class="comparator",
        proposed_deck_template=bad_fixture,
        expected_range=(0.0, 1.0),
        unit="%"
    )
    assert not audit["accepted"], "Golden Oracle must reject any proposed fixture using behavioral B-sources!"
    assert "behavioral" in audit["diagnostic"].lower()
    print("[PASS] Golden Oracle successfully rejected behavioral fixture!")


def test_dual_harness2_coordinator_initialization():
    coordinator = DualHarness2Coordinator()
    assert coordinator.circuit_architect is not None
    assert coordinator.verifier_architect is not None
    assert coordinator.anchor is not None

    # Test preparation on mock IC
    ic_info = {"name": "TEST_LDO", "category": "ldo", "description": "Low-Dropout Linear Regulator"}
    pins = [{"name": "VIN"}, {"name": "GND"}, {"name": "VOUT"}, {"name": "ADJ"}]
    specs = [
        {"symbol": "V_DROPOUT", "name": "Dropout Voltage", "min": 0.05, "typ": 0.15, "max": 0.35, "unit": "V"}
    ]
    mock_plan = {"rows": [], "summary": {"planned": 0, "unsupported_kind": 1}}

    res = coordinator.prepare_dual_evolution_for_ic(ic_info, pins, specs, mock_plan)
    assert "verifier_evolved" in res
    print("[PASS] DualHarness2Coordinator initialized and verified!")


if __name__ == "__main__":
    test_validator_rejects_behavioral_b_sources()
    test_validator_rejects_logic_a_devices()
    test_validator_accepts_pure_physical_analog()
    test_golden_oracle_gatekeeper_rejection_of_behavioral_fixtures()
    test_dual_harness2_coordinator_initialization()
    print("\nALL DUAL-HARNESS² & PHYSICAL ANALOG TESTS PASSED!")
