"""
Deterministic verification flow used by the closed-loop agent.

Wraps spec_planner + deterministic_testbench into a result object that the agent and the reports understand.
Reports coverage (measured / testable) separately from the pass rate among measured specs, so a design that
simply "is not measured" can no longer look like a 100 % pass.
"""
import json
import os
import shutil
from typing import Any

from .deterministic_testbench import (
    FixtureContext,
    build_decks,
    compile_check,
    evaluate,
    feedback_text,
    run_all,
)
from .spec_planner import build_plan
from .units import fmt


def plan_for(ic_info: dict[str, Any], pins: list[dict[str, Any]], specs: list[dict[str, Any]]) -> dict[str, Any]:
    return build_plan(ic_info, pins, specs)


def verify(netlist: str, plan: dict[str, Any], schedule_us: dict[str, float], out_dir: str,
           dut_name: str | None = None, workers: int = 4, label: str = "") -> dict[str, Any]:
    """Runs all fixtures for this netlist and returns a legacy-compatible evaluation dict."""
    run_dir = os.path.join(out_dir, "testbenches", label or "run")
    if os.path.isdir(run_dir):
        shutil.rmtree(run_dir, ignore_errors=True)
    try:
        cc = compile_check(netlist, plan, run_dir, dut_name=dut_name, schedule_us=schedule_us)
    except Exception as e:
        cc = {"ok": False, "errors": [f"{type(e).__name__}: {e}"], "path": None}
    if not cc["ok"]:
        # The netlist does not compile / reach an operating point: report it and skip all fixtures.
        stage_msg = f"netlist blocked by {cc.get('stage', 'PDG_GATE')}: {'; '.join(cc.get('errors', [])[:2])}"
        deck_errors = {it["fixture_key"]: stage_msg
                       for it in plan["items"] if it["status"] == "PLANNED"}
        ev = evaluate(plan, {}, deck_errors)
        for r in ev["rows"]:
            if r["result"] == "NO_FIXTURE":
                r["result"] = "SIM_ERROR"
        ev["summary"]["sim_errors"] = sum(r["result"] == "SIM_ERROR" for r in ev["rows"])
        ev["summary"]["no_fixture"] = 0
    else:
        ctx = FixtureContext(netlist, plan, schedule_us, dut_name=dut_name)
        decks, deck_errors = build_decks(ctx)
        results = run_all(decks, netlist, run_dir, workers=workers)
        ev = evaluate(plan, results, deck_errors)

    spec_evals = []
    for r in ev["rows"]:
        passed = r["result"] in ("PASS", "PASS_TYP")
        lim = r.get("limits_canonical") or {}
        spec_evals.append({
            "symbol": r["symbol"], "name": r["name"], "category": r["category"],
            "measured": r.get("measured"), "min_target": lim.get("min"), "typ_target": lim.get("typ"),
            "max_target": lim.get("max"), "unit": r.get("canonical_unit") or r.get("unit") or "",
            "passed": passed, "status": r["result"], "diagnostic": r.get("diagnostic", ""),
            "conditions": r.get("test_conditions"), "fixture": r.get("fixture_key"), "note": r.get("note", ""),
        })
    s = ev["summary"]
    if cc["ok"]:
        sim_errors = [f"{r['symbol']}: {r.get('diagnostic')}" for r in ev["rows"] if r["result"] == "SIM_ERROR"]
        feedback = feedback_text(ev)
    else:
        sim_errors = list(cc["errors"]) or ["netlist failed the LTspice compile check"]
        feedback = ("The netlist FAILED the LTspice compile / operating-point check, so NO specification could be measured.\n"
                    "LTspice errors (fix every one of them; the text after '|' is the offending netlist line):\n"
                    + "\n".join(f"- {e}" for e in sim_errors))
    unmeasured = [r["symbol"] for r in ev["rows"] if r["result"] in ("NOT_OBSERVED", "NO_FIXTURE", "NOT_RUN")]

    return {
        "pass_rate_percent": s["pass_rate_measured_pct"],
        "pass_rate_hard_percent": s["pass_rate_hard_pct"],
        "unique_pass_rate_percent": s.get("unique_kind_pass_rate_pct", 0.0),
        "unique_kinds_passed": s.get("unique_kinds_passed", 0),
        "unique_kinds_measured": s.get("unique_kinds_measured", 0),
        "pdg_gate_stage": cc.get("stage", "UNKNOWN"),
        "pdg_gate_metrics": cc.get("pdg_metrics", {}),
        "coverage_pct": s["coverage_pct"],
        "passed_specs": s["pass_hard"] + s["pass_typ"],
        "failed_specs": s["fail_hard"] + s["fail_typ"],
        "unmeasured_specs": len(unmeasured),
        "total_specs": s["planned"],
        "all_passed": s["fail_hard"] == 0 and s["fail_typ"] == 0 and s["measured"] > 0,
        "spec_evaluations": spec_evals,
        "diagnostic_feedback": feedback,
        "compile_ok": cc["ok"],
        "compile_errors": cc["errors"],
        "simulation_errors": sim_errors,
        "coverage_summary": {k: s[k] for k in ("total_rows", "electrical_rows", "planned", "measured", "unsupported_kind",
                                               "not_testable", "no_fixture", "not_observed", "sim_errors")},
        "device_class": plan["device_class"],
        "rows": ev["rows"],
    }


def write_artifacts(ev: dict[str, Any], out_dir: str, prefix: str) -> dict[str, str]:
    os.makedirs(out_dir, exist_ok=True)
    paths = {"evaluation": os.path.join(out_dir, f"{prefix}_SPEC_EVALUATION.json"),
             "coverage": os.path.join(out_dir, f"{prefix}_SPEC_COVERAGE.md")}
    slim = {k: v for k, v in ev.items() if k != "rows"}
    with open(paths["evaluation"], "w", encoding="utf-8") as f:
        json.dump(slim, f, indent=2, default=str)

    s = ev["coverage_summary"]
    lines = [f"# Specification coverage — {prefix}", "",
             f"- Verification target rows (all): **{s['total_rows']}**",
             f"- Electrical (testable) rows: **{s['electrical_rows']}**",
             f"- Mapped to a deterministic fixture: **{s['planned']}**",
             f"- Actually measured: **{s['measured']}** → coverage **{ev['coverage_pct']} %**",
             f"- PDG Causal Gate Status: **{ev.get('pdg_gate_stage', 'UNKNOWN')}**",
             f"- Pass among measured rows: **{ev['pass_rate_percent']} %** ({ev['passed_specs']}/{ev['passed_specs'] + ev['failed_specs']})",
             f"- Pass among unique parameter kinds: **{ev.get('unique_pass_rate_percent', 0.0)} %** ({ev.get('unique_kinds_passed', 0)}/{ev.get('unique_kinds_measured', 0)})",
             f"- Sim errors {s['sim_errors']} | not observed {s['not_observed']} | no fixture {s['no_fixture']} | "
             f"unsupported kind {s['unsupported_kind']} | not testable {s['not_testable']}", "",
             "| Symbol | Name | Conditions | Limits (canonical) | Measured | Result |", "|---|---|---|---|---|---|"]
    for r in ev["rows"]:
        lim = r.get("limits_canonical") or {}
        u = r.get("canonical_unit", "")
        lims = " / ".join(fmt(lim.get(k), u) if lim.get(k) is not None else "-" for k in ("min", "typ", "max"))
        m = r.get("measured")
        lines.append(f"| {r['symbol']} | {str(r['name'])[:38]} | {str(r.get('test_conditions') or '')[:34]} | {lims} | "
                     f"{fmt(m, u) if m is not None else '-'} | {r['result']} |")
    with open(paths["coverage"], "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return paths
