"""
Deterministic gm/ID Transistor Sizing & Structure-Table Engine.
Integrates jiyun's GF180 6V gm/ID sizing algorithm, structure-table parser/serializer,
and PDG 5-terminal op-amp compatibility checker with both ngspice (GF180 PDK) and
LTspice physical subcircuit output for AnalogVerifier.
"""
from __future__ import annotations

import json
import math
import os
import re
import shutil
import subprocess
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any

import numpy as np

_DATA_DIR = Path(__file__).resolve().parent / "data"
TABLE_FILE = _DATA_DIR / "devices_gf180.json"

MOS_PINS = ("D", "G", "S", "B")
TWO_PINS = ("P", "N")
KIND_PREFIX = {"nmos": "NM", "pmos": "PM", "res": "R", "cap": "C"}
KIND_ORDER = ("pmos", "nmos", "res", "cap")
POWER_PORTS = ("VDD", "VSS")
PORTS_5 = ("VDD", "VSS", "IN1", "IN2", "OUT")
NGSPICE_PORT_NAMES = {"INP": "IN1", "INN": "IN2", "OUT": "OUT", "VDD": "VDD", "VSS": "VSS"}
NGSPICE_MODELS = {"nfet_06v0": "nmos", "pfet_06v0": "pmos"}
NGSPICE_MODEL_OF = {"nmos": "nfet_06v0", "pmos": "pfet_06v0"}
LTSPICE_MODEL_OF = {"nmos": "GNM", "pmos": "GPM"}
DEFAULT_MOS = {"w": "10u", "l": "1u"}
DEFAULT_VALUE = {"res": "10k", "cap": "1p"}

# Standard Level-1 physical MOSFET models matching GF180 6V nominal thresholds
LTSPICE_GENERIC_MODELS = (
    ".model GNM NMOS(LEVEL=1 VTO=0.65 KP=180u GAMMA=0.45 PHI=0.7 LAMBDA=0.04)",
    ".model GPM PMOS(LEVEL=1 VTO=-0.70 KP=75u GAMMA=0.45 PHI=0.7 LAMBDA=0.05)",
)

# Role -> (target gm/ID [1/V], channel length [um])
ROLE_TARGETS: dict[str, tuple[float, float]] = {
    "input": (12.0, 1.0),
    "diode": (8.0, 2.0),
    "source": (8.0, 2.0),
    "cascode": (12.0, 1.0),
    "gain": (10.0, 1.0),
    "other": (10.0, 1.0),
}

UNIT_CURRENT = 20e-6
BIAS_CURRENT = 20e-6
CASCODE_HEADROOM = 0.25
BODY_EFFECT_MARGIN = 0.20
SAT_MARGIN = 0.05
OFF_CURRENT = 1e-9
W_MIN_UM, W_MAX_UM = 0.5, 100.0
INITIAL_WIDTH_UM = 10.0
MAX_ITERATIONS = 8
CONVERGED_CHANGE = 0.05

_DEVICE_TABLE_CACHE: dict[str, Any] | None = None


def load_device_table(table_path: Path | None = None) -> dict[str, Any]:
    """Loads the GF180 6V gm/ID characteristic lookup table."""
    global _DEVICE_TABLE_CACHE
    if table_path is None and _DEVICE_TABLE_CACHE is not None:
        return _DEVICE_TABLE_CACHE
    path = table_path or TABLE_FILE
    data = json.loads(path.read_text(encoding="utf-8"))["devices"]
    if table_path is None:
        _DEVICE_TABLE_CACHE = data
    return data


def lookup_gm_id(kind: str, length_um: float, gm_id: float, field: str) -> float:
    """Interpolates device characteristics (j, vgs, vdsat) from GF180 lookup table."""
    table = load_device_table()
    branch = table["n" if kind == "nmos" else "p"]
    len_key = str(float(length_um))
    if len_key not in branch:
        # Nearest available channel length
        avail = sorted(branch.keys(), key=lambda k: abs(float(k) - float(length_um)))
        len_key = avail[0]
    data = branch[len_key]
    return float(np.interp(gm_id, data["gm_id"], data[field]))


def _port_rank(net: str) -> tuple[int, int] | None:
    order = {"VDD": 0, "VSS": 1, "IN1": 2, "IN2": 3, "OUT": 4}
    if net in order:
        return (order[net], 0)
    if re.fullmatch(r"VB\d+", net):
        return (5, int(net[2:]))
    if re.fullmatch(r"IB\d+", net):
        return (6, int(net[2:]))
    return None


def parse_table_text(text: str) -> dict[str, Any]:
    """Parses structure-table text (either newline- or ';'-separated) into a structured dict."""
    rows: list[dict[str, Any]] = []
    kinds = {prefix: kind for kind, prefix in KIND_PREFIX.items()}
    normalized = text.replace(";", "\n")
    for raw_line in normalized.strip().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("*"):
            continue
        tokens = line.split()
        m = re.match(r"[A-Z]+", tokens[0].upper())
        prefix = m.group() if m else ""
        if prefix not in kinds:
            raise ValueError(f"Unknown device prefix in structure row: {line}")
        kind = kinds[prefix]
        pins = dict(token.split("=", 1) for token in tokens[1:] if "=" in token)
        expected = MOS_PINS if kind in ("nmos", "pmos") else TWO_PINS
        if tuple(pins.keys()) != expected:
            raise ValueError(f"Invalid pin order for {tokens[0]}: expected {expected}, got {tuple(pins.keys())}")
        rows.append({"name": tokens[0].upper(), "kind": kind, "pins": pins, "source_name": tokens[0].upper(), "params": {}})
    if not rows:
        raise ValueError("Structure table has no device rows.")
    ports = sorted({net for row in rows for net in row["pins"].values() if _port_rank(net)}, key=_port_rank)  # type: ignore[arg-type]
    return {"ports": ports, "rows": rows}


def table_text(table: dict[str, Any]) -> str:
    """Formats a structure table dict into canonical text."""
    return "\n".join(
        f"{row['name']} " + " ".join(f"{pin}={net}" for pin, net in row["pins"].items())
        for row in table["rows"]
    )


def parse_ngspice_subckt(text: str) -> dict[str, Any]:
    """Parses a GF180 ngspice .subckt into a normalized circuit dict."""
    devices: list[dict[str, Any]] = []
    ports: list[str] = []
    rename: dict[str, str] = {}
    for raw in text.splitlines():
        tokens = raw.split()
        if not tokens or tokens[0].startswith("*"):
            continue
        head = tokens[0].upper()
        if head == ".SUBCKT":
            rename = {pin: NGSPICE_PORT_NAMES.get(pin.upper(), pin.upper()) for pin in tokens[2:]}
            ports = [rename[pin] for pin in tokens[2:]]
            continue
        if head.startswith("."):
            continue
        net = lambda node, _r=rename: _r.get(node, node)  # noqa: E731
        if head.startswith(("X", "M")):
            model = tokens[5] if len(tokens) > 5 else ""
            if model in NGSPICE_MODELS:
                kind = NGSPICE_MODELS[model]
            elif "PM" in model.upper() or "PFET" in model.upper():
                kind = "pmos"
            elif "NM" in model.upper() or "NFET" in model.upper():
                kind = "nmos"
            else:
                raise ValueError(f"Unsupported MOSFET model '{model}' in line: {raw.strip()}")
            params = dict(token.split("=", 1) for token in tokens[6:] if "=" in token)
            devices.append({"kind": kind, "pins": dict(zip(MOS_PINS, map(net, tokens[1:5]))), "params": params, "source_name": tokens[0]})
        elif head[0] in "RC" and len(tokens) >= 4:
            kind = "res" if head[0] == "R" else "cap"
            devices.append({"kind": kind, "pins": dict(zip(TWO_PINS, map(net, tokens[1:3]))), "params": {"value": tokens[3]}, "source_name": tokens[0]})
    return {"ports": ports, "devices": devices}


def circuit_to_table(circuit: dict[str, Any]) -> dict[str, Any]:
    """Normalizes a parsed circuit dict into canonical structure table with N1, N2... nets."""
    ports = sorted(
        {net for dev in circuit["devices"] for net in dev["pins"].values() if _port_rank(net)} | set(circuit["ports"]),
        key=_port_rank,  # type: ignore[arg-type]
    )

    def sort_key(indexed: tuple[int, dict[str, Any]]) -> tuple[int, int, int]:
        index, dev = indexed
        touching = sum(net in ports for net in dev["pins"].values())
        return (KIND_ORDER.index(dev["kind"]), -touching, index)

    ordered = [dev for _, dev in sorted(enumerate(circuit["devices"]), key=sort_key)]
    inner: dict[str, str] = {}
    counters: dict[str, int] = {}
    rows: list[dict[str, Any]] = []
    for dev in ordered:
        pins: dict[str, str] = {}
        for pin, net in dev["pins"].items():
            if net not in ports:
                inner.setdefault(net, f"N{len(inner) + 1}")
                net = inner[net]
            pins[pin] = net
        counters[dev["kind"]] = counters.get(dev["kind"], 0) + 1
        rows.append({
            "name": f"{KIND_PREFIX[dev['kind']]}{counters[dev['kind']]}",
            "kind": dev["kind"],
            "pins": pins,
            "source_name": dev.get("source_name", ""),
            "params": dev.get("params", {}),
        })
    return {"ports": ports, "rows": rows}


def rule_problems(table: dict[str, Any]) -> list[str]:
    """Deterministic topology sanity checks before sizing or simulation."""
    found: list[str] = []
    names = [row["name"] for row in table["rows"]]
    if len(set(names)) != len(names):
        found.append("Duplicate device names exist in structure table.")
    count = Counter(net for row in table["rows"] for net in row["pins"].values())
    found.extend(f"Missing required port: {port}" for port in PORTS_5 if port not in count)
    gates = {row["pins"].get("G") for row in table["rows"]}
    found.extend(f"Input {port} is not connected to any transistor gate." for port in ("IN1", "IN2") if port not in gates)
    floating = [net for net, n in count.items() if n < 2 and net not in PORTS_5 and not net.startswith(("VB", "IB"))]
    if floating:
        found.append(f"Floating single-connection internal nodes: {', '.join(floating)}")
    return found


def mos_rows(table: dict[str, Any]) -> list[dict[str, Any]]:
    return [row for row in table["rows"] if row["kind"] in ("nmos", "pmos")]


def assign_roles(table: dict[str, Any]) -> dict[str, str]:
    """Classifies each MOSFET into input / diode / source / cascode / gain / other."""
    rows = mos_rows(table)
    diode_nets = {row["pins"]["G"] for row in rows if row["pins"]["G"] == row["pins"]["D"]}
    bias_nets = {net for net in table["ports"] if net.startswith(("VB", "IB"))}
    mirror_nets = diode_nets | bias_nets
    roles: dict[str, str] = {}
    for row in rows:
        gate, drain, source = row["pins"]["G"], row["pins"]["D"], row["pins"]["S"]
        if gate in ("IN1", "IN2"):
            roles[row["name"]] = "input"
        elif gate == drain:
            roles[row["name"]] = "diode"
        elif gate in mirror_nets:
            roles[row["name"]] = "source" if source in POWER_PORTS else "cascode"
        elif source in POWER_PORTS:
            roles[row["name"]] = "gain"
        else:
            roles[row["name"]] = "other"
    return roles


def mirror_groups(table: dict[str, Any], roles: dict[str, str]) -> dict[str, tuple[float, float]]:
    """Aligns (gm/ID, L) for transistors sharing (kind, Gate, Source) to preserve current mirror ratios."""
    groups: dict[tuple[str, str, str], list[str]] = {}
    for row in mos_rows(table):
        key = (row["kind"], row["pins"]["G"], row["pins"]["S"])
        groups.setdefault(key, []).append(row["name"])
    targets: dict[str, tuple[float, float]] = {}
    for members in groups.values():
        member_roles = [roles[name] for name in members]
        lead = "diode" if "diode" in member_roles else member_roles[0]
        gm_id, _ = ROLE_TARGETS[lead]
        length = max(ROLE_TARGETS[role][1] for role in member_roles)
        for name in members:
            targets[name] = (gm_id, length)
    return targets


def bias_lines(table: dict[str, Any], targets: dict[str, tuple[float, float]], *, spice_dialect: str = "ltspice") -> tuple[list[str], set[str]]:
    """Generates internal bias voltage/current sources for VB# / IB# ports."""
    lines: list[str] = []
    fixed: set[str] = set()
    rows = mos_rows(table)
    dc_kw = "" if spice_dialect == "ltspice" else "dc "
    for port in table["ports"]:
        if port.startswith("VB"):
            gated = [row for row in rows if row["pins"]["G"] == port]
            if not gated:
                continue
            row = gated[0]
            gm_id, length = targets[row["name"]]
            vgs = abs(lookup_gm_id(row["kind"], length, gm_id, "vgs"))
            if row["pins"]["S"] in POWER_PORTS:
                level = vgs
                fixed.update(r["name"] for r in gated if r["pins"]["S"] in POWER_PORTS)
            else:
                below = abs(lookup_gm_id(row["kind"], ROLE_TARGETS["source"][1], ROLE_TARGETS["source"][0], "vdsat"))
                level = vgs + below + CASCODE_HEADROOM + BODY_EFFECT_MARGIN
            if row["kind"] == "nmos":
                lines.append(f"VBIAS_{port} {port} VSS {dc_kw}{level:.4f}".strip())
            else:
                lines.append(f"VBIAS_{port} VDD {port} {dc_kw}{level:.4f}".strip())
        elif port.startswith("IB"):
            touching = [(row, pin) for row in rows for pin, net in row["pins"].items() if net == port and pin != "B"]
            sinks = any(
                (row["kind"] == "nmos" and pin == "S") or (row["kind"] == "pmos" and pin == "D")
                for row, pin in touching
            )
            if sinks:
                lines.append(f"IBIAS_{port} {port} VSS {dc_kw}{BIAS_CURRENT}".strip())
            else:
                lines.append(f"IBIAS_{port} VDD {port} {dc_kw}{BIAS_CURRENT}".strip())
    return lines, fixed


def size_text(width_um: float, length_um: float) -> dict[str, str]:
    count = max(1, math.ceil(width_um / W_MAX_UM))
    width = min(max(width_um / count, W_MIN_UM), W_MAX_UM)
    size: dict[str, str] = {"w": f"{width:.3g}u", "l": f"{length_um:g}u"}
    if count > 1:
        size["m"] = str(count)
    return size


def total_width(size: dict[str, str]) -> float:
    return float(size["w"].rstrip("u")) * int(size.get("m", 1))


def width_for_current(kind: str, current: float, gm_id: float, length_um: float) -> float:
    """Computes transistor width [um] yielding `current` at target `gm/ID`."""
    j_sq = max(lookup_gm_id(kind, length_um, gm_id, "j"), 1e-12)
    return current / j_sq * length_um


def startup_devices(table: dict[str, Any]) -> set[str]:
    """Identifies startup switch/sense devices by topology pattern."""
    mos = mos_rows(table)
    diode_nets = {row["pins"]["G"] for row in mos if row["pins"]["G"] == row["pins"]["D"]}
    by_net: dict[str, list[tuple[dict[str, Any], str]]] = {}
    for row in table["rows"]:
        for pin, net in row["pins"].items():
            by_net.setdefault(net, []).append((row, pin))
    found: set[str] = set()
    for net, links in by_net.items():
        if net in POWER_PORTS or net in table["ports"] or net in diode_nets:
            continue
        pull = [r for r, _ in links if r["kind"] == "res" and set(r["pins"].values()) - {net} <= set(POWER_PORTS)]
        drains = [r for r, p in links if r["kind"] in ("nmos", "pmos") and p == "D"]
        gates = [r for r, p in links if r["kind"] in ("nmos", "pmos") and p == "G"]
        if not pull or len(drains) != 1 or len(pull) + len(drains) + len(gates) != len(links):
            continue
        switches = [r for r in gates if r["pins"]["D"] in diode_nets or r["pins"]["S"] in diode_nets]
        if switches:
            found |= {r["name"] for r in switches} | {drains[0]["name"]}
    return found


def saturation_report(op: dict[str, Any], table: dict[str, Any]) -> dict[str, list[str]]:
    startup = startup_devices(table)
    checked = {n: d for n, d in op["devices"].items() if n not in startup}
    off = [n for n, d in checked.items() if d is None or d["id"] < OFF_CURRENT]
    triode = [n for n, d in checked.items() if d and d["id"] >= OFF_CURRENT and d["vds"] < d["vdsat"] + SAT_MARGIN]
    return {"off": off, "triode": triode, "startup": sorted(startup)}


def to_ngspice_subckt(
    table: dict[str, Any],
    sizes: dict[str, dict[str, str]] | None = None,
    name: str = "opamp",
    polarity: tuple[str, str] = ("IN1", "IN2"),
    extra_lines: list[str] | None = None,
) -> str:
    """Renders a GF180 ngspice .subckt netlist."""
    sizes = sizes or {}
    rename = {polarity[0]: "INP", polarity[1]: "INN"}
    lines = [f".subckt {name} INP INN OUT VDD VSS"]
    for row in table["rows"]:
        nets = [rename.get(net, net) for net in row["pins"].values()]
        size = sizes.get(row["name"], {})
        if row["kind"] in NGSPICE_MODEL_OF:
            params = {**DEFAULT_MOS, **{k: v for k, v in size.items() if k in ("w", "l", "m")}}
            lines.append(
                f"X{row['name']} {' '.join(nets)} {NGSPICE_MODEL_OF[row['kind']]} "
                + " ".join(f"{k}={v}" for k, v in params.items())
            )
        else:
            lines.append(f"{row['name']} {' '.join(nets)} {size.get('value', DEFAULT_VALUE[row['kind']])}")
    lines.extend(extra_lines or [])
    lines.append(f".ends {name}")
    return "\n".join(lines) + "\n"


def to_ltspice_subckt(
    table: dict[str, Any],
    sizes: dict[str, dict[str, str]] | None = None,
    subckt_name: str = "OPAMP",
    pin_names: list[str] | None = None,
    polarity: tuple[str, str] = ("IN1", "IN2"),
    extra_lines: list[str] | None = None,
) -> str:
    """
    Renders a pure physical LTspice .subckt netlist (M-devices + R/C + .model GNM/GPM),
    strictly compliant with AnalogVerifier's NetlistValidator physical guardrails.
    """
    sizes = sizes or {}
    # Map canonical ports (IN1, IN2, OUT, VDD, VSS) -> target DUT pin names if provided
    target_pins = pin_names or ["INP", "INN", "OUT", "VDD", "VSS"]
    inp_pin = next((p for p in target_pins if any(k in p.upper() for k in ("INP", "IN+", "1IN+", "IN1_P", "NONINV"))), target_pins[0])
    inn_pin = next((p for p in target_pins if p != inp_pin and any(k in p.upper() for k in ("INN", "INM", "IN-", "1IN-", "IN1_N", "INV"))), target_pins[1] if len(target_pins) > 1 else "INN")
    out_pin = next((p for p in target_pins if "OUT" in p.upper()), target_pins[2] if len(target_pins) > 2 else "OUT")
    vdd_pin = next((p for p in target_pins if p.upper() in ("VCC", "VDD", "VP", "V+", "AVCC", "PVCC")), "VDD")
    vss_pin = next((p for p in target_pins if p.upper() in ("GND", "VSS", "VEE", "VM", "V-", "COM")), "VSS")

    rename = {
        polarity[0]: inp_pin,
        polarity[1]: inn_pin,
        "OUT": out_pin,
        "VDD": vdd_pin,
        "VSS": vss_pin,
    }
    header_pins = " ".join(target_pins)
    lines = [
        f"* Physical gm/ID Sized Subcircuit for {subckt_name}",
        *LTSPICE_GENERIC_MODELS,
        "",
        f".subckt {subckt_name} {header_pins}",
    ]
    for row in table["rows"]:
        nets = [rename.get(net, net) for net in row["pins"].values()]
        size = sizes.get(row["name"], {})
        if row["kind"] in LTSPICE_MODEL_OF:
            w_val = size.get("w", DEFAULT_MOS["w"])
            l_val = size.get("l", DEFAULT_MOS["l"])
            m_mult = int(size.get("m", 1))
            # Scale width if m > 1 for clean LTspice Level-1 compatibility
            if m_mult > 1 and w_val.endswith("u"):
                eff_w = f"{float(w_val[:-1]) * m_mult:.3g}u"
            else:
                eff_w = w_val
            lines.append(f"M{row['name']} {' '.join(nets)} {LTSPICE_MODEL_OF[row['kind']]} W={eff_w} L={l_val}")
        else:
            lines.append(f"{row['name']} {' '.join(nets)} {size.get('value', DEFAULT_VALUE[row['kind']])}")
    for el in (extra_lines or []):
        # Rewrite VDD/VSS inside extra_lines to match target subckt rail names
        tokens = el.split()
        rewritten = [rename.get(t, t) for t in tokens]
        lines.append(" ".join(rewritten))
    lines.append(f".ends {subckt_name}")
    return "\n".join(lines) + "\n"


def _estimate_branch_currents(table: dict[str, Any], roles: dict[str, str], unit_current: float, output_scale: float) -> dict[str, float]:
    """Analytical branch-current estimator for offline/LTspice gm/ID sizing without ngspice."""
    currents: dict[str, float] = {}
    rows = mos_rows(table)
    at_output = {row["name"] for row in rows if row["pins"]["D"] == "OUT"}
    # Identify differential input pairs (shared source node)
    input_sources: dict[str, list[str]] = {}
    for row in rows:
        if roles[row["name"]] == "input":
            input_sources.setdefault(row["pins"]["S"], []).append(row["name"])
    for row in rows:
        name = row["name"]
        role = roles[name]
        if name in at_output:
            currents[name] = unit_current * output_scale
        elif role == "input":
            pair_count = max(1, len(input_sources.get(row["pins"]["S"], [name])))
            currents[name] = unit_current / pair_count
        elif role == "gain":
            currents[name] = unit_current * max(1.0, output_scale)
        else:
            currents[name] = unit_current
    return currents


def _run_ngspice_op(subckt: str, table: dict[str, Any], pdk_dir: str, ngspice_exe: str, vdd: float = 5.0) -> dict[str, Any]:
    """Runs unity-gain follower DC operating point in ngspice + GF180 PDK."""
    names = [row["name"] for row in mos_rows(table)]
    prints = ["print " + " ".join(f"@m.x1.x{name.lower()}.m0[{f}]" for f in ("id", "vds", "vdsat")) for name in names]
    vcm = vdd / 2.0
    deck = "\n".join([
        "* gm_id_sizer operating point",
        f".include {pdk_dir}/design.ngspice",
        f".lib {pdk_dir}/sm141064.ngspice typical",
        subckt,
        "X1 VCM INN OUT VDD 0 opamp",
        f"VDD VDD 0 {vdd}",
        f"VCM VCM 0 {vcm}",
        "LFB OUT INN 1G",
        "RL OUT VCM 100k",
        ".control",
        "op",
        "print v(out)",
        *prints,
        ".endc",
        ".end",
        "",
    ])
    with tempfile.NamedTemporaryFile("w", suffix=".cir", delete=False, encoding="utf-8") as handle:
        handle.write(deck)
        path = Path(handle.name)
    try:
        done = subprocess.run([ngspice_exe, "-b", str(path)], capture_output=True, text=True, timeout=120)
    except subprocess.TimeoutExpired:
        return {"vout": None, "devices": {}, "error": "ngspice op simulation timed out (120s)"}
    finally:
        path.unlink(missing_ok=True)
    values = dict(re.findall(r"^(\S+) = (\S+)$", done.stdout, flags=re.MULTILINE))
    if "v(out)" not in values:
        return {"vout": None, "devices": {}, "error": (done.stdout + done.stderr)[-400:]}
    devices: dict[str, Any] = {}
    for name in names:
        try:
            devices[name] = {f: abs(float(values[f"@m.x1.x{name.lower()}.m0[{f}]"])) for f in ("id", "vds", "vdsat")}
        except KeyError:
            devices[name] = None
    return {"vout": float(values["v(out)"]), "devices": devices}


def auto_size(
    table: dict[str, Any],
    passive_values: dict[str, dict[str, str]] | None = None,
    unit_current: float = UNIT_CURRENT,
    output_scale: float = 1.0,
    *,
    simulator: str = "auto",
    subckt_name: str = "OPAMP",
    pin_names: list[str] | None = None,
    vdd: float = 5.0,
) -> dict[str, Any]:
    """
    Computes gm/ID-based transistor widths/lengths for a structure table.

    - When `simulator="ngspice"` (or `"auto"` with ngspice + GF180 PDK available),
      performs iterative DC operating-point sizing using GF180 ngspice.
    - Otherwise performs deterministic analytical gm/ID sizing from `devices_gf180.json`
      and emits both an LTspice physical `.subckt` and a GF180 ngspice `.subckt`.
    """
    roles = assign_roles(table)
    targets = mirror_groups(table, roles)
    at_output = {row["name"] for row in mos_rows(table) if row["pins"]["D"] == "OUT"}
    scale = {name: output_scale if name in at_output else 1.0 for name in targets}

    ngspice_exe = os.environ.get("EDAI_NGSPICE") or shutil.which("ngspice") or shutil.which("ngspice_con")
    pdk_dir = os.environ.get("EDAI_PDK_DIR", str(Path.home() / "pdk" / "gf180mcu_fd_pr" / "models" / "ngspice"))
    use_ngspice = (
        simulator == "ngspice"
        or (simulator == "auto" and bool(ngspice_exe) and Path(pdk_dir, "design.ngspice").is_file())
    )

    extra_ng, fixed = bias_lines(table, targets, spice_dialect="ngspice")
    extra_lt, _ = bias_lines(table, targets, spice_dialect="ltspice")

    sizes: dict[str, dict[str, str]] = {
        name: size_text(INITIAL_WIDTH_UM * scale[name], targets[name][1]) for name in targets
    }
    for name in fixed:
        row = next(r for r in table["rows"] if r["name"] == name)
        gm_id, length = targets[name]
        sizes[name] = size_text(width_for_current(row["kind"], unit_current * scale[name], gm_id, length), length)
    sizes.update(passive_values or {})
    kinds = {row["name"]: row["kind"] for row in mos_rows(table)}

    if use_ngspice and ngspice_exe:
        vcm = vdd / 2.0
        polarity: tuple[str, str] | None = None
        op: dict[str, Any] | None = None
        for cand in (("IN1", "IN2"), ("IN2", "IN1")):
            trial = _run_ngspice_op(to_ngspice_subckt(table, sizes, polarity=cand, extra_lines=extra_ng), table, pdk_dir, ngspice_exe, vdd=vdd)
            if trial["vout"] is not None and (op is None or op["vout"] is None or abs(trial["vout"] - vcm) < abs(op["vout"] - vcm)):
                polarity, op = cand, trial
        if polarity is None or op is None:
            return {"ok": False, "mode": "ngspice", "reason": "ngspice DC operating point failed", "roles": roles}
        iterations = 0
        for iterations in range(1, MAX_ITERATIONS + 1):
            change = 0.0
            for name, info in op["devices"].items():
                if name in fixed or info is None or info["id"] < OFF_CURRENT:
                    continue
                gm_id, length = targets[name]
                width = min(max(width_for_current(kinds[name], info["id"], gm_id, length), W_MIN_UM), 20 * W_MAX_UM)
                old = total_width(sizes[name])
                change = max(change, abs(width - old) / max(old, 1e-9))
                sizes[name] = size_text(width, length)
            op = _run_ngspice_op(to_ngspice_subckt(table, sizes, polarity=polarity, extra_lines=extra_ng), table, pdk_dir, ngspice_exe, vdd=vdd)
            if op["vout"] is None:
                return {"ok": False, "mode": "ngspice", "reason": "ngspice OP failed during sizing iteration", "roles": roles, "iterations": iterations}
            if change < CONVERGED_CHANGE:
                break
        report = saturation_report(op, table)
        output_ok = abs(op["vout"] - vcm) <= 0.5
        ok = output_ok and not report["off"] and not report["triode"]
        reason = "" if ok else ("Output VOUT deviated from VCM" if not output_ok else "Some devices are not in saturation")
        return {
            "ok": ok,
            "mode": "ngspice",
            "reason": reason,
            "subckt_ngspice": to_ngspice_subckt(table, sizes, polarity=polarity, extra_lines=extra_ng),
            "subckt_ltspice": to_ltspice_subckt(table, sizes, subckt_name=subckt_name, pin_names=pin_names, polarity=polarity, extra_lines=extra_lt),
            "sizes": sizes,
            "polarity": polarity,
            "roles": roles,
            "targets": {k: {"gm_id": v[0], "length_um": v[1]} for k, v in targets.items()},
            "vout": op["vout"],
            "iterations": iterations,
            **report,
        }

    # Analytical gm/ID sizing mode (deterministic, zero external simulator dependency)
    branch_currents = _estimate_branch_currents(table, roles, unit_current, output_scale)
    for name, (gm_id, length) in targets.items():
        id_est = branch_currents.get(name, unit_current)
        w_um = min(max(width_for_current(kinds[name], id_est, gm_id, length), W_MIN_UM), 20 * W_MAX_UM)
        sizes[name] = size_text(w_um, length)

    polarity = ("IN1", "IN2")
    return {
        "ok": True,
        "mode": "analytical_gm_id",
        "reason": "Sized deterministically from GF180 6V gm/ID lookup table; verify in LTspice/ngspice.",
        "subckt_ngspice": to_ngspice_subckt(table, sizes, polarity=polarity, extra_lines=extra_ng),
        "subckt_ltspice": to_ltspice_subckt(table, sizes, subckt_name=subckt_name, pin_names=pin_names, polarity=polarity, extra_lines=extra_lt),
        "sizes": sizes,
        "polarity": polarity,
        "roles": roles,
        "targets": {k: {"gm_id": v[0], "length_um": v[1]} for k, v in targets.items()},
        "estimated_currents_a": branch_currents,
        "startup": sorted(startup_devices(table)),
        "iterations": 1,
    }


def check_opamp_pdg(pins: list[dict[str, Any]], port_dependencies: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """
    Verifies whether a DUT pin interface matches a standard 5-terminal op-amp channel
    (IN1, IN2, OUT, VDD, VSS) for FLAN-T5 / gm-ID topology synthesis.
    """
    role_precedence = {"GROUND": 0, "POWER": 0, "BIAS": 1, "REFERENCE": 1, "ENABLE": 2, "CONTROL": 2, "SIGNAL": 3, "INPUT": 3, "FEEDBACK": 4, "OUTPUT": 4}
    norm_pins = [
        {"name": p["name"], "role": str(p.get("role") or "SIGNAL").upper(), "description": p.get("description", "")}
        for p in pins if isinstance(p, dict) and str(p.get("role", "")).upper() != "NC"
    ]
    power = [p["name"] for p in norm_pins if p["role"] == "POWER"]
    ground = [p["name"] for p in norm_pins if p["role"] == "GROUND"]
    outputs = [p["name"] for p in norm_pins if role_precedence.get(p["role"], 3) == 4]
    signals = [p["name"] for p in norm_pins if role_precedence.get(p["role"], 3) == 3]

    # Try channel matching via port_dependencies if present, else fallback to global signals
    pin_map = {p["name"]: p for p in norm_pins}
    channels: list[dict[str, Any]] = []
    for out in outputs:
        deps = [d["source"] for d in (port_dependencies or []) if d.get("target") == out and d.get("source") in pin_map]
        sig_inputs = [n for n in deps if role_precedence.get(pin_map[n]["role"], 3) == 3]
        if not sig_inputs and len(outputs) == 1:
            sig_inputs = signals
        elif not sig_inputs and len(outputs) > 1:
            # Multi-channel heuristic (e.g. 1OUT <-> 1IN+/1IN-)
            m = re.match(r"(\d+)", out)
            if m:
                ch = m.group(1)
                sig_inputs = [s for s in signals if ch in s]
        problems: list[str] = []
        if len(sig_inputs) != 2:
            problems.append(f"Expected 2 differential signal inputs for {out}, found {len(sig_inputs)}")
        if not power:
            problems.append("Missing POWER pin")
        if not ground:
            problems.append("Missing GROUND pin")
        channels.append({"output": out, "inputs": sig_inputs, "ok": not problems, "problems": problems})

    usable = [c for c in channels if c["ok"]]
    return {
        "ok": bool(usable),
        "power_pins": power,
        "ground_pins": ground,
        "channels": channels,
        "chosen": usable[0] if usable else None,
    }
