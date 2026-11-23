"""
비교 실험(2026-11-22, docs/비교실험_결과.docx) 의 모델 방식 결과(C, C3)를 UI 의 "지난 결과" 실행 폴더로 옮긴다.
D(학습 데이터 찾기)는 더 하지 않기로 해서 옮기지 않는다.

    1~3단계: 그때 만든 추출 결과, 스펙, 후보, 바이어스·크기 정하기 결과를 그대로 복사 (PDG 는 지금 코드로 만듦)
    4단계: C 는 그때 규칙(v1: 통과 수 -> 공급 전류), C3 는 v3 로 고른 결과
    5단계: 그때는 규칙 단계가 없었다 -> "모델 구조 그대로" 만 적는다
    6단계: 그때 하네스 실행 (LTspice 판, 반복 5번) 의 통과율과 최종 넷리스트
    7단계: 회로도를 지금 코드로 다시 그린다

사용법 (WSL 가상환경, 회로도 그리기에 node 가 필요): ~/.venvs/edai/bin/python import_compare_runs.py
결과: runs/<그때 실행 날짜_시각>_<칩>/  (UI 실행과 같은 이름 형식, 이미 있으면 다시 만든다)
제목 = 칩 이름, 메모 = 고르기 방식 (UI 에서 고칠 수 있음)
"""

import json
import shutil
import sys
from pathlib import Path

from file_find import find_file, find_files, name_key

HERE = Path(__file__).resolve().parent
AV_OLD = Path("/mnt/d/analogverifier") if Path("/mnt/d").exists() else Path("D:/analogverifier")
COMPARE = AV_OLD / "edai_compare"
HKG_CACHE = AV_OLD / "output_interactive" / ".hkg_cache"
HARNESS_OUT = AV_OLD / "output_interactive"
# 칩: (우리 파일 이름, 데이터시트 PDF, 추출 캐시 이름)
CHIPS = {"TLV271": ("tlv271", "TLV271.PDF", "tlv271"), "OPA2376": ("opa376", "OPA2376.pdf", "opa2376"),
         "OPA320": ("opa320", "OPA320.pdf", "opa320"), "MCP6441": ("mcp6441", "MCP6441.pdf", "mcp6441")}
# 방식: (하네스 기록, 고르기 결과 파일, 고르기 규칙, 메모, 설명)
ARMS = {"C": ("arm_c_runs.json", "_dev", "v1", "기본 고르기", "통과 항목 수 -> 공급 전류 순으로 고름 (규칙 v1)"),
        "C3": ("arm_c3_runs.json", "_v3", "v3", "이득 우선 고르기", "목표 이득이 높으면 이득 노드 2개 이상인 구조 먼저 (규칙 v3)")}
HARNESS_NOTE = "2026-11-22 비교 실험 때 결과 (시뮬레이터 LTspice판, 반복 5번). 지금 UI 의 하네스는 ngspice판."
FAIL_NOTE = {"OPA320": "원래 시스템 오류로 중단: HKG 에 숫자 기호가 있어 .lower() 에서 멈춤 (ngspice판에서 고침)"}


def main() -> None:
    sys.path.insert(0, str(HERE))
    import pipeline
    import rank_v2
    for old in (HERE / "runs").glob("20261122_compare_*"):      # 예전 이름 형식으로 만든 폴더
        shutil.rmtree(old)
    for arm, (record_file, sel_suffix, rule, memo, arm_text) in ARMS.items():
        records = {name_key(r["pdf"]): r
                   for r in json.loads((COMPARE / record_file).read_text(encoding="utf-8"))}
        for chip, (key, pdf_name, cache) in CHIPS.items():
            started = records.get(name_key(pdf_name), {}).get("started") or "2026-11-22 00:00:00"
            run_dir = HERE / "runs" / f"{started[:10].replace('-', '')}_{started[11:].replace(':', '')}_{chip.lower()}"
            shutil.rmtree(run_dir, ignore_errors=True)
            run_dir.mkdir(parents=True)
            (run_dir / "input.json").write_text(json.dumps(
                {"title": chip, "memo": memo, "name": f"cmp_{key}", "pdf_name": pdf_name,
                 "imported_from": "비교 실험 2026-11-22"}, ensure_ascii=False, indent=1), encoding="utf-8")
            shutil.copyfile(find_file(COMPARE / "pdfs", pdf_name), run_dir / "datasheet.pdf")
            shutil.copyfile(HKG_CACHE / f"{cache}_hkg.json", run_dir / "hkg.json")
            write_pages_and_pdg(run_dir)
            shutil.copyfile(HERE / f"spec_cmp_{key}.json", run_dir / "spec.json")
            shutil.copyfile(HERE / "data" / "train" / f"cmp_{key}.json", run_dir / "model_input.json")
            shutil.copyfile(HERE / "data" / "train" / f"cmp_{key}_candidates.json", run_dir / "candidates.json")
            shutil.copyfile(HERE / "data" / f"selection_cmp_{key}_dev.json", run_dir / "selection_dev.json")
            shutil.copyfile(HERE / "data" / f"selection_cmp_{key}{sel_suffix}.json", run_dir / "selection.json")
            run = pipeline.Run(run_dir)
            run.status["started"] = started
            run.status["note"] = f"2026-11-22 비교 실험 결과를 불러옴. 고르기: {arm_text}"
            summaries = {}
            hkg, spec = run.read("hkg.json"), run.read("spec.json")
            summaries["extract"] = {"part": hkg["ic_device"].get("name"), "rows": len(hkg["electrical_parameters"]),
                                    "pins": len(hkg["pins"]), "judged": len(spec["specs"]),
                                    "model_input": run.read("model_input.json")["input"]}
            cands = run.read("candidates.json")["candidates"]
            ok = [c for c in cands if not c["problems"]]
            summaries["candidates"] = {"total": len(cands), "rule_ok": len(ok), "new": sum(not c["in_train"] for c in ok)}
            entries = run.read("selection_dev.json")["entries"]
            working = [e for e in entries if e.get("best")]
            summaries["select"] = {"evaluated": len(entries), "working": len(working),
                                   "best_passed": max((f"{e['best']['passed']}/{e['best']['judged']}" for e in working), default=None)}
            sel = run.read("selection.json")
            top = rank_v2.ranked(run.read("selection_dev.json"), rule)
            chosen_index = sel["summary"]["selected"]
            top = [r for r in top if r["index"] == chosen_index] + [r for r in top if r["index"] != chosen_index]
            keep = ("index", "passed", "judged", "scale", "gain_nodes", "input_ok", "avd", "shortfall")
            summaries["rank"] = {"rule": rule, "top": [{k: r[k] for k in keep} for r in top[:5]]}
            entry = sel["entries"][chosen_index]
            v = next(x for x in entry["variants"] if x["valid"] and x["output_scale"] == entry["best"]["output_scale"])
            final = {"label": "모델 구조 그대로 (그때는 규칙 단계가 없었음)", "rules": [], "table": entry["table"],
                     "output_scale": v["output_scale"], "subckt": v["subckt"], "sizes": v.get("sizes"), "bias": v.get("bias"),
                     "spec": v["spec"], "passed": v["passed"], "judged": v["judged"],
                     "tried": [{"label": "모델 구조 그대로 (그때는 규칙 단계가 없었음)", "scale": v["output_scale"], "valid": True,
                                "reason": "", "passed": v["passed"], "judged": v["judged"], "spec": v["spec"]}]}
            (run_dir / "final.json").write_text(json.dumps(final, ensure_ascii=False, indent=1), encoding="utf-8")
            summaries["rules"] = {"chosen": final["label"], "passed": f"{v['passed']}/{v['judged']}", "tried": 1}
            harness_state, harness_error = import_harness(run_dir, chip, arm, records.get(name_key(pdf_name)) or {})
            for step in run.status["steps"]:
                step.update(state="done", summary=summaries.get(step["key"]), seconds=None)
            hs = run.step("harness")
            if harness_state == "fail":
                hs.update(state="fail", error=harness_error, summary=None)
            else:
                result = run.read("harness/result.json")
                hs["summary"] = {"pass_rate": result.get("pass_rate_percent"), "iterations": result.get("iterations_count"),
                                 "has_netlist": bool(result.get("final_netlist"))}
            sc = run.step("schematic")
            try:
                sc["summary"] = pipeline.step_schematic(run)
            except Exception as error:
                sc.update(state="fail", error=f"{type(error).__name__}: {error}")
            run.status["state"] = "done"
            run.save()
            print(f"{run_dir.name}: 하네스 {hs.get('summary') or hs.get('error')}", flush=True)


def write_pages_and_pdg(run_dir: Path) -> None:
    """쪽별 원문(로컬 글자 읽기, API 없음)과 PDG. 그때 추출 때의 쪽 원문은 남아 있지 않아서 로컬로 다시 읽는다."""
    import extract_datasheet
    sys.path.insert(0, str(extract_datasheet.AV_DIR))
    from ai_analog_designer.pdf_to_graph.pdf_parser import PDFDatasheetParser
    parsed = PDFDatasheetParser(use_nemotron=False).parse_pdf(str(run_dir / "datasheet.pdf"))
    (run_dir / "pages.json").write_text(json.dumps({str(k): v for k, v in PDFDatasheetParser.audit_pages(parsed).items()},
                                                   ensure_ascii=False), encoding="utf-8")
    extract_datasheet.build_pdg(run_dir / "hkg.json", run_dir, log=lambda m: None, pages_file=run_dir / "pages.json")


def import_harness(run_dir: Path, chip: str, arm: str, record: dict) -> tuple:
    """그때 하네스 결과 -> harness/result.json. 중단된 실행은 ('fail', 이유)."""
    out = run_dir / "harness"
    out.mkdir(exist_ok=True)
    seed = COMPARE / f"seeds_{arm}" / "operational_amplifier" / f"EDAI_{arm}_{chip}" / "EXPERIENCE.json"
    pin_map = {}
    if seed.exists():
        exp = json.loads(seed.read_text(encoding="utf-8"))
        shutil.copyfile(seed, out / "blueprint.json")
        pin_map = {k: v for k, v in (exp.get("evidence", {}).get("pin_map") or {}).items() if isinstance(v, str)}
    task_dir = HARNESS_OUT / str(record.get("task_id"))
    if record.get("status") != "completed":
        return "fail", FAIL_NOTE.get(chip, record.get("error") or "하네스 실행 실패")
    summary_file = find_file(task_dir, "*_design_summary.json")
    summary = json.loads(summary_file.read_text(encoding="utf-8")) if summary_file else {}
    netlist = ""
    for path in find_files(task_dir, "*.cir"):
        name = path.name.lower()
        if "final_hermes_harness2" in name and not name.endswith("_dyn.cir"):
            netlist = path.read_text(encoding="utf-8", errors="ignore")
            break
    iterations = [{"iteration": it.get("iteration"), "pass_rate_percent": it.get("pass_rate_percent")}
                  for it in summary.get("iterations") or [] if isinstance(it, dict)]
    result = {"pass_rate_percent": record.get("pass_rate_percent"), "part_name": summary.get("part_name"),
              "iterations_count": record.get("iterations_count") or len(iterations), "iterations": iterations,
              "final_netlist": netlist, "pin_map": pin_map, "seconds": record.get("seconds"), "note": HARNESS_NOTE,
              "task_id": record.get("task_id")}
    (out / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    for f in find_files(task_dir, "*_spec_evaluation.json"):
        shutil.copyfile(f, out / f.name)
    return "done", None


if __name__ == "__main__":
    main()
