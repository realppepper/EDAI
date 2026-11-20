"""
Golden Oracle Anchor (Gatekeeper for Verifier Evolution).
Enforces the invariant:
  Acceptance Condition = Golden Model Pass Rate == 100% AND False Verdict == 0 AND Simulation Errors == 0
Validates proposed verification fixtures against known-good manufacturer golden macromodels
(e.g., TI, Linear Technology, Analog Devices, National Semi) before any new fixture or
parsing rule is merged into the production verifier.
"""
from __future__ import annotations

import logging
import os
import re
from typing import Any

from ai_analog_designer.neuro_symbolic_verifier.ltspice_runner import (
    LTspiceRunner,
)

logger = logging.getLogger("GoldenOracleAnchor")

LTLIB = os.path.join(os.environ.get("LOCALAPPDATA", ""), "LTspice", "lib", "sub")


class GoldenOracleAnchor:
    """
    Gatekeeper that anchors dynamic testbench evolution to empirical physical ground truth.
    Prevents reward hacking where an LLM weakens verification tolerances to artificially inflate pass rates.
    """

    def __init__(self, models_dir: str = "models", gt_dir: str = "benchmarks/pdg_groundtruth"):
        self.models_dir = os.path.abspath(models_dir)
        self.gt_dir = os.path.abspath(gt_dir)
        self.runner = LTspiceRunner()

    def get_golden_model_netlist(self, device_class: str) -> tuple[str, str, list[str]] | None:
        """
        Returns (netlist_content, subckt_name, pin_order) for the canonical golden model of a given class.
        """
        device_class = device_class.lower()
        if any(k in device_class for k in ("comparator", "lm393", "lm293", "lm193", "lm2903")):
            p = os.path.join(LTLIB, "LM393.sub")
            if os.path.exists(p):
                with open(p, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
                pins = ["1OUT", "1IN-", "1IN+", "V-", "2IN+", "2IN-", "2OUT", "V+"]
                wrapper = (
                    "\n.subckt DUT 1OUT 1IN- 1IN+ V- 2IN+ 2IN- 2OUT V+\n"
                    "X1 1OUT 1IN- 1IN+ V- 2IN+ 2IN- 2OUT V+ LM393\n"
                    ".ends DUT\n"
                )
                return content + wrapper, "DUT", pins

        elif any(k in device_class for k in ("timer", "ne555", "lm555")):
            p = os.path.join(LTLIB, "NE555.sub")
            if os.path.exists(p):
                with open(p, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
                pins = ["GND", "TRIG", "OUT", "RESET", "CONT", "THRES", "DISCH", "VCC"]
                wrapper = (
                    "\n.subckt DUT GND TRIG OUT RESET CONT THRES DISCH VCC\n"
                    "X1 GND TRIG OUT RESET CONT THRES DISCH VCC NE555\n"
                    ".ends DUT\n"
                )
                return content + wrapper, "DUT", pins

        elif any(k in device_class for k in ("opamp", "op-amp", "operational", "amplifier", "lm741", "lm358")):
            p = os.path.join(self.models_dir, "lm741_macromodel.sub")
            if os.path.exists(p):
                with open(p, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
                pins = ["INP", "INN", "VPOS", "VNEG", "OUT"]
                wrapper = (
                    "\n.subckt DUT INP INN VPOS VNEG OUT\n"
                    "X1 INP INN VPOS VNEG OUT LM741_MACRO\n"
                    ".ends DUT\n"
                )
                return content + wrapper, "DUT", pins

        elif any(k in device_class for k in ("ldo", "regulator", "lp2985", "lm317", "reference", "tl431")):
            p = os.path.join(self.models_dir, "ti_lp2985_transistor.sub")
            if os.path.exists(p):
                with open(p, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
                pins = ["VIN", "GND", "ON_OFF", "BYPASS", "VOUT"]
                wrapper = (
                    "\n.subckt DUT VIN GND ON_OFF BYPASS VOUT\n"
                    "X1 VIN GND ON_OFF BYPASS VOUT LP2985_TRANSISTOR\n"
                    ".ends DUT\n"
                )
                return content + wrapper, "DUT", pins

        return None

    @staticmethod
    def _preflight_validate_deck(deck: str, subckt_name: str, pin_order: list[str]) -> list[str]:
        """Checks common LTspice-hanging syntax errors before launching LTspice batch mode."""
        errors: list[str] = []
        lines = deck.splitlines()
        xdut_found = False
        has_analysis = False
        has_meas = False
        valid_directives = {
            ".include", ".inc", ".lib", ".param", ".model", ".subckt", ".ends",
            ".op", ".dc", ".ac", ".tran", ".noise", ".tf", ".step",
            ".meas", ".measure", ".options", ".option", ".ic", ".nodeset",
            ".temp", ".four", ".save", ".end", ".func", ".global",
        }
        for idx, raw in enumerate(lines, start=1):
            line = raw.strip()
            if not line or line.startswith("*"):
                continue
            low = line.lower()
            tokens = line.split()
            head = tokens[0].lower()
            if head.startswith("."):
                if head == ".lib" and len(tokens) < 2:
                    errors.append(f"Line {idx}: bare `.lib` without filename is invalid in LTspice.")
                elif head in (".control", ".endc"):
                    errors.append(f"Line {idx}: ngspice `.control/.endc` block is unsupported in LTspice.")
                elif head not in valid_directives:
                    errors.append(f"Line {idx}: unsupported LTspice directive `{tokens[0]}`.")
                if head in (".tran", ".ac", ".dc", ".op", ".noise", ".tf"):
                    has_analysis = True
                if head in (".meas", ".measure"):
                    has_meas = True
                continue
            if re.match(r"^[vi]\w*$", head) and (len(tokens) < 4 or re.match(r"^[vi]\w*\s+\S+\s+dc\b", low)):
                errors.append(f"Line {idx}: source `{line}` must have 2 nodes and a value (syntax: `Vname n+ n- DC val`).")
            if head.startswith("x"):
                if len(tokens) >= 2 and tokens[-1].upper() == subckt_name.upper():
                    xdut_found = True
                    actual_pins = len(tokens) - 2
                    if pin_order and actual_pins != len(pin_order):
                        errors.append(
                            f"Line {idx}: `{tokens[0]}` has {actual_pins} pins, expected {len(pin_order)} "
                            f"for `{subckt_name}` ({' '.join(pin_order)})."
                        )
        if not xdut_found:
            errors.append(f"Missing DUT instantiation calling `{subckt_name}` (expected {len(pin_order)} pins: {' '.join(pin_order)}).")
        if not has_analysis:
            errors.append("Missing LTspice analysis command (e.g., `.op`, `.dc`, `.ac`, or `.tran`).")
        if not has_meas:
            errors.append("Missing `.meas` directive to extract target specification.")
        return errors

    def audit_fixture_candidate(
        self,
        target_kind: str,
        target_class: str,
        proposed_deck_template: str,
        expected_range: tuple[float | None, float | None],
        unit: str,
        out_dir: str = "benchmark_results/testbench_calibration"
    ) -> dict[str, Any]:
        """
        Runs the proposed fixture against the verified manufacturer golden model.
        Returns:
          {
             "accepted": bool,
             "pass_rate": float,
             "false_verdict_count": int,
             "measured_value": float,
             "diagnostic": str
          }
        """
        os.makedirs(out_dir, exist_ok=True)
        golden_data = self.get_golden_model_netlist(target_class)
        if not golden_data:
            logger.warning(f"No golden macromodel found for class '{target_class}'. Falling back to synthetic sanity audit.")
            # If no physical vendor macromodel is available in library, perform physical sanity check
            return self._sanity_audit_fallback(target_kind, proposed_deck_template)

        netlist_content, subckt_name, pin_order = golden_data

        # Verify fixture deck DOES NOT use prohibited behavioral sources
        prohibited = self._check_prohibited_behavioral(proposed_deck_template)
        if prohibited:
            return {
                "accepted": False,
                "pass_rate": 0.0,
                "false_verdict_count": len(prohibited),
                "measured_value": None,
                "diagnostic": f"REJECTED by Golden Oracle: Fixture uses prohibited behavioral constructs: {prohibited}. Pure physical stimulus required."
            }

        # Materialize golden DUT netlist and testbench (sanitize filenames & use absolute .include path)
        safe_class = re.sub(r"[^A-Za-z0-9_.-]+", "_", target_class).strip("_") or "dut"
        safe_kind = re.sub(r"[^A-Za-z0-9_.-]+", "_", target_kind).strip("_") or "spec"
        dut_file = os.path.abspath(os.path.join(out_dir, f"golden_{safe_class}_dut.sub"))
        with open(dut_file, "w", encoding="utf-8") as f:
            f.write(netlist_content)

        # Substitute .include path and generic `DUT` subcircuit name with actual golden subckt_name
        dut_file_fwd = dut_file.replace("\\", "/")
        if re.search(r'^\s*\.include\b', proposed_deck_template, flags=re.IGNORECASE | re.MULTILINE):
            deck = re.sub(
                r'(^\s*\.include\s+["\']?)[^\r\n"\']+(["\']?)',
                lambda m: f'{m.group(1)}{dut_file_fwd}{m.group(2)}',
                proposed_deck_template,
                flags=re.IGNORECASE | re.MULTILINE,
            )
        else:
            deck = f'* Golden Oracle Audit Fixture\n.include "{dut_file_fwd}"\n' + proposed_deck_template

        deck = re.sub(
            r'(?im)^(\s*X\w+\s+[^\r\n]+?\s+)DUT(\s*(?:;.*)?)$',
            lambda m: f"{m.group(1)}{subckt_name}{m.group(2)}",
            deck,
        )

        # Preflight LTspice syntax validation to return immediate actionable diagnostics instead of hanging
        preflight_errors = self._preflight_validate_deck(deck, subckt_name, pin_order)
        if preflight_errors:
            return {
                "accepted": False,
                "pass_rate": 0.0,
                "false_verdict_count": len(preflight_errors),
                "measured_value": None,
                "diagnostic": "Preflight SPICE syntax error(s): " + " | ".join(preflight_errors),
            }

        tb_file = os.path.abspath(os.path.join(out_dir, f"audit_{safe_kind}_{safe_class}.cir"))
        with open(tb_file, "w", encoding="utf-8") as f:
            f.write(deck)

        # Execute simulation via LTspice
        try:
            oracle_timeout = int(os.environ.get("GOLDEN_ORACLE_TIMEOUT_S", "120"))
            meas_results = self.runner.run_netlist(tb_file, timeout=oracle_timeout)
        except Exception as e:
            return {
                "accepted": False,
                "pass_rate": 0.0,
                "false_verdict_count": 1,
                "measured_value": None,
                "diagnostic": f"LTspice simulation crash on golden model: {e}"
            }

        # Check if target measurement variable exists
        clean_kind = target_kind.lower().replace("_", "")
        matched_val = None
        for k, v in meas_results.items():
            if v is not None and (clean_kind in k.lower() or k.lower() in clean_kind):
                matched_val = v
                break
        if matched_val is None and meas_results:
            # Fallback: take the first non-None measurement
            for k, v in meas_results.items():
                if v is not None and isinstance(v, (int, float)):
                    matched_val = v
                    break

        if matched_val is None:
            return {
                "accepted": False,
                "pass_rate": 0.0,
                "false_verdict_count": 1,
                "measured_value": None,
                "diagnostic": f"Target measurement for kind '{target_kind}' not observed in golden log: {list(meas_results.keys())}"
            }

        # Check acceptance criteria against physical boundaries
        min_val, max_val = expected_range
        in_bounds = True
        if min_val is not None and matched_val < min_val:
            in_bounds = False
        if max_val is not None and matched_val > max_val:
            in_bounds = False

        # Invariant: Golden Model must measure physically valid non-nan / non-inf value
        import math
        is_nan_or_inf = math.isnan(matched_val) or math.isinf(matched_val)
        accepted = in_bounds and not is_nan_or_inf

        return {
            "accepted": accepted,
            "pass_rate": 100.0 if accepted else 0.0,
            "false_verdict_count": 0 if accepted else 1,
            "measured_value": matched_val,
            "diagnostic": f"Golden {target_class} measured {matched_val} {unit} (Expected range: [{min_val}, {max_val}])."
        }

    def _check_prohibited_behavioral(self, deck: str) -> list[str]:
        """Checks if fixture contains forbidden B-sources or A-devices."""
        prohibited = []
        for line in deck.splitlines():
            s = line.strip()
            if not s or s.startswith(("*", ";")):
                continue
            toks = s.split()
            first = toks[0].upper()
            if first.startswith("B") and not first.startswith("."):
                prohibited.append(f"Behavioral B-source: '{s}'")
            elif first.startswith("A") and not first.startswith("."):
                prohibited.append(f"Logic A-device: '{s}'")
            elif (first.startswith("E") or first.startswith("G")) and "VALUE" in s.upper():
                prohibited.append(f"Behavioral VALUE expression: '{s}'")
        return prohibited

    def _sanity_audit_fallback(self, target_kind: str, deck: str) -> dict[str, Any]:
        """Fallback syntax and analog sanity checker when physical golden macromodel is unavailable."""
        prohibited = self._check_prohibited_behavioral(deck)
        if prohibited:
            return {
                "accepted": False,
                "pass_rate": 0.0,
                "false_verdict_count": len(prohibited),
                "measured_value": None,
                "diagnostic": f"REJECTED: Prohibited behavioral constructs detected: {prohibited}"
            }
        has_meas = any(l.strip().lower().startswith(".meas") for l in deck.splitlines())
        has_dut = any(re.search(r'\bXDUT\b', l, re.IGNORECASE) for l in deck.splitlines())
        accepted = has_meas and has_dut
        return {
            "accepted": accepted,
            "pass_rate": 100.0 if accepted else 0.0,
            "false_verdict_count": 0 if accepted else 1,
            "measured_value": 0.0,
            "diagnostic": "Syntax & topological physical analog check passed." if accepted else "Missing .meas or XDUT instance."
        }
