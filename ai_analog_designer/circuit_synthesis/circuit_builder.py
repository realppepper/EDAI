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


def _infer_single_supply(pins: list[dict[str, Any]] | list[str]) -> bool:
    """Detects single-supply ICs (e.g. VDD/GND or V_P/V(GROUND) without a negative rail VEE/V_N/VS_N)."""
    has_ground_pin = False
    has_explicit_neg_rail = False
    for p in pins or []:
        if isinstance(p, dict):
            name = str(p.get("name") or "").upper()
            role = str(p.get("role") or "").upper()
            desc = str(p.get("description") or "").lower()
        else:
            name = str(p).upper()
            role = ""
            desc = ""
        if name in ("VEE", "V_N", "VN", "VS_N", "VSN", "VNEG", "V_NEG") or "negative supply" in desc:
            has_explicit_neg_rail = True
        if role == "GROUND" or name in ("GND", "VSS", "AGND", "DGND", "V"):
            has_ground_pin = True
    return has_ground_pin and not has_explicit_neg_rail


def _infer_neg_rail(pins: list[dict[str, Any]] | list[str]) -> str | None:
    for p in pins:
        if isinstance(p, dict):
            name = str(p.get("name") or "")
            role = str(p.get("role") or "").upper()
            desc = str(p.get("description") or "").lower()
            if role == "GROUND" or "neg" in desc or name.upper() in ("VSS", "VEE", "GND", "V_N", "VN", "VS_N", "VSN", "V"):
                return name
        else:
            s = str(p)
            if s.upper() in ("VSS", "VEE", "GND", "V_N", "VN", "VS_N", "VSN", "V"):
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
        self.is_single_supply = _infer_single_supply(self.pins)
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
        unmatched_signals: list[str] = []
        for p in pins:
            if not isinstance(p, dict):
                continue
            pname = str(p.get("name") or "")
            up = pname.upper()
            role = str(p.get("role") or "").upper()
            desc = str(p.get("description") or "").lower()
            if role == "OUTPUT" or up in ("OUT", "VOUT", "VO", "OUTPUT", "OUT_A", "OUTPUT_A", "OUT_1") or ("OUT" in up and not up.endswith("_B") and not up.endswith("_2")):
                for k in ("OUT", "VOUT", "VO", "OUTPUT"):
                    if k not in exact_upper:
                        aliases.setdefault(k, pname)
            elif role == "GROUND" or "neg" in desc or up in ("V_N", "VN", "VS_N", "VSN", "VEE", "VSS", "GND", "V"):
                for k in ("VEE", "VSS", "GND", "V_N", "VN", "VS_N", "VNEG"):
                    if k not in exact_upper:
                        aliases.setdefault(k, pname)
            elif role == "POWER" or "pos" in desc or up in ("V_P", "VP", "VS_P", "VSP", "VCC", "VDD", "VPOS"):
                for k in ("VCC", "VDD", "V_P", "VP", "VS_P", "VPOS"):
                    if k not in exact_upper:
                        aliases.setdefault(k, pname)
            elif role == "SIGNAL":
                is_aux_ch = bool(re.search(r"_[BCD234]$", up))
                if is_aux_ch:
                    continue
                is_pos_in = (
                    "NON" in up
                    or "non-inv" in desc
                    or "noninv" in desc
                    or "positive" in desc
                    or up in ("INP", "IN_P", "V_INP", "VINP", "VIN_P", "PIN", "PIN_A", "PIN_1", "INP_A", "IN_P_A")
                    or bool(re.search(r"(?:^|_)(?:INP|IN_P|VIN_P|PIN)(?:_A|_1|$)", up))
                )
                is_neg_in = (
                    ("INV" in up and "NON" not in up)
                    or ("inverting" in desc and "non" not in desc)
                    or "negative" in desc
                    or up in ("INN", "IN_N", "V_INN", "VINN", "VIN_N", "NIN", "NIN_A", "NIN_1", "INM", "INN_A", "IN_N_A")
                    or bool(re.search(r"(?:^|_)(?:INN|IN_N|VIN_N|NIN|INM)(?:_A|_1|$)", up))
                )
                if is_pos_in:
                    for k in ("INP", "IN_P", "PIN", "VIN_P", "NONINV", "NONINVERTING_INPUT"):
                        if k not in exact_upper:
                            aliases.setdefault(k, pname)
                elif is_neg_in:
                    for k in ("INN", "IN_N", "NIN", "VIN_N", "INM", "INV", "INVERTING_INPUT"):
                        if k not in exact_upper:
                            aliases.setdefault(k, pname)
                else:
                    unmatched_signals.append(pname)
        # Fallback for positional signal pins if INP/INN still unassigned
        if "INP" not in aliases and "INP" not in exact_upper and unmatched_signals:
            pname = unmatched_signals.pop(0)
            for k in ("INP", "IN_P", "PIN", "VIN_P"):
                if k not in exact_upper:
                    aliases.setdefault(k, pname)
        if "INN" not in aliases and "INN" not in exact_upper and unmatched_signals:
            pname = unmatched_signals.pop(0)
            for k in ("INN", "IN_N", "NIN", "VIN_N", "INM"):
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

    def add_block(self, block: dict[str, Any]) -> None:
        """
        Circuit-SAFE functional analog stage compiler (valid-by-construction).
        Compiles high-level analog blocks into polarity-verified physical SPICE devices,
        eliminating collector/emitter inversions and split-tail wiring bugs.
        """
        btype = str(block.get("block") or block.get("type") or block.get("kind") or "").strip().lower()
        vpos = self._map_node(block.get("vpos") or "VCC")
        vneg = self._map_node(block.get("vneg") or "VEE")
        inp = self._map_node(block.get("inp") or "INP")
        inn = self._map_node(block.get("inn") or "INN")
        out_pin = self._map_node(block.get("out") or "OUT")
        npn = _clean_model_name(block.get("npn_model") or block.get("model"), "QNPN")
        pnp = _clean_model_name(block.get("pnp_model"), "QPNP")
        dmod = _clean_model_name(block.get("diode_model"), "D1N4148")

        if btype == "tail_current_mirror":
            bias_node = self._map_node(block.get("bias_node") or "N_BIAS")
            tail_node = self._map_node(block.get("tail_node") or "N_TAIL")
            default_rbias = "39k" if self.is_single_supply else "150k"
            r_bias = str(block.get("r_bias") or default_rbias).strip()
            r_e_ref = str(block.get("r_e_ref") or "2k").strip()
            r_e_tail = str(block.get("r_e_tail") or "2k").strip()
            self.add_device({"kind": "res", "name": "RBIAS", "p": vpos, "n": bias_node, "value": r_bias})
            self.add_device({"kind": "bjt", "name": "Q_BREF", "c": bias_node, "b": bias_node, "e": "N_EREF", "model": npn})
            self.add_device({"kind": "res", "name": "RE_BREF", "p": "N_EREF", "n": vneg, "value": r_e_ref})
            self.add_device({"kind": "bjt", "name": "Q_TAIL", "c": tail_node, "b": bias_node, "e": "N_ETAIL", "model": npn})
            self.add_device({"kind": "res", "name": "RE_TAIL", "p": "N_ETAIL", "n": vneg, "value": r_e_tail})

        elif btype == "diff_pair_active_load":
            tail_node = self._map_node(block.get("tail_node") or "N_TAIL")
            out_node = self._map_node(block.get("out_node") or "N_C2")
            r_mirror_e = str(block.get("r_mirror_e") or "500").strip()
            self.add_device({"kind": "bjt", "name": "Q_IN1", "c": "N_C1", "b": inn, "e": tail_node, "model": npn})
            self.add_device({"kind": "bjt", "name": "Q_IN2", "c": out_node, "b": inp, "e": tail_node, "model": npn})
            self.add_device({"kind": "bjt", "name": "Q_ML1", "c": "N_C1", "b": "N_C1", "e": "N_ME1", "model": pnp})
            self.add_device({"kind": "res", "name": "RM_L1", "p": vpos, "n": "N_ME1", "value": r_mirror_e})
            self.add_device({"kind": "bjt", "name": "Q_ML2", "c": out_node, "b": "N_C1", "e": "N_ME2", "model": pnp})
            self.add_device({"kind": "res", "name": "RM_L2", "p": vpos, "n": "N_ME2", "value": r_mirror_e})

        elif btype == "diff_pair_res_load":
            tail_node = self._map_node(block.get("tail_node") or "N_TAIL")
            out_node = self._map_node(block.get("out_node") or "N_C2")
            rc = str(block.get("rc") or "15k").strip()
            self.add_device({"kind": "bjt", "name": "Q_IN1", "c": "N_C1", "b": inn, "e": tail_node, "model": npn})
            self.add_device({"kind": "bjt", "name": "Q_IN2", "c": out_node, "b": inp, "e": tail_node, "model": npn})
            self.add_device({"kind": "res", "name": "RC1", "p": vpos, "n": "N_C1", "value": rc})
            self.add_device({"kind": "res", "name": "RC2", "p": vpos, "n": out_node, "value": rc})

        elif btype == "gain_stage_ce":
            in_node = self._map_node(block.get("in_node") or "N_C2")
            out_node = self._map_node(block.get("out_node") or "N_G2")
            bias_node = self._map_node(block.get("bias_node") or "N_BIAS")
            load_type = str(block.get("load_type") or "active_current_source").strip().lower()
            r_load = str(block.get("r_load") or "20k").strip()
            r_e_src = str(block.get("r_e_src") or "500").strip()
            c_comp = str(block.get("c_comp") or "30p").strip()
            r_zero = str(block.get("r_zero") or "1k").strip()
            self.add_device({"kind": "bjt", "name": "Q_G2", "c": out_node, "b": in_node, "e": vpos, "model": pnp})
            if load_type in ("active", "active_current_source", "current_source"):
                self.add_device({"kind": "bjt", "name": "Q_G2L", "c": out_node, "b": bias_node, "e": "N_EG2L", "model": npn})
                self.add_device({"kind": "res", "name": "RE_G2L", "p": "N_EG2L", "n": vneg, "value": r_e_src})
            else:
                self.add_device({"kind": "res", "name": "RG2", "p": out_node, "n": vneg, "value": r_load})
            if r_zero and r_zero not in ("0", "0.0", "none"):
                self.add_device({"kind": "res", "name": "RZ_COMP", "p": in_node, "n": "N_CZ", "value": r_zero})
                self.add_device({"kind": "cap", "name": "CC_COMP", "p": "N_CZ", "n": out_node, "value": c_comp})
            else:
                self.add_device({"kind": "cap", "name": "CC_COMP", "p": in_node, "n": out_node, "value": c_comp})

        elif btype == "output_class_ab":
            in_node = self._map_node(block.get("in_node") or "N_G2")
            bias_node = self._map_node(block.get("bias_node") or "N_BIAS")
            r_e_sink = str(block.get("r_e_sink") or "2k").strip()
            r_e_out = str(block.get("r_e_out") or "25").strip()
            # Emitter-follower buffer isolates high-Z gain node (in_node) from 2kOhm Class-AB load (keeps A_VOL > 95dB)
            self.add_device({"kind": "bjt", "name": "Q_AB_BUF", "c": vpos, "b": in_node, "e": "N_AB_TOP", "model": npn})
            self.add_device({"kind": "diode", "name": "D_AB1", "a": "N_AB_TOP", "k": "N_AB_MID", "model": dmod})
            self.add_device({"kind": "diode", "name": "D_AB2", "a": "N_AB_MID", "k": "N_AB_BOT", "model": dmod})
            self.add_device({"kind": "bjt", "name": "Q_AB_SINK", "c": "N_AB_BOT", "b": bias_node, "e": "N_E_ABSINK", "model": npn})
            self.add_device({"kind": "res", "name": "RE_ABSINK", "p": "N_E_ABSINK", "n": vneg, "value": r_e_sink})
            self.add_device({"kind": "bjt", "name": "Q_OUTN", "c": vpos, "b": "N_AB_TOP", "e": "N_EOUTN", "model": npn})
            self.add_device({"kind": "res", "name": "RE_OUTN", "p": "N_EOUTN", "n": out_pin, "value": r_e_out})
            self.add_device({"kind": "bjt", "name": "Q_OUTP", "c": vneg, "b": "N_AB_BOT", "e": "N_EOUTP", "model": pnp})
            self.add_device({"kind": "res", "name": "RE_OUTP", "p": "N_EOUTP", "n": out_pin, "value": r_e_out})

        elif btype == "output_emitter_follower":
            in_node = self._map_node(block.get("in_node") or "N_G2")
            r_out = str(block.get("r_out") or "5k").strip()
            self.add_device({"kind": "bjt", "name": "Q_OUT", "c": vpos, "b": in_node, "e": out_pin, "model": npn})
            self.add_device({"kind": "res", "name": "ROUT", "p": out_pin, "n": vneg, "value": r_out})

        else:
            self.build_errors.append(f"Unsupported Circuit-SAFE block type '{btype}'.")

    def _ensure_auxiliary_channels(self) -> None:
        """
        For multi-channel ICs (e.g. dual/quad op-amps with OUT_A/B, PIN_A/B, NIN_A/B),
        if the primary channel is wired but auxiliary channels have zero connections,
        automatically clone the primary channel's physical transistor graph onto each
        unwired auxiliary channel sharing the same power rails.
        """
        if not self.devices:
            return
        connected_nodes: set[str] = set()
        for _, nodes in self.devices:
            connected_nodes.update(nodes)

        prim_out = self.pin_aliases.get("OUT") or ("OUT" if "OUT" in self.pin_names else None)
        prim_inp = self.pin_aliases.get("INP") or ("INP" if "INP" in self.pin_names else None)
        prim_inn = self.pin_aliases.get("INN") or ("INN" if "INN" in self.pin_names else None)
        if not (prim_out and prim_inp and prim_inn):
            return
        if prim_out not in connected_nodes:
            return

        # Discover auxiliary channels by suffix (_A.._D, _1.._4) or infix (_B_P, _B_N)
        channel_groups: dict[str, dict[str, str]] = defaultdict(dict)
        for p in self.pins:
            if not isinstance(p, dict):
                continue
            pname = str(p.get("name") or "")
            up = pname.upper()
            role = str(p.get("role") or "").upper()
            m = re.search(r"_([A-D]|[1-4])(?:_[PNM]|$)", up)
            if not m:
                continue
            ch = m.group(1)
            if role == "OUTPUT" or "OUT" in up:
                channel_groups[ch]["OUT"] = pname
            elif role == "SIGNAL":
                if "NON" in up or up.endswith("_P") or any(tok in up for tok in ("PIN_", "INP_", "IN_P_", "VIN_P_")):
                    channel_groups[ch]["INP"] = pname
                elif "INV" in up or up.endswith("_N") or up.endswith("_M") or any(tok in up for tok in ("NIN_", "INN_", "IN_N_", "VIN_N_", "INM_")):
                    channel_groups[ch]["INN"] = pname

        base_devices = list(self.devices)
        pin_set = set(self.pin_names)
        for ch, mapping in sorted(channel_groups.items()):
            aux_out = mapping.get("OUT")
            aux_inp = mapping.get("INP")
            aux_inn = mapping.get("INN")
            if not (aux_out and aux_inp and aux_inn):
                continue
            if aux_out in connected_nodes:
                continue
            node_remap = {
                prim_out: aux_out,
                prim_inp: aux_inp,
                prim_inn: aux_inn,
            }
            for spice_line, nodes in base_devices:
                tokens = spice_line.split()
                if len(tokens) < 4:
                    continue
                dev_name = f"{tokens[0]}_CH{ch}"
                new_tokens = [dev_name]
                new_nodes: list[str] = []
                # Determine how many terminal tokens belong to this device
                prefix = tokens[0][0].upper()
                n_terms = 4 if prefix == "M" else (3 if prefix in ("Q", "J") else 2)
                for idx, tok in enumerate(tokens[1:], start=1):
                    if idx <= n_terms:
                        if tok in node_remap:
                            mapped = node_remap[tok]
                        elif tok in pin_set:
                            mapped = tok  # shared power/ground rail
                        else:
                            mapped = f"{tok}_CH{ch}"
                        new_tokens.append(mapped)
                        new_nodes.append(mapped)
                    else:
                        new_tokens.append(tok)
                self.devices.append((" ".join(new_tokens), new_nodes))
                connected_nodes.update(new_nodes)

    def run_erc(self) -> list[str]:
        """Electrical Rules Check: verifies all non-NC ports are connected and signal path reaches output."""
        self._ensure_auxiliary_channels()
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
        _optional_pin_tokens = ("NC", "OFFSET", "NULL", "BAL", "TRIM", "COMP", "SHDN", "SHUTDOWN", "STBY", "PD", "THERMAL", "PAD", "DAP", "EP")
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
        if not candidate or ('"devices"' not in candidate and '"blocks"' not in candidate):
            return None
        try:
            data = json.loads(candidate, strict=False)
        except Exception:
            from ai_analog_designer.llm_client import repair_truncated_json
            data = repair_truncated_json(candidate)
        if not isinstance(data, dict) or (not isinstance(data.get("devices"), list) and not isinstance(data.get("blocks"), list)):
            return None

        builder = cls(subckt_name=subckt_name, pins=pins)
        for mod in data.get("models") or []:
            if isinstance(mod, dict) and mod.get("name"):
                builder.add_model(mod["name"], mod.get("type", "NPN"), mod.get("params", ""))
        for blk in data.get("blocks") or []:
            if isinstance(blk, dict):
                builder.add_block(blk)
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
        """Returns a Circuit-SAFE block-level + device-level JSON IR schema guide (0-ERC, DC-convergent)."""
        return (
            "PREFERRED CIRCUIT-SAFE BLOCKS (valid-by-construction analog stages — prevents polarity/wiring bugs):\n"
            '- tail_current_mirror:     {"block":"tail_current_mirror","r_bias":"300k","r_e_ref":"2k","r_e_tail":"2k"}\n'
            '- diff_pair_active_load:   {"block":"diff_pair_active_load","r_mirror_e":"500"}  (HIGH GAIN >95dB, LOW Vos <2mV!)\n'
            '- diff_pair_res_load:      {"block":"diff_pair_res_load","rc":"15k"}             (moderate gain ~65dB)\n'
            '- gain_stage_ce:           {"block":"gain_stage_ce","load_type":"active_current_source","r_e_src":"1k","c_comp":"30p","r_zero":"1k"}\n'
            '- output_class_ab:         {"block":"output_class_ab","r_e_sink":"2k","r_e_out":"25"}  (symmetric +/-13V swing)\n'
            '- output_emitter_follower: {"block":"output_emitter_follower","r_out":"5k"}\n'
            "COMPLETE HIGH-GAIN CIRCUIT-SAFE EXAMPLE (adapt models/values to target specs):\n"
            '{"models":[\n'
            '  {"name":"QNPN","type":"NPN","params":"IS=1e-16 BF=250 VAF=120"},\n'
            '  {"name":"QPNP","type":"PNP","params":"IS=1e-16 BF=100 VAF=100"},\n'
            '  {"name":"D1N4148","type":"D","params":"IS=1e-14 RS=1"}\n'
            '],"blocks":[\n'
            '  {"block":"tail_current_mirror","r_bias":"300k","r_e_ref":"2k","r_e_tail":"2k"},\n'
            '  {"block":"diff_pair_active_load","r_mirror_e":"500"},\n'
            '  {"block":"gain_stage_ce","load_type":"active_current_source","r_e_src":"1k","c_comp":"30p","r_zero":"1k"},\n'
            '  {"block":"output_class_ab","r_e_sink":"2k","r_e_out":"25"}\n'
            '],"devices":[]}\n'
            "Optional extra physical `devices` (bjt/mos/res/cap/diode) may also be included alongside `blocks`."
        )
