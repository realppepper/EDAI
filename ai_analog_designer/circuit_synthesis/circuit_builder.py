"""
Structured Python SPICE Circuit Builder & ERC (Electrical Rules Check).
Eliminates raw SPICE syntax errors (wrong pin counts, W/L on BJTs, inline model params,
duplicate instance names, node-0 ground leaks, disconnected ports) by serializing
validated structured JSON IR directly into strict LTspice/ngspice `.subckt` netlists.
"""
from __future__ import annotations

import json
import re
from collections import defaultdict, deque
from typing import Any

DEFAULT_MODELS: dict[str, str] = {
    "QNPN": ".model QNPN NPN(IS=1e-16 BF=150 VAF=100 CJE=1p CJC=0.5p TF=0.3n)",
    "QPNP": ".model QPNP PNP(IS=1e-16 BF=80 VAF=80 CJE=1p CJC=0.5p TF=0.5n)",
    "NMOS_MOD": ".model NMOS_MOD NMOS(LEVEL=1 VTO=0.7 KP=120u LAMBDA=0.02)",
    "PMOS_MOD": ".model PMOS_MOD PMOS(LEVEL=1 VTO=-0.7 KP=50u LAMBDA=0.02)",
    "D1N4148": ".model D1N4148 D(IS=2.52n RS=0.568 N=1.752 CJO=4p VJ=0.5 M=0.333 BV=100)",
}

_PROHIBITED_KINDS = {"v", "vsource", "i", "isource", "b", "bsource", "a", "adevice", "e", "g", "f", "h"}


def _clean_node(node: Any, neg_rail: str | None) -> str:
    s = re.sub(r"[^A-Za-z0-9_]", "_", str(node or "").strip())
    if not s:
        return neg_rail or "N_INT"
    if s in ("0", "GND", "gnd") and neg_rail:
        return neg_rail
    return s


def _clean_model_name(name: Any, default: str) -> str:
    s = re.sub(r"\(.*\)", "", str(name or "")).strip()
    s = re.sub(r"[^A-Za-z0-9_]", "_", s)
    return s or default


def _infer_neg_rail(pins: list[dict[str, Any]] | list[str]) -> str | None:
    for p in pins:
        if isinstance(p, dict):
            name = str(p.get("name") or "")
            role = str(p.get("role") or "").upper()
            desc = str(p.get("description") or "").lower()
            if role == "GROUND" or "neg" in desc or name.upper() in ("VSS", "VEE", "GND", "V_N", "VN", "V"):
                return name
        else:
            s = str(p)
            if s.upper() in ("VSS", "VEE", "GND", "V_N", "VN", "V"):
                return s
    return None


class CircuitBuilder:
    """Builds strict physical transistor-level SPICE subcircuits from structured JSON IR."""

    def __init__(self, subckt_name: str, pins: list[dict[str, Any]] | list[str]):
        self.subckt_name = re.sub(r"[^A-Za-z0-9_]", "_", subckt_name).upper() or "DUT"
        self.pins = pins or []
        self.pin_names: list[str] = [
            str(p.get("name")) if isinstance(p, dict) else str(p)
            for p in self.pins
        ] or ["INP", "INN", "VCC", "VEE", "OUT"]
        self.neg_rail = _infer_neg_rail(self.pins)
        self.pin_aliases = self._build_pin_aliases(self.pins, self.pin_names)
        self.devices: list[tuple[str, list[str]]] = []  # (spice_line, connected_nodes)
        self.models: dict[str, str] = {}
        self.referenced_models: set[str] = set()
        self._used_names: set[str] = set()
        self.build_errors: list[str] = []

    @staticmethod
    def _build_pin_aliases(pins: list[dict[str, Any]] | list[str], pin_names: list[str]) -> dict[str, str]:
        """Maps common generic pin names (INP, INN, VCC, VEE, OUT) to actual DUT pin names."""
        aliases: dict[str, str] = {}
        exact_upper = {p.upper(): p for p in pin_names}
        for p in pins:
            if not isinstance(p, dict):
                continue
            pname = str(p.get("name") or "")
            up = pname.upper()
            role = str(p.get("role") or "").upper()
            desc = str(p.get("description") or "").lower()
            if role == "OUTPUT" or "OUT" in up:
                for k in ("OUT", "VOUT", "OUTPUT"):
                    if k not in exact_upper:
                        aliases.setdefault(k, pname)
            elif role == "GROUND" or "neg" in desc or up in ("V_N", "VN", "VEE", "VSS", "GND", "V"):
                for k in ("VEE", "VSS", "GND", "V_N", "VN", "VNEG"):
                    if k not in exact_upper:
                        aliases.setdefault(k, pname)
            elif role == "POWER" or "pos" in desc or up in ("V_P", "VP", "VCC", "VDD", "VPOS"):
                for k in ("VCC", "VDD", "V_P", "VP", "VPOS"):
                    if k not in exact_upper:
                        aliases.setdefault(k, pname)
            elif role == "SIGNAL":
                if "NON" in up or up in ("INP", "IN_P", "V_INP", "VINP") or "non-inv" in desc or "noninv" in desc:
                    for k in ("INP", "IN_P", "NONINV", "NONINVERTING_INPUT"):
                        if k not in exact_upper:
                            aliases.setdefault(k, pname)
                elif "INV" in up or up in ("INN", "IN_N", "V_INN", "VINN"):
                    for k in ("INN", "IN_N", "INV", "INVERTING_INPUT"):
                        if k not in exact_upper:
                            aliases.setdefault(k, pname)
        return aliases

    def _map_node(self, node: Any, _neg_rail: str | None = None) -> str:
        n = _clean_node(node, self.neg_rail)
        return self.pin_aliases.get(n.upper(), n)

    def _unique_name(self, prefix: str, raw_name: Any) -> str:
        base = re.sub(r"[^A-Za-z0-9_]", "", str(raw_name or ""))
        if not base or not base.upper().startswith(prefix.upper()):
            base = f"{prefix}{base or (len(self._used_names) + 1)}"
        cand = base
        idx = 2
        while cand.upper() in self._used_names:
            cand = f"{base}_{idx}"
            idx += 1
        self._used_names.add(cand.upper())
        return cand

    def add_model(self, name: str, mtype: str, params: str = "") -> None:
        mname = _clean_model_name(name, "QNPN")
        mt = re.sub(r"[^A-Za-z]", "", str(mtype or "NPN")).upper()
        if mt not in ("NPN", "PNP", "NMOS", "PMOS", "NJF", "PJF", "D"):
            return
        p_clean = str(params or "").strip().strip("()")
        self.models[mname] = f".model {mname} {mt}({p_clean})" if p_clean else f".model {mname} {mt}()"

    def add_device(self, dev: dict[str, Any]) -> None:
        kind = str(dev.get("kind") or dev.get("type") or "").strip().lower()
        if kind in _PROHIBITED_KINDS:
            self.build_errors.append(f"Prohibited device kind '{kind}' inside subcircuit (only physical Q/M/J/D/R/C/L allowed).")
            return

        if kind in ("bjt", "q", "npn", "pnp"):
            name = self._unique_name("Q", dev.get("name"))
            c = self._map_node(dev.get("c") or dev.get("collector"), self.neg_rail)
            b = self._map_node(dev.get("b") or dev.get("base"), self.neg_rail)
            e = self._map_node(dev.get("e") or dev.get("emitter"), self.neg_rail)
            default_mod = "QPNP" if kind == "pnp" else "QNPN"
            model = _clean_model_name(dev.get("model"), default_mod)
            self.referenced_models.add(model)
            self.devices.append((f"{name} {c} {b} {e} {model}", [c, b, e]))
        elif kind in ("mos", "mosfet", "m", "nmos", "pmos"):
            name = self._unique_name("M", dev.get("name"))
            d = self._map_node(dev.get("d") or dev.get("drain"), self.neg_rail)
            g = self._map_node(dev.get("g") or dev.get("gate"), self.neg_rail)
            s = self._map_node(dev.get("s") or dev.get("source"), self.neg_rail)
            b = self._map_node(dev.get("b") or dev.get("bulk") or dev.get("body") or s, self.neg_rail)
            default_mod = "PMOS_MOD" if kind == "pmos" else "NMOS_MOD"
            model = _clean_model_name(dev.get("model"), default_mod)
            w = str(dev.get("w") or dev.get("W") or "20u").strip()
            l_val = str(dev.get("l") or dev.get("L") or "1u").strip()
            self.referenced_models.add(model)
            self.devices.append((f"{name} {d} {g} {s} {b} {model} W={w} L={l_val}", [d, g, s, b]))
        elif kind in ("res", "r", "resistor"):
            name = self._unique_name("R", dev.get("name"))
            p = self._map_node(dev.get("p") or dev.get("n1") or dev.get("a"), self.neg_rail)
            n = self._map_node(dev.get("n") or dev.get("n2") or dev.get("b"), self.neg_rail)
            val = str(dev.get("value") or dev.get("val") or "10k").strip()
            self.devices.append((f"{name} {p} {n} {val}", [p, n]))
        elif kind in ("cap", "c", "capacitor"):
            name = self._unique_name("C", dev.get("name"))
            p = self._map_node(dev.get("p") or dev.get("n1") or dev.get("a"), self.neg_rail)
            n = self._map_node(dev.get("n") or dev.get("n2") or dev.get("b"), self.neg_rail)
            val = str(dev.get("value") or dev.get("val") or "10p").strip()
            self.devices.append((f"{name} {p} {n} {val}", [p, n]))
        elif kind in ("ind", "l", "inductor"):
            name = self._unique_name("L", dev.get("name"))
            p = self._map_node(dev.get("p") or dev.get("n1") or dev.get("a"), self.neg_rail)
            n = self._map_node(dev.get("n") or dev.get("n2") or dev.get("b"), self.neg_rail)
            val = str(dev.get("value") or dev.get("val") or "1u").strip()
            self.devices.append((f"{name} {p} {n} {val}", [p, n]))
        elif kind in ("diode", "d"):
            name = self._unique_name("D", dev.get("name"))
            a = self._map_node(dev.get("a") or dev.get("anode") or dev.get("p"), self.neg_rail)
            k = self._map_node(dev.get("k") or dev.get("cathode") or dev.get("n"), self.neg_rail)
            model = _clean_model_name(dev.get("model"), "D1N4148")
            self.referenced_models.add(model)
            self.devices.append((f"{name} {a} {k} {model}", [a, k]))
        else:
            self.build_errors.append(f"Unsupported device kind '{kind}'.")

    def run_erc(self) -> list[str]:
        """Electrical Rules Check: verifies all non-NC ports are connected and signal path reaches output."""
        errors = list(self.build_errors)
        if not self.devices:
            errors.append("ERC_EMPTY_CIRCUIT: No physical devices defined.")
            return errors

        adj: dict[str, set[str]] = defaultdict(set)
        dc_adj: dict[str, set[str]] = defaultdict(set)
        node_degree: dict[str, int] = defaultdict(int)
        for spice_line, nodes in self.devices:
            uniq = set(nodes)
            is_cap = spice_line.lstrip().upper().startswith("C")
            for n in uniq:
                node_degree[n] += 1
            for a in uniq:
                for b in uniq:
                    if a != b:
                        adj[a].add(b)
                        if not is_cap:
                            dc_adj[a].add(b)

        pin_set = set(self.pin_names)
        floating_internal = sorted(
            n for n, deg in node_degree.items()
            if n not in pin_set and deg < 2
        )
        if floating_internal:
            sample = ", ".join(floating_internal[:6])
            errors.append(
                f"ERC_FLOATING_INTERNAL_NODE: Internal node(s) connected to only 1 device ({sample}). "
                "Every internal node must connect to at least 2 device terminals."
            )

        signal_pins: list[str] = []
        output_pins: list[str] = []
        power_pins: list[str] = []
        _optional_pin_tokens = ("NC", "OFFSET", "NULL", "BAL", "TRIM", "COMP", "SHDN", "STBY")
        for p in self.pins:
            if isinstance(p, dict):
                pname = str(p.get("name") or "")
                up = pname.upper()
                role = str(p.get("role") or "").upper()
                if role == "NC" or up == "NC":
                    continue
                is_optional_ctrl = role == "CONTROL" or any(tok in up for tok in _optional_pin_tokens)
                if node_degree.get(pname, 0) == 0 and not is_optional_ctrl:
                    errors.append(f"ERC_UNCONNECTED_PORT: Declared {role or 'PIN'} '{pname}' has zero device connections.")
                if role == "SIGNAL":
                    signal_pins.append(pname)
                elif role == "OUTPUT":
                    output_pins.append(pname)
                elif role in ("POWER", "GROUND"):
                    power_pins.append(pname)
            else:
                pname = str(p)
                up = pname.upper()
                if up != "NC" and not any(tok in up for tok in _optional_pin_tokens) and node_degree.get(pname, 0) == 0:
                    errors.append(f"ERC_UNCONNECTED_PORT: Declared pin '{pname}' has zero device connections.")

        # Check DC bias path between power/ground rails (excluding capacitors)
        if len(power_pins) >= 2 and all(node_degree.get(pp, 0) > 0 for pp in power_pins[:2]):
            p0, p1 = power_pins[0], power_pins[1]
            visited_dc: set[str] = set()
            q_dc = deque([p0])
            while q_dc:
                cur = q_dc.popleft()
                if cur in visited_dc:
                    continue
                visited_dc.add(cur)
                for nxt in dc_adj.get(cur, ()):
                    if nxt not in visited_dc:
                        q_dc.append(nxt)
            if p1 not in visited_dc:
                errors.append(
                    f"ERC_NO_DC_POWER_PATH: No DC bias current path between supply rails '{p0}' and '{p1}' "
                    "(capacitors block DC). Add a DC biasing/tail path between supplies."
                )

        # Check graph connectivity from signal inputs to outputs
        for out_p in output_pins:
            if node_degree.get(out_p, 0) == 0:
                continue
            visited: set[str] = set()
            q = deque([out_p])
            while q:
                cur = q.popleft()
                if cur in visited:
                    continue
                visited.add(cur)
                for nxt in adj.get(cur, ()):
                    if nxt not in visited:
                        q.append(nxt)
            for sig_p in signal_pins:
                if sig_p not in visited:
                    errors.append(f"ERC_DISCONNECTED_SIGNAL_PATH: Input '{sig_p}' has no topological path to output '{out_p}'.")

        return errors

    def to_spice(self) -> str:
        """Serializes the structured circuit into a strict LTspice/ngspice `.subckt` netlist."""
        lines = [
            f".subckt {self.subckt_name} {' '.join(self.pin_names)}",
            "* Synthesized via CircuitBuilder IR (strict physical SPICE)",
        ]
        for spice_line, _ in self.devices:
            lines.append(spice_line)

        # Ensure every referenced model has a valid .model card
        for mname in sorted(self.referenced_models):
            if mname not in self.models:
                if mname in DEFAULT_MODELS:
                    self.models[mname] = DEFAULT_MODELS[mname]
                elif "PNP" in mname.upper():
                    self.models[mname] = f".model {mname} PNP(IS=1e-16 BF=80 VAF=80)"
                elif "NPN" in mname.upper():
                    self.models[mname] = f".model {mname} NPN(IS=1e-16 BF=150 VAF=100)"
                elif "PMOS" in mname.upper() or "PFET" in mname.upper():
                    self.models[mname] = f".model {mname} PMOS(LEVEL=1 VTO=-0.7 KP=50u LAMBDA=0.02)"
                elif "NMOS" in mname.upper() or "NFET" in mname.upper():
                    self.models[mname] = f".model {mname} NMOS(LEVEL=1 VTO=0.7 KP=120u LAMBDA=0.02)"
                else:
                    self.models[mname] = f".model {mname} D(IS=2.52n RS=0.568 N=1.752)"

        for mname in sorted(self.models):
            lines.append(self.models[mname])

        lines.append(f".ends {self.subckt_name}")
        return "\n".join(lines)

    @classmethod
    def from_json(
        cls,
        raw_text: str,
        subckt_name: str,
        pins: list[dict[str, Any]] | list[str],
    ) -> dict[str, Any] | None:
        """Parses `<circuit_json>...</circuit_json>` (or raw JSON with `devices`) into SPICE + ERC."""
        m = re.search(r"<circuit_json>([\s\S]*?)</circuit_json>", raw_text, re.IGNORECASE)
        candidate = m.group(1).strip() if m else raw_text.strip()
        if not candidate or '"devices"' not in candidate:
            return None
        try:
            data = json.loads(candidate, strict=False)
        except Exception:
            from ai_analog_designer.llm_client import repair_truncated_json
            data = repair_truncated_json(candidate)
        if not isinstance(data, dict) or not isinstance(data.get("devices"), list):
            return None

        builder = cls(subckt_name=subckt_name, pins=pins)
        for mod in data.get("models") or []:
            if isinstance(mod, dict) and mod.get("name"):
                builder.add_model(mod["name"], mod.get("type", "NPN"), mod.get("params", ""))
        for dev in data.get("devices") or []:
            if isinstance(dev, dict):
                builder.add_device(dev)

        erc_errors = builder.run_erc()
        return {
            "ok": len(erc_errors) == 0,
            "netlist": builder.to_spice(),
            "erc_errors": erc_errors,
            "device_count": len(builder.devices),
        }

    @staticmethod
    def schema_guide() -> str:
        """Returns a compact, physically closed (0-ERC, DC-convergent) JSON IR schema guide."""
        return (
            "DEVICE KINDS (physical ONLY — NEVER v, i, b, a sources):\n"
            '- bjt:   {"kind":"bjt","name":"Q1","c":"<node>","b":"<node>","e":"<node>","model":"QNPN"}\n'
            '- mos:   {"kind":"mos","name":"M1","d":"<node>","g":"<node>","s":"<node>","b":"<node>","model":"NMOS_MOD","w":"20u","l":"1u"}\n'
            '- res:   {"kind":"res","name":"R1","p":"<node>","n":"<node>","value":"10k"}\n'
            '- cap:   {"kind":"cap","name":"C1","p":"<node>","n":"<node>","value":"30p"}\n'
            '- diode: {"kind":"diode","name":"D1","a":"<node>","k":"<node>","model":"D1N4148"}\n'
            "COMPLETE CONNECTED EXAMPLE (adapt pin names & sizing to target DUT):\n"
            '{"models":[\n'
            '  {"name":"QNPN","type":"NPN","params":"IS=1e-16 BF=150 VAF=100"},\n'
            '  {"name":"QPNP","type":"PNP","params":"IS=1e-16 BF=80 VAF=80"}\n'
            '],"devices":[\n'
            '  {"kind":"bjt","name":"Q1","c":"N_C1","b":"INP","e":"N_TAIL","model":"QNPN"},\n'
            '  {"kind":"bjt","name":"Q2","c":"N_C2","b":"INN","e":"N_TAIL","model":"QNPN"},\n'
            '  {"kind":"res","name":"RC1","p":"VCC","n":"N_C1","value":"15k"},\n'
            '  {"kind":"res","name":"RC2","p":"VCC","n":"N_C2","value":"15k"},\n'
            '  {"kind":"bjt","name":"Q3","c":"N_TAIL","b":"N_BIAS","e":"N_E3","model":"QNPN"},\n'
            '  {"kind":"res","name":"RE3","p":"N_E3","n":"VEE","value":"1k"},\n'
            '  {"kind":"bjt","name":"Q4","c":"N_BIAS","b":"N_BIAS","e":"N_E4","model":"QNPN"},\n'
            '  {"kind":"res","name":"RE4","p":"N_E4","n":"VEE","value":"1k"},\n'
            '  {"kind":"res","name":"RBIAS","p":"VCC","n":"N_BIAS","value":"30k"},\n'
            '  {"kind":"bjt","name":"Q5","c":"N_G2","b":"N_C2","e":"VCC","model":"QPNP"},\n'
            '  {"kind":"res","name":"RG2","p":"N_G2","n":"VEE","value":"10k"},\n'
            '  {"kind":"cap","name":"CC","p":"N_C2","n":"N_G2","value":"30p"},\n'
            '  {"kind":"bjt","name":"Q6","c":"VCC","b":"N_G2","e":"OUT","model":"QNPN"},\n'
            '  {"kind":"res","name":"ROUT","p":"OUT","n":"VEE","value":"5k"}\n'
            "]}"
        )
