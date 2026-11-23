"""
Kestrel-Inspired Continuous Numerical Circuit Sizer (Log-Space Powell / Nelder-Mead).

Separates discrete topological synthesis (LLM + Circuit-SAFE) from continuous
transistor/passive sizing (gradient-free log-space numerical optimization over
real LTspice simulations with RFChipAgent Sigmoid-Harmonic multi-objective).

Supports both dual-supply (+/-15V) and single-supply (VDD/GND, mid-rail Vcm=VDD/2)
analog subcircuits, symmetric component grouping across multi-channel ICs, and
datasheet-driven target extraction.
"""
from __future__ import annotations

import logging
import math
import re
import tempfile
from pathlib import Path
from typing import Any

from ai_analog_designer.circuit_synthesis.dc_convergence_fixer import (
    _classify_pin,
    run_quick_dc_op_check,
)
from ai_analog_designer.neuro_symbolic_verifier.ltspice_runner import LTspiceRunner

logger = logging.getLogger(__name__)

_SPICE_SUFFIXES: dict[str, float] = {
    "f": 1e-15,
    "p": 1e-12,
    "n": 1e-9,
    "u": 1e-6,
    "m": 1e-3,
    "k": 1e3,
    "meg": 1e6,
    "g": 1e9,
    "t": 1e12,
}


def parse_spice_value(raw: str) -> float | None:
    s = str(raw or "").strip().lower()
    m = re.match(r"^([+-]?(?:\d+\.?\d*|\.\d+)(?:e[+-]?\d+)?)\s*(meg|[fpnumkgt])?", s)
    if not m:
        return None
    val = float(m.group(1))
    suf = m.group(2)
    return val * _SPICE_SUFFIXES.get(suf, 1.0) if suf else val


def format_spice_value(val: float, is_cap: bool = False) -> str:
    val = abs(float(val))
    if is_cap:
        if val >= 1e-6:
            return f"{val * 1e6:.3g}u"
        if val >= 1e-9:
            return f"{val * 1e9:.3g}n"
        return f"{val * 1e12:.3g}p"
    if val >= 1e6:
        return f"{val / 1e6:.3g}Meg"
    if val >= 1e3:
        return f"{val / 1e3:.3g}k"
    return f"{val:.3g}"


def extract_sizing_targets(
    measurement_plan: dict[str, Any] | None,
    specifications: list[dict[str, Any]] | None = None,
) -> dict[str, float]:
    """Extracts datasheet numeric targets (A_OL dB, Vos V, Ib A, Iq A, GBW Hz) for multi-objective sizing."""
    targets: dict[str, float] = {
        "aol_db_min": 90.0,
        "vos_max": 5e-3,
        "ib_max": 500e-9,
        "iq_max": 5e-3,
        "gbw_min": 1e6,
    }
    items = (measurement_plan or {}).get("items") or []
    for it in items:
        if it.get("status") != "PLANNED":
            continue
        kind = str(it.get("kind") or "").lower()
        lim = it.get("limits_canonical") or {}
        mn, tp, mx = lim.get("min"), lim.get("typ"), lim.get("max")
        if kind in ("aol_db", "av_db", "open_loop_gain"):
            v = mn if isinstance(mn, (int, float)) else tp
            if isinstance(v, (int, float)) and 40.0 <= v <= 160.0:
                targets["aol_db_min"] = max(targets["aol_db_min"], float(v))
        elif kind in ("vos", "input_offset_voltage"):
            v = mx if isinstance(mx, (int, float)) else tp
            if isinstance(v, (int, float)) and v > 0:
                targets["vos_max"] = min(targets["vos_max"], abs(float(v)))
        elif kind in ("ib", "input_bias_current"):
            v = mx if isinstance(mx, (int, float)) else tp
            if isinstance(v, (int, float)) and v > 0:
                targets["ib_max"] = min(targets["ib_max"], abs(float(v)))
        elif kind in ("iq", "supply_current", "quiescent_current"):
            v = mx if isinstance(mx, (int, float)) else tp
            if isinstance(v, (int, float)) and v > 0:
                targets["iq_max"] = min(targets["iq_max"], abs(float(v)))
        elif kind in ("gbw", "unity_gain_bandwidth", "f_t"):
            v = mn if isinstance(mn, (int, float)) else tp
            if isinstance(v, (int, float)) and v > 1e3:
                targets["gbw_min"] = max(targets["gbw_min"], float(v))
    return targets


def _sigmoid(x: float) -> float:
    if x >= 30.0:
        return 1.0
    if x <= -30.0:
        return 1e-13
    return 1.0 / (1.0 + math.exp(-x))


def compute_rfchip_harmonic_score(metrics: dict[str, float], targets: dict[str, float]) -> float:
    """RFChipAgent §3.4 Sigmoid-Normalized Harmonic Mean score in (0, 1]."""
    terms: list[float] = []
    aol_db = metrics.get("aol_db")
    if aol_db is not None and math.isfinite(aol_db):
        t_aol = targets.get("aol_db_min", 90.0)
        terms.append(_sigmoid((aol_db - t_aol) / 6.0))
    else:
        return 0.0

    vos = metrics.get("vos_abs")
    if vos is not None and math.isfinite(vos):
        t_vos = max(targets.get("vos_max", 5e-3), 50e-6)
        terms.append(_sigmoid((t_vos - vos) / max(t_vos * 0.5, 1e-3)))

    ib = metrics.get("ib_abs")
    if ib is not None and math.isfinite(ib):
        t_ib = max(targets.get("ib_max", 500e-9), 1e-9)
        # Log-ratio sigmoid so nanoamp vs microamp scales smoothly
        terms.append(_sigmoid((math.log10(t_ib) - math.log10(max(ib, 1e-13))) / 0.5))

    iq = metrics.get("iq_abs")
    if iq is not None and math.isfinite(iq):
        t_iq = max(targets.get("iq_max", 5e-3), 1e-6)
        if iq < 1e-7 or iq > 0.25:
            return 0.0
        terms.append(_sigmoid((math.log10(t_iq) - math.log10(max(iq, 1e-9))) / 0.4))

    gbw = metrics.get("gbw_hz")
    if gbw is not None and math.isfinite(gbw) and gbw > 0:
        t_gbw = max(targets.get("gbw_min", 1e6), 1e4)
        terms.append(_sigmoid((math.log10(gbw) - math.log10(t_gbw)) / 0.4))

    if not terms:
        return 0.0
    denom = sum(1.0 / max(1e-4, q) for q in terms)
    return len(terms) / denom


def parameterize_subcircuit(
    subckt_netlist: str,
    max_params: int = 6,
) -> tuple[str, list[dict[str, Any]]]:
    """
    Replaces tunable passive values (R and C) with `{p_...}` placeholders,
    grouping symmetric pairs and multi-channel clones (_CHB, _CH2) together.
    """
    lines = subckt_netlist.splitlines()
    param_defs: list[dict[str, Any]] = []
    param_map: dict[str, dict[str, Any]] = {}
    new_lines: list[str] = []

    for ln in lines:
        s = ln.strip()
        m_r = re.match(r"^(R[A-Za-z0-9_]*)\s+(\S+)\s+(\S+)\s+(\S+)(.*)$", s, re.IGNORECASE)
        if m_r:
            rname, n1, n2, rval, rest = m_r.groups()
            num_val = parse_spice_value(rval)
            if num_val and 10.0 <= num_val <= 2e6 and "OFFSET" not in rname.upper():
                base = re.sub(r"_CH[A-D1-4]$", "", rname.upper())
                group_key = re.sub(r"\d+$", "", base) or base
                pname = f"p_{group_key.lower()}"
                if pname not in param_map and len(param_defs) < max_params:
                    pdef = {
                        "name": pname,
                        "initial": num_val,
                        "is_cap": False,
                        "log_min": math.log10(max(5.0, num_val * 0.12)),
                        "log_max": math.log10(min(5e6, num_val * 8.0)),
                    }
                    param_map[pname] = pdef
                    param_defs.append(pdef)
                if pname in param_map:
                    new_lines.append(f"{rname} {n1} {n2} {{{pname}}}{rest}")
                    continue

        m_c = re.match(r"^(C[A-Za-z0-9_]*)\s+(\S+)\s+(\S+)\s+(\S+)(.*)$", s, re.IGNORECASE)
        if m_c:
            cname, n1, n2, cval, rest = m_c.groups()
            num_val = parse_spice_value(cval)
            if num_val and 0.5e-12 <= num_val <= 100e-9:
                base = re.sub(r"_CH[A-D1-4]$", "", cname.upper())
                group_key = re.sub(r"\d+$", "", base) or base
                pname = f"p_{group_key.lower()}"
                if pname not in param_map and len(param_defs) < max_params:
                    pdef = {
                        "name": pname,
                        "initial": num_val,
                        "is_cap": True,
                        "log_min": math.log10(max(0.5e-12, num_val * 0.1)),
                        "log_max": math.log10(min(100e-9, num_val * 10.0)),
                    }
                    param_map[pname] = pdef
                    param_defs.append(pdef)
                if pname in param_map:
                    new_lines.append(f"{cname} {n1} {n2} {{{pname}}}{rest}")
                    continue

        new_lines.append(ln)

    return "\n".join(new_lines), param_defs


def extract_supply_voltage(
    measurement_plan: dict[str, Any] | None,
    is_single_supply: bool,
) -> tuple[float, float, float]:
    """
    Reads the nominal total supply voltage `vs` from `measurement_plan` (derived from
    the datasheet's own electrical conditions) and returns (v_pos, v_neg, v_cm).
    Eliminates hardcoded +/-15V or +5V assumptions across diverse IC families.
    """
    vs_candidates: list[float] = []
    for it in (measurement_plan or {}).get("items") or []:
        cond = it.get("conditions") or {}
        vs = cond.get("vs")
        if isinstance(vs, (int, float)) and 1.2 <= float(vs) <= 100.0:
            vs_candidates.append(float(vs))
    if vs_candidates:
        vs_candidates.sort()
        vs_nom = vs_candidates[len(vs_candidates) // 2]  # median datasheet supply
    else:
        vs_nom = 5.0 if is_single_supply else 10.0

    if is_single_supply:
        return vs_nom, 0.0, vs_nom * 0.5
    half = vs_nom * 0.5
    return half, -half, 0.0


def _build_fast_eval_deck(
    param_subckt: str,
    sub_name: str,
    hdr_pins: list[str],
    pins_meta: list[dict[str, Any]] | list[str],
    param_values: dict[str, float],
    param_is_cap: dict[str, bool],
    measurement_plan: dict[str, Any] | None = None,
) -> tuple[str, bool] | tuple[None, bool]:
    """Builds a single fast DC LTspice deck matching the datasheet's own supply rails."""
    pin_lookup = {
        (str(p.get("name")) if isinstance(p, dict) else str(p)).upper(): p
        for p in (pins_meta or [])
    }
    node_list: list[str] = []
    has_vpos = has_vneg = has_gnd = has_inp = has_inn = has_out = False
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
        elif kind == "GND":
            node_list.append("N_GND")
            has_gnd = True
        elif kind == "OUT" and not has_out:
            node_list.append("N_OUT")
            has_out = True
        elif kind == "INP" and not has_inp:
            node_list.append("N_INP")
            has_inp = True
        elif kind in ("INN", "INP") and not has_inn:
            node_list.append("N_INN")
            has_inn = True
        else:
            cn = f"N_CTRL_{idx}"
            node_list.append(cn)
            ctrl_nodes.append(cn)

    is_single_supply = has_gnd and not has_vneg
    if not (has_vpos and (has_vneg or has_gnd) and has_inp and has_inn and has_out):
        return None, is_single_supply

    v_pos_val, v_neg_val, v_cm = extract_supply_voltage(measurement_plan, is_single_supply)
    v_span = v_pos_val - v_neg_val
    v_step = min(1.0, max(0.2, v_span * 0.1))
    ref_node = "N_VCM" if is_single_supply else "0"

    rendered_sub = param_subckt
    for pname, val in param_values.items():
        rendered_sub = rendered_sub.replace(
            f"{{{pname}}}", format_spice_value(val, is_cap=param_is_cap.get(pname, False))
        )

    lines = [
        f"* Kestrel-style Fast Sizing Eval for {sub_name} ({'single-supply' if is_single_supply else 'dual-supply'} Vs={v_span:g}V)",
        ".options gmin=1e-10 abstol=1e-10 reltol=1e-3",
        rendered_sub,
        f"XDUT {' '.join(node_list)} {sub_name}",
        f"V_POS N_VPOS 0 DC {v_pos_val:g}",
    ]
    if has_vneg:
        lines.append(f"V_NEG N_VNEG 0 DC {v_neg_val:g}")
    if has_gnd:
        lines.append("V_GND N_GND 0 DC 0")
    if is_single_supply:
        lines.append(f"V_CM N_VCM 0 DC {v_cm:g}")
    lines += [
        f"V_INP N_INP 0 DC {v_cm:g}",
        "R_FB N_OUT N_INN 10k",
        f"R_LOAD N_OUT {ref_node} 10k",
        *[f"R_CTRL_{idx} {cn} {ref_node} 100k" for idx, cn in enumerate(ctrl_nodes)],
        f".dc V_INP {v_cm - v_step:g} {v_cm + v_step:g} {v_step:g}",
        f".meas dc v_id_hi FIND V(N_INP,N_INN) AT {v_cm + v_step:g}",
        f".meas dc v_id_lo FIND V(N_INP,N_INN) AT {v_cm - v_step:g}",
        f".meas dc v_out_mid FIND V(N_OUT) AT {v_cm:g}",
        f".meas dc v_out_hi FIND V(N_OUT) AT {v_cm + v_step:g}",
        f".meas dc v_out_lo FIND V(N_OUT) AT {v_cm - v_step:g}",
        f".meas dc ib_abs FIND abs(I(V_INP)) AT {v_cm:g}",
        f".meas dc iq_abs FIND abs(I(V_POS)) AT {v_cm:g}",
        f".meas dc aol_lin PARAM 'abs(v_out_hi-v_out_lo)/max(1e-9,abs(v_id_hi-v_id_lo))'",
        ".meas dc aol_db PARAM '20.0*log10(max(1.0,aol_lin))'",
        f".meas dc vos_abs PARAM 'abs(v_out_mid-{v_cm:g})'",
        ".end",
    ]
    return "\n".join(lines) + "\n", is_single_supply


def optimize_subcircuit_powell(
    subckt_netlist: str,
    dut_name: str,
    pins: list[dict[str, Any]] | list[str],
    measurement_plan: dict[str, Any] | None = None,
    specifications: list[dict[str, Any]] | None = None,
    max_evals: int = 24,
    timeout_s: int = 12,
) -> dict[str, Any]:
    """
    Optimizes passive sizing (R and C) of a DC-convergent subcircuit in log-space
    using SciPy Powell (with pure-Python coordinate-search fallback), maximizing
    the datasheet-driven RFChipAgent Sigmoid-Harmonic score.
    """
    lines = subckt_netlist.splitlines()
    hdr_idx = next((i for i, ln in enumerate(lines) if ln.strip().lower().startswith(".subckt")), None)
    if hdr_idx is None:
        return {"status": "OPT_SKIPPED", "is_valid": False, "error": "No .subckt header found."}
    hdr_parts = lines[hdr_idx].split()
    sub_name = hdr_parts[1] if len(hdr_parts) > 1 else dut_name
    hdr_pins = hdr_parts[2:]

    param_subckt, param_defs = parameterize_subcircuit(subckt_netlist, max_params=6)
    if not param_defs:
        return {"status": "OPT_SKIPPED", "is_valid": False, "error": "No tunable R/C elements found."}

    try:
        runner = LTspiceRunner()
    except FileNotFoundError:
        return {"status": "OPT_SKIPPED", "is_valid": False, "error": "LTspice not available."}

    targets = extract_sizing_targets(measurement_plan, specifications)
    param_is_cap = {p["name"]: p["is_cap"] for p in param_defs}
    x0 = [math.log10(p["initial"]) for p in param_defs]
    bounds = [(p["log_min"], p["log_max"]) for p in param_defs]

    best_score = -1.0
    best_params: dict[str, float] = {p["name"]: p["initial"] for p in param_defs}
    best_metrics: dict[str, float] = {}
    eval_count = 0
    is_single_supply = False

    with tempfile.TemporaryDirectory(prefix="edai_powell_") as tmpdir:
        tmp_path = Path(tmpdir)

        def _evaluate_log_vec(x_vec: list[float]) -> float:
            nonlocal best_score, best_params, best_metrics, eval_count, is_single_supply
            if eval_count >= max_evals:
                return 1.0 - max(0.0, best_score)
            eval_count += 1
            clamped = [min(max(float(v), lo), hi) for v, (lo, hi) in zip(x_vec, bounds)]
            pvals = {p["name"]: 10.0 ** lv for p, lv in zip(param_defs, clamped)}
            deck, single_flag = _build_fast_eval_deck(
                param_subckt, sub_name, hdr_pins, pins, pvals, param_is_cap,
                measurement_plan=measurement_plan,
            )
            is_single_supply = single_flag
            if deck is None:
                return 1.0
            cir_file = tmp_path / f"eval_{eval_count:03d}.cir"
            cir_file.write_text(deck, encoding="utf-8")
            try:
                meas = runner.run_netlist(str(cir_file), timeout=timeout_s)
            except Exception:
                return 1.0

            v_hi = meas.get("v_out_hi")
            v_lo = meas.get("v_out_lo")
            if v_hi is None or v_lo is None:
                return 1.0
            dv = float(v_hi) - float(v_lo)
            min_dv = 0.5 if is_single_supply else 0.8
            if dv < min_dv:
                return 1.0  # Reject cutoff or inverted polarity

            metrics = {
                k: float(meas[k])
                for k in ("aol_db", "vos_abs", "ib_abs", "iq_abs", "gbw_hz")
                if isinstance(meas.get(k), (int, float))
            }
            score = compute_rfchip_harmonic_score(metrics, targets)
            if score > best_score:
                best_score = score
                best_params = dict(pvals)
                best_metrics = dict(metrics)
            return 1.0 - score

        # Baseline evaluation first
        init_loss = _evaluate_log_vec(x0)
        init_score = 1.0 - init_loss

        try:
            from scipy.optimize import minimize

            minimize(
                _evaluate_log_vec,
                x0,
                method="Powell",
                bounds=bounds,
                options={"maxfev": max_evals, "xtol": 0.08, "ftol": 0.01},
            )
        except Exception as exc:
            logger.debug(f"SciPy Powell unavailable or stopped ({exc}); running coordinate search fallback.")
            cur = list(x0)
            for step in (0.35, 0.15):
                for idx in range(len(cur)):
                    if eval_count >= max_evals:
                        break
                    for delta in (-step, step):
                        cand = list(cur)
                        cand[idx] = min(max(cur[idx] + delta, bounds[idx][0]), bounds[idx][1])
                        loss = _evaluate_log_vec(cand)
                        if (1.0 - loss) > best_score - 1e-6:
                            cur = cand

    if best_score <= 0.0:
        return {
            "status": "OPT_NO_VALID_RUN",
            "is_valid": False,
            "runs_count": eval_count,
            "error": "No valid DC-convergent operating point found during Powell sizing.",
        }

    tuned_subckt = param_subckt
    for pname, val in best_params.items():
        tuned_subckt = tuned_subckt.replace(
            f"{{{pname}}}", format_spice_value(val, is_cap=param_is_cap.get(pname, False))
        )

    dc_check = run_quick_dc_op_check(tuned_subckt, subckt_name=dut_name, pins=pins, timeout_s=15)
    return {
        "status": "SWEEP_COMPLETE",
        "method": "kestrel_log_powell",
        "is_valid": True,
        "dc_converged": bool(dc_check.get("converged")),
        "dc_diagnostic": dc_check.get("diagnostic", ""),
        "init_score": round(init_score, 4),
        "best_score": round(best_score, 4),
        "best_params": {k: round(v, 4) for k, v in best_params.items()},
        "best_metrics": best_metrics,
        "targets": targets,
        "runs_count": eval_count,
        "cleaned_netlist": tuned_subckt,
    }
