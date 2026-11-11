"""
데이터시트 -> 구조 선택 과정을 페이지로 만든다.

보여주는 것
    0. 추출      : 데이터시트 추출 결과(있으면)와 OP-Amp 공통 측정 항목으로 옮긴 결과
    1. 입력      : 스펙 항목
    2. 구조 생성 : FLAN-T5 학습 데이터, 검증 결과, 후보 생성 방법
    3. 후보      : 후보마다 규칙 검사 -> 크기 정하기 -> 동작 판정 -> 스펙 판정 결과
    4. 선택      : 통과 항목 수 순위, 고른 구조의 소자 표와 항목별 판정

사용법 (프로젝트 폴더에서, select_structure.py, selection_curves.py, make_schematic_svg.py 를 돌린 뒤):
    python make_selection_page.py lm358      (부품을 빼면 tlv271)
결과: docs/selection_<부품>.html (자세히 보기), docs/story_<부품>.html (영상처럼 넘어가는 설명)
화면 모양은 docs/*_template.html 에서 고친다. 결과 html 은 다시 만들면 덮어써진다.
"""

import json
from pathlib import Path

import make_train_data
import run_sim

HERE = Path(__file__).resolve().parent
TRAIN_DIR = HERE / "data" / "train"
DEFAULT_PART = "tlv271"
# (화면 틀, 결과 파일 이름 형식): 자세히 보는 페이지와 영상처럼 넘어가는 설명 페이지
PAGES = ((HERE / "docs" / "selection_page_template.html", "selection_{part}.html"),
         (HERE / "docs" / "selection_story_template.html", "story_{part}.html"))
DATA_MARK = "/*DATA*/null"
GENERATED = {"beam": 10, "sample": 30}   # 후보 파일에 generated 가 없을 때 (Colab 노트북 8번 셀 값)
UNUSED_SHOWN = 40                         # 화면에 보여줄 '쓰지 않는 추출 줄' 수


def read_jsonl(path: Path) -> list:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def train_stats() -> dict:
    train, val = read_jsonl(TRAIN_DIR / "train.jsonl"), read_jsonl(TRAIN_DIR / "val.jsonl")
    # 설명용 학습 예시 하나: 항목이 가장 많은 문장 중 정답이 가장 짧은 것
    most = max(r["input"].count(";") for r in train)
    example = min((r for r in train if r["input"].count(";") == most), key=lambda r: len(r["target"]))
    return {"train": len(train), "val": len(val), "example": {"input": example["input"], "target": example["target"]},
            "structures": len({r["target"] for r in train + val}),
            "val_structures": len({r["target"] for r in val})}


def spec_items(spec: dict) -> list:
    """화면에 쓸 스펙 항목: 이름, 쉬운 설명, 목표 글, 추출 원문."""
    items = []
    for s in spec["specs"]:
        if s.get("scope") == "excluded":
            continue
        low, high, unit = s.get("min"), s.get("max"), s["unit"]
        if low is not None and high is not None:
            target = f"{low} ~ {high} {unit}"
        elif low is not None:
            target = f"≥ {low} {unit}"
        elif high is not None:
            target = f"≤ {high} {unit}"
        else:
            target = f"참고 {s.get('typ')} {unit}"
        items.append({"measure": s["measure"], "symbol": s.get("symbol", s["measure"]), "label": s["label"],
                      "plain": s.get("plain", ""), "unit": unit, "target": target, "min": low, "max": high,
                      "extracted": s.get("extracted")})
    return items


def extraction_view(spec: dict) -> dict:
    """데이터시트 추출 결과 요약. 추출 결과로 만든 스펙이 아니면 None."""
    info = spec.get("extraction")
    if not info:
        return None
    hkg = json.loads((HERE / "data" / "extraction" / info["file"]).read_text(encoding="utf-8"))
    rows = hkg["electrical_parameters"]
    categories = {}
    for r in rows:
        key = str(r.get("category") or "기타")
        categories[key] = categories.get(key, 0) + 1
    return {"file": info["file"], "device": hkg.get("ic_device", {}),
            "pins": [{k: p.get(k) for k in ("name", "pin_number", "direction", "role", "description")} for p in hkg.get("pins", [])],
            "total_rows": len(rows), "categories": categories, "electrical_rows": info["electrical_rows"],
            "used_rows": info["used_rows"], "missing": [s["label"] for s in spec["specs"] if s.get("scope") == "excluded"],
            "unused": spec.get("unused", [])[:UNUSED_SHOWN], "unused_count": len(spec.get("unused", []))}


def pdg_view(part: str):
    """pdg_check.py 결과 (핀 그래프와 OP-Amp 5단자 확인). 없으면 None."""
    path = HERE / "data" / f"pdg_{part}.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def schematics(part: str) -> dict:
    """netlistsvg 로 만든 회로도 {후보 번호(0부터): svg 글}."""
    folder = HERE / "data" / "schematics" / part
    return {str(int(f.stem.split("_")[1]) - 1): f.read_text(encoding="utf-8") for f in sorted(folder.glob("candidate_*.svg"))}


def parse_rows(text: str) -> list:
    """모델이 쓴 한 줄 글 -> [[소자 이름, {단자: 노드}]]. 형식이 이상한 조각은 글 그대로 둔다."""
    rows = []
    for part in text.split(";"):
        tokens = part.split()
        if tokens:
            rows.append([tokens[0], dict(t.split("=", 1) for t in tokens[1:] if "=" in t)])
    return rows


def training_structures(spec: dict) -> list:
    """학습에 쓴 구조마다: 이름, 줄 집합, 이 부품 스펙 항목별 값과 통과 수 (출력단 배율 중 더 좋은 쪽)."""
    best = {}
    for row in make_train_data.load_rows():
        judged = [r for r in run_sim.judge(row["measured"], spec)
                  if r["status"] in (run_sim.STATUS_PASS, run_sim.STATUS_FAIL, run_sim.STATUS_UNMEASURED)]
        passed = sum(r["status"] == run_sim.STATUS_PASS for r in judged)
        if row["target"] not in best or passed > best[row["target"]]["passed"]:
            best[row["target"]] = {"name": row["structure"], "source": row["source"], "passed": passed,
                                   "values": {r["measure"]: r["value"] for r in judged}}
    return [dict(info, rows=set(row_texts(target))) for target, info in best.items()]


def row_texts(text: str) -> list:
    return [" ".join(part.split()) for part in text.split(";") if part.strip()]


def nearest(text: str, structures: list) -> dict:
    """줄(소자 연결)이 가장 많이 겹치는 학습 구조와, 후보에만 있는 줄·학습 구조에만 있는 줄."""
    rows = set(row_texts(text))
    match = max(structures, key=lambda s: len(rows & s["rows"]) / len(rows | s["rows"]))
    return {"name": match["name"], "source": match["source"], "passed": match["passed"],
            "same": len(rows & match["rows"]), "added": sorted(rows - match["rows"]),
            "removed": sorted(match["rows"] - rows)}


def variant_view(variant: dict) -> dict:
    keep = ("output_scale", "valid", "reason", "passed", "judged", "sizes", "subckt", "seconds",
            "off", "triode", "startup")
    view = {k: variant.get(k) for k in keep}
    view["idd"] = (variant.get("measured") or {}).get("idd")
    view["spec"] = [{"measure": r["measure"], "value": r["value"], "status": r["status"]}
                    for r in variant.get("spec") or []]
    return view


def main() -> None:
    import sys
    part = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_PART
    candidates = json.loads((TRAIN_DIR / f"{part}_candidates.json").read_text(encoding="utf-8"))
    selection_file = HERE / "data" / f"selection_{part}.json"
    selection = json.loads(selection_file.read_text(encoding="utf-8")) if selection_file.exists() else {}
    done = selection.get("entries", [])
    spec = run_sim.load_spec(HERE / f"spec_{part}.json")
    structures = training_structures(spec)
    curve_file = HERE / "data" / f"selection_{part}_curves.json"
    curves = json.loads(curve_file.read_text(encoding="utf-8")) if curve_file.exists() else {}
    drawings = schematics(part)
    entries = []
    for number, candidate in enumerate(candidates["candidates"]):
        entry = {"no": number + 1, "how": candidate["how"], "in_train": candidate["in_train"],
                 "rows": parse_rows(candidate["table"]), "nearest": nearest(candidate["table"], structures),
                 "curves": curves.get(str(number)), "schematic": drawings.get(str(number))}
        if number < len(done):
            result = done[number]
            entry.update(state="done", rules=result["steps"]["rules"], best=result.get("best"),
                         variants=[variant_view(v) for v in result["variants"]])
        else:
            entry.update(state="waiting", rules={"ok": not candidate["problems"], "problems": candidate["problems"]})
        entries.append(entry)
    data = {"model": candidates["model"], "epochs": candidates["epochs"], "input": candidates["input"],
            "eval": candidates["eval"], "eval_count": candidates["eval_count"],
            "generated": candidates.get("generated", GENERATED), "part": part.upper(), "source": spec.get("source"),
            "extraction": extraction_view(spec), "pdg": pdg_view(part), "train": train_stats(), "spec": spec_items(spec), "entries": entries,
            "summary": selection.get("summary"), "evaluated": len(done),
            "training": [{"name": t["name"], "source": t["source"], "passed": t["passed"], "values": t["values"]}
                         for t in structures]}
    payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    for template, name in PAGES:
        out = HERE / "docs" / name.format(part=part)
        if template.exists():
            out.write_text(template.read_text(encoding="utf-8").replace(DATA_MARK, payload), encoding="utf-8")
            print(f"후보 {len(entries)}개 중 {len(done)}개 평가됨 -> {out.relative_to(HERE)}")


if __name__ == "__main__":
    main()
