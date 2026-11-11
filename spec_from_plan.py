"""
데이터시트 분석 시스템 결과물(팀원 analogverifier)의 측정 계획(spec_planner)으로 판정 항목과 목표값을 정한다.

spec_from_hkg.py 는 우리가 정해 둔 15개 항목에 맞는 줄을 찾아 넣었다. 이 스크립트는 반대로
팀원 측정 계획이 "이 부품은 이것을 잰다"고 정한 줄(status 가 PLANNED/NO_FIXTURE 등 fixture 가 있는 줄)에서 시작한다.

입력
    *_SPEC_EVALUATION.json : 측정 계획 결과. 줄마다 측정 종류(fixture 앞부분 = kind), 단위를 맞춘 목표값
                             (min/typ/max_target), 조건, 온도 범위 메모(note)
    *_knowledge_graph.json : 같은 순서의 추출 결과. 쪽 번호와 근거 글을 붙이는 데 쓴다

고르는 규칙
    1. 부품 구간: 같은 데이터시트에 여러 부품(LM2904B, LM358, LM158 ...)이 있으므로, 부품 이름이 처음
       나오는 줄부터 다른 부품 이름이 나오는 줄 전까지만 쓴다. 같은 구간의 다른 등급(예: LM358BA) 줄은 뺀다
    2. 25°C 줄만: 온도 범위 줄(note 가 Full-temperature...)은 뺀다
    3. 측정 종류(kind) -> 우리 측정 항목. 우리가 아직 못 재는 종류는 이유와 함께 "계획에 있으나 측정 없음"으로 남긴다
    4. 계획에 없는 우리 항목(정착시간, 이득여유)은 판정하지 않는다

사용법:
    python spec_from_plan.py data/extraction/LM358B_SPEC_EVALUATION.json data/extraction/LM358B_knowledge_graph.json LM358B lm358
결과: spec_lm358.json (판정 기준), data/train/lm358.json (모델 입력 문장)
"""

import json
import re
import sys
from pathlib import Path

import spec_from_hkg

HERE = Path(__file__).resolve().parent
TEST_SUPPLY = spec_from_hkg.TEST_SUPPLY
TEMPLATE_SPEC = spec_from_hkg.TEMPLATE_SPEC
PART_NAME = re.compile(r"\b(LM\d{3,4}[A-Z]*|TL[V]?\d{3,4}[A-Z]*|OPA\d+[A-Z]*)\b")
TEMPERATURE_NOTE = "Full-temperature"
CURRENT_IN_COND = re.compile(r"I\s*OUT\s*=\s*(\d+\.?\d*)\s*([mµu]?)A", re.I)

# 측정 종류 -> 우리 측정을 못 하는 이유
NOT_MEASURED = {
    "vos": "입력 오프셋 전압: 소자 편차 통계 해석이 필요해 아직 재지 않음",
    "ib": "입력 바이어스 전류: MOS 입력이라 시뮬레이션에서 거의 0이 되어 의미 없음",
    "ios": "입력 오프셋 전류: MOS 입력이라 시뮬레이션에서 거의 0이 되어 의미 없음",
    "en": "입력 잡음 밀도: 잡음 해석(.noise) 측정을 아직 만들지 않음",
    "isc": "단락 전류: ±10 V 전원 조건이라 6 V 소자로 잴 수 없음",
}


def measure_of(kind: str, row: dict):
    """측정 계획 한 줄 -> 우리 측정 항목 이름 (없으면 None 과 이유)."""
    text = f"{row['name']} {row.get('conditions') or ''}"
    if kind == "aol_db":
        return "avd", None
    if kind == "cmrr_db":
        return "cmrr", None
    if kind == "psrr_db":
        return "psrr", None
    if kind == "iq":
        return "idd", None
    if kind == "gbw":
        return "ugbw", None
    if kind in ("sr", "pm"):
        return kind, None
    if kind == "vswing":
        m = CURRENT_IN_COND.search(text)
        if not m:
            return None, "출력 스윙: 부하 전류 조건이 없어 우리 측정과 맞지 않음"
        amps = float(m.group(1)) * {"m": 1e-3, "µ": 1e-6, "u": 1e-6, "": 1}[m.group(2)]
        side = "voh" if re.search(r"positive|V\+", text, re.I) else "vol" if re.search(r"negative|V-|V–", text, re.I) else None
        tag = {1e-3: "1ma", 5e-3: "5ma"}.get(round(amps, 6))
        if side and tag:
            return f"{side}_{tag}", None
        return None, f"출력 스윙 ({m.group(0)}): 우리는 1 mA, 5 mA 부하만 잼"
    if kind == "iout":
        if re.search(r"source", text, re.I):
            return "io_source", None
        if re.search(r"sink", text, re.I) and not re.search(r"200\s*mV", text):
            return "io_sink", None
        return None, "출력 전류 (출력 200 mV): 우리 측정 조건과 다름"
    return None, NOT_MEASURED.get(kind, f"{kind}: 우리 측정에 없는 종류")


def to_ours(measure: str, row: dict):
    """측정 계획의 목표값(단위 정리됨) -> 우리 단위의 (min, typ, max)."""
    lo, typ, hi = row["min_target"], row["typ_target"], row["max_target"]
    if measure == "idd":
        return tuple(None if v is None else v * 1e6 for v in (lo, typ, hi))
    if measure == "ugbw":
        return tuple(None if v is None else v * 1e-6 for v in (lo, typ, hi))
    if measure in ("io_source", "io_sink"):
        mags = [None if v is None else abs(v) * 1e3 for v in (lo, typ, hi)]
        return mags[0], mags[1], mags[2]
    if measure.startswith("voh"):
        # 레일에서 떨어지는 폭: 최대 폭 -> 최소 VOH
        return (None if hi is None else TEST_SUPPLY - hi, None if typ is None else TEST_SUPPLY - typ,
                None if lo is None else TEST_SUPPLY - lo)
    return lo, typ, hi


def part_rows(rows: list, part: str) -> range:
    """부품 이름이 처음 나오는 줄부터 다른 부품 이름이 나오는 줄 전까지."""
    def names(r):
        return set(PART_NAME.findall(r.get("conditions") or ""))
    electrical = [i for i, r in enumerate(rows) if str(r.get("category", "")).upper() == "ELECTRICAL"]
    start = next(i for i in electrical if part in names(rows[i]))
    family = part.rstrip("ABCDEFGHIJKLMNOPQRSTUVWXYZ")       # LM358B -> LM358
    end = len(rows)
    for i in range(start, len(rows)):
        if str(rows[i].get("category", "")).upper() != "ELECTRICAL" or any(not n.startswith(family) for n in names(rows[i])):
            end = i
            break
    return range(start, end)


def build(plan: dict, hkg: dict, part: str) -> dict:
    rows, extracted = plan["spec_evaluations"], hkg["electrical_parameters"]
    template = {s["measure"]: s for s in json.loads(TEMPLATE_SPEC.read_text(encoding="utf-8"))["specs"]}
    section = part_rows(rows, part)
    specs, missing, seen = [], [], set()
    planned = [i for i in section if rows[i].get("fixture")]
    for i in planned:
        row = rows[i]
        named = set(PART_NAME.findall(row.get("conditions") or ""))
        if (named and part not in named) or (row.get("note") or "").startswith(TEMPERATURE_NOTE):
            continue
        kind = row["fixture"].rsplit("_", 1)[0]
        source = extracted[i]
        evidence = {k: source.get(k) for k in ("symbol", "name", "min", "typ", "max", "unit", "test_conditions", "page", "evidence")}
        measure, reason = measure_of(kind, row)
        if measure is None:
            missing.append({"kind": kind, "symbol": row["symbol"], "name": row["name"], "condition": row.get("conditions"),
                            "min": row["min_target"], "typ": row["typ_target"], "max": row["max_target"],
                            "unit": row["unit"], "page": source.get("page"), "reason": reason})
            continue
        if measure in seen:
            continue
        seen.add(measure)
        base = template[measure]
        item = {k: base[k] for k in ("measure", "label", "unit", "scale", "plain", "headline") if k in base}
        low, typ, high = (spec_from_hkg.rounded(v) for v in to_ours(measure, row))
        item.update({k: v for k, v in (("min", low), ("typ", typ), ("max", high)) if v is not None})
        if low is None and high is None:
            item["typ_rule"] = "higher"
        item.update(symbol=row["symbol"], condition=row.get("conditions"), extracted=evidence,
                    plan={"kind": kind, "fixture": row["fixture"], "row": i})
        specs.append(item)
    order = list(template)
    specs.sort(key=lambda s: order.index(s["measure"]))
    not_planned = [m for m in ("ts", "gm", "vol_5ma") if m not in seen]
    device = hkg.get("ic_device", {})
    return {"description": f"{part} 측정 계획(팀원 spec_planner 결과)에서 판정 항목과 목표값을 가져온 것 (spec_from_plan.py 가 만듦)",
            "circuit": "opamp", "source": part, "category": device.get("category"),
            "conditions": f"VDD = {TEST_SUPPLY:g} V 단일 전원 (공통 측정 조건). 계획의 측정 전원(예: 15 V)과 다를 수 있음",
            "typ_rule": spec_from_hkg.TEAM_RULE, "specs": specs,
            "extraction": {"total_rows": len(extracted), "electrical_rows": len(spec_from_hkg.electrical(extracted)),
                           "used_rows": len(specs), "pins": len(hkg.get("pins", [])), "file": None},
            "plan": {"file": None, "planned_rows": sum(1 for r in rows if r.get("fixture")),
                     "part_rows": [section.start, section.stop], "part_planned": len(planned),
                     "used": len(specs), "not_measured": missing,
                     "not_planned": [{"measure": m, "label": template[m]["label"],
                                      "reason": "측정 계획에 없음 (계획이 이 데이터시트 줄을 측정 대상으로 정하지 않음)"} for m in not_planned]},
            "unused": []}


def main() -> None:
    plan_file, hkg_file, part, name = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3], sys.argv[4]
    spec = build(json.loads(plan_file.read_text(encoding="utf-8")), json.loads(hkg_file.read_text(encoding="utf-8")), part)
    spec["extraction"]["file"] = hkg_file.name
    spec["plan"]["file"] = plan_file.name
    (HERE / f"spec_{name}.json").write_text(json.dumps(spec, ensure_ascii=False, indent=1), encoding="utf-8")
    sentence = spec_from_hkg.model_input(spec)
    (HERE / "data" / "train" / f"{name}.json").write_text(json.dumps(sentence, ensure_ascii=False, indent=1), encoding="utf-8")
    p = spec["plan"]
    print(f"측정 계획 {p['planned_rows']}줄 중 {part} 구간(줄 {p['part_rows'][0]}~{p['part_rows'][1] - 1}) {p['part_planned']}줄 -> 판정 항목 {p['used']}개")
    for s in spec["specs"]:
        print(f"  {s['measure']:10s} {s.get('min')} / {s.get('typ')} / {s.get('max')} {s['unit']}   <- {s['plan']['kind']} p.{s['extracted'].get('page')}")
    print("계획에 있으나 측정 없음:")
    for m in p["not_measured"]:
        print(f"  {m['kind']:8s} {m['symbol']:6s} {m['reason']}")
    print("계획에 없어 판정 안 함:", [m["measure"] for m in p["not_planned"]])
    print("모델 입력:", sentence["input"])


if __name__ == "__main__":
    main()
