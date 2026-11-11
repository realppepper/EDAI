"""
FLAN-T5 가 만든 TLV271 후보 구조를 하나씩 검사하고, 크기를 정하고, 시뮬레이션으로 판정해 하나를 고른다.

단계 (후보마다)
    1. 규칙 검사   : 표 형식, 입출력·전원 단자, 입력이 게이트에 붙는지, 한 곳에만 붙은 노드
    2. 크기 정하기 : auto_size (출력단 전류 배율 label_dataset.VARIANTS 마다)
    3. 동작 판정   : label_dataset.judge (출력 VDD/2 근처, 포화 영역, 무부하 이득)
    4. 스펙 판정   : run_sim.judge 로 TLV271 15개 항목 PASS/FAIL
    5. 순위        : 통과 항목 수가 많은 순, 같으면 공급 전류가 작은 순
결과: data/selection_<부품>.json  (단계별 기록. 화면이 이 파일을 읽어 과정을 보여준다)

사용법 (WSL, 프로젝트 폴더에서):
    ~/.venvs/edai/bin/python select_structure.py            # tlv271: data/train/tlv271_candidates.json, spec_tlv271.json
    ~/.venvs/edai/bin/python select_structure.py lm358      # data/train/lm358_candidates.json, spec_lm358.json
"""

import json
import sys
import time
from collections import Counter
from pathlib import Path

import label_dataset
import netlist_table as nt
import run_sim

HERE = Path(__file__).resolve().parent
DEFAULT_PART = "tlv271"
ROW_SEP = ";"
PORTS = ("VDD", "VSS", "IN1", "IN2", "OUT")


def to_table(text: str) -> dict:
    """모델이 쓴 한 줄 글 -> 구조 표. 형식이 틀리면 ValueError."""
    return nt.parse_table_text("\n".join(part.strip() for part in text.split(ROW_SEP) if part.strip()))


def rule_problems(table: dict) -> list:
    """시뮬레이션 전에 걸러낼 문제 목록 (Colab 노트북의 검사와 같은 규칙)."""
    found = []
    names = [row["name"] for row in table["rows"]]
    if len(set(names)) != len(names):
        found.append("같은 이름의 소자가 있음")
    count = Counter(net for row in table["rows"] for net in row["pins"].values())
    found += [f"{port} 단자가 없음" for port in PORTS if port not in count]
    gates = {row["pins"].get("G") for row in table["rows"]}
    found += [f"{port} 가 트랜지스터 게이트에 붙지 않음" for port in ("IN1", "IN2") if port not in gates]
    floating = [net for net, n in count.items() if n < 2 and net not in PORTS and not net.startswith(("VB", "IB"))]
    if floating:
        found.append(f"한 곳에만 붙은 노드: {', '.join(floating)}")
    return found


def spec_rows(measured: dict, spec: dict) -> list:
    """TLV271 목표 항목마다 판정. 재지 못한 항목(예: 이득이 낮아 대역폭이 없음)도 넣어 후보끼리 분모를 같게 한다."""
    rows = run_sim.judge(measured, spec)
    kept = (run_sim.STATUS_PASS, run_sim.STATUS_FAIL, run_sim.STATUS_UNMEASURED)
    return [{"measure": r["measure"], "label": r["label"], "unit": r["unit"], "value": r["value"],
             "target": run_sim.target_text(r), "status": r["status"]}
            for r in rows if r["status"] in kept]


# 구조 선택에서 해 보는 (전류원 전류, 출력단 배율). 학습 데이터(label_dataset.VARIANTS)는 1배·5배만 썼지만,
# 데이터시트 부품은 출력 전류가 mA 단위라 선택할 때는 출력단을 더 크게도 해 본다.
EXTRA_SCALES = (20.0, 50.0)
SELECT_VARIANTS = tuple(label_dataset.VARIANTS) + tuple((label_dataset.VARIANTS[0][0], s) for s in EXTRA_SCALES)


def evaluate_variant(table: dict, unit_current: float, output_scale: float, spec: dict) -> dict:
    """크기 정하기 한 번과 스펙 판정."""
    record = label_dataset.label(table, None, unit_current, output_scale)
    variant = {"output_scale": output_scale, "op_ok": record["op_ok"], "valid": record["valid"],
               "reason": record["reason"], "off": record.get("off"), "triode": record.get("triode"),
               "startup": record.get("startup"), "sizes": record.get("sizes"), "subckt": record.get("subckt"),
               "seconds": record["seconds"]}
    if record["valid"]:
        rows = spec_rows(record["measured"], spec)
        variant.update(measured=record["measured"], spec=rows,
                       passed=sum(r["status"] == run_sim.STATUS_PASS for r in rows), judged=len(rows))
    return variant


def finish_entry(entry: dict) -> dict:
    """변형들 중 가장 좋은 것을 best 로."""
    working = [v for v in entry["variants"] if v["valid"]]
    entry["steps"]["sizing"] = {"ok": bool(working),
                                "reasons": [v["reason"] for v in entry["variants"] if not v["valid"]]}
    entry.pop("best", None)
    if working:
        best = max(working, key=rank_key)
        entry["best"] = {"output_scale": best["output_scale"], "passed": best["passed"], "judged": best["judged"],
                         "idd": best["measured"].get("idd")}
    return entry


def evaluate_candidate(candidate: dict, spec: dict) -> dict:
    """후보 하나를 1~4단계로 평가한 기록."""
    entry = {"how": candidate.get("how"), "in_train": candidate.get("in_train"), "table": candidate["table"],
             "steps": {}, "variants": []}
    try:
        table = to_table(candidate["table"])
    except ValueError as error:
        entry["steps"]["rules"] = {"ok": False, "problems": [f"형식: {error}"]}
        return entry
    problems = rule_problems(table)
    entry["steps"]["rules"] = {"ok": not problems, "problems": problems,
                               "transistors": sum(r["kind"] in ("nmos", "pmos") for r in table["rows"])}
    if problems:
        return entry
    for unit_current, output_scale in SELECT_VARIANTS:
        entry["variants"].append(evaluate_variant(table, unit_current, output_scale, spec))
    return finish_entry(entry)


def add_scales(part: str) -> None:
    """이미 판정한 결과에 빠진 출력단 배율만 더 돌려 합친다 (처음부터 다시 돌리지 않음)."""
    out_file = HERE / "data" / f"selection_{part}.json"
    result = json.loads(out_file.read_text(encoding="utf-8"))
    spec = run_sim.load_spec(HERE / f"spec_{part}.json")
    started = time.time()
    for number, entry in enumerate(result["entries"], 1):
        if not entry["steps"]["rules"]["ok"]:
            continue
        table = to_table(entry["table"])
        have = {v["output_scale"] for v in entry["variants"]}
        for unit_current, output_scale in SELECT_VARIANTS:
            if output_scale not in have:
                entry["variants"].append(evaluate_variant(table, unit_current, output_scale, spec))
        finish_entry(entry)
        b = entry.get("best")
        print(f"  후보 {number}: " + (f"{b['passed']}/{b['judged']} (출력단 {b['output_scale']:g}배)" if b else "동작 안 함"), flush=True)
        result["summary"] = summarize(result["entries"])
        out_file.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    s = result["summary"]
    print(f"동작 {s['working']} (학습에 없던 구조 {s['new_working']})  {time.time() - started:.0f} s")
    if s["selected"] is not None:
        e = result["entries"][s["selected"]]
        print(f"선택: 후보 {s['selected'] + 1}, {e['best']['passed']}/{e['best']['judged']} 통과 (출력단 {e['best']['output_scale']:g}배)")


def rank_key(variant: dict) -> tuple:
    return (variant["passed"], -(variant["measured"].get("idd") or float("inf")))


def summarize(entries: list) -> dict:
    stats = {"candidates": len(entries),
             "rules_ok": sum(e["steps"]["rules"]["ok"] for e in entries),
             "working": sum(bool(e.get("best")) for e in entries),
             "new_working": sum(bool(e.get("best")) and not e.get("in_train") for e in entries)}
    ranked = sorted((i for i, e in enumerate(entries) if e.get("best")),
                    key=lambda i: (entries[i]["best"]["passed"], -(entries[i]["best"]["idd"] or float("inf"))),
                    reverse=True)
    stats["ranking"] = ranked
    stats["selected"] = ranked[0] if ranked else None
    return stats


def main() -> None:
    part = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_PART
    if "--add-scales" in sys.argv:
        add_scales(part)
        return
    source = HERE / "data" / "train" / f"{part}_candidates.json"
    out_file = HERE / "data" / f"selection_{part}.json"
    data = json.loads(source.read_text(encoding="utf-8"))
    spec = run_sim.load_spec(HERE / f"spec_{part}.json")
    result = {"source": source.name, "model": data.get("model"), "input": data.get("input"),
              "model_eval": data.get("eval"), "entries": []}
    started = time.time()
    for number, candidate in enumerate(data["candidates"], 1):
        entry = evaluate_candidate(candidate, spec)
        result["entries"].append(entry)
        if entry.get("best"):
            note = f"동작, {part.upper()} {entry['best']['passed']}/{entry['best']['judged']} 통과"
        elif not entry["steps"]["rules"]["ok"]:
            note = "규칙 검사 탈락: " + "; ".join(entry["steps"]["rules"]["problems"])[:120]
        else:
            note = "크기 정하기 탈락: " + "; ".join(entry["steps"]["sizing"]["reasons"])[:120]
        print(f"  후보 {number}/{len(data['candidates'])} ({candidate.get('how')}"
              f"{', 학습에 있던 구조' if candidate.get('in_train') else ''}) {note}", flush=True)
        result["summary"] = summarize(result["entries"])
        out_file.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    s = result["summary"]
    print(f"후보 {s['candidates']}개 -> 규칙 통과 {s['rules_ok']} -> 동작 {s['working']} "
          f"(학습에 없던 구조 {s['new_working']})  {time.time() - started:.0f} s")
    if s["selected"] is not None:
        best = result["entries"][s["selected"]]["best"]
        print(f"선택: 후보 {s['selected'] + 1}, {part.upper()} {best['passed']}/{best['judged']} 통과 -> {out_file.name}")


if __name__ == "__main__":
    main()
