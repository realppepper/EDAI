"""
구조 규칙: 상보 뒤집기 (2026-11-22).

입력쌍 종류가 공통모드 입력 범위를 덮지 못하면(auto_size.input_pair_covers_range) 회로 전체를 뒤집는다.
    NMOS <-> PMOS, VDD <-> VSS, 소자 이름 NM# <-> PM#
연결 모양과 이득 노드 수는 그대로이고 입력쌍 종류만 바뀐다.
예: TLV271 은 공통모드 범위가 0 V 부터인데 모델이 낸 2-이득노드 구조는 NMOS 입력이라 0 V 근처에서 입력쌍이 꺼진다
    (CMRR 3 dB). 뒤집으면 PMOS 입력이 되어 0 V 까지 동작한다.

사용법: python complement.py data/selection_cmp_tlv271_v3.json    선택된 구조를 뒤집은 표를 보여 줌
"""

import json
import sys
from pathlib import Path

import auto_size
import netlist_table as nt

SWAP_KIND = {"nmos": "pmos", "pmos": "nmos"}
SWAP_RAIL = {"VDD": "VSS", "VSS": "VDD"}
SWAP_PREFIX = {"NM": "PM", "PM": "NM"}


def input_kinds(table: dict) -> set:
    return {r["kind"] for r in table["rows"] if r["kind"] in SWAP_KIND and r["pins"].get("G") in ("IN1", "IN2")}


def flip(table: dict) -> dict:
    """NMOS/PMOS 와 VDD/VSS 를 맞바꾼 새 구조 표."""
    rows = []
    for r in table["rows"]:
        pins = {k: SWAP_RAIL.get(v, v) for k, v in r["pins"].items()}
        if r["kind"] in SWAP_KIND:
            name = SWAP_PREFIX[r["name"][:2]] + r["name"][2:] if r["name"][:2] in SWAP_PREFIX else r["name"]
            rows.append(dict(r, name=name, kind=SWAP_KIND[r["kind"]], pins=pins))
        else:
            rows.append(dict(r, pins=pins))
    # 뒤집은 뒤 이름이 겹치지 않게 (예: NM1 과 PM1 이 원래 둘 다 있던 경우 -> 서로 바뀌므로 겹치지 않음)
    names = [r["name"] for r in rows]
    assert len(names) == len(set(names)), "뒤집은 뒤 소자 이름이 겹침"
    return dict(table, rows=rows)


def fit_input_range(table: dict) -> tuple:
    """(구조 표, 뒤집었는지). 입력쌍이 공통모드 범위를 못 덮고 뒤집으면 덮을 때만 뒤집는다."""
    kinds = input_kinds(table)
    if auto_size.input_pair_covers_range(kinds):
        return table, False
    if auto_size.input_pair_covers_range({SWAP_KIND[k] for k in kinds}):
        return flip(table), True
    return table, False


def main() -> None:
    sel = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    e = sel["entries"][sel["summary"]["selected"]]
    table = nt.parse_table_text("\n".join(p.strip() for p in e["table"].split(";") if p.strip()))
    new, flipped = fit_input_range(table)
    print(f"입력쌍 {sorted(input_kinds(table))} -> {'뒤집음' if flipped else '그대로'}")
    print(nt.table_text(new))


if __name__ == "__main__":
    main()
