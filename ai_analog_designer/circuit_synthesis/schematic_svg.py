"""
Circuit Schematic SVG Renderer.
Integrates jiyun's netlistsvg (Yosys JSON + custom MOSFET analog skin) renderer when
Node.js & netlistsvg are installed, with a deterministic pure-Python SVG fallback so
any structure table or SPICE subcircuit always produces a clean schematic SVG.
"""
from __future__ import annotations

import html
import json
import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from .gm_id_sizer import parse_table_text

INPUTS = ("IN1", "IN2", "INP", "INN", "IN+", "IN-")
OUTPUTS = ("OUT", "VOUT")
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


def _size_label(size: dict[str, str] | None) -> str:
    if not size:
        return ""
    if "value" in size:
        return str(size["value"])
    w = size.get("w", "")
    l = size.get("l", "")
    m = f" x{size['m']}" if size.get("m") else ""
    return f"{w}/{l}{m}".strip("/")


def to_yosys_json(table: dict[str, Any], sizes: dict[str, dict[str, str]] | None = None) -> dict[str, Any]:
    """Converts a structure table dict into Yosys JSON consumable by netlistsvg."""
    sizes = sizes or {}
    bits: dict[str, int] = {}
    cells: dict[str, Any] = {}
    counter = iter(range(2, 100000))

    def bit(net: str) -> int:
        if net not in bits:
            bits[net] = next(counter)
        return bits[net]

    def rail(net: str) -> int:
        num = next(counter)
        kind = "vcc" if net == "VDD" else "gnd"
        cells[f"{net}_{num}"] = {
            "type": kind,
            "port_directions": {"A": "input" if kind == "gnd" else "output"},
            "connections": {"A": [num]},
            "attributes": {"name": net},
        }
        return num

    def connect(net: str) -> int:
        return rail(net) if net in ("VDD", "VSS") else bit(net)

    for row in table["rows"]:
        name = row["name"]
        pins = row["pins"]
        kind = row["kind"]
        if kind in ("nmos", "pmos"):
            prefix = "NM" if kind == "nmos" else "PM"
            ref = name if pins.get("B") == NORMAL_BULK[prefix] else f"{name} B={pins.get('B')}"
            top, bottom = ("D", "S") if kind == "nmos" else ("S", "D")
            cells[name] = {
                "type": kind,
                "port_directions": {top: "input", "G": "input", bottom: "output"},
                "connections": {p: [connect(pins[p])] for p in (top, "G", bottom)},
                "attributes": {"ref": ref, "value": _size_label(sizes.get(name))},
            }
        else:
            cells[name] = {
                "type": "r_v" if kind == "res" else "c_v",
                "connections": {"A": [connect(pins["P"])], "B": [connect(pins["N"])]},
                "attributes": {"ref": name, "value": _size_label(sizes.get(name))},
            }

    ports = {net: {"direction": "input", "bits": [bit(net)]} for net in ("IN1", "IN2") if net in bits}
    if "OUT" in bits:
        ports["OUT"] = {"direction": "output", "bits": [bit("OUT")]}
    return {"modules": {"opamp": {"ports": ports, "cells": cells}}}


def _render_with_netlistsvg(table: dict[str, Any], sizes: dict[str, dict[str, str]] | None = None) -> str | None:
    node_exe = os.environ.get("EDAI_NODE", str(Path.home() / "node" / "bin" / "node"))
    netlistsvg_dir = Path(os.environ.get("EDAI_NETLISTSVG", str(Path.home() / "netlistsvg" / "node_modules" / "netlistsvg")))
    js_bin = netlistsvg_dir / "bin" / "netlistsvg.js"
    analog_svg = netlistsvg_dir / "lib" / "analog.svg"
    if not (Path(node_exe).is_file() and js_bin.is_file() and analog_svg.is_file()):
        return None
    try:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            skin_path = tmp_dir / "edai_mos_skin.svg"
            skin_path.write_text(analog_svg.read_text(encoding="utf-8").replace("</svg>", MOS_SYMBOLS + "</svg>"), encoding="utf-8")
            json_path = tmp_dir / "circuit.json"
            svg_path = tmp_dir / "circuit.svg"
            json_path.write_text(json.dumps(to_yosys_json(table, sizes)), encoding="utf-8")
            subprocess.run(
                [node_exe, str(js_bin), str(json_path), "--skin", str(skin_path), "-o", str(svg_path)],
                check=True, capture_output=True, text=True, timeout=60,
            )
            if svg_path.is_file():
                return svg_path.read_text(encoding="utf-8")
    except Exception:
        return None
    return None


def _spice_to_rows(netlist: str) -> tuple[list[dict[str, Any]], dict[str, dict[str, str]]]:
    """Parses a general SPICE netlist/subckt into schematic device rows + sizes."""
    rows: list[dict[str, Any]] = []
    sizes: dict[str, dict[str, str]] = {}
    for raw in netlist.splitlines():
        line = raw.strip()
        if not line or line.startswith(("*", ".", "+")):
            continue
        toks = line.split()
        name = toks[0]
        lead = name[0].upper()
        if lead in ("M", "X") and len(toks) >= 6:
            model = toks[5].upper()
            kind = "pmos" if ("PM" in model or "PFET" in model) else "nmos"
            rows.append({"name": name, "kind": kind, "pins": {"D": toks[1], "G": toks[2], "S": toks[3], "B": toks[4]}})
            kv = dict(t.split("=", 1) for t in toks[6:] if "=" in t)
            sizes[name] = {"w": kv.get("W", kv.get("w", "")), "l": kv.get("L", kv.get("l", ""))}
        elif lead == "Q" and len(toks) >= 5:
            kind = "pnp" if "PNP" in toks[4].upper() else "npn"
            rows.append({"name": name, "kind": kind, "pins": {"C": toks[1], "B": toks[2], "E": toks[3]}})
        elif lead in ("R", "C", "L", "D") and len(toks) >= 4:
            kind_map = {"R": "res", "C": "cap", "L": "ind", "D": "diode"}
            rows.append({"name": name, "kind": kind_map[lead], "pins": {"P": toks[1], "N": toks[2]}})
            sizes[name] = {"value": toks[3]}
    return rows, sizes


def _render_python_svg(rows: list[dict[str, Any]], sizes: dict[str, dict[str, str]] | None = None, title: str = "Circuit Schematic") -> str:
    """Deterministic pure-Python SVG schematic card renderer (no Node/netlistsvg required)."""
    sizes = sizes or {}
    cols = max(1, min(4, len(rows)))
    row_count = max(1, (len(rows) + cols - 1) // cols)
    cell_w, cell_h = 200, 128
    pad_x, pad_y = 24, 54
    width = pad_x * 2 + cols * cell_w
    height = pad_y + row_count * cell_h + 24

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="{width}" height="{height}" role="img" aria-label="{html.escape(title)}">',
        '<rect width="100%" height="100%" rx="12" fill="#fbfcf9" stroke="#dce5dd"/>',
        f'<text x="20" y="30" font-family="Segoe UI, sans-serif" font-size="14" font-weight="700" fill="#173c34">{html.escape(title)} ({len(rows)} devices)</text>',
    ]

    for idx, dev in enumerate(rows):
        c = idx % cols
        r = idx // cols
        x0 = pad_x + c * cell_w + 8
        y0 = pad_y + r * cell_h + 6
        w_box, h_box = cell_w - 16, cell_h - 14
        kind = dev["kind"]
        name = dev["name"]
        lbl = _size_label(sizes.get(name))
        pins = dev["pins"]

        parts.append(f'<g transform="translate({x0},{y0})">')
        parts.append(f'<rect width="{w_box}" height="{h_box}" rx="9" fill="#ffffff" stroke="#cddcc9"/>')
        parts.append(f'<text x="10" y="18" font-family="Consolas, monospace" font-size="12" font-weight="700" fill="#296b55">{html.escape(name)}</text>')
        if lbl:
            parts.append(f'<text x="{w_box - 10}" y="18" text-anchor="end" font-family="Consolas, monospace" font-size="11" fill="#66786f">{html.escape(lbl)}</text>')

        # Draw schematic glyph in center-left
        gx, gy = 18, 28
        if kind in ("nmos", "pmos"):
            parts.append(f'<line x1="{gx}" y1="{gy+22}" x2="{gx+12}" y2="{gy+22}" stroke="#173c34" stroke-width="1.6"/>')
            if kind == "pmos":
                parts.append(f'<circle cx="{gx+9}" cy="{gy+22}" r="2.5" fill="#ffffff" stroke="#173c34" stroke-width="1.4"/>')
            parts.append(f'<line x1="{gx+13}" y1="{gy+10}" x2="{gx+13}" y2="{gy+34}" stroke="#173c34" stroke-width="2"/>')
            parts.append(f'<line x1="{gx+18}" y1="{gy+12}" x2="{gx+18}" y2="{gy+32}" stroke="#173c34" stroke-width="1.6" stroke-dasharray="5 3"/>')
            parts.append(f'<polyline points="{gx+18},{gy+14} {gx+30},{gy+14} {gx+30},{gy+2}" fill="none" stroke="#173c34" stroke-width="1.6"/>')
            parts.append(f'<polyline points="{gx+18},{gy+30} {gx+30},{gy+30} {gx+30},{gy+42}" fill="none" stroke="#173c34" stroke-width="1.6"/>')
            pin_lines = [
                f'D={pins.get("D","")}',
                f'G={pins.get("G","")}',
                f'S={pins.get("S","")}',
                f'B={pins.get("B","")}',
            ]
        elif kind in ("npn", "pnp"):
            parts.append(f'<line x1="{gx}" y1="{gy+22}" x2="{gx+14}" y2="{gy+22}" stroke="#173c34" stroke-width="1.6"/>')
            parts.append(f'<line x1="{gx+14}" y1="{gy+10}" x2="{gx+14}" y2="{gy+34}" stroke="#173c34" stroke-width="2.2"/>')
            parts.append(f'<polyline points="{gx+14},{gy+16} {gx+28},{gy+4}" fill="none" stroke="#173c34" stroke-width="1.6"/>')
            parts.append(f'<polyline points="{gx+14},{gy+28} {gx+28},{gy+40}" fill="none" stroke="#173c34" stroke-width="1.6"/>')
            pin_lines = [f'C={pins.get("C","")}', f'B={pins.get("B","")}', f'E={pins.get("E","")}']
        elif kind == "cap":
            parts.append(f'<line x1="{gx+15}" y1="{gy+4}" x2="{gx+15}" y2="{gy+18}" stroke="#173c34" stroke-width="1.6"/>')
            parts.append(f'<line x1="{gx+4}" y1="{gy+18}" x2="{gx+26}" y2="{gy+18}" stroke="#173c34" stroke-width="2.2"/>')
            parts.append(f'<line x1="{gx+4}" y1="{gy+25}" x2="{gx+26}" y2="{gy+25}" stroke="#173c34" stroke-width="2.2"/>')
            parts.append(f'<line x1="{gx+15}" y1="{gy+25}" x2="{gx+15}" y2="{gy+40}" stroke="#173c34" stroke-width="1.6"/>')
            pin_lines = [f'+={pins.get("P","")}', f'-={pins.get("N","")}']
        else:
            parts.append(f'<polyline points="{gx+15},{gy+4} {gx+15},{gy+10} {gx+21},{gy+13} {gx+9},{gy+18} {gx+21},{gy+23} {gx+9},{gy+28} {gx+15},{gy+31} {gx+15},{gy+40}" fill="none" stroke="#173c34" stroke-width="1.6"/>')
            pin_lines = [f'1={pins.get("P","")}', f'2={pins.get("N","")}']

        for p_idx, pl in enumerate(pin_lines):
            parts.append(
                f'<text x="64" y="{42 + p_idx * 15}" font-family="Consolas, monospace" font-size="11" fill="#39583e">{html.escape(pl)}</text>'
            )
        parts.append("</g>")

    parts.append("</svg>")
    return "\n".join(parts)


def render_schematic_svg(
    *,
    structure_table: str | None = None,
    netlist: str | None = None,
    sizes: dict[str, dict[str, str]] | None = None,
    title: str = "Circuit Schematic",
) -> dict[str, Any]:
    """
    Renders an SVG schematic from either a structure-table string or a SPICE netlist.
    Prefers netlistsvg when available for structure tables; falls back cleanly to pure-Python SVG.
    """
    if structure_table:
        tbl = parse_table_text(structure_table)
        svg = _render_with_netlistsvg(tbl, sizes)
        if svg:
            return {"ok": True, "renderer": "netlistsvg", "svg": svg, "device_count": len(tbl["rows"])}
        return {
            "ok": True,
            "renderer": "python_svg",
            "svg": _render_python_svg(tbl["rows"], sizes, title=title),
            "device_count": len(tbl["rows"]),
        }

    if netlist:
        rows, parsed_sizes = _spice_to_rows(netlist)
        merged_sizes = {**parsed_sizes, **(sizes or {})}
        return {
            "ok": True,
            "renderer": "python_svg",
            "svg": _render_python_svg(rows, merged_sizes, title=title),
            "device_count": len(rows),
        }

    raise ValueError("Either 'structure_table' or 'netlist' must be provided.")
