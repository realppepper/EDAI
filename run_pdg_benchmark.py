"""
PDG Fidelity Benchmark.

For every hand-labelled datasheet in benchmarks/pdg_groundtruth/*.json:
  PDF -> parse -> LLM HKG extraction -> PDG -> (A) provenance audit + (B) ground-truth comparison.

Usage:
  python run_pdg_benchmark.py                       # all ICs with ground truth, default model
  python run_pdg_benchmark.py --ics lm358,ne555 --model z-ai/glm-5.3
  python run_pdg_benchmark.py --reuse               # re-score cached extractions (no LLM calls)
Outputs: benchmark_results/pdg_fidelity/<model>/<ic>.json and SUMMARY.md
"""
import argparse
import concurrent.futures as cf
import glob
import json
import os
import re
import sys
import time

from ai_analog_designer.llm_client import LLMClient
from ai_analog_designer.pdf_to_graph import (
    HardwareKnowledgeGraphBuilder,
    PDFDatasheetParser,
    PDGFidelityVerifier,
    PortDependencyGraphExtractor,
)

GT_DIR = "benchmarks/pdg_groundtruth"


def run_one(ic: str, gt: dict, model: str, out_dir: str, reuse: bool):
    cache = os.path.join(out_dir, f"{ic}_extraction.json")
    parser = PDFDatasheetParser(max_pages=30)
    parsed = parser.parse_pdf(gt["datasheet"])
    llm = LLMClient(default_model=model)
    llm.fallback_models = []  # benchmark a single model honestly
    builder = HardwareKnowledgeGraphBuilder(llm_client=llm)
    t0 = time.time()
    if reuse and os.path.exists(cache):
        raw = json.load(open(cache, encoding="utf-8"))
        llm_s = None
    else:
        raw = builder.extract_raw(parsed)
        llm_s = round(time.time() - t0, 1)
        json.dump(raw, open(cache, "w", encoding="utf-8"), indent=2)
    hkg = builder._json_to_networkx_graph(json.loads(json.dumps(raw)))
    hkg.graph["parsed_pages"] = PDFDatasheetParser.audit_pages(parsed)
    pdg, sched, levels = PortDependencyGraphExtractor().extract_pdg(hkg)
    audit = PDGFidelityVerifier.audit_pdg(hkg, pdg, sched)
    cmp = PDGFidelityVerifier.compare_to_groundtruth(hkg.graph["raw_extraction"], pdg, gt)
    res = {"ic": ic, "model": model, "llm_seconds": llm_s, "llm_calls": llm.call_log,
           "groundtruth_comparison": cmp, "provenance_audit": audit,
           "schedule_us": {k: round(v * 1e6, 3) for k, v in sched.items()}}
    json.dump(res, open(os.path.join(out_dir, f"{ic}.json"), "w", encoding="utf-8"), indent=2, default=str)
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ics", default="")
    ap.add_argument("--model", default=None)
    ap.add_argument("--reuse", action="store_true")
    ap.add_argument("--workers", type=int, default=4)
    args = ap.parse_args()

    model = args.model or LLMClient().default_model
    out_dir = os.path.join("benchmark_results", "pdg_fidelity", re.sub(r"[^a-zA-Z0-9._-]", "_", model))
    os.makedirs(out_dir, exist_ok=True)

    gts = {}
    for f in sorted(glob.glob(os.path.join(GT_DIR, "*.json"))):
        ic = os.path.splitext(os.path.basename(f))[0]
        if args.ics and ic not in args.ics.split(","):
            continue
        gts[ic] = json.load(open(f, encoding="utf-8"))
    if not gts:
        sys.exit("no ground truth files found")

    results = []
    with cf.ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(run_one, ic, gt, model, out_dir, args.reuse): ic for ic, gt in gts.items()}
        for f in cf.as_completed(futs):
            ic = futs[f]
            try:
                r = f.result()
                results.append(r)
                c = r["groundtruth_comparison"]
                print(f"[{ic}] GT score={c['score']} pinF1={c['pins']['f1']} depF1={c['dependencies_full_pdg']['f1']} "
                      f"elecRecall={c['electrical_spec_recall']} valAcc={c['spec_value_accuracy']} "
                      f"provenance={r['provenance_audit']['fidelity_score_pct']} llm={r['llm_seconds']}s", flush=True)
            except Exception as e:
                print(f"[{ic}] FAILED: {e}", flush=True)
                results.append({"ic": ic, "error": str(e)})

    results.sort(key=lambda r: r["ic"])
    lines = [f"# PDG Fidelity Benchmark — model `{model}`", "",
             f"Generated {time.strftime('%Y-%m-%d %H:%M')}. Ground truth: `{GT_DIR}/` (hand-labelled, page-cited).", "",
             "| IC | GT score | Pin P/R | Role acc | Dep P/R (full PDG) | Dep R (datasheet layer) | Sched. order | Elec. spec recall | Value acc | Category acc | AbsMax/Rec leak | Timing recall | Provenance score | Pins grounded | Specs grounded | LLM s |",
             "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    agg = []
    for r in results:
        if "error" in r:
            lines.append(f"| {r['ic']} | ERROR: {r['error'][:60]} |" + " |" * 15)
            continue
        c, a = r["groundtruth_comparison"], r["provenance_audit"]
        agg.append(c["score"])
        tr = c["timing"]["recall"]
        lines.append(
            f"| {r['ic']} | **{c['score']}** | {c['pins']['precision']:.2f}/{c['pins']['recall']:.2f} | {c['pins']['role_accuracy']:.2f} | "
            f"{c['dependencies_full_pdg']['precision']:.2f}/{c['dependencies_full_pdg']['recall']:.2f} | "
            f"{c['dependencies_datasheet_only']['recall']:.2f} | {c['schedule_consistency']['ratio']:.2f} | {c['electrical_spec_recall']:.2f} | {c['spec_value_accuracy']:.2f} | "
            f"{c['spec_category_accuracy']:.2f} | {c['nonelectrical_leak_rate']:.2f} | {'-' if tr is None else f'{tr:.2f}'} | "
            f"{a['fidelity_score_pct']} | {a['pin_provenance']['grounded_pct']}% | {a['spec_provenance']['grounded_pct']}% | {r['llm_seconds']} |")
    if agg:
        lines += ["", f"**Mean GT score: {sum(agg)/len(agg):.1f} / 100** over {len(agg)} ICs."]
    lines += ["", "Metric definitions: see `benchmarks/README.md`."]
    open(os.path.join(out_dir, "SUMMARY.md"), "w", encoding="utf-8").write("\n".join(lines))
    print("\n".join(lines))


if __name__ == "__main__":
    main()
