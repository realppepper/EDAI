"""
넷리스트 <-> 구조 표 변환.

FLAN-T5 가 읽고 쓰는 "구조 표"를 만든다. AaLLM 논문처럼 소자 단자와 연결선(노드)의 관계를
적는데, 빈 칸이 대부분인 행렬 대신 단자마다 붙은 선만 한 줄씩 적는다 (같은 정보).

    NM1 D=OUT G=N1 S=VSS B=VSS
    PM1 D=N1 G=N1 S=VDD B=VDD
    C1 P=N1 N=OUT

규칙
    회로 단자 이름은 통일한다: VDD, VSS, IN1, IN2, OUT, 바이어스 전압 VB1.., 바이어스 전류 IB1..
    안쪽 노드는 표에 처음 나오는 순서대로 N1, N2 ... 로 다시 붙인다.
    소자 이름은 종류별 번호다: NM(nmos), PM(pmos), R, C. 소자 크기는 표에 넣지 않는다 (구조만).

읽을 수 있는 넷리스트
    parse_ngspice  : 우리 회로 파일 (.subckt, XM.. nfet_06v0/pfet_06v0, R, C)
    parse_spectre  : AnalogGenie 넷리스트 (M9 (D G S B) pmos4, R1 (a b) resistor ...)

사용법 (프로젝트 폴더에서):
    python netlist_table.py opamp_gen.cir      # 회로 파일을 구조 표로 보기
"""

import re
import sys
from pathlib import Path

POWER_PORTS = ("VDD", "VSS")
MOS_PINS = ("D", "G", "S", "B")
TWO_PINS = ("P", "N")
KIND_PREFIX = {"nmos": "NM", "pmos": "PM", "res": "R", "cap": "C"}
KIND_ORDER = ("pmos", "nmos", "res", "cap")
# 우리 회로 파일의 단자 이름 -> 통일한 이름
NGSPICE_PORT_NAMES = {"INP": "IN1", "INN": "IN2", "OUT": "OUT", "VDD": "VDD", "VSS": "VSS"}
NGSPICE_MODELS = {"nfet_06v0": "nmos", "pfet_06v0": "pmos"}
# AnalogGenie 소자 종류 -> 우리 종류. 여기에 없는 종류가 있으면 그 회로는 다루지 않는다
SPECTRE_MODELS = {"nmos4": "nmos", "pmos4": "pmos", "nmos": "nmos", "pmos": "pmos",
                  "resistor": "res", "capacitor": "cap"}
GROUND_NAMES = {"0", "gnd", "GND", "gnd!"}


class UnsupportedCircuit(ValueError):
    """다루지 않는 소자나 단자가 있는 회로."""


def _device(kind: str, pins: dict, params: dict = None, name: str = "") -> dict:
    return {"kind": kind, "pins": pins, "params": params or {}, "source_name": name}


# ---------------------------------------------------------------- 읽기
def parse_ngspice(text: str) -> dict:
    """우리 회로 파일(.subckt opamp INP INN OUT VDD VSS)을 읽는다.

    돌려주는 값: {"ports": [...], "devices": [{"kind", "pins", "params", "source_name"}]}
    단자 이름은 통일한 이름으로 바꾼다.
    """
    devices = []
    ports = []
    rename = {}
    for line in text.splitlines():
        tokens = line.split()
        if not tokens or tokens[0].startswith("*"):
            continue
        head = tokens[0].upper()
        if head == ".SUBCKT":
            rename = {pin: NGSPICE_PORT_NAMES.get(pin, pin) for pin in tokens[2:]}
            ports = [rename[pin] for pin in tokens[2:]]
            continue
        if head.startswith("."):
            continue
        net = lambda node: rename.get(node, node)  # noqa: E731
        if head.startswith("X"):
            model = tokens[5] if len(tokens) > 5 else ""
            if model not in NGSPICE_MODELS:
                raise UnsupportedCircuit(f"모르는 소자 모델: {model}")
            params = dict(token.split("=", 1) for token in tokens[6:] if "=" in token)
            devices.append(_device(NGSPICE_MODELS[model], dict(zip(MOS_PINS, map(net, tokens[1:5]))),
                                   params, tokens[0]))
        elif head[0] in "RC":
            kind = "res" if head[0] == "R" else "cap"
            devices.append(_device(kind, dict(zip(TWO_PINS, map(net, tokens[1:3]))),
                                   {"value": tokens[3]}, tokens[0]))
        else:
            raise UnsupportedCircuit(f"모르는 소자 줄: {line.strip()}")
    return {"ports": ports, "devices": devices}


SPECTRE_LINE = re.compile(r"^(\S+)\s*\(([^)]*)\)\s*(\S+)(.*)$")


def parse_spectre(text: str, ports: list) -> dict:
    """AnalogGenie 넷리스트를 읽는다. ports 는 Port#.txt 에 적힌 회로 단자 목록이다.

    단자 이름 통일: VIN1->IN1, VIN2->IN2, VOUT1->OUT, VDD/VSS 그대로.
    바이어스 단자 VB#(전압), IB#(전류)는 이름을 그대로 둔다.
    다루지 않는 소자(트랜지스터·저항·커패시터 밖의 것)나 단자(클럭, 출력 둘 등)가 있으면
    UnsupportedCircuit 을 던진다.
    """
    rename = {}
    for port in ports:
        if port in POWER_PORTS:
            rename[port] = port
        elif re.fullmatch(r"VIN[12]", port):
            rename[port] = "IN" + port[-1]
        elif port == "VOUT1":
            rename[port] = "OUT"
        elif re.fullmatch(r"(VB|IB)\d+", port):
            rename[port] = port
        else:
            raise UnsupportedCircuit(f"다루지 않는 단자: {port}")
    for needed in ("VDD", "VSS", "IN1", "IN2", "OUT"):
        if needed not in rename.values():
            raise UnsupportedCircuit(f"단자 {needed} 이 없습니다")
    for name in GROUND_NAMES:
        rename.setdefault(name, "VSS")
    devices = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith(("*", "//")):
            continue
        match = SPECTRE_LINE.match(line)
        if not match:
            raise UnsupportedCircuit(f"읽지 못한 줄: {line}")
        name, nodes, model, rest = match.groups()
        nodes = [rename.get(node, node) for node in nodes.split()]
        if model not in SPECTRE_MODELS:
            raise UnsupportedCircuit(f"다루지 않는 소자: {model}")
        kind = SPECTRE_MODELS[model]
        pin_names = MOS_PINS if kind in ("nmos", "pmos") else TWO_PINS
        if len(nodes) != len(pin_names):
            raise UnsupportedCircuit(f"단자 수가 맞지 않는 줄: {line}")
        devices.append(_device(kind, dict(zip(pin_names, nodes)), {}, name))
    if not devices:
        raise UnsupportedCircuit("소자가 없습니다")
    return {"ports": [rename[port] for port in ports], "devices": devices}


# ---------------------------------------------------------------- 표
def _port_rank(net: str) -> tuple:
    order = {"VDD": 0, "VSS": 1, "IN1": 2, "IN2": 3, "OUT": 4}
    if net in order:
        return (order[net], 0)
    if re.fullmatch(r"VB\d+", net):
        return (5, int(net[2:]))
    if re.fullmatch(r"IB\d+", net):
        return (6, int(net[2:]))
    return None


def to_table(circuit: dict) -> dict:
    """회로를 구조 표로 바꾼다.

    돌려주는 값: {"ports": [...], "rows": [{"name", "kind", "pins": {핀: 선}, "source_name", "params"}]}
    소자 순서: 종류(PMOS, NMOS, R, C) -> 회로 단자에 붙은 핀이 많은 것 먼저 -> 원래 순서.
    """
    ports = sorted({net for device in circuit["devices"] for net in device["pins"].values()
                    if _port_rank(net)} | set(circuit["ports"]), key=_port_rank)

    def sort_key(indexed):
        index, device = indexed
        touching = sum(net in ports for net in device["pins"].values())
        return (KIND_ORDER.index(device["kind"]), -touching, index)

    ordered = [device for _, device in sorted(enumerate(circuit["devices"]), key=sort_key)]
    inner, counters, rows = {}, {}, []
    for device in ordered:
        pins = {}
        for pin, net in device["pins"].items():
            if net not in ports:
                inner.setdefault(net, f"N{len(inner) + 1}")
                net = inner[net]
            pins[pin] = net
        counters[device["kind"]] = counters.get(device["kind"], 0) + 1
        rows.append({"name": f"{KIND_PREFIX[device['kind']]}{counters[device['kind']]}", "kind": device["kind"],
                     "pins": pins, "source_name": device["source_name"], "params": device["params"]})
    return {"ports": ports, "rows": rows}


def table_text(table: dict) -> str:
    """구조 표를 모델이 읽고 쓰는 글로 만든다 (한 줄에 소자 하나)."""
    return "\n".join(f"{row['name']} " + " ".join(f"{pin}={net}" for pin, net in row["pins"].items())
                     for row in table["rows"])


def parse_table_text(text: str) -> dict:
    """table_text 로 만든 글(또는 모델이 쓴 글)을 다시 표로 읽는다. 형식이 틀리면 ValueError."""
    rows, kinds = [], {prefix: kind for kind, prefix in KIND_PREFIX.items()}
    for line in text.strip().splitlines():
        tokens = line.split()
        prefix = re.match(r"[A-Z]+", tokens[0]).group() if tokens and re.match(r"[A-Z]+", tokens[0]) else ""
        if prefix not in kinds:
            raise ValueError(f"모르는 소자 이름: {line}")
        kind = kinds[prefix]
        pins = dict(token.split("=", 1) for token in tokens[1:])
        expected = MOS_PINS if kind in ("nmos", "pmos") else TWO_PINS
        if tuple(pins) != expected:
            raise ValueError(f"단자가 맞지 않습니다: {line}")
        rows.append({"name": tokens[0], "kind": kind, "pins": pins, "source_name": tokens[0], "params": {}})
    ports = sorted({net for row in rows for net in row["pins"].values() if _port_rank(net)}, key=_port_rank)
    return {"ports": ports, "rows": rows}


def matrix_text(table: dict) -> str:
    """사람이 보는 행렬 모양 (행: 소자 단자, 열: 선). 논문의 표와 같은 모양이다."""
    nets = table["ports"] + sorted({net for row in table["rows"] for net in row["pins"].values()
                                    if net not in table["ports"]}, key=lambda n: int(n[1:]))
    width = max(len(net) for net in nets) + 1
    lines = [" " * 6 + "".join(net.rjust(width) for net in nets)]
    for row in table["rows"]:
        for pin, net in row["pins"].items():
            lines.append(f"{row['name']}.{pin}".ljust(6) + "".join(("●" if n == net else "·").rjust(width) for n in nets))
    return "\n".join(lines)


def signature(table: dict) -> tuple:
    """연결이 같은지 비교할 때 쓰는 값. 소자 이름과 노드 번호는 무시한다."""
    return tuple(sorted((row["kind"], tuple(sorted(row["pins"].items()))) for row in table["rows"]))


# ---------------------------------------------------------------- 표 -> 넷리스트
NGSPICE_MODEL_OF = {"nmos": "nfet_06v0", "pmos": "pfet_06v0"}
SUBCKT_PORT_ORDER = ("IN1", "IN2", "OUT", "VDD", "VSS")
DEFAULT_MOS = {"w": "10u", "l": "1u"}
DEFAULT_VALUE = {"res": "10k", "cap": "1p"}


def to_ngspice(table: dict, sizes: dict = None, name: str = "opamp", polarity: tuple = ("IN1", "IN2"),
               extra_lines: list = None) -> str:
    """구조 표를 우리 회로 파일(.subckt NAME INP INN OUT VDD VSS)로 만든다.

    sizes    : {소자 이름: {"w":..,"l":..,"m":..} 또는 {"value":..}}. 없으면 기본값.
    polarity : (비반전 입력, 반전 입력)이 표의 어느 단자인지. AnalogGenie 는 VIN1/VIN2 중
               어느 쪽이 비반전인지 표시가 없어서, 동작점을 보고 정한다.
    extra_lines : 회로 안에 덧붙일 줄 (바이어스 단자 VB# 를 만드는 소자 등).
    """
    sizes = sizes or {}
    rename = {polarity[0]: "INP", polarity[1]: "INN"}
    lines = [f".subckt {name} INP INN OUT VDD VSS"]
    for row in table["rows"]:
        nets = [rename.get(net, net) for net in row["pins"].values()]
        size = sizes.get(row["name"], {})
        if row["kind"] in NGSPICE_MODEL_OF:
            params = {**DEFAULT_MOS, **{k: v for k, v in size.items() if k in ("w", "l", "m")}}
            lines.append(f"X{row['name']} {' '.join(nets)} {NGSPICE_MODEL_OF[row['kind']]} "
                         + " ".join(f"{k}={v}" for k, v in params.items()))
        else:
            lines.append(f"{row['name']} {' '.join(nets)} {size.get('value', DEFAULT_VALUE[row['kind']])}")
    lines += [line for line in (extra_lines or [])]
    lines.append(f".ends {name}")
    return "\n".join(lines) + "\n"


def main() -> None:
    if len(sys.argv) != 2:
        print(__doc__)
        return
    table = to_table(parse_ngspice(Path(sys.argv[1]).read_text(encoding="utf-8")))
    print(table_text(table))
    print()
    print(matrix_text(table))


if __name__ == "__main__":
    main()
