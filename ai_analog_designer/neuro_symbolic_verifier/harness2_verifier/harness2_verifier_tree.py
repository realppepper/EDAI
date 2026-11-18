"""
Harness² Verifier Tree: Structured 3-Dimension Evolution State for Verification.
Holds evolutionary rules for:
  V1. Spec Classifier & Condition Parsing (spec_planner extension)
  V2. Fixture Circuit & Deck Synthesis (deterministic_testbench extension)
  V3. Physical Unit & Metric Conversion (units extension)
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("Harness2VerifierTree")


class Harness2VerifierTree:
    """
    Represents the mutable execution state of the Verifier within the Dual-Harness² framework.
    """

    def __init__(self):
        # V1: Classifier rules (classes, symbol_regex, name_regex, kind, canonical_unit, magnitude_compare)
        self.v1_kind_rules: list[dict[str, Any]] = [
            {
                "classes": ["audio_amp", "amplifier"],
                "symbol_regex": r"^THD\+?N?$|^D\b",
                "name_regex": r"total harmonic distortion|distortion\s*\+?\s*noise",
                "kind": "thd_n",
                "canonical_unit": "%",
                "magnitude_compare": True
            },
            {
                "classes": ["audio_amp", "power_stage", "amplifier"],
                "symbol_regex": r"^P(O|OUT|L)\b|^P_O$",
                "name_regex": r"continuous output power|output power|power output",
                "kind": "p_out",
                "canonical_unit": "W",
                "magnitude_compare": False
            },
            {
                "classes": ["audio_amp", "timer", "pll", "switching_converter"],
                "symbol_regex": r"^f(OSC|SW|CLK)\b|^F_OSC$",
                "name_regex": r"oscillator frequency|switching frequency|clock frequency",
                "kind": "f_osc",
                "canonical_unit": "Hz",
                "magnitude_compare": False
            },
            {
                "classes": ["audio_amp", "power_switch", "ldo", "switching_converter"],
                "symbol_regex": r"^r(DS\(on\)|ON|ds_on)\b|^RDS\(ON\)$",
                "name_regex": r"drain[- ]source on[- ]state resistance|on[- ]resistance",
                "kind": "rds_on",
                "canonical_unit": "Ohm",
                "magnitude_compare": True
            },
            {
                "classes": ["ldo", "regulator", "pmic"],
                "symbol_regex": r"^V(DO|DROPOUT)$",
                "name_regex": r"dropout voltage",
                "kind": "v_dropout",
                "canonical_unit": "V",
                "magnitude_compare": True
            },
            {
                "classes": ["ldo", "regulator", "pmic"],
                "symbol_regex": r"^(ΔV_LINE|LINE_REG)$",
                "name_regex": r"line regulation",
                "kind": "line_reg",
                "canonical_unit": "%/V",
                "magnitude_compare": True
            },
            {
                "classes": ["ldo", "regulator", "pmic"],
                "symbol_regex": r"^(ΔV_LOAD|LOAD_REG)$",
                "name_regex": r"load regulation",
                "kind": "load_reg",
                "canonical_unit": "%",
                "magnitude_compare": True
            }
        ]

        # V2: Fixture Circuit Templates (Pure Physical Analog Only - strictly no B-sources)
        self.v2_fixture_templates: dict[str, str] = {
            "thd_n": """* Pure Physical Analog Audio Fixture for THD / THD+N
.include "{dut_netlist_path}"
XDUT {dut_pins} {dut_name}
* Physical Power Supplies
VPOS {vpos_pin} 0 DC {vsupply_pos}
VNEG {vneg_pin} 0 DC {vsupply_neg}
* Physical Pure Analog Sinusoidal Stimulus (1 kHz fundamental)
VIN_P {inp_pin} 0 SINE(0 {vin_amp} 1k 25u)
VIN_N {inn_pin} 0 SINE(0 -{vin_amp} 1k 25u)
* Physical Passive Load Resistor
RLOAD {outp_pin} {outn_pin} {r_load}
* Fourier Harmonic Distortion Analysis Directive
.four 1k 9 V({outp_pin}, {outn_pin})
.tran 10u 20m 10m
.meas tran v_rms RMS V({outp_pin}, {outn_pin}) from=15m to=20m
.meas tran p_out AVG (V({outp_pin})-V({outn_pin}))*I(RLOAD) from=15m to=20m
.end
""",
            "f_osc": """* Pure Physical Analog Frequency Fixture
.include "{dut_netlist_path}"
XDUT {dut_pins} {dut_name}
VPOS {vpos_pin} 0 DC {vsupply_pos}
VNEG {vneg_pin} 0 DC {vsupply_neg}
* External timing capacitor/resistor if required
.tran 10n 50u 10u
.meas tran t1 when V({out_pin})=({vsupply_pos}/2) rise=5
.meas tran t2 when V({out_pin})=({vsupply_pos}/2) rise=6
.meas tran f_osc param 1/(t2-t1)
.end
""",
            "v_dropout": """* Pure Physical Analog LDO Dropout Fixture
.include "{dut_netlist_path}"
XDUT {dut_pins} {dut_name}
* Input voltage swept down to find saturation / dropout threshold
VIN {vin_pin} 0 DC {vin_nom}
RLOAD {vout_pin} 0 {r_load}
.dc VIN {vin_nom} 0.5 -0.05
.meas dc v_dropout find (V({vin_pin})-V({vout_pin})) when V({vout_pin})=({vout_nom}*0.98)
.end
"""
        }

        # V3: Physical Unit Conversions
        self.v3_unit_conversions: dict[str, dict[str, Any]] = {
            "nV/rtHz": {"canonical": "V/rtHz", "factor": 1e-9},
            "uV/rtHz": {"canonical": "V/rtHz", "factor": 1e-6},
            "%/V": {"canonical": "percent_per_volt", "factor": 1.0},
            "ppm/C": {"canonical": "ppm_per_degc", "factor": 1.0},
            "mOhm": {"canonical": "Ohm", "factor": 1e-3},
            "mohm": {"canonical": "Ohm", "factor": 1e-3},
            "W": {"canonical": "W", "factor": 1.0},
            "mW": {"canonical": "W", "factor": 1e-3},
            "kHz": {"canonical": "Hz", "factor": 1e3},
            "MHz": {"canonical": "Hz", "factor": 1e6},
            "dBm": {"canonical": "dBm", "factor": 1.0}
        }

    def register_classifier_rule(self, rule: dict[str, Any]):
        """Registers a newly evolved spec classifier rule."""
        self.v1_kind_rules.append(rule)
        logger.info(f"[Harness² Verifier V1] Registered new classifier rule for kind '{rule.get('kind')}'.")

    def register_fixture_template(self, kind: str, template: str):
        """Registers a newly evolved pure analog fixture template."""
        self.v2_fixture_templates[kind] = template
        logger.info(f"[Harness² Verifier V2] Registered new physical fixture template for '{kind}'.")

    def register_unit_conversion(self, unit_str: str, canonical: str, factor: float):
        """Registers a newly evolved physical unit scaling rule."""
        self.v3_unit_conversions[unit_str] = {"canonical": canonical, "factor": factor}
        logger.info(f"[Harness² Verifier V3] Registered unit scaling for '{unit_str}' -> {factor} * {canonical}.")

    def to_dict(self) -> dict[str, Any]:
        return {
            "v1_kind_rules": self.v1_kind_rules,
            "v2_fixture_templates": self.v2_fixture_templates,
            "v3_unit_conversions": self.v3_unit_conversions
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Harness2VerifierTree:
        tree = cls()
        tree.v1_kind_rules = data.get("v1_kind_rules", tree.v1_kind_rules)
        tree.v2_fixture_templates = data.get("v2_fixture_templates", tree.v2_fixture_templates)
        tree.v3_unit_conversions = data.get("v3_unit_conversions", tree.v3_unit_conversions)
        return tree
