"""
AnalogGenie 데이터셋에서 출력이 하나인 OP-Amp 를 골라 구조 표로 모은다.

데이터 출처: github.com/xz-group/AnalogGenie (MIT 라이선스). external/AnalogGenie 에 받아 둔다:
    git clone --depth 1 https://github.com/xz-group/AnalogGenie.git external/AnalogGenie

사용법 (프로젝트 폴더에서):
    python opamp_dataset.py        # data/opamp_tables.json 을 만들고 걸러진 이유를 센다

걸러 내는 회로
    1. 트랜지스터·저항·커패시터 밖의 소자가 있다 (스위치, 전류원, 부품 기호 등)
    2. 입력 두 개(VIN1, VIN2), 출력 하나(VOUT1), 전원 VDD/VSS 밖의 단자가 있다
       (바이어스 전압 VB#, 바이어스 전류 IB# 는 허용. 출력이 둘인 완전 차동 OP-Amp 는 아직 다루지 않는다)
    3. 단자 하나만 이어진 안쪽 노드가 있다 (떠 있는 선)
    4. 같은 구조가 이미 있다
손보는 것
    바디(B) 단자만 모인 노드는 NMOS 는 VSS, PMOS 는 VDD 에 붙인다 (그림에서 바디 연결을 생략한 경우).
    게이트에만 이어지고 전압을 주는 소자가 없는 노드는 바이어스 전압 단자로 본다
    (책 그림에서 Vb 기호를 단자로 적지 않은 경우). 새 VB 번호를 붙인다.
"""

import collections
import json
from pathlib import Path

import netlist_table as nt

HERE = Path(__file__).resolve().parent
SOURCE_DIR = HERE / "external" / "AnalogGenie" / "Dataset"
OUT_FILE = HERE / "data" / "opamp_tables.json"
SOURCE_NAME = "AnalogGenie (github.com/xz-group/AnalogGenie)"
# data_categorization.md 에서 OP-Amp 로 분류된 번호 범위 (양 끝 포함)
OPAMP_RANGES = {
    (281, 336): "Razavi, Design of Analog CMOS ICs - operational amplifiers",
    (628, 631): "operational amplifiers",
    (636, 639): "transconductance amplifiers",
    (705, 725): "basic opamp design and compensation",
    (884, 902): "operational amplifiers with single-ended outputs",
    (921, 932): "fully differential operational amplifiers",
    (978, 1029): "Allen & Holberg - CMOS / high-performance op amps",
    (1781, 2180): "opamp papers",
}
DRIVING_PINS = {"D", "S", "P", "N"}
BULK_RAIL = {"nmos": "VSS", "pmos": "VDD"}


def opamp_ids() -> list:
    return [(number, label) for (low, high), label in OPAMP_RANGES.items() for number in range(low, high + 1)]


def fix_bulks(circuit: dict) -> int:
    """바디 단자만 모인 노드를 전원에 붙인다. 고친 소자 수를 돌려준다."""
    uses = collections.defaultdict(set)
    for device in circuit["devices"]:
        for pin, net in device["pins"].items():
            uses[net].add(pin)
    fixed = 0
    for device in circuit["devices"]:
        bulk = device["pins"].get("B")
        if bulk and uses[bulk] == {"B"}:
            device["pins"]["B"] = BULK_RAIL[device["kind"]]
            fixed += 1
    return fixed


def promote_hidden_bias(circuit: dict) -> int:
    """게이트에만 이어진 노드를 바이어스 전압 단자(VB#)로 바꾼다. 바꾼 노드 수를 돌려준다."""
    driven, gates = set(), set()
    for device in circuit["devices"]:
        for pin, net in device["pins"].items():
            (driven if pin in DRIVING_PINS else gates).add(net)
    ports = set(circuit["ports"]) | {"VDD", "VSS"}
    hidden = sorted(net for net in gates - driven if net not in ports)
    used = [int(p[2:]) for p in circuit["ports"] if p.startswith("VB")]
    rename = {net: f"VB{max(used, default=0) + i + 1}" for i, net in enumerate(hidden)}
    for device in circuit["devices"]:
        device["pins"] = {pin: rename.get(net, net) for pin, net in device["pins"].items()}
    circuit["ports"] += list(rename.values())
    return len(rename)


def connection_problems(circuit: dict) -> list:
    """떠 있는 노드를 찾는다."""
    count = collections.Counter(net for device in circuit["devices"] for net in device["pins"].values())
    ports = set(circuit["ports"]) | {"VDD", "VSS"}
    return [f"떠 있는 노드 {net}" for net, n in count.items() if net not in ports and n < 2]


def load_one(number: int) -> dict:
    folder = SOURCE_DIR / str(number)
    ports = (folder / f"Port{number}.txt").read_text(encoding="utf-8").split()
    circuit = nt.parse_spectre((folder / f"{number}.cir").read_text(encoding="utf-8"), ports)
    fixed = fix_bulks(circuit)
    hidden = promote_hidden_bias(circuit)
    problems = connection_problems(circuit)
    if problems:
        raise nt.UnsupportedCircuit(problems[0])
    table = nt.to_table(circuit)
    return {"id": number, "table": nt.table_text(table), "ports": table["ports"],
            "transistors": sum(row["kind"] in ("nmos", "pmos") for row in table["rows"]),
            "bias_ports": [p for p in table["ports"] if p.startswith(("VB", "IB"))], "bulk_fixed": fixed,
            "hidden_bias": hidden,
            "signature": nt.signature(table)}


def reason_group(message: str) -> str:
    for key in ("다루지 않는 소자", "다루지 않는 단자", "떠 있는 노드", "구동되지 않는", "단자 수", "읽지 못한", "없습니다"):
        if key in message:
            return key
    return message


def build() -> dict:
    kept, rejected, reasons, seen = [], [], collections.Counter(), {}
    for number, label in opamp_ids():
        if not (SOURCE_DIR / str(number) / f"{number}.cir").exists():
            reasons["파일 없음"] += 1
            continue
        try:
            record = load_one(number)
        except nt.UnsupportedCircuit as error:
            reasons[reason_group(str(error))] += 1
            rejected.append({"id": number, "reason": str(error)})
            continue
        signature = record.pop("signature")
        if signature in seen:
            reasons["같은 구조 중복"] += 1
            rejected.append({"id": number, "reason": f"{seen[signature]}번과 같은 구조"})
            continue
        seen[signature] = number
        record["category"] = label
        kept.append(record)
    data = {"source": SOURCE_NAME, "ranges": {f"{lo}-{hi}": v for (lo, hi), v in OPAMP_RANGES.items()},
            "candidates": len(opamp_ids()), "kept": len(kept), "reject_reasons": dict(reasons),
            "circuits": kept, "rejected": rejected}
    OUT_FILE.parent.mkdir(exist_ok=True)
    OUT_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    return data


def main() -> None:
    data = build()
    print(f"OP-Amp 후보 {data['candidates']}개 -> 남은 구조 {data['kept']}개  ({OUT_FILE.relative_to(HERE)})")
    for reason, n in sorted(data["reject_reasons"].items(), key=lambda kv: -kv[1]):
        print(f"  걸러짐 {n:>4}  {reason}")
    sizes = collections.Counter(min(c["transistors"] // 5 * 5, 30) for c in data["circuits"])
    print("  트랜지스터 수:", ", ".join(f"{k}~{k + 4 if k < 30 else ''}개 {v}" for k, v in sorted(sizes.items())))
    bias = collections.Counter(len(c["bias_ports"]) for c in data["circuits"])
    print("  바이어스 단자 수:", ", ".join(f"{k}개 {v}" for k, v in sorted(bias.items())))


if __name__ == "__main__":
    main()
