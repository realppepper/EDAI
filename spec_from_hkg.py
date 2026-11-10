"""
데이터시트 추출 결과(analogverifier 의 *_knowledge_graph.json)를 우리 스펙 파일과 모델 입력 문장으로 바꾼다.

추출 결과의 electrical_parameters 한 줄: symbol, name, min/typ/max, unit, test_conditions, page, evidence
우리 스펙 파일: spec_tlv271.json 과 같은 형식 (measure, label, unit, scale, min/typ/max, condition ...)

- OP-Amp 공통 측정 항목 15개(make_train_data.spec_items)마다 맞는 줄을 찾아 단위를 바꾼다.
  예) 개방루프 이득 70 V/mV -> 96.9 dB, CMRR 100 µV/V(최대) -> 80 dB(최소), 레일에서 1.48 V(최대) -> VOH 3.52 V(최소)
- 같은 항목이 여러 줄이면 25°C 줄(온도 범위가 적힌 줄이 아닌 것)을 고른다.
- 대응이 없는 항목(오프셋, 잡음 등)은 unused 에 이유와 함께 남긴다. 모델은 이 항목을 쓰지 않는다.

사용법:
    python spec_from_hkg.py data/extraction/LM358B_knowledge_graph.json lm358
결과: spec_lm358.json (판정 기준), data/train/lm358.json (모델 입력 문장)
"""

import json
import math
import re
import sys
from pathlib import Path

import make_train_data

HERE = Path(__file__).resolve().parent
TEMPLATE_SPEC = HERE / "spec_tlv271.json"     # 항목 이름·쉬운 말·단위를 빌려 온다
TEST_SUPPLY = 5.0                             # 공통 측정 조건의 전원 전압 [V]
WIDE_TEMPERATURE = re.compile(r"TA\s*=\s*[-–]\s*\d+")
TEAM_RULE = {"min_ratio": 0.8, "max_ratio": 1.2, "note": "데이터시트가 보장하는 값이 아니라 팀이 정한 기준 (2026-10-12)"}
CURRENT_SCALE = {"a": 1.0, "ma": 1e-3, "ua": 1e-6, "µa": 1e-6, "na": 1e-9}
VOLT_SCALE = {"v": 1.0, "mv": 1e-3, "uv": 1e-6, "µv": 1e-6}


def unit_key(unit: str) -> str:
    return (unit or "").strip().lower().replace("μ", "µ")


def gain_db(value, unit):
    u = unit_key(unit)
    if value is None:
        return None
    if u == "db":
        return value
    ratio = value * (1000 if u == "v/mv" else 1e6 if u == "v/µv" else 1)
    return 20 * math.log10(abs(ratio))


def rejection_db(value, unit):
    """µV/V 같은 비율 -> dB (값이 작을수록 좋으므로 dB 는 클수록 좋다)."""
    u = unit_key(unit)
    if value is None:
        return None
    if u == "db":
        return value
    ratio = value * (1e-6 if u in ("uv/v", "µv/v") else 1e-3 if u == "mv/v" else 1)
    return -20 * math.log10(abs(ratio))


def scaled(value, unit, table):
    if value is None:
        return None
    return abs(value) * table[unit_key(unit)]


# 항목마다: 찾는 조건(기호, 이름, 조건 글)과 값 바꾸기. 바꾸기는 (min, typ, max, 단위) -> (min, typ, max) [우리 단위]
def convert_gain(r):
    return gain_db(r["min"], r["unit"]), gain_db(r["typ"], r["unit"]), gain_db(r["max"], r["unit"])


def convert_rejection(r):
    # 비율의 최대값이 dB 의 최소값이 된다
    return rejection_db(r["max"], r["unit"]), rejection_db(r["typ"], r["unit"]), rejection_db(r["min"], r["unit"])


def convert_current(target):
    def run(r):
        to = 1 / CURRENT_SCALE[target]
        values = [scaled(r[k], r["unit"], CURRENT_SCALE) for k in ("min", "typ", "max")]
        return tuple(None if v is None else v * to for v in values)
    return run


def convert_plain(r):
    return r["min"], r["typ"], r["max"]


def convert_from_upper_rail(r):
    """레일에서 떨어진 거리 -> VOH (거리가 클수록 나쁘므로 최대 거리가 VOH 최소)."""
    d = [scaled(r[k], r["unit"], VOLT_SCALE) for k in ("min", "typ", "max")]
    return (None if d[2] is None else TEST_SUPPLY - d[2], None if d[1] is None else TEST_SUPPLY - d[1],
            None if d[0] is None else TEST_SUPPLY - d[0])


def convert_from_lower_rail(r):
    return tuple(scaled(r[k], r["unit"], VOLT_SCALE) for k in ("min", "typ", "max"))


RULES = {
    "avd": dict(name=r"open[- ]loop (voltage )?gain|large[- ]signal", convert=convert_gain),
    "cmrr": dict(name=r"common[- ]mode rejection", convert=convert_rejection),
    "psrr": dict(name=r"(power )?supply rejection", convert=convert_rejection),
    "idd": dict(name=r"quiescent current|supply current", cond=r"VS\s*=\s*5\s*V|VDD\s*=\s*5", convert=convert_current("µa")),
    "ugbw": dict(name=r"gain[- ]bandwidth|unity[- ]gain bandwidth", convert=convert_plain, typ_rule="higher"),
    "sr": dict(name=r"slew rate", convert=convert_plain, typ_rule="higher"),
    "pm": dict(name=r"phase margin", convert=convert_plain, typ_rule="higher"),
    "gm": dict(name=r"gain margin", convert=convert_plain, typ_rule="higher"),
    "ts": dict(name=r"settling time", convert=convert_plain, typ_rule="lower"),
    "voh_1ma": dict(name=r"swing from rail.*(positive|V\+)|high[- ]level output", cond=r"1\s*mA", convert=convert_from_upper_rail),
    "voh_5ma": dict(name=r"swing from rail.*(positive|V\+)|high[- ]level output", cond=r"5\s*mA", convert=convert_from_upper_rail),
    "vol_1ma": dict(name=r"swing from rail.*(negative|V-)|low[- ]level output", cond=r"1\s*mA", convert=convert_from_lower_rail),
    "vol_5ma": dict(name=r"swing from rail.*(negative|V-)|low[- ]level output", cond=r"5\s*mA", convert=convert_from_lower_rail),
    "io_source": dict(name=r"output current.*source", convert=convert_current("ma"), typ_rule="higher"),
    "io_sink": dict(name=r"output current.*sink", unit=r"^mA$", convert=convert_current("ma"), typ_rule="higher"),
}
UNUSED_REASON = "OP-Amp 공통 측정 항목 15개에 없어 모델 입력에 쓰지 않음"


def electrical(rows: list) -> list:
    return [r for r in rows if str(r.get("category", "")).upper() == "ELECTRICAL"
            and any(r.get(k) is not None for k in ("min", "typ", "max"))]


def find(rows: list, rule: dict):
    """규칙에 맞는 줄 중 25°C 줄을 먼저 고른다."""
    hits = [r for r in rows if re.search(rule["name"], r.get("name", ""), re.I)
            and (not rule.get("cond") or re.search(rule["cond"], r.get("test_conditions") or "", re.I))
            and (not rule.get("unit") or re.search(rule["unit"], r.get("unit") or ""))]
    hits.sort(key=lambda r: bool(WIDE_TEMPERATURE.search(r.get("test_conditions") or "")))
    return hits[0] if hits else None


def rounded(value):
    return None if value is None else float(f"{value:.4g}")


def build(hkg: dict) -> dict:
    template = {s["measure"]: s for s in json.loads(TEMPLATE_SPEC.read_text(encoding="utf-8"))["specs"]}
    rows = electrical(hkg["electrical_parameters"])
    used, specs = set(), []
    for measure, rule in RULES.items():
        row = find(rows, rule)
        base = template[measure]
        item = {k: base[k] for k in ("measure", "label", "unit", "scale", "plain", "headline") if k in base}
        if row is None:
            item.update(scope="excluded", reason="데이터시트(추출 결과)에 이 항목이 없음")
            specs.append(item)
            continue
        used.add(id(row))
        low, typ, high = (rounded(v) for v in rule["convert"](row))
        item.update({k: v for k, v in (("min", low), ("typ", typ), ("max", high)) if v is not None})
        if low is None and high is None and rule.get("typ_rule"):
            item["typ_rule"] = rule["typ_rule"]
        item.update(symbol=row.get("symbol"), condition=row.get("test_conditions"),
                    extracted={k: row.get(k) for k in ("symbol", "name", "min", "typ", "max", "unit", "test_conditions", "page", "evidence")})
        specs.append(item)
    unused = [{k: r.get(k) for k in ("symbol", "name", "min", "typ", "max", "unit", "test_conditions", "page")}
              for r in rows if id(r) not in used]
    device = hkg.get("ic_device", {})
    return {"description": f"{device.get('name')} 데이터시트 추출 결과(analogverifier)를 OP-Amp 공통 측정 항목으로 옮긴 것 (spec_from_hkg.py 가 만듦)",
            "circuit": "opamp", "source": device.get("name"), "category": device.get("category"),
            "conditions": f"VDD = {TEST_SUPPLY:g} V 단일 전원 (공통 측정 조건). 데이터시트 조건과 다를 수 있음",
            "typ_rule": TEAM_RULE, "specs": specs,
            "extraction": {"total_rows": len(hkg["electrical_parameters"]), "electrical_rows": len(rows),
                           "used_rows": len(used), "pins": len(hkg.get("pins", []))},
            "unused": [dict(u, reason=UNUSED_REASON) for u in unused]}


def model_input(spec: dict) -> dict:
    """스펙의 목표값(대표값, 없으면 최소/최대값) -> 모델 입력 문장."""
    values = {}
    for s in spec["specs"]:
        if s.get("scope") == "excluded":
            continue
        value = next((s[k] for k in ("typ", "min", "max") if s.get(k) is not None), None)
        if value is not None:
            values[s["measure"]] = value / s.get("scale", 1.0)
    return {"input": make_train_data.spec_text(values, make_train_data.spec_items()), "values": values}


def main() -> None:
    source, part = Path(sys.argv[1]), sys.argv[2]
    spec = build(json.loads(source.read_text(encoding="utf-8")))
    spec["extraction"]["file"] = source.name
    (HERE / f"spec_{part}.json").write_text(json.dumps(spec, ensure_ascii=False, indent=1), encoding="utf-8")
    sentence = model_input(spec)
    (HERE / "data" / "train" / f"{part}.json").write_text(json.dumps(sentence, ensure_ascii=False, indent=1), encoding="utf-8")
    kept = [s for s in spec["specs"] if s.get("scope") != "excluded"]
    print(f"전기적 특성 {spec['extraction']['electrical_rows']}줄 중 {spec['extraction']['used_rows']}줄 사용 -> 항목 {len(kept)}/15")
    for s in spec["specs"]:
        if s.get("scope") == "excluded":
            print(f"  {s['measure']:10s} 없음")
        else:
            bounds = " ".join(f"{k}={s[k]}" for k in ("min", "typ", "max") if k in s)
            print(f"  {s['measure']:10s} {bounds} {s['unit']}  <- p{s['extracted'].get('page')} {s['extracted']['name']} "
                  f"({s['extracted']['min']}, {s['extracted']['typ']}, {s['extracted']['max']} {s['extracted']['unit']})")
    print("입력 문장:", sentence["input"])


if __name__ == "__main__":
    main()
