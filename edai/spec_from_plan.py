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
    python spec_from_plan.py data/extraction/TL071H_SPEC_EVALUATION.json data/extraction/TL071H_knowledge_graph.json TL071H tl071 \
        --fix data/extraction/TL071H_corrections.json
결과: spec_lm358.json (판정 기준), data/train/lm358.json (모델 입력 문장)

--fix: 추출 결과를 PDF 원문과 대조해 고친 파일. 쓸 줄 구간(section.rows)과 줄별 고친 값(rows)을 담는다.
       고친 줄은 판정 항목에 원래 값과 고친 이유가 함께 남는다.
"""

import json
import os
import re
import sys
from pathlib import Path

import spec_from_hkg

HERE = Path(__file__).resolve().parent
TEST_SUPPLY = spec_from_hkg.TEST_SUPPLY
TEMPLATE_SPEC = spec_from_hkg.TEMPLATE_SPEC
PART_NAME = re.compile(r"\b(LMV?\d{3,4}[A-Z]*|TL[V]?\d{3,4}[A-Z]*|OPA\d+[A-Z]*)\b")
# 판정할 전원 범위: 칩 양 끝 전압(V+ - V-) [V]. 회로를 GF180 6 V 소자·5 V 전원으로 만들고 재므로 그 근처 조건 줄만 쓴다.
# 하네스와 같은 값 (extract_datasheet 가 AV_SUPPLY_BAND_V 로 둠). ±5 V 는 10 V 라 빠진다 (2026-11-27 결정)
DEFAULT_SUPPLY_BAND = (4.5, 5.5)
# 표 제목 하나에 전원이 여러 개 (예: "VDD = 2.7 V, 5 V, and ±5 V") -> 줄마다 어느 전원인지 몰라 쓰지 않는다
LISTED_SUPPLIES = re.compile(r"=\s*±?\d+(?:\.\d+)?\s*V\s*,\s*±?\d")


def supply_band() -> tuple:
    raw = os.environ.get("AV_SUPPLY_BAND_V")
    return tuple(float(x) for x in raw.split(",")) if raw else DEFAULT_SUPPLY_BAND


def supply_range(text: str):
    """조건 글의 칩 양 끝 전압 범위 (아래, 위) [V] 또는 None. 하네스(spec_planner.condition_supply_range)와 같은 읽기:
    'VCC+ = 5 V, VCC- = -5 V' -> (10, 10), 'VS = ±15 V' -> (30, 30), 'VS = 2.7 V to 5.5 V' -> (2.7, 5.5).
    전에는 앞의 '+5 V' 만 보고 5 V 로 읽어 LM6172 의 ±5 V 표 목표를 골랐다 (2026-11-27)."""
    from extract_datasheet import AV_DIR
    if str(AV_DIR) not in sys.path:
        sys.path.insert(0, str(AV_DIR))
    from ai_analog_designer.neuro_symbolic_verifier.spec_planner import condition_supply_range
    return condition_supply_range(text or "")


def in_band(rng) -> bool:
    lo, hi = supply_band()
    return rng[1] >= lo - 1e-9 and rng[0] <= hi + 1e-9


def same_part(name: str, part: str) -> bool:
    """조건의 부품 이름이 이 부품인지. 끝의 온도 등급 I 는 같은 부품 (LMV321I = LMV321)."""
    return name == part or name == part + "I"


def row_supply(row: dict, table_rng=None):
    """줄의 전원 범위. 줄에 없으면 그 쪽 표 제목의 전원 (page_supplies)."""
    return supply_range(row.get("conditions") or "") or table_rng


def supply_rank(row: dict, table_rng=None) -> int:
    """같은 측정 항목이 여러 전원 조건으로 있을 때 고르는 순서 (작을수록 먼저).
    0: 판정 전원 범위(5 V 근처) 줄, 1: 전원을 모르는 줄, 2: 다른 전원 줄 (build 에서 뺀다).
    데이터시트는 낮은 전원 표가 먼저 나오는 일이 많아, 먼저 나온 줄을 쓰면 2.7 V 값이 목표가 됐다 (LMV321, 2026-11-25)."""
    rng = row_supply(row, table_rng)
    if rng is None:
        return 1
    return 0 if in_band(rng) else 2


def has_limit(row: dict) -> bool:
    """데이터시트가 보장하는 값(최소나 최대)이 있는 줄인지. 보통값만 있으면 판정 기준을 팀 규칙으로 정해야 한다."""
    return row.get("min_target") is not None or row.get("max_target") is not None


# 표 제목 줄: "6.8 Electrical Characteristics: VCC+ = 5 V", "VCC+ = 5 V, TA = 25°C (unless otherwise noted)"
TABLE_TITLE = re.compile(r"electrical characteristics|unless otherwise noted", re.I)


def page_supplies(pages: dict | None) -> dict:
    """쪽 번호 -> 그 쪽 표 제목의 전원 범위 (아래, 위) [V]. 제목 전원이 하나로 분명한 쪽만
    (둘 이상이거나 '2.7 V, 5 V, ±5 V' 처럼 나열되면 어느 줄이 어느 표인지 몰라 뺀다).
    추출 LLM 이 표 제목 조건을 줄마다 붙이기도 하고 안 붙이기도 해서 (LMV321 2026-11-26: 2.7 V 표는 붙이고
    5 V 표는 안 붙임) 5 V 표 줄을 5 V 로 알아보지 못하고 1쪽 요약표 줄(보통값만 있음)을 골랐다. 하네스(run_harness)도 쓴다."""
    found = {}
    for key, text in (pages or {}).items():
        if not isinstance(text, str):
            continue
        titles = [line for line in text.splitlines() if TABLE_TITLE.search(line)]
        if any(LISTED_SUPPLIES.search(line) for line in titles):
            continue
        values = {supply_range(line) for line in titles} - {None}
        if len(values) == 1:
            found[int(key)] = values.pop()
    return found


# 작을수록 좋은 항목. 데이터시트에 보통값만 있으면 "보통값 x max_ratio 이하"로 판정한다 (나머지는 "보통값 x min_ratio 이상").
# 전에는 모두 "이상"으로 판정해 공급 전류가 "104 µA 이상"이 되어 528 µA 회로가 통과했다 (LMV321, 2026-11-26)
# 출력 스윙(voh/vol)은 레일에서 떨어진 거리로 바꿔 두므로 작을수록 좋다
LOWER_IS_BETTER = {"idd", "ts", "voh_1ma", "voh_5ma", "vol_1ma", "vol_5ma", "vio", "vio_drift", "iio", "iib",
                   "cic", "vn_1k", "vn_10k", "in_1k", "thd_av1"}
TEMPERATURE_NOTE = "Full-temperature"
# 조건에 25°C 가 적힌 줄은 온도 범위가 같이 적혀 있어도 25°C 줄로 본다. 추출 LLM 이 표 위 조건(TA = 25°C)과
# 줄 조건(TA = -40°C to +125°C)을 한데 붙여 적어, LM358 공급 전류 25°C 줄이 온도 범위 줄로 빠졌다 (2026-11-28)
AT_25C = re.compile(r"T\s*A\s*=\s*25\s*°?\s*C|25\s*°\s*C", re.I)
# 보통값만 있는 항목은 데이터시트가 정한 합격 기준이 없어 판정하지 않고 참고로만 잰다 (2026-11-28 결정).
# 위상 여유만은 발진하지 않는 회로를 고르도록 우리 설계 안전 조건(PM_GUARD_DEG 이상)으로 판정한다
PM_GUARD_DEG = 45.0
# 조건에 적힌 온도 범위 (예: "TA = –40°C to 125°C", "Full range") -> 25°C 줄이 아니므로 뺀다
TEMPERATURE_RANGE = re.compile(r"[–−-]?\d+\s*°?\s*C\s*to\s*\+?\d+|Full range|Temperature\s*\(", re.I)
CURRENT_IN_COND = re.compile(r"I\s*OUT\s*=\s*(\d+\.?\d*)\s*([mµμu]?)A", re.I)

# 측정 종류 -> 우리 측정을 못 하는 이유
NOT_MEASURED = {
    "vos": "입력 오프셋 전압: 소자 편차 통계 해석이 필요해 아직 재지 않음",
    "ib": "입력 바이어스 전류: MOS 입력이라 시뮬레이션에서 거의 0이 되어 의미 없음",
    "ios": "입력 오프셋 전류: MOS 입력이라 시뮬레이션에서 거의 0이 되어 의미 없음",
    "en": "입력 잡음 밀도: 잡음 해석(.noise) 측정을 아직 만들지 않음",
    "isc": "단락 전류: 출력 단락 측정을 아직 만들지 않음 (LM358B 는 ±10 V 조건이라 6 V 소자로 잴 수도 없음)",
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
        # 마이크로는 µ(U+00B5)와 μ(그리스 뮤, U+03BC) 두 글자로 들어온다. 정규식이 대소문자를 무시해 'M', 'U' 도 걸린다
        # (LM324 2026-11-27: 'μ' 로 KeyError 가 나 1단계가 멈춤)
        prefix = m.group(2).replace("μ", "µ").replace("Μ", "µ")
        amps = float(m.group(1)) * {"m": 1e-3, "M": 1e-3, "µ": 1e-6, "u": 1e-6, "U": 1e-6, "": 1}.get(prefix, 1e-6)
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


# 추출 값 점검 (2026-11-28). 추출 LLM 이 표 칸을 밀려 읽으면 맞는 회로도 실패가 된다
# (LM358: VOL "0.75 1 V" 를 최소 0.75 / 보통 1 로 읽어 "0.75 V 이상"이 됨). 칸 머리글이 근거 글에 없어
# LLM 에 다시 물어도 어느 칸인지 알 수 없으므로, 물리적으로 뜻이 있는 방향으로 바로잡고 안 되면 판정에서 뺀다.
# 작을수록 좋은 항목(레일에서 떨어진 폭 포함, 추출 원래 값 기준): 최소만 있으면 뜻이 없다 -> 칸이 밀린 것
SHIFT_UP = {"idd", "voh_1ma", "voh_5ma", "vol_1ma", "vol_5ma", "iib", "iio", "ts", "vn_1k", "vn_10k", "in_1k", "thd_av1"}
# 클수록 좋은 항목: 최대만 있으면 뜻이 없다 -> 칸이 밀린 것
SHIFT_DOWN = {"avd", "cmrr", "psrr", "ugbw", "sr"}
# 우리 단위로 바꾼 뒤 말이 되는 범위 (벗어나면 단위나 숫자를 잘못 읽은 것)
PLAUSIBLE = {"avd": (20, 200), "cmrr": (20, 200), "psrr": (20, 200), "idd": (0.01, 1e5), "ugbw": (1e-4, 1e3),
             "sr": (1e-4, 1e4), "voh_1ma": (0, TEST_SUPPLY), "voh_5ma": (0, TEST_SUPPLY), "vol_1ma": (0, TEST_SUPPLY),
             "vol_5ma": (0, TEST_SUPPLY), "pm": (1, 120)}


def check_values(measure: str, lo, typ, hi) -> tuple:
    """추출한 (최소, 보통, 최대) 를 점검한다. 돌려주는 값: (최소, 보통, 최대, 고친 내용 또는 None, 오류 또는 None)."""
    fixed = None
    if measure in SHIFT_UP and lo is not None and hi is None:
        lo, typ, hi = None, (lo if typ is not None else None), (typ if typ is not None else lo)
        fixed = "작을수록 좋은 항목에 최소값만 있어 칸이 밀린 것으로 보고 보통/최대로 읽음"
    elif measure in SHIFT_DOWN and hi is not None and lo is None:
        lo, typ, hi = (typ if typ is not None else hi), (hi if typ is not None else None), None
        fixed = "클수록 좋은 항목에 최대값만 있어 칸이 밀린 것으로 보고 최소/보통으로 읽음"
    values = [v for v in (lo, typ, hi) if v is not None]
    if any(a > b for a, b in zip(values, values[1:])):
        return lo, typ, hi, fixed, f"최소 ≤ 보통 ≤ 최대 순서가 아님 ({lo} / {typ} / {hi})"
    return lo, typ, hi, fixed, None


def plausible_error(measure: str, values: tuple):
    """우리 단위로 바꾼 값이 말이 되는 범위 밖이면 그 설명, 아니면 None."""
    bounds = PLAUSIBLE.get(measure)
    bad = [v for v in values if v is not None and bounds and not bounds[0] <= v <= bounds[1]]
    return f"값이 말이 되는 범위({bounds[0]:g}~{bounds[1]:g}) 밖: {bad[0]:g}" if bad else None


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


def apply_fix(rows: list, fix: dict) -> dict:
    """교정 파일의 줄별 값을 덮어쓴다. 줄 번호 -> 원래 값과 이유 (판정 항목에 기록용)."""
    changed = {}
    for key, new in fix.get("rows", {}).items():
        i = int(key)
        values = {k: v for k, v in new.items() if k not in ("reason", "pdf")}
        changed[i] = {"original": {k: rows[i].get(k) for k in values}, "reason": new.get("reason"), "pdf": new.get("pdf")}
        rows[i] = {**rows[i], **values}
    return changed


def build(plan: dict, hkg: dict, part: str, fix: dict | None = None, whole: bool = False,
          pages: dict | None = None) -> dict:
    """whole=True: 한 부품(채널 수 변형만 있는) 데이터시트라 부품 구간을 자르지 않고 계획 전체를 쓴다.
    pages: 쪽 번호 -> 쪽 글 (extract_datasheet 의 *_pages.json). 있으면 표 제목의 전원 조건을 줄에 이어 붙여 고른다.
    고르는 순서: 판정 전원 범위(5 V 근처) 줄 -> 보장값(최소·최대)이 있는 줄 -> 먼저 나온 줄.
    전원이 판정 범위 밖인 줄(±5 V = 10 V, ±15 V, 2.7 V 표 등)은 고르지 않고 other_supply 에 센다.
    판정 항목이 0개이고 other_supply 가 있으면 '전압 조건 때문에 생성 불가' (pipeline.step_extract)."""
    rows, extracted = [dict(r) for r in plan["spec_evaluations"]], hkg["electrical_parameters"]
    template = {s["measure"]: s for s in json.loads(TEMPLATE_SPEC.read_text(encoding="utf-8"))["specs"]}
    changed = apply_fix(rows, fix) if fix else {}
    if whole:
        section = range(len(rows))
    else:
        section = range(*fix["section"]["rows"]) if fix and fix.get("section") else part_rows(rows, part)
    specs, missing, seen = [], [], set()
    titles = page_supplies(pages)

    def table_supply(i):
        return titles.get(extracted[i].get("page")) if i < len(extracted) else None

    other_supply = {}                                   # 판정 범위 밖 전원 [V] -> 줄 수
    for i in section:
        if rows[i].get("fixture") or rows[i].get("status") == "NOT_TESTABLE_SUPPLY":
            rng = row_supply(rows[i], table_supply(i))
            if rng is not None and not in_band(rng):
                other_supply[rng[0]] = other_supply.get(rng[0], 0) + 1
    planned = sorted((i for i in section if rows[i].get("fixture") and supply_rank(rows[i], table_supply(i)) < 2),
                     key=lambda i: (supply_rank(rows[i], table_supply(i)), not has_limit(rows[i])))
    for i in planned:
        row = rows[i]
        named = set(PART_NAME.findall(row.get("conditions") or ""))
        at_25c = bool(AT_25C.search(row.get("conditions") or ""))
        if (named and not any(same_part(n, part) for n in named)) or                 ((row.get("note") or "").startswith(TEMPERATURE_NOTE) and not at_25c):
            continue
        if whole and TEMPERATURE_RANGE.search(row.get("conditions") or "") and not at_25c:
            continue                                    # 온도 범위만 적힌 줄은 무시 (시뮬레이션은 25°C 하나)
        if whole and all(row.get(k) is None for k in ("min_target", "typ_target", "max_target")):
            continue                                    # 목표값이 하나도 없는 줄
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
        lo, ty, hi, fixed, error = check_values(measure, row["min_target"], row["typ_target"], row["max_target"])
        low, typ, high = (spec_from_hkg.rounded(v) for v in to_ours(measure, dict(row, min_target=lo, typ_target=ty,
                                                                                    max_target=hi)))
        error = error or plausible_error(measure, (low, typ, high))
        item.update({k: v for k, v in (("min", low), ("typ", typ), ("max", high)) if v is not None})
        if fixed:
            item["value_fix"] = fixed
        if error:                                      # 판정에서 빼고 결과 화면에 '추출 오류'로 보여 줌
            item.update(reference=True, extract_error=error)
            item.pop("min", None)
            item.pop("max", None)
        elif low is None and high is None:
            if measure == "pm":                        # 발진 방지용 우리 안전 조건 (데이터시트 기준 아님)
                item.update(min=PM_GUARD_DEG, basis="guard")
            else:
                item["reference"] = True               # 판정하지 않고 참고로만 (run_sim.judge 가 '참고'로 둠)
        item.update(symbol=row["symbol"], condition=row.get("conditions"), extracted=evidence,
                    plan={"kind": kind, "fixture": row["fixture"], "row": i})
        if table_supply(i) is not None and supply_range(row.get("conditions") or "") is None:
            item["table_supply_v"] = list(table_supply(i))    # 줄에 없고 표 제목에서 읽은 전원 범위
        if i in changed:
            item["corrected"] = changed[i]
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
                     "corrections": None if not fix else {"section_reason": (fix.get("section") or {}).get("reason"),
                                                          "rows": len(changed)},
                     "not_planned": [{"measure": m, "label": template[m]["label"],
                                      "reason": "측정 계획에 없음 (계획이 이 데이터시트 줄을 측정 대상으로 정하지 않음)"} for m in not_planned]},
            "unused": [],
            "supply_band_v": list(supply_band()),
            "other_supply": {"rows": sum(other_supply.values()), "supplies_v": sorted(other_supply)}}


def main() -> None:
    args = sys.argv[1:]
    fix_file = None
    whole = "--whole" in args
    if whole:
        args.remove("--whole")
    if "--fix" in args:
        at = args.index("--fix")
        fix_file = Path(args[at + 1])
        del args[at:at + 2]
    plan_file, hkg_file, part, name = Path(args[0]), Path(args[1]), args[2], args[3]
    fix = json.loads(fix_file.read_text(encoding="utf-8")) if fix_file else None
    spec = build(json.loads(plan_file.read_text(encoding="utf-8")), json.loads(hkg_file.read_text(encoding="utf-8")), part, fix, whole)
    spec["extraction"]["file"] = hkg_file.name
    spec["plan"]["file"] = plan_file.name
    if fix_file:
        spec["plan"]["corrections"]["file"] = fix_file.name
    (HERE / f"spec_{name}.json").write_text(json.dumps(spec, ensure_ascii=False, indent=1), encoding="utf-8")
    sentence = spec_from_hkg.model_input(spec)
    (HERE / "data" / "train" / f"{name}.json").write_text(json.dumps(sentence, ensure_ascii=False, indent=1), encoding="utf-8")
    p = spec["plan"]
    print(f"측정 계획 {p['planned_rows']}줄 중 {part} 구간(줄 {p['part_rows'][0]}~{p['part_rows'][1] - 1}) {p['part_planned']}줄 -> 판정 항목 {p['used']}개")
    for s in spec["specs"]:
        mark = "  (교정)" if "corrected" in s else ""
        print(f"  {s['measure']:10s} {s.get('min')} / {s.get('typ')} / {s.get('max')} {s['unit']}   <- {s['plan']['kind']} p.{s['extracted'].get('page')}{mark}")
    print("계획에 있으나 측정 없음:")
    for m in p["not_measured"]:
        print(f"  {m['kind']:8s} {str(m['symbol']):6s} {m['reason']}")
    print("계획에 없어 판정 안 함:", [m["measure"] for m in p["not_planned"]])
    print("모델 입력:", sentence["input"])


if __name__ == "__main__":
    main()
