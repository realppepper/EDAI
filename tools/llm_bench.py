"""
Provider-agnostic LLM benchmark (latency + JSON validity + cost) on the two real workloads of the pipeline:

  spec_page : one column-tagged spec-table page of the LM358 datasheet -> JSON rows   (Phase 1, ~12 calls per IC)
  synth     : the netlist-synthesis prompt for LM358 (Phase 3, 1 call per iteration)

Usage:
  python tools/llm_bench.py --provider openrouter --models anthropic/claude-haiku-5.5,openai/gpt-6-luna --runs 2
"""
import argparse
import concurrent.futures as cf
import json
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from ai_analog_designer.llm_client import LLMClient


def spec_page_prompt():
    from ai_analog_designer.pdf_to_graph import PDFDatasheetParser as P
    from ai_analog_designer.pdf_to_graph.hardware_kg_builder import SPECS_PROMPT
    parsed = P().parse_pdf("testcases/lm358.pdf")
    page = P.select_pages(parsed, "specs")[2]
    return SPECS_PROMPT.format(text=P.page_tagged_text(parsed, [page], 14000, layout=True), ic="LM358"), page


def run(provider, model, workload, prompt):
    c = LLMClient(provider=provider, default_model=model)
    c.fallback_models = []
    t0 = time.time()
    ok, valid, rows, err = False, False, 0, None
    try:
        if workload == "spec_page":
            out = c.complete_json(prompt, system_prompt="Extract only what the datasheet states.", max_tokens=6000, tag="bench_spec")
            rows = len(out.get("electrical_parameters", []))
            valid = rows > 0
        else:
            txt = c.complete(prompt, system_prompt="You are an analog IC designer. Output JSON with spice_netlist.",
                             max_tokens=8192, tag="bench_synth")
            out = c.parse_json_text(txt)
            nl = out.get("spice_netlist", "")
            valid = ".subckt" in nl.lower() and ".ends" in nl.lower()
            rows = len(nl.splitlines())
        ok = True
    except Exception as e:
        err = str(e)[:160]
    log = c.call_log[-1] if c.call_log else {}
    return {"provider": provider, "model": model, "workload": workload, "ok": ok, "valid": valid, "rows_or_lines": rows,
            "ttft_s": log.get("ttft_s"), "total_s": round(time.time() - t0, 1), "out_tokens": log.get("completion_tokens"),
            "cost_usd": log.get("cost_usd"), "error": err}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--provider", default="openrouter")
    ap.add_argument("--models", required=True)
    ap.add_argument("--workloads", default="spec_page,synth")
    ap.add_argument("--runs", type=int, default=2)
    ap.add_argument("--out", default="benchmark_results/LLM_BENCH_{provider}.json")
    args = ap.parse_args()

    sp, page = spec_page_prompt()
    from ai_analog_designer.circuit_synthesis import AICircuitArchitect
    gt = json.load(open("benchmarks/pdg_groundtruth/lm358.json", encoding="utf-8"))
    pins = [{"name": p["name"].replace("+", "_P").replace("-", "_N"), "role": p["role"], "direction": p["direction"]} for p in gt["pins"]]
    specs = [{"symbol": s["symbol"], "name": s["name"], "min": s["min"], "typ": s["typ"], "max": s["max"], "unit": s["unit"]}
             for s in gt["specs"] if s["category"] == "ELECTRICAL"][:30]
    arch = AICircuitArchitect(llm_client=None)
    synth_prompt = arch.build_prompt({"name": "LM358", "category": "Dual Op-Amp"}, pins, specs, {}, 1, None, None) \
        if hasattr(arch, "build_prompt") else (
        "Design a transistor-level SPICE subcircuit '.subckt LM358 " + " ".join(p["name"] for p in pins) +
        "' for a dual bipolar op-amp meeting: " + json.dumps(specs)[:6000] +
        ". Use only R, C, Q, M, D, I, V elements with inline .model cards inside the file. "
        "Return JSON {\"spice_netlist\": str, \"architecture_summary\": str}.")
    prompts = {"spec_page": sp, "synth": synth_prompt}

    jobs = [(m.strip(), w) for _ in range(args.runs) for m in args.models.split(",") if m.strip()
            for w in args.workloads.split(",")]
    res = []
    with cf.ThreadPoolExecutor(max_workers=4) as ex:
        for r in ex.map(lambda j: run(args.provider, j[0], j[1], prompts[j[1]]), jobs):
            print(json.dumps(r), flush=True)
            res.append(r)
    out = args.out.format(provider=args.provider)
    json.dump(res, open(out, "w", encoding="utf-8"), indent=2)

    print("\n| model | workload | ok | valid | TTFT med (s) | total med (s) | out tok | cost/call ($) |")
    print("|---|---|---|---|---|---|---|---|")
    for m in dict.fromkeys(j[0] for j in jobs):
        for w in args.workloads.split(","):
            rs = [r for r in res if r["model"] == m and r["workload"] == w]
            oks = [r for r in rs if r["ok"]]
            med = lambda k, _oks=oks: sorted((r[k] or 0) for r in _oks)[len(_oks) // 2] if _oks else "-"
            cost = round(sum((r["cost_usd"] or 0) for r in oks) / len(oks), 5) if oks else "-"
            print(f"| {m} | {w} | {len(oks)}/{len(rs)} | {sum(r['valid'] for r in rs)}/{len(rs)} | {med('ttft_s')} | "
                  f"{med('total_s')} | {med('out_tokens')} | {cost} |")


if __name__ == "__main__":
    main()
