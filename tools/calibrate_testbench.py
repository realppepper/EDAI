"""
Calibrates the deterministic testbench library against KNOWN-GOOD vendor macromodels.

If the verifier is correct, a vendor model of part X measured against the hand-labelled datasheet
specs of part X must pass (most of) them. Any systematic failure here is a verifier bug, not a design bug.

  python tools/calibrate_testbench.py            # LM393 (TI model in LTspice lib), NE555 (LTspice lib), LM741 (repo macromodel)
"""
import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from ai_analog_designer.neuro_symbolic_verifier.deterministic_testbench import (
    FixtureContext,
    build_decks,
    evaluate,
    run_all,
)
from ai_analog_designer.neuro_symbolic_verifier.spec_planner import build_plan

LTLIB = os.path.join(os.environ.get("LOCALAPPDATA", ""), "LTspice", "lib", "sub")


def read_lib(name):
    p = os.path.join(LTLIB, name)
    with open(p, "r", encoding="utf-8", errors="ignore") as f:
        return f.read()


def gt_specs_and_pins(ic):
    gt = json.load(open(f"benchmarks/pdg_groundtruth/{ic}.json", encoding="utf-8"))
    pins = []
    from ai_analog_designer.pdf_to_graph.pdf_parser import PDFDatasheetParser as P
    for p in gt["pins"]:
        pins.append({"name": P.sanitize_pin_name(p["name"]), "raw_name": p["name"], "role": p["role"], "direction": p["direction"]})
    specs = [{"symbol": s["symbol"], "name": s["name"], "category": s["category"], "min": s["min"], "typ": s["typ"],
              "max": s["max"], "unit": s["unit"], "test_conditions": s.get("conditions", "")} for s in gt["specs"]]
    return gt, pins, specs


CASES = {
    # LM393: TI macromodel shipped with LTspice; DIP wrapper exposes datasheet pin names.
    "lm393": {
        "ic_info": {"name": "LM393", "category": "Dual Comparator"},
        "netlist": lambda pins: read_lib("LM393.sub") + "\n" + wrap("LM393_DIP", ["1OUT", "1IN-", "1IN+", "V-", "2IN+", "2IN-", "2OUT", "V+"], pins),
    },
    # NE555: LTspice built-in behavioural model (pins 1..8 = GND TRIG OUT RESET CONT THRES DISCH VCC)
    "ne555": {
        "ic_info": {"name": "NE555", "category": "Precision Timer"},
        "netlist": lambda pins: read_lib("NE555.sub") + "\n" + wrap("NE555", ["GND", "TRIG", "OUT", "RESET", "CONT", "THRES", "DISCH", "VCC"], pins),
    },
    # LM358 specs vs. the repo's LM741 behavioural macromodel: NOT the same part -> VOS/IB/GBW etc. must FAIL,
    # but the fixtures must still MEASURE (coverage), which is what we calibrate here.
    "lm358_vs_lm741": {
        "gt": "lm358",
        "ic_info": {"name": "LM358", "category": "Dual Operational Amplifier"},
        "split": True,
        "netlist": lambda pins: open("models/lm741_macromodel.sub", encoding="utf-8", errors="ignore").read() + "\n" +
                                 dual_opamp_wrapper(pins),
    },
}


def _key(x):
    return re.sub(r"[^A-Z0-9]", "", str(x).upper().replace("+", "P").replace("-", "N"))


def wrap(inner, inner_pins_by_datasheet_name, pins):
    """Creates `.subckt DUT <sanitized GT pin names>` that calls the vendor subckt using the same nets."""
    gt_by_key = {_key(p["raw_name"]): p["name"] for p in pins}
    alias = {"V-": "GND", "V+": "VCC", "GND/V-": "GND", "V-/GND": "GND"}
    call = []
    for n in inner_pins_by_datasheet_name:
        node = gt_by_key.get(_key(n)) or gt_by_key.get(_key(alias.get(n, n)))
        if node is None:
            node = next((p["name"] for p in pins if
                         (n in ("V+", "VCC") and p["role"] == "POWER") or
                         (n in ("V-", "GND") and p["role"] == "GROUND")), f"nc_{_key(n)}")
        call.append(node)
    order = [p["name"] for p in pins]
    return "\n".join([f".subckt DUT {' '.join(order)}", "X1 " + " ".join(call) + f" {inner}", ".ends DUT"])


def dual_opamp_wrapper(pins):
    """Wraps a single op-amp macromodel (LM741_MACRO 1=IN+ 2=IN- 3=V+ 4=V- 5=OUT) as a dual op-amp DUT."""
    return "\n".join([f".subckt DUT {' '.join(p['name'] for p in pins)}",
                      "X1 IN1_P IN1_N V_P V_N OUT1 LM741_MACRO",
                      "X2 IN2_P IN2_N V_P V_N OUT2 LM741_MACRO",
                      ".ends DUT"])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cases", default=",".join(CASES))
    ap.add_argument("--out", default="benchmark_results/testbench_calibration")
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)
    report = ["# Deterministic testbench calibration against vendor models", ""]
    for case in args.cases.split(","):
        cfg = CASES[case]
        os.environ["TB_SPLIT_SUPPLY"] = "1" if cfg.get("split") else "0"
        gt, pins, specs = gt_specs_and_pins(cfg.get("gt", case))
        plan = build_plan(cfg["ic_info"], pins, specs)
        netlist = cfg["netlist"](pins)
        ctx = FixtureContext(netlist, plan, {"OUT": 50.0})
        decks, errs = build_decks(ctx)
        out_dir = os.path.join(args.out, case)
        results = run_all(decks, netlist, out_dir)
        ev = evaluate(plan, results, errs)
        json.dump({"plan": plan, "evaluation": ev, "deck_errors": errs,
                   "results": {k: {kk: vv for kk, vv in v.items() if kk != "raw"} | {"raw": v["raw"]} for k, v in results.items()}},
                  open(os.path.join(out_dir, "calibration.json"), "w", encoding="utf-8"), indent=2, default=str)
        s = ev["summary"]
        print(f"\n=== {case}: class={plan['device_class']} channels={plan['summary']['channels']} "
              f"rows={s['total_rows']} planned={s['planned']} measured={s['measured']} coverage={s['coverage_pct']}% "
              f"PASS={s['pass_hard']} FAIL={s['fail_hard']} PASS_TYP={s['pass_typ']} FAIL_TYP={s['fail_typ']} "
              f"sim_err={s['sim_errors']} not_obs={s['not_observed']} no_fixture={s['no_fixture']}")
        report += [f"## {case} — class `{plan['device_class']}`", "",
                   f"rows {s['total_rows']} | planned {s['planned']} | measured {s['measured']} (coverage {s['coverage_pct']} %) | "
                   f"PASS {s['pass_hard']} / FAIL {s['fail_hard']} | PASS_TYP {s['pass_typ']} / FAIL_TYP {s['fail_typ']} | "
                   f"sim errors {s['sim_errors']} | not observed {s['not_observed']} | no fixture {s['no_fixture']}", "",
                   "| symbol | name | conditions | limits (canonical) | measured | result |", "|---|---|---|---|---|---|"]
        for r in ev["rows"]:
            if r["result"].startswith("NOT_TESTABLE") or r["result"] == "UNSUPPORTED_KIND":
                continue
            lim = r.get("limits_canonical") or {}
            lims = f"{lim.get('min')} / {lim.get('typ')} / {lim.get('max')} {r.get('canonical_unit', '')}"
            meas = r.get("measured")
            print(f"  {r['result']:12s} {r['symbol']!s:10s} {str(r['name'])[:34]:34s} meas={meas if meas is None else f'{meas:.4g}'} lim={lims}  {str(r.get('diagnostic') or '')[:90]}")
            report.append(f"| {r['symbol']} | {str(r['name'])[:40]} | {str(r.get('test_conditions') or '')[:40]} | {lims} | "
                          f"{'-' if meas is None else f'{meas:.4g}'} | {r['result']} |")
        if errs:
            print("  deck errors:", errs)
        report.append("")
    open(os.path.join(args.out, "CALIBRATION.md"), "w", encoding="utf-8").write("\n".join(report))


if __name__ == "__main__":
    main()
