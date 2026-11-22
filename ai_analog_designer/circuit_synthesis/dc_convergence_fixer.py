"""
Lightweight DC Operating Point (.op) Convergence Checker for `subagent.dc_convergence_fixer`.
Runs a fast (~1-2s) standalone unity-gain `.op` simulation in LTspice and extracts
actionable convergence diagnostics (Singular matrix, Gmin stepping failure, cutoff/short,
rail saturation, or LTspice syntax/log errors) for iterative LLM repair.
"""
from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path
from typing import Any

from ai_analog_designer.neuro_symbolic_verifier.ltspice_runner import LTspiceRunner

_FATAL_PATTERNS = [
    r"Fatal Error:[^\r\n]*",
    r"Singular matrix[^\r\n]*",
    r"Direct Newton iteration failed[^\r\n]*",
    r"Gmin stepping failed[^\r\n]*",
    r"Source stepping failed[^\r\n]*",
    r"Could not converge[^\r\n]*",
    r"Unknown subcircuit[^\r\n]*",
    r"Error on line[^\r\n]*",
    r"Missing model[^\r\n]*",
    r"Can't find definition of model[^\r\n]*",
]


def _classify_pin(pin: dict[str, Any] | str) -> tuple[str, str]:
    if isinstance(pin, dict):
        name = str(pin.get("name") or "")
        role = str(pin.get("role") or "").upper()
        desc = str(pin.get("description") or "").lower()
    else:
        name = str(pin)
        role = ""
        desc = ""
    up = name.upper()
    if role == "NC" or up == "NC":
        return name, "NC"
    if role == "GROUND" or up in ("GND", "VSS", "VEE", "VNEG", "V_NEG", "V_N", "VN", "V") or "neg" in desc:
        return name, "VNEG"
    if role == "POWER" or up in ("VCC", "VDD", "V_P", "VP", "VS", "VIN") or "pos" in desc:
        return name, "VPOS"
    if role == "OUTPUT" or "OUT" in up:
        return name, "OUT"
    if "NONINV" in up or "NON_INV" in up or "NON-INV" in up or "non-inv" in desc or "noninv" in desc:
        return name, "INP"
    if "INVERT" in up or re.search(r"(?:^|_)INN(?:_|$)|(?:^|_)IN_N(?:_|$)|_N$|^INM$", up):
        return name, "INN"
    if re.search(r"(?:^|_)INP(?:_|$)|(?:^|_)IN_P(?:_|$)|_P$", up):
        return name, "INP"
    if role == "SIGNAL":
        return name, "INP"
    return name, "CTRL"


def build_quick_dc_op_deck(
    netlist: str,
    subckt_name: str,
    pins: list[dict[str, Any]] | list[str],
    dut_file_path: str,
) -> tuple[str, bool]:
    """Builds a minimal unity-gain DC `.op` testbench around the candidate subcircuit."""
    classified = [_classify_pin(p) for p in (pins or [])]
    node_list: list[str] = []
    has_vpos = False
    has_vneg = False
    has_out = False
    ctrl_nodes: list[str] = []
    inp_assigned = False

    for idx, (pname, kind) in enumerate(classified):
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
        elif kind == "INP":
            if not inp_assigned:
                node_list.append("N_INP")
                inp_assigned = True
            else:
                node_list.append("N_INN")
        elif kind == "INN":
            node_list.append("N_INN")
        else:
            cn = f"N_CTRL_{idx}"
            node_list.append(cn)
            ctrl_nodes.append(cn)

    dut_fwd = dut_file_path.replace("\\", "/")
    lines = [
        f"* Quick DC Operating Point Convergence Check for {subckt_name}",
        f'.include "{dut_fwd}"',
        ".options gmin=1e-10 abstol=1e-10 reltol=1e-3",
        f"XDUT {' '.join(node_list)} {subckt_name}",
    ]
    has_inp = "N_INP" in node_list
    use_dc_sweep = has_inp and has_out
    if has_vpos:
        lines.append("V_POS N_VPOS 0 DC 15")
    if has_vneg:
        lines.append("V_NEG N_VNEG 0 DC -15")
    if has_inp:
        if use_dc_sweep:
            # Unity-gain transient step (-1V -> 0V -> +1V) verifies DC bias, signal transfer, AND negative-feedback stability
            lines.append("V_INP N_INP 0 PWL(0 -1 30u -1 35u 0 65u 0 70u 1 100u 1)")
        else:
            lines.append("V_INP N_INP 0 DC 0")
    if "N_INN" in node_list:
        if has_out:
            # Unity-gain DC feedback prevents open-loop rail saturation during check
            lines.append("R_FB N_OUT N_INN 10k")
        else:
            lines.append("V_INN N_INN 0 DC 0")
    if has_out:
        lines.append("R_LOAD N_OUT 0 10k")
    for idx, cn in enumerate(ctrl_nodes):
        lines.append(f"R_CTRL_{idx} {cn} 0 100k")

    if use_dc_sweep:
        lines.append(".tran 1u 100u")
        lines.append(".meas tran v_out_m1 FIND V(N_OUT) AT 25u")
        lines.append(".meas tran v_out_0 FIND V(N_OUT) AT 60u")
        lines.append(".meas tran v_out_p1 FIND V(N_OUT) AT 95u")
        lines.append(".meas tran i_bias_na FIND abs(I(V_INP))*1e9 AT 60u")
        if has_vpos:
            lines.append(".meas tran i_pos FIND I(V_POS) AT 60u")
    else:
        lines.append(".op")
        if has_out:
            lines.append(".meas op v_out_0 FIND V(N_OUT)")
        if has_vpos:
            lines.append(".meas op i_pos FIND I(V_POS)")
    lines.append(".end")
    return "\n".join(lines) + "\n", has_vpos, use_dc_sweep


def run_quick_dc_op_check(
    netlist: str,
    subckt_name: str,
    pins: list[dict[str, Any]] | list[str],
    timeout_s: int = 15,
) -> dict[str, Any]:
    """Runs a quick `.op` check in LTspice and returns convergence status + diagnostics."""
    try:
        runner = LTspiceRunner()
    except FileNotFoundError:
        return {"converged": True, "skipped": True, "diagnostic": "LTspice not installed; DC .op check skipped."}

    with tempfile.TemporaryDirectory(prefix="edai_dc_op_") as tmpdir:
        dut_path = Path(tmpdir) / "candidate_dut.sub"
        tb_path = Path(tmpdir) / "dc_op_check.cir"
        log_path = Path(tmpdir) / "dc_op_check.log"

        dut_path.write_text(netlist, encoding="utf-8")
        deck, has_vpos, use_dc_sweep = build_quick_dc_op_deck(netlist, subckt_name, pins, str(dut_path))
        tb_path.write_text(deck, encoding="utf-8")

        meas: dict[str, Any] = {}
        run_err = ""
        try:
            meas = runner.run_netlist(str(tb_path), timeout=timeout_s)
        except Exception as exc:
            run_err = str(exc)

        log_text = ""
        if log_path.is_file():
            log_text = log_path.read_text(encoding="utf-8", errors="replace")

        fatal_hits: list[str] = []
        for pat in _FATAL_PATTERNS:
            for m in re.finditer(pat, log_text, re.IGNORECASE):
                msg = m.group(0).strip()
                if msg not in fatal_hits:
                    fatal_hits.append(msg)

        if run_err:
            return {
                "converged": False,
                "diagnostic": f"LTspice DC .op execution failed: {run_err}" + (f" | Log: {'; '.join(fatal_hits[:3])}" if fatal_hits else ""),
                "v_out": None,
                "i_pos": None,
                "log_excerpt": log_text[-600:],
            }

        if fatal_hits:
            return {
                "converged": False,
                "diagnostic": "LTspice DC .op convergence/syntax error: " + " | ".join(fatal_hits[:4]),
                "v_out": meas.get("v_out"),
                "i_pos": meas.get("i_pos"),
                "log_excerpt": log_text[-600:],
            }

        v_out = meas.get("v_out_0") if meas.get("v_out_0") is not None else meas.get("v_out")
        v_out_m1 = meas.get("v_out_m1")
        v_out_p1 = meas.get("v_out_p1")
        i_pos = meas.get("i_pos")
        dv_out = (
            float(v_out_p1) - float(v_out_m1)
            if (v_out_p1 is not None and v_out_m1 is not None)
            else None
        )
        issues: list[str] = []
        if has_vpos and i_pos is not None:
            abs_i = abs(float(i_pos))
            if abs_i < 1e-9:
                issues.append(f"DC_CUTOFF: Supply current |I(V_POS)|={abs_i:.3e}A (~0A, circuit is dead/disconnected).")
            elif abs_i > 0.5:
                issues.append(f"DC_SHORT_CIRCUIT: Supply current |I(V_POS)|={abs_i:.3f}A (>0.5A, excessive bias or short).")
        if v_out is not None and abs(float(v_out)) > 2.5:
            issues.append(
                f"DC_BIAS_SATURATED: Unity-gain DC output V_OUT(0V)={float(v_out):.3f}V is far from 0V "
                "(must be within +/-2.5V; fix stage DC biasing/collector loads/output emitter follower)."
            )
        if use_dc_sweep:
            if dv_out is None:
                issues.append("DC_SWEEP_MISSING: Could not measure V_OUT(-1V)/V_OUT(+1V) in unity-gain DC sweep.")
            elif dv_out < -0.5:
                issues.append(
                    f"DC_POLARITY_INVERTED: V_OUT(-1V)={float(v_out_m1):.3f}V -> V_OUT(+1V)={float(v_out_p1):.3f}V "
                    f"(dV={dv_out:.3f}V < 0). Non-inverting and inverting feedback polarity is swapped (positive feedback)."
                )
            elif dv_out < 0.8:
                issues.append(
                    f"DC_NO_SIGNAL_TRANSFER: Output stuck in unity-gain sweep "
                    f"(V_OUT(-1V)={float(v_out_m1):.3f}V, V_OUT(0V)={float(v_out):.3f}V, V_OUT(+1V)={float(v_out_p1):.3f}V, dV={dv_out:.3f}V < 0.8V). "
                    "Check differential pair base/collector wiring and gain-stage bias."
                )

        if issues:
            return {
                "converged": False,
                "diagnostic": " | ".join(issues),
                "v_out": v_out,
                "dv_out": dv_out,
                "i_pos": i_pos,
                "log_excerpt": log_text[-400:],
            }

        i_bias_na = meas.get("i_bias_na")
        return {
            "converged": True,
            "diagnostic": (
                f"DC bias & unity-gain transfer PASSED "
                f"(V_OUT(0V)={v_out}, dV_OUT={dv_out}, I_POS={i_pos}, I_BIAS_nA={i_bias_na})."
            ),
            "v_out": v_out,
            "dv_out": dv_out,
            "i_pos": i_pos,
            "i_bias_na": i_bias_na,
            "log_excerpt": "",
        }
