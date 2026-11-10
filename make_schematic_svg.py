"""
구조 표(크기 포함)를 netlistsvg 로 회로도(SVG)로 만든다. 소자 배치와 배선은 netlistsvg(ELK 자동 배치)가 한다.

netlistsvg 의 아날로그 기호 모음(analog.svg)에는 MOSFET 이 없어서, NMOS·PMOS 기호 두 개만 더한 기호 모음을 만들어 쓴다.
    NMOS: 위 D, 왼쪽 G, 아래 S        PMOS: 위 S, 왼쪽 G(동그라미), 아래 D
    몸체(B)가 제 전원(NMOS=VSS, PMOS=VDD)이 아니면 이름 옆에 B=노드 를 적는다.
VDD 는 위쪽 화살표, VSS 는 접지 기호로 연결마다 따로 붙인다 (긴 전원선을 줄이려고).

필요한 것 (WSL): Node.js (~/node), netlistsvg (~/netlistsvg/node_modules/netlistsvg)
    경로는 환경변수 EDAI_NODE, EDAI_NETLISTSVG 로 바꿀 수 있다.

사용법 (WSL, 프로젝트 폴더에서, select_structure.py 를 돌린 뒤):
    ~/.venvs/edai/bin/python make_schematic_svg.py lm358      (부품을 빼면 tlv271)
결과: data/schematics/<부품>/candidate_NN.svg  (동작한 후보마다, NN 은 후보 번호)
"""

import json
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_PART = "tlv271"
WORK_DIR = HERE / "sim_out"
NODE = Path(os.environ.get("EDAI_NODE", Path.home() / "node" / "bin" / "node"))
NETLISTSVG = Path(os.environ.get("EDAI_NETLISTSVG", Path.home() / "netlistsvg" / "node_modules" / "netlistsvg"))
ROW_SEP = ";"
INPUTS, OUTPUTS = ("IN1", "IN2"), ("OUT",)
NORMAL_BULK = {"NM": "VSS", "PM": "VDD"}

MOS_SYMBOLS = """
<g s:type="nmos" s:width="40" s:height="50" transform="translate(300,350)">
  <s:alias val="nmos"/>
  <text x="34" y="20" s:attribute="ref" class="$cell_id">M1</text>
  <text x="34" y="34" s:attribute="value" class="$cell_id">W/L</text>
  <path d="M0,25 H12 M12,13 V37" class="symbol $cell_id"/>
  <path d="M17,11 V19 M17,21 V29 M17,31 V39" class="symbol $cell_id"/>
  <path d="M17,15 H28 V0 M17,35 H28 V50" class="connect $cell_id"/>
  <path d="M25,35 L19,32 L19,38 Z" style="fill:#000" class="$cell_id"/>
  <g s:x="28" s:y="0" s:pid="D" s:position="top"/>
  <g s:x="0" s:y="25" s:pid="G" s:position="left"/>
  <g s:x="28" s:y="50" s:pid="S" s:position="bottom"/>
</g>
<g s:type="pmos" s:width="40" s:height="50" transform="translate(360,350)">
  <s:alias val="pmos"/>
  <text x="34" y="20" s:attribute="ref" class="$cell_id">M1</text>
  <text x="34" y="34" s:attribute="value" class="$cell_id">W/L</text>
  <path d="M0,25 H6.5 M12,13 V37" class="symbol $cell_id"/>
  <circle cx="9.2" cy="25" r="2.7" class="symbol $cell_id"/>
  <path d="M17,11 V19 M17,21 V29 M17,31 V39" class="symbol $cell_id"/>
  <path d="M17,15 H28 V0 M17,35 H28 V50" class="connect $cell_id"/>
  <path d="M18,15 L24,12 L24,18 Z" style="fill:#000" class="$cell_id"/>
  <g s:x="28" s:y="0" s:pid="S" s:position="top"/>
  <g s:x="0" s:y="25" s:pid="G" s:position="left"/>
  <g s:x="28" s:y="50" s:pid="D" s:position="bottom"/>
</g>
"""


def make_skin() -> Path:
    """netlistsvg 의 analog.svg 에 MOSFET 기호를 더한 기호 모음."""
    base = (NETLISTSVG / "lib" / "analog.svg").read_text(encoding="utf-8")
    skin = WORK_DIR / "edai_mos_skin.svg"
    skin.write_text(base.replace("</svg>", MOS_SYMBOLS + "</svg>"), encoding="utf-8")
    return skin


def parse_rows(text: str) -> list:
    rows = []
    for part in text.split(ROW_SEP):
        tokens = part.split()
        if tokens:
            rows.append((tokens[0], dict(t.split("=", 1) for t in tokens[1:] if "=" in t)))
    return rows


def size_text(size: dict) -> str:
    if not size:
        return ""
    return f"{size['w']}/{size['l']}" + (f" x{size['m']}" if size.get("m") else "")


def to_yosys(rows: list, sizes: dict) -> dict:
    """구조 표 -> netlistsvg 가 읽는 yosys JSON (모듈 하나)."""
    bits, cells = {}, {}
    counter = iter(range(2, 100000))

    def bit(net: str) -> int:
        if net not in bits:
            bits[net] = next(counter)
        return bits[net]

    def rail(net: str) -> int:
        """전원 연결마다 따로 기호를 붙인다."""
        number = next(counter)
        kind = "vcc" if net == "VDD" else "gnd"
        cells[f"{net}_{number}"] = {"type": kind, "port_directions": {"A": "input" if kind == "gnd" else "output"},
                                    "connections": {"A": [number]}, "attributes": {"name": net}}
        return number

    def connect(net: str) -> int:
        return rail(net) if net in ("VDD", "VSS") else bit(net)

    for name, pins in rows:
        kind = name[:2]
        if kind in ("NM", "PM"):
            ref = name if pins.get("B") == NORMAL_BULK[kind] else f"{name} B={pins.get('B')}"
            top, bottom = ("D", "S") if kind == "NM" else ("S", "D")
            cells[name] = {"type": "nmos" if kind == "NM" else "pmos",
                           "port_directions": {top: "input", "G": "input", bottom: "output"},
                           "connections": {p: [connect(pins[p])] for p in (top, "G", bottom)},
                           "attributes": {"ref": ref, "value": size_text(sizes.get(name))}}
        else:
            cells[name] = {"type": "r_v" if name.startswith("R") else "c_v",
                           "connections": {"A": [connect(pins["P"])], "B": [connect(pins["N"])]},
                           "attributes": {"ref": name, "value": ""}}
    ports = {net: {"direction": "input", "bits": [bit(net)]} for net in INPUTS if net in bits}
    ports.update({net: {"direction": "output", "bits": [bit(net)]} for net in OUTPUTS if net in bits})
    return {"modules": {"opamp": {"ports": ports, "cells": cells}}}


def render(rows: list, sizes: dict, out: Path, skin: Path) -> None:
    netlist = WORK_DIR / f"{out.stem}.json"
    netlist.write_text(json.dumps(to_yosys(rows, sizes)), encoding="utf-8")
    subprocess.run([str(NODE), str(NETLISTSVG / "bin" / "netlistsvg.js"), str(netlist), "--skin", str(skin), "-o", str(out)],
                   check=True, capture_output=True, text=True, timeout=120)
    netlist.unlink()


def main() -> None:
    part = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_PART
    selection = json.loads((HERE / "data" / f"selection_{part}.json").read_text(encoding="utf-8"))
    out_dir = HERE / "data" / "schematics" / part
    WORK_DIR.mkdir(exist_ok=True)
    out_dir.mkdir(parents=True, exist_ok=True)
    skin = make_skin()
    made = 0
    for number, entry in enumerate(selection["entries"], 1):
        if not entry.get("best"):
            continue
        variant = next(v for v in entry["variants"] if v["output_scale"] == entry["best"]["output_scale"])
        out = out_dir / f"candidate_{number:02d}.svg"
        render(parse_rows(entry["table"]), variant.get("sizes") or {}, out, skin)
        made += 1
        print(f"  후보 {number}: {out.relative_to(HERE)}", flush=True)
    skin.unlink()
    print(f"회로도 {made}개")


if __name__ == "__main__":
    main()
