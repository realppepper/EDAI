"""
Multi-Datasheet Harness Closed-Loop Evaluation & Regression Runner.
Runs AutonomousAnalogDesignAgent over Train/Val/Test splits from `datasets/split_manifest.json`,
classifies failure modes (PARSING / ERC / DC_BIAS / SPEC_SHORTFALL / PASS),
and tracks per-category generalization & regressions across harness versions.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import traceback
from collections import defaultdict
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _load_dotenv(env_path: Path) -> None:
    if not env_path.is_file():
        return
    for ln in env_path.read_text(encoding="utf-8").splitlines():
        ln = ln.strip()
        if ln and not ln.startswith("#") and "=" in ln:
            k, v = ln.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def _classify_failure(eval_json: dict[str, Any] | None, err: str) -> str:
    if err:
        return "CRASH"
    if not eval_json:
        return "NO_EVAL_ARTIFACT"
    pr = float(eval_json.get("pass_rate_percent") or 0.0)
    total = int(eval_json.get("total_specs") or 0)
    stage = str(eval_json.get("pdg_gate_stage") or "").upper()
    if pr >= 100.0 and total > 0:
        return "PASS_100"
    if pr > 0.0:
        return "PARTIAL_SPEC_SHORTFALL"
    if total == 0:
        return "PARSING_OR_PLAN_FAIL"
    if "STAGE0" in stage:
        return "ERC_OR_SYNTAX_FAIL"
    if "STAGE1" in stage or "STAGE2" in stage:
        return "DC_BIAS_FAIL"
    return "SPEC_SHORTFALL_0"


def _find_spec_eval(ic_out_dir: Path) -> dict[str, Any] | None:
    matches = sorted(ic_out_dir.glob("*_SPEC_EVALUATION.json"))
    if not matches:
        return None
    try:
        return json.loads(matches[0].read_text(encoding="utf-8"))
    except Exception:
        return None


def main() -> None:
    parser = argparse.ArgumentParser(description="Run multi-datasheet generalization & regression evaluation.")
    parser.add_argument("--manifest", default="datasets/split_manifest.json", help="Path to split_manifest.json")
    parser.add_argument("--split", default="val", choices=["train", "val", "test"], help="Dataset split to evaluate")
    parser.add_argument("--tag", required=True, help="Harness version tag (e.g. v23_baseline)")
    parser.add_argument("--iterations", type=int, default=6, help="Closed-loop synthesis budget per datasheet")
    parser.add_argument("--limit", type=int, default=0, help="Optional cap on number of datasheets (0 = all)")
    parser.add_argument("--stratified-sample", type=int, default=0, help="Pick up to N ICs evenly across categories")
    parser.add_argument("--categories", default="", help="Comma-separated category filter")
    parser.add_argument("--compare", default="", help="Optional previous summary.json for regression diff")
    args = parser.parse_args()

    _load_dotenv(REPO_ROOT / ".env")
    os.environ.setdefault("ANALOG_EVOLVE_VERIFIER", "0")  # Keep eval fast & deterministic across batch
    if args.split in ("val", "test"):
        # Prevent Val/Test contamination of shared harness2_library across runs
        os.environ["ANALOG_HARNESS2_READONLY"] = "1"

    manifest_path = REPO_ROOT / args.manifest
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    items: list[dict[str, Any]] = list(manifest["splits"][args.split])

    if args.categories.strip():
        allowed = {c.strip() for c in args.categories.split(",") if c.strip()}
        items = [x for x in items if x["category"] in allowed]

    if args.stratified_sample > 0 and len(items) > args.stratified_sample:
        by_cat: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for x in items:
            by_cat[x["category"]].append(x)
        picked: list[dict[str, Any]] = []
        cat_keys = sorted(by_cat.keys())
        while len(picked) < args.stratified_sample and any(by_cat.values()):
            for c in cat_keys:
                if by_cat[c] and len(picked) < args.stratified_sample:
                    picked.append(by_cat[c].pop(0))
        items = picked

    if args.limit > 0:
        items = items[: args.limit]

    eval_root = REPO_ROOT / "datasets" / "eval_runs" / args.tag
    eval_root.mkdir(parents=True, exist_ok=True)

    prev_map: dict[str, float] = {}
    if args.compare:
        cmp_path = Path(args.compare)
        if not cmp_path.is_absolute():
            cmp_path = REPO_ROOT / cmp_path
        if cmp_path.is_file():
            prev_data = json.loads(cmp_path.read_text(encoding="utf-8"))
            for r in prev_data.get("results", []):
                prev_map[r["file"]] = float(r.get("pass_rate_percent") or 0.0)

    from ai_analog_designer.autonomous_design_agent import AutonomousAnalogDesignAgent

    results: list[dict[str, Any]] = []
    print(f"=== Benchmark Eval: tag={args.tag} | split={args.split} | count={len(items)} | iter={args.iterations} ===", flush=True)

    for idx, item in enumerate(items, 1):
        pdf_path = REPO_ROOT / item["path"]
        stem = pdf_path.stem
        ic_out_dir = eval_root / stem
        ic_out_dir.mkdir(parents=True, exist_ok=True)
        print(f"\n[{idx}/{len(items)}] Running {item['file']} ({item['category']})...", flush=True)
        t0 = time.time()
        err_msg = ""
        try:
            agent = AutonomousAnalogDesignAgent(
                output_dir=str(ic_out_dir),
                max_iterations=args.iterations,
            )
            agent.run(datasheet_pdf_path=str(pdf_path))
        except Exception as exc:
            err_msg = f"{type(exc).__name__}: {exc}"
            (ic_out_dir / "eval_error.txt").write_text(traceback.format_exc(), encoding="utf-8")

        elapsed = round(time.time() - t0, 1)
        ev = _find_spec_eval(ic_out_dir)
        pr = float((ev or {}).get("pass_rate_percent") or 0.0)
        passed = int((ev or {}).get("passed_specs") or 0)
        total = int((ev or {}).get("total_specs") or 0)
        stage = str((ev or {}).get("pdg_gate_stage") or "UNKNOWN")
        bucket = _classify_failure(ev, err_msg)
        delta = round(pr - prev_map[item["file"]], 1) if item["file"] in prev_map else None

        rec = {
            "file": item["file"],
            "category": item["category"],
            "pass_rate_percent": pr,
            "passed_specs": passed,
            "total_specs": total,
            "pdg_gate_stage": stage,
            "failure_bucket": bucket,
            "elapsed_s": elapsed,
            "delta_vs_baseline": delta,
            "error": err_msg,
            "output_dir": str(ic_out_dir),
        }
        results.append(rec)
        print(
            f"  -> {item['file']}: {pr:.1f}% ({passed}/{total}) | stage={stage} | bucket={bucket} | {elapsed}s"
            + (f" | delta={delta:+.1f}%" if delta is not None else ""),
            flush=True,
        )

        # Save incremental checkpoint after every IC
        _write_summary(eval_root, args.tag, args.split, results)

    print(f"\n=== Eval Complete: {eval_root / 'summary.md'} ===", flush=True)


def _write_summary(eval_root: Path, tag: str, split: str, results: list[dict[str, Any]]) -> None:
    n = len(results)
    mean_pr = round(sum(r["pass_rate_percent"] for r in results) / max(1, n), 2)
    pdg_passed = sum(1 for r in results if r["pdg_gate_stage"] == "PDG_GATE_PASSED")
    full_pass = sum(1 for r in results if r["failure_bucket"] == "PASS_100")

    by_cat: dict[str, list[dict[str, Any]]] = defaultdict(list)
    buckets: dict[str, int] = defaultdict(int)
    for r in results:
        by_cat[r["category"]].append(r)
        buckets[r["failure_bucket"]] += 1

    cat_summary = {
        c: {
            "count": len(rs),
            "mean_pass_rate": round(sum(x["pass_rate_percent"] for x in rs) / len(rs), 2),
            "pdg_passed": sum(1 for x in rs if x["pdg_gate_stage"] == "PDG_GATE_PASSED"),
        }
        for c, rs in sorted(by_cat.items())
    }
    regressions = [r["file"] for r in results if r.get("delta_vs_baseline") is not None and r["delta_vs_baseline"] < 0]

    payload = {
        "tag": tag,
        "split": split,
        "evaluated_count": n,
        "mean_pass_rate_percent": mean_pr,
        "pdg_gate_passed_count": pdg_passed,
        "full_pass_100_count": full_pass,
        "failure_buckets": dict(buckets),
        "by_category": cat_summary,
        "regressions": regressions,
        "results": results,
    }
    (eval_root / "summary.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")

    md = [
        f"# Harness Generalization Eval: `{tag}` (`{split}` split)",
        "",
        f"- **Evaluated ICs**: `{n}`",
        f"- **Mean Pass Rate**: **`{mean_pr:.2f}%`**",
        f"- **PDG Gate Passed (DC + Signal Alive)**: `{pdg_passed}/{n}` (`{100.0 * pdg_passed / max(1, n):.1f}%`)",
        f"- **100% Spec Pass**: `{full_pass}/{n}`",
        f"- **Failure Buckets**: `{dict(buckets)}`",
        f"- **Regressions vs Baseline**: `{regressions}`",
        "",
        "## Per-Category Summary",
        "| Category | Count | Mean Pass Rate | PDG Gate Passed |",
        "|---|---:|---:|---:|",
    ]
    for c, st in cat_summary.items():
        md.append(f"| `{c}` | {st['count']} | {st['mean_pass_rate']:.1f}% | {st['pdg_passed']}/{st['count']} |")

    md.extend([
        "",
        "## Per-IC Results",
        "| IC | Category | Pass Rate | Passed/Total | PDG Stage | Bucket | Time (s) | Delta |",
        "|---|---|---:|---:|---|---|---:|---:|",
    ])
    for r in results:
        d_str = f"{r['delta_vs_baseline']:+.1f}%" if r["delta_vs_baseline"] is not None else "-"
        md.append(
            f"| `{r['file']}` | `{r['category']}` | {r['pass_rate_percent']:.1f}% | "
            f"{r['passed_specs']}/{r['total_specs']} | `{r['pdg_gate_stage']}` | `{r['failure_bucket']}` | "
            f"{r['elapsed_s']} | {d_str} |"
        )
    (eval_root / "summary.md").write_text("\n".join(md) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
