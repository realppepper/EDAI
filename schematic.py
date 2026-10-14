"""
넷리스트(.cir)를 읽어 NMOS-input 캐스코드 증폭기 회로도를 그린다.
이전 넷리스트를 함께 주면 값이 바뀐 소자를 빨간색으로 강조한다.

사용법 (WSL):
    ~/.venvs/edai/bin/python schematic.py cascode.cir tb_cascode_ac.cir -o sim_out/schematic.svg
    ~/.venvs/edai/bin/python schematic.py cascode_lp.cir tb_cascode_ac.cir \
        --prev cascode.cir tb_cascode_ac.cir -o sim_out/schematic.svg

회로 본체와 테스트벤치가 다른 파일에 있으므로 두 파일을 함께 준다. 회로 파일의
.subckt 핀 이름과 테스트벤치의 노드 이름이 같아야 한 장의 회로도로 이어진다.

회로도의 배치는 캐스코드 구조 전용 틀이다. 넷리스트의 연결이 이 틀과 다르면
틀린 그림을 그리지 않도록 에러를 낸다.
"""

import argparse
from pathlib import Path

import schemdraw
import schemdraw.elements as elm

HIGHLIGHT_COLOR = "#d62728"
NORMAL_COLOR = "black"
UNIT = 2.5
FONT_SIZE = 12

# 소자 이름 -> 연결 노드 (M은 D G S B 순서)
CASCODE_TOPOLOGY = {
    "M1": ["VX", "VIN", "0", "0"],
    "M2": ["VOUT", "VCASC", "VX", "VX"],
    "RD": ["VDD", "VOUT"],
    "CL": ["VOUT", "0"],
    "VDD": ["VDD", "0"],
    "VCASC": ["VCASC", "0"],
    "VIN": ["VIN", "0"],
}


def parse_netlist(path: Path) -> dict:
    """넷리스트에서 소자별 연결 노드와 표시용 값을 읽는다."""
    elements = {}
    for raw_line in Path(path).read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith(("*", ".")):
            continue
        tokens = line.split()
        name = tokens[0].upper()
        if name.startswith("M"):
            params = {}
            for token in tokens[6:]:
                if "=" in token:
                    key, value = token.split("=", 1)
                    params[key.upper()] = value
            elements[name] = {
                "nodes": [t.upper() for t in tokens[1:5]],
                "value": f"W/L={params.get('W', '?')}/{params.get('L', '?')}",
            }
        elif name[0] in "RCV":
            elements[name] = {
                "nodes": [t.upper() for t in tokens[1:3]],
                "value": " ".join(tokens[3:]),
            }
    return elements


def parse_netlists(paths) -> dict:
    """여러 넷리스트(회로 본체 + 테스트벤치)의 소자를 한데 모은다."""
    elements = {}
    for path in paths:
        elements.update(parse_netlist(path))
    return elements


def check_topology(elements: dict) -> None:
    """넷리스트 연결이 캐스코드 틀과 같은지 확인한다."""
    for name, nodes in CASCODE_TOPOLOGY.items():
        if name not in elements:
            raise ValueError(f"넷리스트에 {name}이(가) 없습니다. 캐스코드 회로도 틀과 맞지 않습니다.")
        if elements[name]["nodes"] != nodes:
            raise ValueError(
                f"{name}의 연결 {elements[name]['nodes']}이(가) 캐스코드 틀 {nodes}과 다릅니다."
            )


def find_changes(prev: dict, curr: dict) -> dict:
    """이전 넷리스트 대비 값이 바뀐 소자를 {이름: (이전 값, 새 값)}으로 돌려준다."""
    return {
        name: (prev[name]["value"], curr[name]["value"])
        for name in curr
        if name in prev and prev[name]["value"] != curr[name]["value"]
    }


def draw_cascode(elements: dict, changes: dict) -> schemdraw.Drawing:
    """캐스코드 틀에 넷리스트 값을 채워 회로도를 그린다."""

    def color(name):
        return HIGHLIGHT_COLOR if name in changes else NORMAL_COLOR

    def pretty(name, value):
        tokens = value.split()
        if name.startswith("V") and len(tokens) == 2 and tokens[0].upper() == "DC":
            return f"{tokens[1]} V"
        return value

    def text(name):
        if name in changes:
            old, new = changes[name]
            return f"{name}\n{pretty(name, old)}\n→ {pretty(name, new)}"
        return f"{name}\n{pretty(name, elements[name]['value'])}"

    d = schemdraw.Drawing(show=False)
    d.config(unit=UNIT, fontsize=FONT_SIZE)

    m2 = d.add(elm.NFet().reverse().anchor("drain").at((0, 0)).color(color("M2"))
               .label(text("M2"), loc="right", ofst=0.4, color=color("M2")))
    m1 = d.add(elm.NFet().reverse().anchor("drain").at(m2.source).color(color("M1"))
               .label(text("M1"), loc="right", ofst=0.4, color=color("M1")))
    d.add(elm.Ground().at(m1.source))

    rd = d.add(elm.Resistor().up().at(m2.drain).color(color("RD"))
               .label(text("RD"), loc="bottom", color=color("RD")))
    d.add(elm.Vdd().at(rd.end).color(color("VDD"))
          .label(text("VDD").replace("\n", " "), color=color("VDD")))

    d.add(elm.Dot().at(m2.drain))
    out_wire = d.add(elm.Line().right().at(m2.drain).length(UNIT * 2))
    d.add(elm.Dot(open=True).at(out_wire.end).label("VOUT", loc="right"))
    cl = d.add(elm.Capacitor().down().at(out_wire.end).color(color("CL"))
               .label(text("CL"), loc="bottom", color=color("CL")))
    d.add(elm.Ground().at(cl.end))

    d.add(elm.Dot().at(m1.drain).label("VX", loc="left", ofst=0.15))

    cas_wire = d.add(elm.Line().left().at(m2.gate).length(UNIT * 0.6))
    d.add(elm.Dot(open=True).at(cas_wire.end).color(color("VCASC"))
          .label(text("VCASC"), loc="left", color=color("VCASC")))

    in_wire = d.add(elm.Line().left().at(m1.gate).length(UNIT * 1.4))
    vin = d.add(elm.SourceSin().down().at(in_wire.end).color(color("VIN"))
                .label(text("VIN"), loc="bottom", color=color("VIN")))
    d.add(elm.Ground().at(vin.end))
    return d


def main():
    parser = argparse.ArgumentParser(description="캐스코드 넷리스트 -> 회로도")
    parser.add_argument("netlist", type=Path, nargs="+", help="회로 본체와 테스트벤치 파일")
    parser.add_argument("--prev", type=Path, nargs="+", help="비교할 이전 넷리스트 (바뀐 소자 강조)")
    parser.add_argument("-o", "--output", type=Path, default=Path("sim_out/schematic.svg"))
    args = parser.parse_args()

    curr = parse_netlists(args.netlist)
    check_topology(curr)
    changes = {}
    if args.prev:
        prev = parse_netlists(args.prev)
        check_topology(prev)
        changes = find_changes(prev, curr)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    draw_cascode(curr, changes).save(str(args.output))
    print(f"회로도 저장: {args.output}")
    if changes:
        for name, (old, new) in changes.items():
            print(f"  변경: {name}  {old} -> {new}")


if __name__ == "__main__":
    main()
