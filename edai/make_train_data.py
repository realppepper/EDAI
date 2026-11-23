"""
학습 데이터(data/labels_*.json)를 FLAN-T5 학습 파일로 바꾼다: 스펙 문장 -> 구조 표.

사용법 (프로젝트 폴더에서):
    python make_train_data.py
결과: data/train/train.jsonl, val.jsonl, tlv271.json  (Colab 노트북 colab/flan_t5_structure.ipynb 에 올린다)

입력 문장: 측정값을 OP-Amp 공통 측정 항목 15개(이름·단위는 스펙 파일 형식을 따름)로 적는다.
    "op-amp spec: avd 105 dB; idd 550 uA; ugbw 3 MHz; ..."
정답: 구조 표를 한 줄로 이은 글. 소자 사이는 " ; " 로 나눈다 (T5 토크나이저가 줄바꿈을 지우기 때문).
    "PM1 D=OUT G=N1 S=VDD B=VDD ; PM2 D=N1 G=N1 S=VDD B=VDD ; ..."
- 동작 판정을 통과한 줄만 쓴다 (label_dataset.py 의 judge).
- 검증용은 구조 단위로 뗀다. 같은 구조가 학습과 검증에 함께 들어가면 점수가 부풀려진다.
- 실제 데이터시트는 항목 일부만 주므로, 항목 일부를 무작위로 뺀 문장도 만든다.
"""

import json
import random
from pathlib import Path

HERE = Path(__file__).resolve().parent
LABEL_FILES = ("labels_blocks.json", "labels_analoggenie_all.json")
OUT_DIR = HERE / "data" / "train"
SPEC_FILE = HERE / "spec_tlv271.json"
PROMPT_HEAD = "op-amp spec: "
ROW_SEP = " ; "
VAL_FRACTION = 0.1          # 검증용으로 떼는 구조의 비율
SUBSET_COPIES = 3           # 한 줄마다 항목 일부만 남긴 문장을 몇 개 더 만들지
SUBSET_KEEP = 0.6           # 일부만 남길 때 항목 하나가 남을 확률
SUBSET_MIN_ITEMS = 3
SEED = 7
SIGNIFICANT = 3             # 값을 적을 때 유효숫자
# 스펙 파일 단위를 영어 토큰으로 (T5 어휘에 µ, ° 가 없다)
UNIT_TEXT = {"µA": "uA", "V/µs": "V/us", "µs": "us", "°": "deg"}


def spec_items() -> list:
    """시뮬레이션으로 재는 스펙 항목: [(measure, scale, unit 글)]. 범위 밖 항목은 뺀다."""
    spec = json.loads(SPEC_FILE.read_text(encoding="utf-8"))
    return [(s["measure"], s.get("scale", 1.0), UNIT_TEXT.get(s["unit"], s["unit"]))
            for s in spec["specs"] if s.get("scope") != "excluded"]


def number_text(value: float) -> str:
    return f"{value:.{SIGNIFICANT}g}"


def spec_text(values: dict, items: list) -> str:
    """{measure: SI 단위 값} -> 입력 문장. 값이 없는 항목은 건너뛴다."""
    parts = [f"{measure} {number_text(values[measure] * scale)} {unit}"
             for measure, scale, unit in items if values.get(measure) is not None]
    return PROMPT_HEAD + "; ".join(parts)


def table_line(table_text: str) -> str:
    return ROW_SEP.join(line.strip() for line in table_text.strip().splitlines())


def load_rows() -> list:
    rows = []
    for name in LABEL_FILES:
        for record in json.loads((HERE / "data" / name).read_text(encoding="utf-8")):
            if record["valid"]:
                rows.append({"structure": record["name"], "source": name, "measured": record["measured"],
                             "target": table_line(record["table"])})
    return rows


def examples(row: dict, items: list, rng: random.Random) -> list:
    """한 줄에서 학습 예제 여러 개: 모든 항목 + 항목 일부만 남긴 것."""
    present = [item for item in items if row["measured"].get(item[0]) is not None]
    out = [spec_text(row["measured"], present)]
    for _ in range(SUBSET_COPIES):
        kept = [item for item in present if rng.random() < SUBSET_KEEP]
        if len(kept) >= SUBSET_MIN_ITEMS:
            out.append(spec_text(row["measured"], kept))
    return [{"input": text, "target": row["target"], "structure": row["structure"]} for text in dict.fromkeys(out)]


def tlv271_values() -> dict:
    """TLV271 스펙의 목표값 (SI 단위). 대표값이 있으면 대표값, 없으면 최소/최대값."""
    spec = json.loads(SPEC_FILE.read_text(encoding="utf-8"))
    values = {}
    for s in spec["specs"]:
        if s.get("scope") == "excluded":
            continue
        value = next((s[k] for k in ("typ", "min", "max") if s.get(k) is not None), None)
        if value is not None:
            values[s["measure"]] = value / s.get("scale", 1.0)
    return values


def main() -> None:
    rng = random.Random(SEED)
    items = spec_items()
    rows = load_rows()
    structures = sorted({r["target"] for r in rows})
    rng.shuffle(structures)
    val_targets = set(structures[:max(1, int(len(structures) * VAL_FRACTION))])
    split = {"train": [], "val": []}
    for row in rows:
        split["val" if row["target"] in val_targets else "train"].extend(examples(row, items, rng))
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for name, data in split.items():
        rng.shuffle(data)
        with open(OUT_DIR / f"{name}.jsonl", "w", encoding="utf-8") as handle:
            for example in data:
                handle.write(json.dumps(example, ensure_ascii=False) + "\n")
    values = tlv271_values()
    tlv = {"input": spec_text(values, items), "values": values}
    (OUT_DIR / "tlv271.json").write_text(json.dumps(tlv, ensure_ascii=False, indent=1), encoding="utf-8")
    longest = max(len(r["target"]) for r in rows)
    print(f"동작하는 줄 {len(rows)}, 서로 다른 구조 {len(structures)} (검증용 {len(val_targets)})")
    print(f"학습 예제 {len(split['train'])}, 검증 예제 {len(split['val'])}, 가장 긴 정답 {longest} 글자")
    print(f"TLV271 입력: {tlv['input']}")


if __name__ == "__main__":
    main()
