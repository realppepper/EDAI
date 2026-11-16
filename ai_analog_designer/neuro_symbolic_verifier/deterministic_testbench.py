"""
Deterministic testbench library.

For every PLANNED spec item (see spec_planner.build_plan) a small, fixed LTspice deck is generated.
Each deck contains exactly one DUT instance, a fixture for ONE measurement kind under ONE set of
conditions, and `.meas` directives with fixed names. A Python extractor turns the raw `.meas` values
into the metric in its canonical unit. No LLM is involved, so a missing measurement is a verifier bug,
not a prompt failure.

Fixture conventions
  * V- (or GND / ANODE) is the global node 0.  V+ = VS.  Mid-supply node "mid" = VS/2.
  * Transient decks ramp the supply with a PWL over t_ramp (from the PDG schedule) and measure after settling.
  * Unused op-amp / comparator channels are parked as followers at mid.
"""
import concurrent.futures as cf
import math
import os
import re
import subprocess
from typing import Any

from .ltspice_runner import LTSPICE_EXE
from .units import fmt, spec_limits_in


# ----------------------------------------------------------------------------- DUT instantiation
def subckt_header(netlist: str, dut_name: str | None = None) -> tuple[str, list[str]]:
    """Returns (name, pins) of the DUT subcircuit: the one called `dut_name`, else the LAST .subckt in the
    file (helper/vendor subcircuits are defined before the top-level wrapper)."""
    heads = re.findall(r"^\s*\.subckt\s+(\S+)\s+(.+?)\s*$", netlist or "", re.MULTILINE | re.IGNORECASE)
    if not heads:
        return (dut_name or "DUT"), ["IN_P", "IN_N", "VCC", "VEE", "OUT"]
    if dut_name:
        for n, p in heads:
            if n.lower() == dut_name.lower():
                return n, p.split()
    n, p = heads[-1]
    return n, p.split()


def _semantic_node_for_pin(pin_str: str, node_of: dict[str, str], lut: dict[str, str]) -> str | None:
    """Resolves a .subckt pin to a fixture node even when pin naming conventions differ
    (e.g., VCC vs VCC_P vs V+, VEE vs VCC_N vs GND, IN+ vs IN_P vs 1IN+)."""
    u = pin_str.upper().strip()
    vals = set(node_of.values())
    # Negative rail / ground
    if re.search(r"(^V-$|^VEE$|^VSS$|^GND$|_N$|-|NEG|ANODE)", u) and re.search(r"(^V|CC|DD|EE|SS|GND|NEG|ANODE)", u):
        if "vn" in vals:
            return "vn"
        if "0" in vals:
            return "0"
    # Positive rail
    if re.search(r"(^V\+$|^VCC$|^VDD$|^VS$|_P$|\+|POS)", u) and re.search(r"(^V|CC|DD|VS|POS)", u) and not re.search(r"IN|OUT", u):
        if "vp" in vals:
            return "vp"
    # Non-inverting input
    if re.search(r"IN", u) and ("+" in u or re.search(r"(_P\b|P$|NONINV)", u)):
        if "inp" in vals:
            return "inp"
    # Inverting input
    if re.search(r"IN", u) and ("-" in u or re.search(r"(_N\b|N$|(?<!NON)INV)", u)):
        if "inn" in vals:
            return "inn"
    # Output
    if re.search(r"(^OUT|\bOUT\d*$|^VO$|^VOUT$)", u):
        if "out" in vals:
            return "out"
    return None


def instantiate(netlist: str, node_of: dict[str, str], inst: str = "XDUT", dut_name: str | None = None) -> str:
    """Builds the X-line, mapping subckt header pins to fixture nodes via exact, sanitized, or semantic role names."""
    name, pins = subckt_header(netlist, dut_name)
    def key(p):
        return re.sub(r"[^A-Z0-9]", "", p.upper().replace("+", "P").replace("-", "N"))
    lut = {key(k): v for k, v in node_of.items()}
    nodes = []
    for p in pins:
        n = node_of.get(p) or lut.get(key(p)) or _semantic_node_for_pin(p, node_of, lut)
        nodes.append(n if n else f"nc_{key(p)}")
    return f"{inst} {' '.join(nodes)} {name}"


# ----------------------------------------------------------------------------- deck assembly
class Deck:
    def __init__(self, key: str, kind: str, title: str, lines: list[str], analysis: str, meas: list[str],
                 extract, fixture: dict[str, Any]):
        self.key, self.kind, self.title = key, kind, title
        self.lines, self.analysis, self.meas = lines, analysis, meas
        self.extract, self.fixture = extract, fixture

    def text(self, netlist: str) -> str:
        return "\n".join([f"* {self.title}", ".temp 25", ".options plotwinsize=0 numdgt=7",
                          netlist.strip(), "", *self.lines, "", self.analysis, *self.meas, ".end", ""])


def _r(v: float) -> str:
    return f"{v:.6g}"


def _ramp(vs: float, t_ramp: float) -> str:
    return f"PWL(0 0 {_r(t_ramp)} {_r(vs)})"


class FixtureContext:
    def __init__(self, netlist: str, plan: dict[str, Any], schedule_us: dict[str, float] | None = None,
                 dut_name: str | None = None):
        self.netlist = netlist
        self.dut_name = dut_name
        # Symmetric-supply fixtures (V- = -VS/2, mid = 0) for macromodels written for +/-15 V rails.
        self.split = os.environ.get("TB_SPLIT_SUPPLY") == "1"
        self.plan = plan
        self.pm = plan["pin_map"]
        self.cls = plan["device_class"]
        sched = schedule_us or {}
        self.t_ramp = min(max(5e-6, 1e-6 * max(sched.values(), default=10.0)), 200e-6)
        ramp = self.t_ramp if os.environ.get("TB_RAMP_SUPPLY") == "1" else 0.0
        self.t_settle = ramp + 100e-6
        self.t_end = self.t_settle + 50e-6

    # -------- helpers
    def park_unused(self, used_channel: dict[str, str], node_of: dict[str, str], lines: list[str], mid: str = "mid"):
        for i, ch in enumerate(self.pm.get("channels", [])):
            if ch is used_channel:
                continue
            if self.cls == "comparator":
                # Open-loop comparators oscillate if connected as unity-gain followers; park with fixed overdrive (OUT high/off)
                node_of[ch["inp"]] = mid
                node_of[ch["inn"]] = "0"
                node_of[ch["out"]] = f"park{i}"
                lines.append(f"Rpark{i} park{i} 0 1G")
            else:
                node_of[ch["inp"]] = mid
                node_of[ch["inn"]] = f"park{i}"
                node_of[ch["out"]] = f"park{i}"
                lines.append(f"Rpark{i} park{i} {mid} 100k")

    def base_nodes(self, vs: float) -> dict[str, str]:
        n = {}
        if self.pm.get("vpos"):
            n[self.pm["vpos"]] = "vp"
        if self.pm.get("vneg"):
            n[self.pm["vneg"]] = "vn" if self.split else "0"
        return n

    def _rails(self, vs: float, ac: bool) -> list[str]:
        if self.split:
            return [f"VPOS vp 0 {_r(vs / 2)}" + (" AC 1" if ac else ""),
                    f"VNEG vn 0 {_r(-vs / 2)}", "VMID mid 0 0"]
        return [f"VPOS vp 0 {_r(vs)}" + (" AC 1" if ac else ""), f"VMID mid 0 {_r(vs / 2)}"]

    def supply_tran(self, vs: float) -> list[str]:
        # Supply ramping (PDG start-up sequencing) is opt-in: several vendor macromodels (e.g. TI LM393) do not
        # converge through a 0->VS ramp in transient, so spec measurements use a DC supply by default.
        if os.environ.get("TB_RAMP_SUPPLY") == "1":
            if self.split:
                return [f"VPOS vp 0 {_ramp(vs / 2, self.t_ramp)}", f"VNEG vn 0 {_ramp(-vs / 2, self.t_ramp)}", "VMID mid 0 0"]
            return [f"VPOS vp 0 {_ramp(vs, self.t_ramp)}", f"VMID mid 0 {_ramp(vs / 2, self.t_ramp)}"]
        return self._rails(vs, False)

    def supply_dc(self, vs: float, ac_on_vp: bool = False) -> list[str]:
        return self._rails(vs, ac_on_vp)

    def tran(self) -> str:
        return f".tran 0 {_r(self.t_end)} 0 {_r(self.t_end / 2000)}"

    def win(self) -> str:
        return f"FROM {_r(self.t_settle)} TO {_r(self.t_end)}"

    def ch(self) -> dict[str, str]:
        chans = self.pm.get("channels") or []
        if chans:
            return chans[0]
        # Soft fallback: infer channel pins from the subckt header pins
        _, pins = subckt_header(self.netlist, self.dut_name)
        from .spec_planner import map_pins
        inferred = map_pins(self.cls, [{"name": p, "raw_name": p} for p in pins])
        if not self.pm.get("vpos") and inferred.get("vpos"):
            self.pm["vpos"] = inferred["vpos"]
        if not self.pm.get("vneg") and inferred.get("vneg"):
            self.pm["vneg"] = inferred["vneg"]
        if inferred.get("channels"):
            self.pm["channels"] = inferred["channels"]
            return inferred["channels"][0]
        non_rails = [p for p in pins if p not in (self.pm.get("vpos"), self.pm.get("vneg"))]
        if len(non_rails) >= 3:
            return {"inp": non_rails[0], "inn": non_rails[1], "out": non_rails[-1]}
        return {"inp": "IN_P", "inn": "IN_N", "out": "OUT"}


# ============================================================================ OP-AMP / INAMP
def opamp_dc(ctx: FixtureContext, key: str, fx: dict[str, Any]) -> Deck:
    vs, ch = fx["vs"], ctx.ch()
    rl = fx.get("rl") or 10e3
    n = ctx.base_nodes(vs); n.update({ch["inp"]: "inp", ch["inn"]: "inn", ch["out"]: "out"})
    lines = ctx.supply_tran(vs) + ["VSP mid inp 0", "VSN out inn 0", f"RL out {('vn' if ctx.split else '0') if fx.get('rl_to') == 'vn' else 'mid'} {_r(rl)}", "CL out mid 20p"]
    ctx.park_unused(ch, n, lines)
    lines.append(instantiate(ctx.netlist, n, dut_name=ctx.dut_name))
    w = ctx.win()
    meas = [f".meas tran m_out AVG V(out) {w}", f".meas tran m_mid AVG V(mid) {w}",
            f".meas tran m_isp AVG I(VSP) {w}", f".meas tran m_isn AVG I(VSN) {w}",
            f".meas tran m_ipos AVG I(VPOS) {w}"]
    nch = max(1, len(ctx.pm.get("channels") or [1]))

    def extract(r):
        out = {}
        if "m_out" in r and "m_mid" in r:
            out["vos"] = r["m_out"] - r["m_mid"]
        ibp = r.get("m_isp")           # current into IN+ (VSP: mid -> inp, I flows mid->inp = into pin)
        ibn = r.get("m_isn")           # current into IN- (VSN: out -> inn)
        if ibp is not None and ibn is not None:
            out["ib"] = (ibp + ibn) / 2
            out["ios"] = abs(ibp - ibn)
        if "m_ipos" in r:
            out["iq_total"] = -r["m_ipos"]
            out["iq"] = -r["m_ipos"] / nch
        return out
    return Deck(key, "opamp_dc", f"follower DC: VOS/IB/IOS/IQ VS={vs}", lines, ctx.tran(), meas, extract, fx)


def opamp_openloop(ctx: FixtureContext, key: str, fx: dict[str, Any], cm: bool = False) -> Deck:
    vs, ch = fx["vs"], ctx.ch()
    rl = fx.get("rl") or 10e3
    cl = fx.get("cl") or 20e-12
    n = ctx.base_nodes(vs); n.update({ch["inp"]: "inp", ch["inn"]: "inn", ch["out"]: "out"})
    lines = ctx.supply_dc(vs)
    if cm:
        lines += ["VCM cmn mid AC 1", "VIN inp cmn 0", "LFB out inn 1G", "CFB inn cmn 1G"]
    else:
        lines += ["VIN inp mid AC 1", "LFB out inn 1G", "CFB inn mid 1G"]
    lines += [f"RL out {('vn' if ctx.split else '0') if fx.get('rl_to') == 'vn' else 'mid'} {_r(rl)}", f"CL out mid {_r(cl)}"]
    ctx.park_unused(ch, n, lines)
    lines.append(instantiate(ctx.netlist, n, dut_name=ctx.dut_name))
    meas = [".meas ac m_a0 FIND V(out) AT 0.1",
            ".meas ac m_ugf WHEN mag(V(out))=1 FALL=1",
            ".meas ac m_ph FIND V(out) WHEN mag(V(out))=1 FALL=1"]

    def extract(r):
        out = {}
        if cm:
            if "m_a0_db" in r:
                out["acm_db"] = r["m_a0_db"]
            return out
        if "m_a0_db" in r:
            out["aol_db"] = r["m_a0_db"]
        if "m_ugf" in r:
            out["gbw"] = r["m_ugf"]
        if "m_ph_phase" in r:
            p = r["m_ph_phase"]
            # open-loop phase of a stable amp sits between -90 and -180 at UGF; unwrap 0..360 reports
            if p > 0:
                p -= 360
            out["pm"] = 180 + p
        return out
    return Deck(key, "opamp_cm" if cm else "opamp_ol", f"open-loop AC {'CM' if cm else 'DM'} VS={vs}", lines,
                ".ac dec 20 0.1 1G", meas, extract, fx)


def opamp_psrr(ctx: FixtureContext, key: str, fx: dict[str, Any]) -> Deck:
    vs, ch = fx["vs"], ctx.ch()
    n = ctx.base_nodes(vs); n.update({ch["inp"]: "mid", ch["inn"]: "out", ch["out"]: "out"})
    lines = ctx.supply_dc(vs, ac_on_vp=True) + ["RL out mid 10k"]
    ctx.park_unused(ch, n, lines)
    lines.append(instantiate(ctx.netlist, n, dut_name=ctx.dut_name))
    f = fx.get("freq") or 10.0
    meas = [f".meas ac m_ps FIND V(out) AT {_r(f)}"]

    def extract(r):
        return {"psrr_db": -r["m_ps_db"]} if "m_ps_db" in r else {}
    return Deck(key, "opamp_psrr", f"PSRR follower VS={vs}", lines, ".ac dec 20 1 10Meg", meas, extract, fx)


def opamp_sr(ctx: FixtureContext, key: str, fx: dict[str, Any], sr_hint: float = 1.0) -> Deck:
    vs, ch = fx["vs"], ctx.ch()
    rl = fx.get("rl") or 10e3
    cl = fx.get("cl") or 20e-12
    amp = min(max(vs / 4, 0.5), 5.0)
    t_sw = max(amp * 2 / max(sr_hint, 0.05) * 1e-6 * 10, 5e-6)   # 10x expected edge time
    t0 = ctx.t_settle
    n = ctx.base_nodes(vs); n.update({ch["inp"]: "inp", ch["inn"]: "out", ch["out"]: "out"})
    lines = ctx.supply_tran(vs) + [
        f"VIN inp mid PULSE({_r(-amp)} {_r(amp)} {_r(t0)} 10n 10n {_r(t_sw)} {_r(2 * t_sw)})",
        f"RL out {('vn' if ctx.split else '0') if fx.get('rl_to') == 'vn' else 'mid'} {_r(rl)}", f"CL out mid {_r(cl)}"]
    ctx.park_unused(ch, n, lines)
    lines.append(instantiate(ctx.netlist, n, dut_name=ctx.dut_name))
    lo, hi = -amp * 0.6, amp * 0.6          # 20% / 80% of the 2*amp swing
    t_end = t0 + 2 * t_sw + 1e-6
    meas = [f".meas tran m_tr1 WHEN V(out,mid)={_r(lo)} RISE=1 TD={_r(t0)}",
            f".meas tran m_tr2 WHEN V(out,mid)={_r(hi)} RISE=1 TD={_r(t0)}",
            f".meas tran m_tf1 WHEN V(out,mid)={_r(hi)} FALL=1 TD={_r(t0 + t_sw)}",
            f".meas tran m_tf2 WHEN V(out,mid)={_r(lo)} FALL=1 TD={_r(t0 + t_sw)}"]

    def extract(r):
        out = {}
        if r.get("m_tr1") is not None and r.get("m_tr2") is not None and r["m_tr2"] > r["m_tr1"]:
            out["sr_rise"] = (hi - lo) / (r["m_tr2"] - r["m_tr1"]) * 1e-6
        if r.get("m_tf1") is not None and r.get("m_tf2") is not None and r["m_tf2"] > r["m_tf1"]:
            out["sr_fall"] = (hi - lo) / (r["m_tf2"] - r["m_tf1"]) * 1e-6
        if out:
            out["sr"] = min(out.values())
        return out
    return Deck(key, "opamp_sr", f"slew rate follower VS={vs}", lines,
                f".tran 0 {_r(t_end)} 0 {_r(t_sw / 2000)}", meas, extract, fx)


def opamp_swing(ctx: FixtureContext, key: str, fx: dict[str, Any]) -> Deck:
    vs, ch = fx["vs"], ctx.ch()
    rail = fx.get("rail") or "pos"
    iout = fx.get("iout")
    rl = fx.get("rl")
    if iout:
        rl = max(1.0, (vs / 2) / abs(iout))
    rl = rl or 10e3
    ovd = 0.2 if rail == "pos" else -0.2
    n = ctx.base_nodes(vs); n.update({ch["inp"]: "inp", ch["inn"]: "mid", ch["out"]: "out"})
    lines = ctx.supply_tran(vs) + [f"VIN inp mid {_r(ovd)}", f"RL out {('vn' if ctx.split else '0') if fx.get('rl_to') == 'vn' else 'mid'} {_r(rl)}"]
    ctx.park_unused(ch, n, lines)
    lines.append(instantiate(ctx.netlist, n, dut_name=ctx.dut_name))
    w = ctx.win()
    meas = [f".meas tran m_out AVG V(out) {w}", f".meas tran m_vp AVG V(vp) {w}"]
    if ctx.split:
        meas.append(f".meas tran m_vn AVG V(vn) {w}")

    def extract(r):
        if "m_out" not in r:
            return {}
        vn = r.get("m_vn", 0.0)
        if rail == "pos":
            return {"voh": r["m_out"], "vswing": r["m_vp"] - r["m_out"], "headroom_pos": r["m_vp"] - r["m_out"]}
        return {"vol": r["m_out"], "vswing": r["m_out"] - vn, "headroom_neg": r["m_out"] - vn}
    return Deck(key, "opamp_swing", f"output swing {rail} rail RL={rl:.4g} VS={vs}", lines, ctx.tran(), meas, extract, fx)


def opamp_iout(ctx: FixtureContext, key: str, fx: dict[str, Any]) -> Deck:
    """Output current at a forced output voltage (datasheet: VO = V+ or V-, VID = +-1 V)."""
    vs, ch = fx["vs"], ctx.ch()
    at = fx.get("vo_at") or "pos"
    off = fx.get("vo_offset") or 0.0
    vp, vn = (vs / 2, -vs / 2) if ctx.split else (vs, 0.0)
    vforce = (vp if at == "pos" else vn + off)
    vid = fx.get("vid") if fx.get("vid") is not None else (-1.0 if at == "pos" else 1.0)
    n = ctx.base_nodes(vs); n.update({ch["inp"]: "inp", ch["inn"]: "mid", ch["out"]: "out"})
    lines = ctx.supply_tran(vs) + [f"VIN inp mid {_r(vid)}", f"VFORCE out 0 {_r(vforce)}"]
    ctx.park_unused(ch, n, lines)
    lines.append(instantiate(ctx.netlist, n, dut_name=ctx.dut_name))
    meas = [f".meas tran m_i AVG I(VFORCE) {ctx.win()}"]

    def extract(r):
        return {"iout": abs(r["m_i"])} if "m_i" in r else {}
    return Deck(key, "opamp_iout", f"output current at VO={at} rail VS={vs}", lines, ctx.tran(), meas, extract, fx)


def opamp_isc(ctx: FixtureContext, key: str, fx: dict[str, Any]) -> Deck:
    vs, ch = fx["vs"], ctx.ch()
    rail = fx.get("rail") or "pos"
    ovd = 1.0 if rail == "pos" else -1.0
    n = ctx.base_nodes(vs); n.update({ch["inp"]: "inp", ch["inn"]: "mid", ch["out"]: "out"})
    lines = ctx.supply_tran(vs) + [f"VIN inp mid {_r(ovd)}", "VSHORT out mid 0"]
    ctx.park_unused(ch, n, lines)
    lines.append(instantiate(ctx.netlist, n, dut_name=ctx.dut_name))
    meas = [f".meas tran m_isc AVG I(VSHORT) {ctx.win()}"]

    def extract(r):
        return {"isc": abs(r["m_isc"]), "iout": abs(r["m_isc"])} if "m_isc" in r else {}
    return Deck(key, "opamp_isc", f"short-circuit current {rail} VS={vs}", lines, ctx.tran(), meas, extract, fx)


def opamp_noise(ctx: FixtureContext, key: str, fx: dict[str, Any]) -> Deck:
    vs, ch = fx["vs"], ctx.ch()
    n = ctx.base_nodes(vs); n.update({ch["inp"]: "inp", ch["inn"]: "out", ch["out"]: "out"})
    lines = ctx.supply_dc(vs) + ["VIN inp mid 0", "RL out mid 10k"]
    ctx.park_unused(ch, n, lines)
    lines.append(instantiate(ctx.netlist, n, dut_name=ctx.dut_name))
    f = fx.get("freq") or 1000.0
    meas = [f".meas noise m_en FIND V(inoise) AT {_r(f)}"]

    def extract(r):
        return {"en": r["m_en"] * 1e9} if r.get("m_en") is not None else {}
    return Deck(key, "opamp_noise", f"input noise density VS={vs}", lines, ".noise V(out) VIN dec 10 1 1Meg", meas, extract, fx)


# ============================================================================ COMPARATOR
def _cmp_pullup(fx, vs):
    return fx.get("rl") or 5.1e3


def cmp_vos(ctx: FixtureContext, key: str, fx: dict[str, Any]) -> Deck:
    vs, ch = fx["vs"], ctx.ch()
    vref = 1.4 if vs >= 3 else vs / 2
    t0, span, tr = ctx.t_settle, 0.05, 400e-6
    n = ctx.base_nodes(vs); n.update({ch["inp"]: "inp", ch["inn"]: "inn", ch["out"]: "out"})
    lines = ctx.supply_tran(vs) + [f"VREF inn 0 {_r(vref)}",
                                   f"VIN inp 0 PWL(0 {_r(vref - span)} {_r(t0)} {_r(vref - span)} {_r(t0 + tr)} {_r(vref + span)})",
                                   f"RPU out vp {_r(_cmp_pullup(fx, vs))}", "CL out 0 15p"]
    ctx.park_unused(ch, n, lines)
    lines.append(instantiate(ctx.netlist, n, dut_name=ctx.dut_name))
    meas = [f".meas tran m_vin FIND V(inp,inn) WHEN V(out)={_r(vs / 2)} RISE=1 TD={_r(t0)}"]

    def extract(r):
        return {"vos": r["m_vin"]} if r.get("m_vin") is not None else {}
    return Deck(key, "cmp_vos", f"comparator VOS ramp VS={vs}", lines,
                f".tran 0 {_r(t0 + tr + 10e-6)} 0 {_r(tr / 4000)}", meas, extract, fx)


def cmp_ib(ctx: FixtureContext, key: str, fx: dict[str, Any]) -> Deck:
    vs, ch = fx["vs"], ctx.ch()
    vcm = 1.4 if vs >= 3 else vs / 2
    n = ctx.base_nodes(vs); n.update({ch["inp"]: "inp", ch["inn"]: "inn", ch["out"]: "out"})
    lines = ctx.supply_tran(vs) + [f"VCM cm 0 {_r(vcm)}", "VSP cm inp 0", "VSN cm inn 0",
                                   f"RPU out vp {_r(_cmp_pullup(fx, vs))}"]
    ctx.park_unused(ch, n, lines)
    lines.append(instantiate(ctx.netlist, n, dut_name=ctx.dut_name))
    w = ctx.win()
    meas = [f".meas tran m_isp AVG I(VSP) {w}", f".meas tran m_isn AVG I(VSN) {w}", f".meas tran m_ipos AVG I(VPOS) {w}"]

    def extract(r):
        out = {}
        if "m_isp" in r and "m_isn" in r:
            out["ib"] = (r["m_isp"] + r["m_isn"]) / 2
            out["ios"] = abs(r["m_isp"] - r["m_isn"])
        return out
    return Deck(key, "cmp_ib", f"comparator IB/IOS VS={vs}", lines, ctx.tran(), meas, extract, fx)


def cmp_avd(ctx: FixtureContext, key: str, fx: dict[str, Any]) -> Deck:
    vs, ch = fx.get("vs") or 15.0, ctx.ch()
    rl = fx.get("rl") or 15e3
    vref = 1.4
    t0, span, tr = ctx.t_settle, 0.02, 300e-6
    n = ctx.base_nodes(vs); n.update({ch["inp"]: "inp", ch["inn"]: "inn", ch["out"]: "out"})
    lines = ctx.supply_tran(vs) + [f"VREF inn 0 {_r(vref)}",
                                   f"VIN inp 0 PWL(0 {_r(vref + span)} {_r(t0)} {_r(vref + span)} {_r(t0 + tr)} {_r(vref - span)})",
                                   f"RPU out vp {_r(rl)}"]
    ctx.park_unused(ch, n, lines)
    lines.append(instantiate(ctx.netlist, n, dut_name=ctx.dut_name))
    vlo, vhi = 1.4, min(11.4, vs - 1.0)
    meas = [f".meas tran m_v1 FIND V(inp,inn) WHEN V(out)={_r(vhi)} FALL=1 TD={_r(t0)}",
            f".meas tran m_v2 FIND V(inp,inn) WHEN V(out)={_r(vlo)} FALL=1 TD={_r(t0)}"]

    def extract(r):
        if r.get("m_v1") is None or r.get("m_v2") is None:
            return {}
        d = abs(r["m_v1"] - r["m_v2"])
        return {"avd_db": 20 * math.log10((vhi - vlo) / d)} if d > 0 else {"avd_db": 200.0}
    return Deck(key, "cmp_avd", f"comparator AVD VS={vs}", lines, f".tran 0 {_r(t0 + tr + 10e-6)} 0 {_r(tr / 3000)}", meas, extract, fx)


def cmp_vol(ctx: FixtureContext, key: str, fx: dict[str, Any]) -> Deck:
    vs, ch = fx["vs"], ctx.ch()
    iol = fx.get("iout") or 4e-3
    vid = fx.get("vid") or -1.0
    n = ctx.base_nodes(vs); n.update({ch["inp"]: "inp", ch["inn"]: "inn", ch["out"]: "out"})
    lines = ctx.supply_tran(vs) + ["VCM inn 0 1.4", f"VID inp inn {_r(-abs(vid))}", f"ISINK vp out {_r(abs(iol))}"]
    ctx.park_unused(ch, n, lines)
    lines.append(instantiate(ctx.netlist, n, dut_name=ctx.dut_name))
    meas = [f".meas tran m_vol AVG V(out) {ctx.win()}"]

    def extract(r):
        return {"vol": r["m_vol"]} if "m_vol" in r else {}
    return Deck(key, "cmp_vol", f"comparator VOL @IOL={iol:.3g} VS={vs}", lines, ctx.tran(), meas, extract, fx)


def cmp_iol(ctx: FixtureContext, key: str, fx: dict[str, Any]) -> Deck:
    vs, ch = fx["vs"], ctx.ch()
    vo = fx.get("vo") or 1.5
    n = ctx.base_nodes(vs); n.update({ch["inp"]: "inp", ch["inn"]: "inn", ch["out"]: "out"})
    lines = ctx.supply_tran(vs) + ["VCM inn 0 1.4", "VID inp inn -1", f"VFORCE out 0 {_r(vo)}"]
    ctx.park_unused(ch, n, lines)
    lines.append(instantiate(ctx.netlist, n, dut_name=ctx.dut_name))
    meas = [f".meas tran m_i AVG I(VFORCE) {ctx.win()}"]

    def extract(r):
        return {"iol": -r["m_i"]} if "m_i" in r else {}
    return Deck(key, "cmp_iol", f"comparator IOL @VOL={vo} VS={vs}", lines, ctx.tran(), meas, extract, fx)


def cmp_ioh(ctx: FixtureContext, key: str, fx: dict[str, Any]) -> Deck:
    vs, ch = fx["vs"], ctx.ch()
    vo = fx.get("vo") or vs
    n = ctx.base_nodes(vs); n.update({ch["inp"]: "inp", ch["inn"]: "inn", ch["out"]: "out"})
    lines = ctx.supply_tran(vs) + ["VCM inn 0 1.4", "VID inp inn 1", f"VFORCE out 0 {_r(vo)}"]
    ctx.park_unused(ch, n, lines)
    lines.append(instantiate(ctx.netlist, n, dut_name=ctx.dut_name))
    meas = [f".meas tran m_i AVG I(VFORCE) {ctx.win()}"]

    def extract(r):
        return {"ioh": abs(r["m_i"])} if "m_i" in r else {}
    return Deck(key, "cmp_ioh", f"comparator IOH @VOH={vo} VS={vs}", lines, ctx.tran(), meas, extract, fx)


def cmp_icc(ctx: FixtureContext, key: str, fx: dict[str, Any]) -> Deck:
    vs, ch = fx["vs"], ctx.ch()
    n = ctx.base_nodes(vs); n.update({ch["inp"]: "inp", ch["inn"]: "inn", ch["out"]: "out"})
    lines = ctx.supply_tran(vs) + ["VCM inn 0 1.4", "VID inp inn -1", "ROUT_BLEED out 0 1G"]
    ctx.park_unused(ch, n, lines)
    lines.append(instantiate(ctx.netlist, n, dut_name=ctx.dut_name))
    meas = [f".meas tran m_ipos AVG I(VPOS) {ctx.win()}"]

    def extract(r):
        return {"iq": -r["m_ipos"], "iq_total": -r["m_ipos"]} if "m_ipos" in r else {}
    return Deck(key, "cmp_icc", f"comparator ICC VS={vs}", lines, ctx.tran(), meas, extract, fx)


def cmp_tresp(ctx: FixtureContext, key: str, fx: dict[str, Any]) -> Deck:
    vs, ch = fx["vs"], ctx.ch()
    rpu = fx.get("rl") or 5.1e3
    cl = fx.get("cl") or 15e-12
    step, ovd = 0.1, 0.005
    t0 = ctx.t_settle
    n = ctx.base_nodes(vs); n.update({ch["inp"]: "inp", ch["inn"]: "inn", ch["out"]: "out"})
    lines = ctx.supply_tran(vs) + [f"VREF inn 0 {_r(1.4 + step - ovd)}",
                                   f"VIN inp 0 PULSE(1.4 {_r(1.4 + step)} {_r(t0)} 10n 10n 20u 40u)",
                                   f"RPU out vp {_r(rpu)}", f"CL out 0 {_r(cl)}"]
    ctx.park_unused(ch, n, lines)
    lines.append(instantiate(ctx.netlist, n, dut_name=ctx.dut_name))
    meas = [f".meas tran m_t WHEN V(out)={_r(vs / 2)} RISE=1 TD={_r(t0)}"]

    def extract(r):
        return {"tresp": r["m_t"] - t0} if r.get("m_t") is not None else {}
    return Deck(key, "cmp_tresp", f"comparator response time VS={vs}", lines, f".tran 0 {_r(t0 + 25e-6)} 0 5n", meas, extract, fx)


# ============================================================================ 555 TIMER
def _t(ctx: FixtureContext) -> dict[str, str]:
    t = dict(ctx.pm.get("timer") or {})
    if not {"trig", "thres", "out"} <= set(t):
        _, pins = subckt_header(ctx.netlist, ctx.dut_name)
        from .spec_planner import map_pins
        inferred = map_pins("timer", [{"name": p, "raw_name": p} for p in pins]).get("timer") or {}
        t.update({k: v for k, v in inferred.items() if k not in t})
    t.setdefault("trig", "TRIG")
    t.setdefault("thres", "THRES")
    t.setdefault("out", "OUT")
    return t


def timer_nodes(ctx, vs):
    t = _t(ctx)
    n = ctx.base_nodes(vs)
    n.update({t["trig"]: "trig", t["thres"]: "thres", t["out"]: "out"})
    if "reset" in t:
        n[t["reset"]] = "rst"
    if "cont" in t:
        n[t["cont"]] = "cont"
    if "disch" in t:
        n[t["disch"]] = "disch"
    return n, t


def timer_common(ctx, vs, rst="vp"):
    lines = ctx.supply_tran(vs)
    lines.append(f"RRST rst {rst} 1" if rst == "vp" else f"VRST rst 0 {rst}")
    lines.append("CCONT cont 0 10n")
    return lines


def t555_vth(ctx, key, fx):
    vs = fx["vs"]; n, t = timer_nodes(ctx, vs)
    t0, tr = ctx.t_settle, 500e-6
    lines = timer_common(ctx, vs) + [
        f"VTRIG trig 0 PWL(0 {_r(vs)} {_r(t0)} {_r(vs)} {_r(t0 + 1e-6)} 0 {_r(t0 + 5e-6)} 0 {_r(t0 + 6e-6)} {_r(vs)})",
        f"VTHR thres 0 PWL(0 0 {_r(t0 + 10e-6)} 0 {_r(t0 + 10e-6 + tr)} {_r(vs)})",
        "RL out 0 10k", instantiate(ctx.netlist, n, dut_name=ctx.dut_name)]
    meas = [f".meas tran m_v FIND V(thres) WHEN V(out)={_r(vs / 2)} FALL=1 TD={_r(t0 + 8e-6)}"]
    return Deck(key, "t555_vth", f"555 VTH ramp VS={vs}", lines, f".tran 0 {_r(t0 + tr + 20e-6)} 0 {_r(tr / 5000)}", meas,
                lambda r: {"vth": r["m_v"]} if r.get("m_v") is not None else {}, fx)


def t555_vtrig(ctx, key, fx):
    vs = fx["vs"]; n, t = timer_nodes(ctx, vs)
    t0, tr = ctx.t_settle, 500e-6
    lines = timer_common(ctx, vs) + [
        f"VTHR thres 0 PWL(0 0 {_r(t0)} 0 {_r(t0 + 1e-6)} {_r(vs)} {_r(t0 + 5e-6)} {_r(vs)} {_r(t0 + 6e-6)} 0)",
        f"VTRIG trig 0 PWL(0 {_r(vs)} {_r(t0 + 10e-6)} {_r(vs)} {_r(t0 + 10e-6 + tr)} 0)",
        "RL out 0 10k", instantiate(ctx.netlist, n, dut_name=ctx.dut_name)]
    meas = [f".meas tran m_v FIND V(trig) WHEN V(out)={_r(vs / 2)} RISE=1 TD={_r(t0 + 8e-6)}"]
    return Deck(key, "t555_vtrig", f"555 VTRIG ramp VS={vs}", lines, f".tran 0 {_r(t0 + tr + 20e-6)} 0 {_r(tr / 5000)}", meas,
                lambda r: {"vtrig": r["m_v"]} if r.get("m_v") is not None else {}, fx)


def t555_vreset(ctx, key, fx):
    vs = fx["vs"]; n, t = timer_nodes(ctx, vs)
    t0, tr = ctx.t_settle, 500e-6
    lines = ctx.supply_tran(vs) + ["CCONT cont 0 10n", "VTHR thres 0 0", "VTRIG trig 0 0",
                                   f"VRST rst 0 PWL(0 {_r(vs)} {_r(t0)} {_r(vs)} {_r(t0 + tr)} 0)",
                                   "RL out 0 10k", instantiate(ctx.netlist, n, dut_name=ctx.dut_name)]
    meas = [f".meas tran m_v FIND V(rst) WHEN V(out)={_r(vs / 2)} FALL=1 TD={_r(t0)}"]
    return Deck(key, "t555_vreset", f"555 VRESET ramp VS={vs}", lines, f".tran 0 {_r(t0 + tr + 20e-6)} 0 {_r(tr / 5000)}", meas,
                lambda r: {"vreset": r["m_v"]} if r.get("m_v") is not None else {}, fx)


def t555_vcont(ctx, key, fx):
    vs = fx["vs"]; n, t = timer_nodes(ctx, vs)
    lines = ctx.supply_tran(vs) + ["RRST rst vp 1", "VTHR thres 0 0", "VTRIG trig vp 0", "RCONT cont 0 1G",
                                   "RL out 0 10k", instantiate(ctx.netlist, n, dut_name=ctx.dut_name)]
    meas = [f".meas tran m_v AVG V(cont) {ctx.win()}"]
    return Deck(key, "t555_vcont", f"555 VCONT VS={vs}", lines, ctx.tran(), meas,
                lambda r: {"vcont": r["m_v"]} if "m_v" in r else {}, fx)


def t555_state(ctx, key, fx, state, kind):
    """Output forced LOW (thres=VCC) or HIGH (trig=0); VOL/VOH under load current, ICC."""
    vs = fx["vs"]; n, t = timer_nodes(ctx, vs)
    io = fx.get("iout")
    lines = timer_common(ctx, vs)
    if state == "low":
        lines += [f"VTHR thres 0 {_r(vs)}", f"VTRIG trig 0 {_r(vs)}"]
    else:
        lines += ["VTHR thres 0 0", "VTRIG trig 0 0"]
    if kind in ("vol555", "voh555") and io:
        rl = max(0.5, (vs / 2) / abs(io))
        lines.append(f"RL out {'vp' if state == 'low' else '0'} {_r(rl)}")
    lines.append(instantiate(ctx.netlist, n, dut_name=ctx.dut_name))
    w = ctx.win()
    meas = [f".meas tran m_out AVG V(out) {w}", f".meas tran m_ipos AVG I(VPOS) {w}"]

    def extract(r):
        out = {}
        if "m_out" in r:
            out["vol555" if state == "low" else "voh555"] = r["m_out"]
        if "m_ipos" in r:
            out["iq"] = -r["m_ipos"]
        return out
    return Deck(key, f"t555_{state}", f"555 output {state} VS={vs} IO={io}", lines, ctx.tran(), meas, extract, fx)


def t555_pin_current(ctx, key, fx, kind):
    vs = fx["vs"]; n, t = timer_nodes(ctx, vs)
    lines = ctx.supply_tran(vs) + ["CCONT cont 0 10n", "RL out 0 10k"]
    if kind == "ith":
        lines += ["RRST rst vp 1", "VTRIG trig vp 0", f"VTHR thres_s 0 {_r(vs * 2 / 3 + 0.3)}", "VSENSE thres_s thres 0"]
        src = "VSENSE"
    elif kind == "itrig":
        lines += ["RRST rst vp 1", "VTHR thres 0 0", "VTRIG trig_s 0 0", "VSENSE trig_s trig 0"]
        src = "VSENSE"
    else:  # ireset
        lvl = fx.get("rst_level", vs)
        lines += ["VTHR thres 0 0", "VTRIG trig vp 0", f"VRST rst_s 0 {_r(lvl)}", "VSENSE rst_s rst 0"]
        src = "VSENSE"
    lines.append(instantiate(ctx.netlist, n, dut_name=ctx.dut_name))
    meas = [f".meas tran m_i AVG I({src}) {ctx.win()}"]
    return Deck(key, f"t555_{kind}", f"555 {kind} VS={vs}", lines, ctx.tran(), meas,
                lambda r: {kind: r["m_i"]} if "m_i" in r else {}, fx)


def t555_disch(ctx, key, fx, kind):
    vs = fx["vs"]; n, t = timer_nodes(ctx, vs)
    if "disch" not in t:
        raise ValueError("no DISCH pin")
    io = fx.get("iout") or 8e-3
    lines = timer_common(ctx, vs) + ["RL out 0 10k"]
    if kind == "vdisch_on":
        lines += [f"VTHR thres 0 {_r(vs)}", f"VTRIG trig 0 {_r(vs)}", f"IDIS vp disch {_r(io)}"]
        meas = [f".meas tran m_v AVG V(disch) {ctx.win()}"]
        ex = lambda r: {"vdisch_on": r["m_v"]} if "m_v" in r else {}
    else:
        lines += ["VTHR thres 0 0", "VTRIG trig 0 0", f"VDIS disch 0 {_r(vs)}"]
        meas = [f".meas tran m_i AVG I(VDIS) {ctx.win()}"]
        ex = lambda r: {"idisch_off": abs(r["m_i"])} if "m_i" in r else {}
    lines.append(instantiate(ctx.netlist, n, dut_name=ctx.dut_name))
    return Deck(key, f"t555_{kind}", f"555 {kind} VS={vs}", lines, ctx.tran(), meas, ex, fx)


def t555_edges(ctx, key, fx):
    vs = fx["vs"]; n, t = timer_nodes(ctx, vs)
    cl = fx.get("cl") or 15e-12
    t0 = ctx.t_settle
    # Output is first forced LOW (THRES high), released at t0+20u, then TRIG is pulled low at t0+30u so the
    # output makes a clean LOW->HIGH edge; THRES is raised again at t0+60u for the HIGH->LOW edge.
    lines = timer_common(ctx, vs) + [
        f"VTRIG trig 0 PWL(0 {_r(vs)} {_r(t0 + 30e-6)} {_r(vs)} {_r(t0 + 30.01e-6)} 0 {_r(t0 + 34e-6)} 0 {_r(t0 + 34.01e-6)} {_r(vs)})",
        f"VTHR thres 0 PWL(0 {_r(vs)} {_r(t0 + 20e-6)} {_r(vs)} {_r(t0 + 20.01e-6)} 0 {_r(t0 + 60e-6)} 0 {_r(t0 + 60.01e-6)} {_r(vs)})",
        f"CL out 0 {_r(cl)}", instantiate(ctx.netlist, n, dut_name=ctx.dut_name)]
    lo, hi = 0.2 * vs, 0.8 * vs
    meas = [f".meas tran m_r1 WHEN V(out)={_r(lo)} RISE=1 TD={_r(t0 + 30e-6)}", f".meas tran m_r2 WHEN V(out)={_r(hi)} RISE=1 TD={_r(t0 + 30e-6)}",
            f".meas tran m_f1 WHEN V(out)={_r(hi)} FALL=1 TD={_r(t0 + 60e-6)}", f".meas tran m_f2 WHEN V(out)={_r(lo)} FALL=1 TD={_r(t0 + 60e-6)}"]

    def extract(r):
        out = {}
        if r.get("m_r1") is not None and r.get("m_r2") is not None:
            out["tr555"] = r["m_r2"] - r["m_r1"]
        if r.get("m_f1") is not None and r.get("m_f2") is not None:
            out["tf555"] = r["m_f2"] - r["m_f1"]
        return out
    return Deck(key, "t555_edges", f"555 rise/fall VS={vs}", lines, f".tran 0 {_r(t0 + 80e-6)} 0 5n", meas, extract, fx)


# ============================================================================ SHUNT REFERENCE (TL431)
def _s(ctx):
    s = dict(ctx.pm.get("shunt") or {})
    if not {"cathode", "ref", "anode"} <= set(s):
        _, pins = subckt_header(ctx.netlist, ctx.dut_name)
        from .spec_planner import map_pins
        inferred = map_pins("shunt_ref", [{"name": p, "raw_name": p} for p in pins]).get("shunt") or {}
        s.update({k: v for k, v in inferred.items() if k not in s})
    s.setdefault("cathode", "CATHODE")
    s.setdefault("ref", "REF")
    s.setdefault("anode", "ANODE")
    return s


def shunt_vref(ctx, key, fx):
    s = _s(ctx); n = {s["cathode"]: "k", s["ref"]: "k", s["anode"]: "0"}
    ika = fx.get("iout") or 10e-3
    lines = [f"IKA k 0 DC {_r(-ika)}" , "VDC vsrc 0 20", f"RK vsrc k {_r((20 - 2.5) / ika)}"]
    lines = ["VDC vsrc 0 20", f"RK vsrc k {_r((20 - 2.5) / ika)}", instantiate(ctx.netlist, n, dut_name=ctx.dut_name)]
    meas = [".meas tran m_v AVG V(k) FROM 150u TO 200u"]
    return Deck(key, "shunt_vref", f"TL431 Vref IKA={ika}", lines, ".tran 0 200u 0 100n", meas,
                lambda r: {"vref": r["m_v"]} if "m_v" in r else {}, fx)


def shunt_dvref(ctx, key, fx):
    s = _s(ctx); n = {s["cathode"]: "k", s["ref"]: "ref", s["anode"]: "0"}
    vka = fx.get("vka") or 10.0
    r1 = 10e3
    r2 = r1 * 2.495 / (vka - 2.495)
    lines = ["VDC vsrc 0 40", f"RK vsrc k {_r((40 - vka) / 10e-3)}", f"R1 k ref {_r(r1)}", f"R2 ref 0 {_r(r2)}",
             instantiate(ctx.netlist, n, dut_name=ctx.dut_name)]
    meas = [".meas tran m_vref AVG V(ref) FROM 150u TO 200u", ".meas tran m_vka AVG V(k) FROM 150u TO 200u"]
    return Deck(key, "shunt_dvref", f"TL431 Vref at VKA={vka}", lines, ".tran 0 200u 0 100n", meas,
                lambda r: {"vref_at_vka": r["m_vref"], "vka": r["m_vka"]} if "m_vref" in r else {}, fx)


def shunt_iref(ctx, key, fx):
    s = _s(ctx); n = {s["cathode"]: "k", s["ref"]: "ref", s["anode"]: "0"}
    lines = ["VDC vsrc 0 20", f"RK vsrc k {_r((20 - 5) / 10e-3)}", "R1 k r1 10k", "VSENSE r1 ref 0", instantiate(ctx.netlist, n, dut_name=ctx.dut_name)]
    meas = [".meas tran m_i AVG I(VSENSE) FROM 150u TO 200u"]
    return Deck(key, "shunt_iref", "TL431 Iref", lines, ".tran 0 200u 0 100n", meas,
                lambda r: {"iref": abs(r["m_i"])} if "m_i" in r else {}, fx)


def shunt_ioff(ctx, key, fx):
    s = _s(ctx); n = {s["cathode"]: "k", s["ref"]: "0", s["anode"]: "0"}
    lines = ["VKA k 0 36", instantiate(ctx.netlist, n, dut_name=ctx.dut_name)]
    meas = [".meas tran m_i AVG I(VKA) FROM 150u TO 200u"]
    return Deck(key, "shunt_ioff", "TL431 Ioff", lines, ".tran 0 200u 0 100n", meas,
                lambda r: {"ioff": abs(r["m_i"])} if "m_i" in r else {}, fx)


def shunt_imin(ctx, key, fx):
    s = _s(ctx); n = {s["cathode"]: "k", s["ref"]: "k", s["anode"]: "0"}
    lines = ["IKA 0 k PWL(0 0 1m 2m)", instantiate(ctx.netlist, n, dut_name=ctx.dut_name)]
    meas = [".meas tran m_v2m FIND V(k) AT 0.99m", ".meas tran m_t WHEN V(k)=2.45 RISE=1"]

    def extract(r):
        return {"imin": r["m_t"] * 2.0} if r.get("m_t") is not None else {}   # I = 2 A/s * t
    return Deck(key, "shunt_imin", "TL431 Imin", lines, ".tran 0 1m 0 200n", meas, extract, fx)


def shunt_zka(ctx, key, fx):
    s = _s(ctx); n = {s["cathode"]: "k", s["ref"]: "k", s["anode"]: "0"}
    lines = ["IKA 0 k DC 10m AC 1m", instantiate(ctx.netlist, n, dut_name=ctx.dut_name)]
    meas = [".meas ac m_z FIND V(k) AT 1k"]
    return Deck(key, "shunt_zka", "TL431 |ZKA|", lines, ".ac dec 10 10 100k", meas,
                lambda r: {"zka": r["m_z_mag"] / 1e-3} if "m_z_mag" in r else {}, fx)


# ============================================================================ LDO (LM317)
def _l(ctx):
    l = dict(ctx.pm.get("ldo") or {})
    if not {"in", "out", "adj"} <= set(l):
        _, pins = subckt_header(ctx.netlist, ctx.dut_name)
        from .spec_planner import map_pins
        inferred = map_pins("ldo", [{"name": p, "raw_name": p} for p in pins]).get("ldo") or {}
        l.update({k: v for k, v in inferred.items() if k not in l})
    l.setdefault("in", "IN")
    l.setdefault("out", "OUT")
    l.setdefault("adj", "ADJ")
    return l


def ldo_base(ctx, fx, vin=None, iload=10e-3, extra=None):
    l = _l(ctx); n = {l["in"]: "vin", l["out"]: "out", l["adj"]: "adj"}
    vout = 5.0
    r1, r2 = 240.0, 720.0
    vin = vin or (vout + 5.0)
    lines = [f"VIN vin 0 {_r(vin)}", f"R1 out adj_s {_r(r1)}", "VSENSE adj_s adj 0", f"R2 adj 0 {_r(r2)}",
             f"ILOAD out 0 {_r(iload)}", "CIN vin 0 100n", "COUT out 0 1u"] + (extra or []) + [instantiate(ctx.netlist, n, dut_name=ctx.dut_name)]
    return lines


def ldo_dc(ctx, key, fx):
    lines = ldo_base(ctx, fx)
    meas = [".meas tran m_vo AVG V(out) FROM 1.5m TO 2m", ".meas tran m_vadj AVG V(adj) FROM 1.5m TO 2m",
            ".meas tran m_iadj AVG I(VSENSE) FROM 1.5m TO 2m"]

    def extract(r):
        o = {}
        if "m_vo" in r and "m_vadj" in r:
            o["vref_ldo"] = r["m_vo"] - r["m_vadj"]
        if "m_iadj" in r:
            o["iadj"] = abs(r["m_iadj"])
        return o
    return Deck(key, "ldo_dc", "LM317 VREF/IADJ", lines, ".tran 0 2m 0 1u", meas, extract, fx)


def ldo_line(ctx, key, fx):
    lines = ldo_base(ctx, fx)
    lines = [l if not l.startswith("VIN ") else "VIN vin 0 8" for l in lines]
    meas = [".meas dc m_v1 FIND V(out) AT 8", ".meas dc m_v2 FIND V(out) AT 45"]

    def extract(r):
        if "m_v1" in r and "m_v2" in r and r["m_v1"]:
            return {"line_reg": abs(r["m_v2"] - r["m_v1"]) / r["m_v1"] * 100 / (45 - 8)}
        return {}
    return Deck(key, "ldo_line", "LM317 line regulation", lines, ".dc VIN 8 45 1", meas, extract, fx)


def ldo_load(ctx, key, fx):
    lines = ldo_base(ctx, fx, vin=10.0)
    meas = [".meas dc m_v1 FIND V(out) AT 10m", ".meas dc m_v2 FIND V(out) AT 1.5"]

    def extract(r):
        if "m_v1" in r and "m_v2" in r:
            return {"load_reg": abs(r["m_v1"] - r["m_v2"]), "load_reg_pct": abs(r["m_v1"] - r["m_v2"]) / r["m_v1"] * 100}
        return {}
    return Deck(key, "ldo_load", "LM317 load regulation", lines, ".dc ILOAD 10m 1.5 10m", meas, extract, fx)


def ldo_ilim(ctx, key, fx):
    l = _l(ctx); n = {l["in"]: "vin", l["out"]: "out", l["adj"]: "0"}
    vdiff = 15.0
    lines = [f"VIN vin 0 {_r(vdiff)}", "VSHORT out 0 0", instantiate(ctx.netlist, n, dut_name=ctx.dut_name)]
    meas = [".meas tran m_i AVG I(VSHORT) FROM 1.5m TO 2m"]
    return Deck(key, "ldo_ilim", "LM317 current limit", lines, ".tran 0 2m 0 1u", meas,
                lambda r: {"ilim": abs(r["m_i"])} if "m_i" in r else {}, fx)


def ldo_psrr(ctx, key, fx):
    l = _l(ctx); n = {l["in"]: "vin", l["out"]: "out", l["adj"]: "adj"}
    r1, r2 = 240.0, 1680.0   # VOUT = 10 V
    lines = ["VIN vin 0 15 AC 1", f"R1 out adj {_r(r1)}", f"R2 adj 0 {_r(r2)}", "CADJ adj 0 10u", "ILOAD out 0 10m",
             "COUT out 0 1u", instantiate(ctx.netlist, n, dut_name=ctx.dut_name)]
    meas = [".meas ac m_v FIND V(out) AT 120"]
    return Deck(key, "ldo_psrr", "LM317 ripple rejection 120Hz", lines, ".ac dec 10 10 10k", meas,
                lambda r: {"psrr_ldo_db": -r["m_v_db"]} if "m_v_db" in r else {}, fx)


# ============================================================================ dispatcher
def build_decks(ctx: FixtureContext) -> tuple[dict[str, Deck], dict[str, str]]:
    """Returns ({fixture_key: Deck}, {fixture_key: error}) for all PLANNED items of the plan."""
    decks: dict[str, Deck] = {}
    errors: dict[str, str] = {}
    sr_hint = 1.0
    for it in ctx.plan["items"]:
        if it.get("kind") == "sr" and it.get("typ"):
            sr_hint = float(it["typ"])
    for it in ctx.plan["items"]:
        if it["status"] != "PLANNED":
            continue
        key, kind, fx = it["fixture_key"], it["kind"], it["fixture"]
        if key in decks or key in errors:
            continue
        try:
            if ctx.cls == "comparator" and kind == "vos":
                d = cmp_vos(ctx, key, fx)
            elif ctx.cls == "comparator" and kind in ("ib", "ios"):
                d = cmp_ib(ctx, key, fx)
            elif ctx.cls == "comparator" and kind == "iq":
                d = cmp_icc(ctx, key, fx)
            elif ctx.cls == "timer" and kind == "iq":
                d = t555_state(ctx, key, fx, fx.get("state") or "low", kind)
            elif kind in ("vos", "ib", "ios", "iq") and ctx.cls in ("opamp", "inamp", "audio_amp"):
                d = opamp_dc(ctx, key, fx)
            elif kind in ("aol_db", "gbw", "pm"):
                d = opamp_openloop(ctx, key, fx)
            elif kind == "cmrr_db":
                d = opamp_openloop(ctx, key, fx, cm=True)
            elif kind == "psrr_db":
                d = opamp_psrr(ctx, key, fx)
            elif kind == "sr":
                d = opamp_sr(ctx, key, fx, sr_hint)
            elif kind == "vswing":
                d = opamp_swing(ctx, key, fx)
            elif kind in ("isc", "iout"):
                d = opamp_iout(ctx, key, fx) if (kind == "iout" and fx.get("vo_at")) else opamp_isc(ctx, key, fx)
            elif kind == "en":
                d = opamp_noise(ctx, key, fx)
            elif kind == "vos" and ctx.cls == "comparator":
                d = cmp_vos(ctx, key, fx)
            elif kind in ("ib", "ios") and ctx.cls == "comparator":
                d = cmp_ib(ctx, key, fx)
            elif kind == "avd_db":
                d = cmp_avd(ctx, key, fx)
            elif kind == "vol" and ctx.cls == "comparator":
                d = cmp_vol(ctx, key, fx)
            elif kind == "iol":
                d = cmp_iol(ctx, key, fx)
            elif kind == "ioh":
                d = cmp_ioh(ctx, key, fx)
            elif kind == "iq" and ctx.cls == "comparator":
                d = cmp_icc(ctx, key, fx)
            elif kind == "tresp":
                d = cmp_tresp(ctx, key, fx)
            elif kind == "vth":
                d = t555_vth(ctx, key, fx)
            elif kind == "vtrig":
                d = t555_vtrig(ctx, key, fx)
            elif kind == "vreset":
                d = t555_vreset(ctx, key, fx)
            elif kind == "vcont":
                d = t555_vcont(ctx, key, fx)
            elif kind in ("vol555", "voh555") or (kind == "iq" and ctx.cls == "timer"):
                state = fx.get("state") or ("low" if kind == "vol555" else "high" if kind == "voh555" else "low")
                d = t555_state(ctx, key, fx, state, kind)
            elif kind in ("ith", "itrig", "ireset"):
                d = t555_pin_current(ctx, key, fx, kind)
            elif kind in ("vdisch_on", "idisch_off"):
                d = t555_disch(ctx, key, fx, kind)
            elif kind in ("tr555", "tf555"):
                d = t555_edges(ctx, key, fx)
            elif kind == "vref":
                d = shunt_vref(ctx, key, fx)
            elif kind == "dvref_dvka":
                d = shunt_dvref(ctx, key, fx)
            elif kind == "iref":
                d = shunt_iref(ctx, key, fx)
            elif kind == "ioff":
                d = shunt_ioff(ctx, key, fx)
            elif kind == "imin":
                d = shunt_imin(ctx, key, fx)
            elif kind == "zka":
                d = shunt_zka(ctx, key, fx)
            elif kind in ("vref_ldo", "iadj"):
                d = ldo_dc(ctx, key, fx)
            elif kind == "line_reg":
                d = ldo_line(ctx, key, fx)
            elif kind == "load_reg":
                d = ldo_load(ctx, key, fx)
            elif kind == "ilim":
                d = ldo_ilim(ctx, key, fx)
            elif kind == "psrr_ldo_db":
                d = ldo_psrr(ctx, key, fx)
            else:
                errors[key] = f"no fixture implemented for kind '{kind}' (class {ctx.cls})"
                continue
            decks[key] = d
        except Exception as e:
            errors[key] = f"{type(e).__name__}: {e}"
    return decks, errors


# ============================================================================ LTspice execution
_NUM = r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?"


def parse_meas_log(path: str) -> dict[str, float]:
    res: dict[str, float] = {}
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        text = f.read()
    for line in text.splitlines():
        s = line.strip()
        m = re.match(rf"^([a-zA-Z_][\w]*)\s*:\s*.*?=\s*\(\s*({_NUM})dB\s*,\s*({_NUM})°?\s*\)(?:\s+at\s+({_NUM}))?", s, re.IGNORECASE)
        if m:
            name = m.group(1).lower()
            db, ph = float(m.group(2)), float(m.group(3))
            res[name + "_db"] = db
            res[name + "_mag"] = 10 ** (db / 20)
            res[name + "_phase"] = ph
            res[name] = db
            if m.group(4):
                res[name + "_at"] = float(m.group(4))
            continue
        m = re.match(rf"^([a-zA-Z_][\w]*)\s*:\s*.*?=\s*({_NUM})\s+AT\s+({_NUM})\s*$", s)
        if m:
            res[m.group(1).lower()] = float(m.group(3))       # WHEN-type: the x coordinate is the result
            res[m.group(1).lower() + "_value"] = float(m.group(2))
            continue
        m = re.match(rf"^([a-zA-Z_][\w]*)\s*:\s*.*?=\s*({_NUM})(?:\s+(?:at|from)\s+.*)?$", s, re.IGNORECASE)
        if m:
            res[m.group(1).lower()] = float(m.group(2))
            continue
        m = re.match(rf"^([a-zA-Z_][\w]*)\s*=\s*({_NUM})\s*$", s)
        if m and not s.lower().startswith(("tnom", "temp")):
            res[m.group(1).lower()] = float(m.group(2))
    return res


_ERR_PATTERNS = re.compile(
    r"(?i)(fatal error|^\s*error\b|singular matrix|unknown subcircuit|can't find definition|could not find|"
    r"time step too small|expected .{0,60} here|unknown parameter|undefined|voltage not found|current not found|"
    r"syntax error|iteration limit reached|simulation failed|is not a valid)")


def ltspice_errors(log_text: str) -> list[str]:
    """Extracts LTspice error lines together with the offending netlist line that follows them."""
    out: list[str] = []
    lines = log_text.splitlines()
    for i, ln in enumerate(lines):
        low = ln.strip().lower()
        if not low or low.startswith(("warning", "gmin", "source step", "changing tseed")):
            continue
        if _ERR_PATTERNS.search(ln):
            nxt = lines[i + 1].strip() if i + 1 < len(lines) else ""
            ctx = nxt if nxt and not nxt.startswith("^") else ""
            msg = re.sub(r"^.*?\.cir\(\d+\):\s*", "", ln.strip())
            out.append((msg + (f" | {ctx}" if ctx else ""))[:240])
    return list(dict.fromkeys(out))



def pdg_topological_audit(netlist: str, plan: dict[str, Any], dut_name: str | None = None) -> list[str]:
    """PDG Stage 0: Structural & Topological Causal Connectivity Audit.
    Verifies:
      1. Zero behavioral constructs (no B-sources, A-devices, VALUE={}, if(), table(), laplace()).
      2. No internal independent voltage/current sources (V... != 0V, I...) inside synthesized .subckt blocks.
      3. No illegal internal connections to global ground '0' when '0' is not a declared subckt pin.
      4. No undeclared floating supply rails (e.g., phantom VCC inside a 3-pin shunt_ref).
      5. No degenerate/shorted active devices or rail-locked output gates.
      6. PDG Causal Signal Connectivity: a continuous non-rail component path exists from SIGNAL_IN to SIGNAL_OUT.
    """
    analog_errs: list[str] = []
    name, pins = subckt_header(netlist, dut_name)
    transistor_count = 0

    # Parse all subcircuits in the netlist
    subckts: dict[str, dict[str, Any]] = {}
    cur_sub: str | None = None
    for raw_ln in netlist.splitlines():
        s = raw_ln.strip()
        if not s or s.startswith(("*", ";", "+")):
            continue
        code_only = re.split(r"[;\$]|(?<!\w)\*", s)[0].strip()
        if not code_only:
            continue
        toks = code_only.split()
        first_tok = toks[0].upper()
        if first_tok == ".SUBCKT" and len(toks) >= 2:
            cur_sub = toks[1].upper()
            subckts[cur_sub] = {"name": toks[1], "pins": toks[2:], "lines": []}
            continue
        if first_tok == ".ENDS":
            cur_sub = None
            continue
        if first_tok.startswith("."):
            continue

        if first_tok.startswith(("Q", "M", "J")):
            transistor_count += 1
        if first_tok.startswith("B"):
            analog_errs.append(f"PDG_STAGE0_BEHAVIORAL: Behavioral B-source '{first_tok}' is prohibited | {s}")
        elif first_tok.startswith("A"):
            analog_errs.append(f"PDG_STAGE0_BEHAVIORAL: Digital/behavioral A-device '{first_tok}' is prohibited | {s}")
        elif re.search(r"\b(?:value\s*=\s*\{|v\s*=\s*if\s*\(|i\s*=\s*if\s*\(|table\s*\(|laplace\s*=)", s, re.IGNORECASE):
            analog_errs.append(f"PDG_STAGE0_BEHAVIORAL: Behavioral expression is prohibited; use physical transistors/passives | {s}")

        if cur_sub is not None:
            subckts[cur_sub]["lines"].append(toks)
            # Check for internal independent voltage/current sources
            if first_tok.startswith("V") and len(toks) >= 4:
                val_str = " ".join(toks[3:]).upper()
                # Allow 0V ammeters (0, 0V, DC 0, DC 0V)
                if not re.match(r"^(?:DC\s+)?0(?:\.0*)?V?$", val_str.strip()):
                    analog_errs.append(
                        f"PDG_STAGE0_INTERNAL_SOURCE: Independent voltage source '{toks[0]}' ({val_str}) inside .subckt '{cur_sub}' is prohibited; references/biases must be generated physically from supply rails | {s}"
                    )
            elif first_tok.startswith("I") and len(toks) >= 4:
                analog_errs.append(
                    f"PDG_STAGE0_INTERNAL_SOURCE: Independent current source '{toks[0]}' inside .subckt '{cur_sub}' is prohibited; use physical BJT/MOSFET/resistor current mirrors | {s}"
                )
            # Check for degenerate shorted transistors
            if first_tok.startswith("Q") and len(toks) >= 5:
                c_n, b_n, e_n = toks[1].upper(), toks[2].upper(), toks[3].upper()
                if c_n == e_n:
                    analog_errs.append(
                        f"PDG_STAGE0_SHORTED_BJT: Transistor '{toks[0]}' has collector and emitter shorted to '{c_n}' | {s}"
                    )

    expected_order = (plan.get("pin_map") or {}).get("pin_order") or []
    if expected_order and len(pins) != len(expected_order):
        analog_errs.append(
            f"PDG_STAGE0_PIN_MISMATCH: Subcircuit header has {len(pins)} pins {pins}, expected {len(expected_order)} pins {expected_order}"
        )
    if transistor_count < 2:
        analog_errs.append(
            f"PDG_STAGE0_NO_TRANSISTORS: Subcircuit contains only {transistor_count} active transistor(s) (Q/M/J). Must synthesize a complete physical transistor-level topology."
        )

    top_sub = subckts.get(name.upper())
    if top_sub:
        top_pins_upper = {p.upper() for p in top_sub["pins"]}
        # Check internal node '0' usage and undeclared supply names in top_sub
        all_top_nodes = set()
        for toks in top_sub["lines"]:
            el = toks[0].upper()
            n_cnt = 4 if el.startswith("M") else (3 if el.startswith(("Q", "J")) else 2)
            if el.startswith("X"):
                el_nodes = [t.upper() for t in toks[1:-1] if "=" not in t]
            else:
                el_nodes = [t.upper() for t in toks[1:1 + n_cnt] if "=" not in t]
            for nd in el_nodes:
                all_top_nodes.add(nd)
                if nd == "0" and "0" not in top_pins_upper:
                    analog_errs.append(
                        f"PDG_STAGE0_GROUND_LEAK: Element '{toks[0]}' connects directly to global node '0' inside .subckt '{name}'; use declared ground/return pin instead."
                    )
        for rail_cand in ("VCC", "VDD", "VSS", "VEE"):
            if rail_cand in all_top_nodes and rail_cand not in top_pins_upper:
                analog_errs.append(
                    f"PDG_STAGE0_UNDECLARED_RAIL: Undeclared supply node '{rail_cand}' used inside .subckt '{name}' (declared pins: {top_sub['pins']})."
                )

        # Build flattened non-rail signal connectivity graph across subcircuits
        pm = plan.get("pin_map") or {}
        rail_pins = {str(pm.get("vpos") or "").upper(), str(pm.get("vneg") or "").upper(), "0", "GND", "VCC", "VDD", "VSS", "VEE", "V+", "V-"}
        rail_pins.discard("")

        adj: dict[str, set] = {}
        def add_clique(nodes_list: list[str]):
            clean_nds = [n for n in nodes_list if n not in rail_pins]
            for u in clean_nds:
                adj.setdefault(u, set()).update(clean_nds)

        def expand_sub(sub_key: str, prefix: str, pin_map_dict: dict[str, str], depth: int = 0):
            if depth > 4 or sub_key not in subckts:
                return
            sb = subckts[sub_key]
            for toks in sb["lines"]:
                el = toks[0].upper()
                if el.startswith("X") and len(toks) >= 3:
                    child_tokens = [t for t in toks[1:] if "=" not in t]
                    if not child_tokens:
                        continue
                    child_sub = child_tokens[-1].upper()
                    inst_nodes = [pin_map_dict.get(n.upper(), f"{prefix}.{n.upper()}" if prefix else n.upper()) for n in child_tokens[:-1]]
                    if child_sub in subckts and len(subckts[child_sub]["pins"]) == len(inst_nodes):
                        child_map = {}
                        for cp, inode in zip(subckts[child_sub]["pins"], inst_nodes):
                            child_map[cp.upper()] = inode if inode not in rail_pins else cp.upper()
                            if inode in rail_pins:
                                rail_pins.add(cp.upper())
                        expand_sub(child_sub, f"{prefix}.{toks[0].upper()}" if prefix else toks[0].upper(), child_map, depth + 1)
                    else:
                        add_clique(inst_nodes)
                else:
                    n_cnt = 4 if el.startswith("M") else (3 if el.startswith(("Q", "J")) else 2)
                    raw_nds = [t.upper() for t in toks[1:1 + n_cnt] if "=" not in t]
                    mapped_nds = [pin_map_dict.get(n, f"{prefix}.{n}" if prefix else n) for n in raw_nds]
                    add_clique(mapped_nds)

        top_identity = {p.upper(): p.upper() for p in top_sub["pins"]}
        expand_sub(name.upper(), "", top_identity, 0)

        def has_path(src_pins: list[str], dst_pin: str) -> bool:
            target = dst_pin.upper()
            visited = set()
            stack = [s.upper() for s in src_pins if s]
            while stack:
                cur = stack.pop()
                if cur == target:
                    return True
                if cur in visited or cur in rail_pins:
                    continue
                visited.add(cur)
                for nxt in adj.get(cur, ()):
                    if nxt not in visited and nxt not in rail_pins:
                        stack.append(nxt)
            return False

        cls = plan.get("device_class")
        if cls in ("opamp", "inamp", "comparator"):
            for ch in pm.get("channels") or []:
                inp, inn, out = ch.get("inp"), ch.get("inn"), ch.get("out")
                if inp and inn and out:
                    if not has_path([inp, inn], out):
                        analog_errs.append(
                            f"PDG_STAGE0_DISCONNECTED_PATH: No internal causal signal path exists from input pins ['{inp}', '{inn}'] to output pin '{out}' (excluding power rails). Output stage is disconnected from input stage."
                        )
        elif cls == "shunt_ref":
            sr = pm.get("shunt") or pm.get("shunt_ref") or {}
            if sr.get("ref") and sr.get("cathode"):
                if not has_path([sr["ref"]], sr["cathode"]):
                    analog_errs.append(
                        f"PDG_STAGE0_DISCONNECTED_PATH: No internal causal signal path exists from reference pin '{sr['ref']}' to cathode '{sr['cathode']}'."
                    )
        elif cls == "timer_555":
            tm = pm.get("timer") or {}
            if tm.get("trig") and tm.get("thres") and tm.get("out"):
                if not has_path([tm["trig"], tm["thres"]], tm["out"]):
                    analog_errs.append(
                        f"PDG_STAGE0_DISCONNECTED_PATH: No internal causal signal path exists from trigger/threshold pins ['{tm['trig']}', '{tm['thres']}'] to output '{tm['out']}'."
                    )

    return list(dict.fromkeys(analog_errs))


def pdg_bias_and_transfer_check(netlist: str, plan: dict[str, Any], out_dir: str,
                                schedule_us: dict[str, float] | None = None,
                                dut_name: str | None = None, vs: float | None = None) -> dict[str, Any]:
    """PDG Stage 1 (Power & DC Bias Gate) & Stage 2 (Causal DC Signal Transfer Gate).
    Sequenced by the PDG startup schedule sigma(p):
      - Stage 1 (at t = sigma(BIAS)): Verifies supply/cathode bias current IQ is in an active physical window
        (neither open-circuit < 100 nA nor shorted > 250 mA).
      - Stage 2 (from t = sigma(IN) to sigma(OUT)): Applies a differential/threshold stimulus across the
        primary PDG SIGNAL_PATH (IN -> OUT) and verifies that the output actively switches/responds
        (dV(OUT) >= 0.5V). Blocks dead/cut-off circuits (e.g. dV = 0.0V) before any spec fixtures run.
    """
    os.makedirs(out_dir, exist_ok=True)
    cls = plan.get("device_class")
    pm = plan.get("pin_map") or {}
    vs = vs or plan.get("vs_default") or 5.0
    sched = schedule_us or {}
    t_bias = min(max(20e-6, 1e-6 * max(sched.values(), default=20.0)), 100e-6)
    t_step = t_bias + 30e-6
    t_end = t_step + 40e-6

    ctx = FixtureContext(netlist, plan, schedule_us=sched, dut_name=dut_name)
    lines = ["* PDG Stage 1 (DC Bias) & Stage 2 (Causal Signal Transfer) Gate", ".temp 25",
             ".options plotwinsize=0 numdgt=7", netlist.strip(), ""]
    meas: list[str] = []

    if cls in ("comparator", "opamp", "inamp"):
        ch = ctx.ch()
        n = ctx.base_nodes(vs)
        n.update({ch["inp"]: "inp", ch["inn"]: "inn", ch["out"]: "out"})
        vcm = 1.4 if (cls == "comparator" and vs >= 3.0) else (0.0 if ctx.split else vs / 2.0)
        lines += ctx.supply_tran(vs)
        lines += [
            f"VCM inn 0 {_r(vcm)}",
            f"VID inp inn PWL(0 -0.1 {_r(t_step)} -0.1 {_r(t_step + 1e-6)} 0.1 {_r(t_end)} 0.1)",
        ]
        if cls == "comparator":
            lines.append("RPU out vp 5.1k")
        else:
            lines.append("RL out mid 10k")
        ctx.park_unused(ch, n, lines)
        lines.append(instantiate(netlist, n, dut_name=dut_name))
        meas = [
            f".meas tran m_iq AVG I(VPOS) FROM {_r(t_bias * 0.5)} TO {_r(t_step - 2e-6)}",
            f".meas tran m_vlo AVG V(out) FROM {_r(t_step - 15e-6)} TO {_r(t_step - 1e-6)}",
            f".meas tran m_vhi AVG V(out) FROM {_r(t_end - 15e-6)} TO {_r(t_end - 1e-6)}",
        ]
    elif cls == "shunt_ref":
        sr = pm.get("shunt") or pm.get("shunt_ref") or {}
        if not (sr.get("cathode") and sr.get("anode") and sr.get("ref")):
            return {"ok": True, "errors": [], "metrics": {}}
        n = {sr["cathode"]: "ka", sr["anode"]: "0", sr["ref"]: "ref"}
        lines += [
            f"VPOS vp 0 {_r(max(vs, 5.0))}",
            "RK vp ka 1k",
            f"VREF ref 0 PWL(0 2.0 {_r(t_step)} 2.0 {_r(t_step + 1e-6)} 2.8 {_r(t_end)} 2.8)",
            instantiate(netlist, n, dut_name=dut_name),
        ]
        meas = [
            f".meas tran m_iq AVG I(VPOS) FROM {_r(t_end - 15e-6)} TO {_r(t_end - 1e-6)}",
            f".meas tran m_vhi AVG V(ka) FROM {_r(t_step - 15e-6)} TO {_r(t_step - 1e-6)}",
            f".meas tran m_vlo AVG V(ka) FROM {_r(t_end - 15e-6)} TO {_r(t_end - 1e-6)}",
        ]
    elif cls == "timer_555":
        n, t = timer_nodes(ctx, vs)
        lines += timer_common(ctx, vs) + [
            f"VTRIG trig 0 PWL(0 {_r(0.15 * vs)} {_r(t_step)} {_r(0.15 * vs)} {_r(t_step + 1e-6)} {_r(0.85 * vs)} {_r(t_end)} {_r(0.85 * vs)})",
            f"VTHR thres 0 PWL(0 {_r(0.15 * vs)} {_r(t_step)} {_r(0.15 * vs)} {_r(t_step + 1e-6)} {_r(0.85 * vs)} {_r(t_end)} {_r(0.85 * vs)})",
            "RL out 0 10k",
            instantiate(netlist, n, dut_name=dut_name),
        ]
        meas = [
            f".meas tran m_iq AVG I(VPOS) FROM {_r(t_bias * 0.5)} TO {_r(t_step - 2e-6)}",
            f".meas tran m_vhi AVG V(out) FROM {_r(t_step - 15e-6)} TO {_r(t_step - 1e-6)}",
            f".meas tran m_vlo AVG V(out) FROM {_r(t_end - 15e-6)} TO {_r(t_end - 1e-6)}",
        ]
    else:
        return {"ok": True, "errors": [], "metrics": {}}

    lines += [f".tran 0 {_r(t_end)} 0 {_r(t_end / 1000)}", *meas, ".end", ""]
    path = os.path.abspath(os.path.join(out_dir, "pdg_gate_check.cir"))
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    log = path[:-4] + ".log"
    if os.path.exists(log):
        os.remove(log)
    try:
        subprocess.run([LTSPICE_EXE, "-b", path], capture_output=True, text=True, timeout=45)
    except subprocess.TimeoutExpired:
        return {"ok": False, "errors": ["PDG_STAGE1_TIMEOUT: PDG DC Bias & Causal Transfer check timed out after 45s"], "path": path}
    if not os.path.exists(log):
        return {"ok": False, "errors": ["PDG_STAGE1_NO_LOG: LTspice produced no log for PDG Gate check"], "path": path}
    with open(log, "r", encoding="utf-8", errors="ignore") as f:
        txt_log = f.read()
    fatal = ltspice_errors(txt_log)
    if fatal:
        return {"ok": False, "errors": [f"PDG_STAGE1_SIM_ERROR: {e}" for e in fatal[:6]], "path": path}

    raw = parse_meas_log(log)
    iq = abs(raw.get("m_iq", 0.0))
    vlo = raw.get("m_vlo")
    vhi = raw.get("m_vhi")
    errs: list[str] = []

    # Stage 1 Gate: Power & DC Bias Operating Point
    if "m_iq" not in raw or iq < 1e-7:
        errs.append(
            f"PDG_STAGE1_DC_BIAS_OPEN: Quiescent supply current IQ = {iq:.3e} A (< 100 nA) at PDG bias settling t={t_bias*1e6:.0f}us; bias core is dead or disconnected from rails."
        )
    elif iq > 0.25:
        errs.append(
            f"PDG_STAGE1_DC_BIAS_SHORT: Quiescent supply current IQ = {iq:.3f} A (> 250 mA) at PDG bias settling t={t_bias*1e6:.0f}us; supply rail short or runaway bias."
        )

    # Stage 2 Gate: Causal Signal Path Transfer (SIGNAL_IN -> SIGNAL_OUT)
    if vlo is None or vhi is None:
        errs.append(
            "PDG_STAGE2_DC_TRANSFER_UNMEASURED: Could not observe V(OUT) across PDG signal-path step stimulus."
        )
    else:
        dv = vhi - vlo
        min_dv = 0.4 if cls == "shunt_ref" else (1.0 if cls == "timer_555" else 0.5)
        if abs(dv) < min_dv:
            errs.append(
                f"PDG_STAGE2_BIAS_CUTOFF: Causal signal transfer (SIGNAL_IN -> SIGNAL_OUT) failed! "
                f"V_low = {vlo:.4f} V, V_high = {vhi:.4f} V (dV = {dv:.4f} V < {min_dv} V required). "
                f"Output is stuck at ~{vlo:.3f} V because an internal current mirror, gain stage, or level shifter is in cut-off or deep saturation "
                f"(check for low-value shunt resistors across current mirrors/active loads or missing bias paths)."
            )
        elif dv < 0:
            errs.append(
                f"PDG_STAGE2_INVERTED_POLARITY: Causal signal transfer (SIGNAL_IN -> SIGNAL_OUT) has inverted polarity! "
                f"V_low = {vlo:.4f} V, V_high = {vhi:.4f} V (dV = {dv:.4f} V < 0 V). "
                f"Swap IN+/IN- connections in the input differential pair or fix the number of inverting gain stages."
            )

    return {"ok": len(errs) == 0, "errors": errs, "path": path, "metrics": {"iq": iq, "v_low": vlo, "v_high": vhi}}


def compile_check(netlist: str, plan: dict[str, Any], out_dir: str, dut_name: str | None = None,
                  vs: float | None = None, strict_analog: bool = True,
                  schedule_us: dict[str, float] | None = None,
                  enforce_pdg_gate: bool = True) -> dict[str, Any]:
    """PDG-Driven Staged Gate:
      - Stage 0: Topological & Structural PDG Audit (no behavioral sources, no internal independent V/I sources,
        no global ground '0' leak, verified SIGNAL_IN -> SIGNAL_OUT connectivity).
      - DC .op Convergence Check.
      - Stage 1: Power & DC Bias Operating Point Gate at sigma(BIAS).
      - Stage 2: Causal DC Signal Transfer / Active Switching Gate from sigma(IN) -> sigma(OUT).
    Fails fast and blocks all 50+ downstream spec fixtures if any stage fails."""
    os.makedirs(out_dir, exist_ok=True)
    name, pins = subckt_header(netlist, dut_name)
    is_synth_dut = strict_analog and (dut_name or "").upper() != "DUT"
    if is_synth_dut:
        topo_errs = pdg_topological_audit(netlist, plan, dut_name=dut_name)
        if topo_errs:
            return {"ok": False, "stage": "PDG_STAGE0_TOPOLOGY", "errors": topo_errs[:12], "path": None}

    pm = plan.get("pin_map", {})
    vs = vs or plan.get("vs_default") or 5.0
    nodes = [f"n_{re.sub(r'[^A-Za-z0-9_]', '_', p.replace('+', 'p').replace('-', 'n'))}" for p in pins]
    lines = [f"* compile check for {name}", ".temp 25", netlist.strip(), ""]
    lines += [f"R_{idx}_{n} {n} 0 1G" for idx, n in enumerate(nodes, 1)]
    for p, n in zip(pins, nodes):
        if pm.get("vpos") and p == pm["vpos"]:
            lines.append(f"VPOS {n} 0 {_r(vs)}")
        if pm.get("vneg") and p == pm["vneg"]:
            lines.append(f"VNEG {n} 0 0")
    lines += [f"XDUT {' '.join(nodes)} {name}", ".op", ".end", ""]
    path = os.path.abspath(os.path.join(out_dir, "compile_check.cir"))
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    log = path[:-4] + ".log"
    if os.path.exists(log):
        os.remove(log)
    try:
        subprocess.run([LTSPICE_EXE, "-b", path], capture_output=True, text=True, timeout=60)
    except subprocess.TimeoutExpired:
        return {"ok": False, "stage": "PDG_STAGE1_OP_CONVERGENCE", "errors": ["compile check timed out after 60 s (operating point does not converge)"], "path": path}
    if not os.path.exists(log):
        return {"ok": False, "stage": "PDG_STAGE1_OP_CONVERGENCE", "errors": ["LTspice produced no log for the compile check"], "path": path}
    with open(log, "r", encoding="utf-8", errors="ignore") as f:
        txt_log = f.read()
    errs = ltspice_errors(txt_log)
    if errs:
        return {"ok": False, "stage": "PDG_STAGE1_OP_CONVERGENCE", "errors": errs[:12], "path": path}

    if enforce_pdg_gate and is_synth_dut:
        pdg_res = pdg_bias_and_transfer_check(netlist, plan, out_dir, schedule_us=schedule_us, dut_name=dut_name, vs=vs)
        if not pdg_res["ok"]:
            stage_name = "PDG_STAGE1_DC_BIAS" if any("STAGE1" in e for e in pdg_res["errors"]) else "PDG_STAGE2_DC_TRANSFER"
            return {"ok": False, "stage": stage_name, "errors": pdg_res["errors"], "path": pdg_res["path"], "pdg_metrics": pdg_res.get("metrics", {})}
        return {"ok": True, "stage": "PDG_GATE_PASSED", "errors": [], "path": path, "pdg_metrics": pdg_res.get("metrics", {})}

    return {"ok": True, "stage": "PDG_GATE_PASSED", "errors": [], "path": path}


def run_deck(deck: Deck, netlist: str, out_dir: str, timeout: int | None = None) -> dict[str, Any]:
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, f"tb_{deck.key}.cir")
    with open(path, "w", encoding="utf-8") as f:
        f.write(deck.text(netlist))
    log = path[:-4] + ".log"
    for ext in (".log", ".raw", ".op.raw"):
        try:
            os.remove(path[:-4] + ext)
        except OSError:
            pass
    rec = {"key": deck.key, "kind": deck.kind, "title": deck.title, "deck_path": path, "raw": {}, "metrics": {}, "error": None}
    if timeout is None:
        timeout = 60 if ".tran" not in deck.analysis else 120
    path = os.path.abspath(path)
    log = path[:-4] + ".log"
    try:
        subprocess.run([LTSPICE_EXE, "-b", path], capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        rec["error"] = f"LTspice timeout after {timeout}s"
        return rec
    if not os.path.exists(log):
        rec["error"] = "LTspice produced no log"
        return rec
    rec["raw"] = parse_meas_log(log)
    with open(log, "r", encoding="utf-8", errors="ignore") as f:
        txt_log = f.read()
    fatal = ltspice_errors(txt_log)
    if fatal:
        rec["error"] = "; ".join(x.strip() for x in fatal[:3])
    try:
        rec["metrics"] = deck.extract(rec["raw"])
    except Exception as e:
        rec["error"] = (rec["error"] or "") + f" extract: {e}"
    return rec


_PDG_DECK_STAGE = {
    # Stage 1: Power & Quiescent Bias
    "opamp_dc": 1, "cmp_icc": 1, "shunt_ioff": 1, "shunt_imin": 1,
    # Stage 2: Causal Static DC Transfer, Thresholds & Output Drive
    "opamp_cmr": 2, "opamp_swing": 2, "opamp_iout": 2, "opamp_isc": 2,
    "cmp_vos": 2, "cmp_ib": 2, "cmp_vol": 2, "cmp_iol": 2, "cmp_ioh": 2, "cmp_avd": 2,
    "shunt_vref": 2, "shunt_iref": 2, "shunt_dvref": 2,
    "t555_vth": 2, "t555_vtrig": 2, "t555_vreset": 2, "t555_vcont": 2, "t555_state": 2, "t555_idis": 2,
    # Stage 3: Small-Signal AC & Dynamic Switching / Timing
    "opamp_ol": 3, "opamp_cm": 3, "opamp_psrr": 3, "opamp_sr": 3, "opamp_noise": 3,
    "cmp_tresp": 3, "shunt_zka": 3, "t555_mono": 3, "t555_astable": 3,
}


def run_all(decks: dict[str, Deck], netlist: str, out_dir: str, workers: int = 4) -> dict[str, dict[str, Any]]:
    """Executes testbench decks in PDG causal stage order:
    Stage 1 (Power/DC Bias) -> Stage 2 (Static DC Transfer/Thresholds) -> Stage 3 (AC/Dynamic Transient)."""
    results: dict[str, dict[str, Any]] = {}
    for stage_num in (1, 2, 3):
        stage_decks = {k: d for k, d in decks.items() if _PDG_DECK_STAGE.get(d.kind, 2) == stage_num}
        if not stage_decks:
            continue
        with cf.ThreadPoolExecutor(max_workers=workers) as ex:
            futs = {ex.submit(run_deck, d, netlist, out_dir): k for k, d in stage_decks.items()}
            for f in cf.as_completed(futs):
                res = f.result()
                res["pdg_stage"] = stage_num
                results[futs[f]] = res

    # derived metrics that need two decks (CMRR = AOL - ACM)
    aol = next((r["metrics"]["aol_db"] for r in results.values() if "aol_db" in r["metrics"]), None)
    for r in results.values():
        if "acm_db" in r["metrics"] and aol is not None:
            r["metrics"]["cmrr_db"] = aol - r["metrics"]["acm_db"]
    vref = next((r["metrics"]["vref"] for r in results.values() if "vref" in r["metrics"]), None)
    for r in results.values():
        if "vref_at_vka" in r["metrics"] and vref is not None and r["metrics"].get("vka"):
            r["metrics"]["dvref_dvka"] = (r["metrics"]["vref_at_vka"] - vref) / (r["metrics"]["vka"] - vref)
    return results


# ============================================================================ evaluation
def _tol(unit: str, typ: float) -> float:
    if unit == "dB":
        return 6.0
    if unit == "deg":
        return 15.0
    return abs(typ) * 0.30


def evaluate(plan: dict[str, Any], results: dict[str, dict[str, Any]], deck_errors: dict[str, str]) -> dict[str, Any]:
    rows = []
    for it in plan["items"]:
        row = {k: it.get(k) for k in ("spec_index", "symbol", "name", "category", "min", "typ", "max", "unit",
                                      "test_conditions", "kind", "status", "note")}
        if it["status"] != "PLANNED":
            row["result"] = it["status"]
            rows.append(row)
            continue
        key, kind, unit = it["fixture_key"], it["kind"], it["canonical_unit"]
        lim = spec_limits_in(unit, it)
        row.update({"fixture_key": key, "canonical_unit": unit, "limits_canonical": lim})
        r = results.get(key)
        if key in deck_errors:
            row["result"] = "NO_FIXTURE"; row["diagnostic"] = deck_errors[key]; rows.append(row); continue
        if r is None:
            row["result"] = "NOT_RUN"; rows.append(row); continue
        val = r["metrics"].get(kind)
        if kind == "load_reg" and it.get("unit", "").startswith("%"):
            val = r["metrics"].get("load_reg_pct")
        if val is None:
            row["result"] = "SIM_ERROR" if r.get("error") else "NOT_OBSERVED"
            row["diagnostic"] = r.get("error") or f"fixture '{r['kind']}' produced no value for '{kind}' (raw: {list(r['raw'])[:6]})"
            rows.append(row); continue
        if it["magnitude"]:
            val = abs(val)
            bounds = [abs(x) for x in (lim["min"], lim["max"]) if x is not None]
            if kind in ("vos", "ib", "ios", "i_ref", "ioh"):
                # Offset/bias/leakage magnitudes only have an upper bound (|val| <= max_limit)
                lo, hi = None, (max(bounds) if bounds else None)
            elif lim["min"] is not None and lim["max"] is not None:
                if lim["min"] <= 0 <= lim["max"]:
                    lo, hi = None, max(bounds)
                else:
                    lo, hi = min(bounds), max(bounds)
            elif lim["min"] is not None and lim["max"] is None:   # e.g. IO min -20 mA  => |IO| >= 20 mA
                lo, hi = abs(lim["min"]), None
            elif lim["min"] is None and lim["max"] is not None:
                lo, hi = None, abs(lim["max"])
            else:
                lo, hi = None, None
            typ = abs(lim["typ"]) if lim["typ"] is not None else None
        else:
            lo, hi, typ = lim["min"], lim["max"], lim["typ"]
        row["measured"] = val
        if kind in ("iq", "iq_total") and abs(val) < 1e-12:
            row["result"] = "FAIL"
            row["diagnostic"] = f"{kind}: measured {fmt(val, unit)} (< 1 pA) indicates disconnected/unbiased supply rail"
            rows.append(row)
            continue
        if lo is None and hi is None and typ is None:
            row["result"] = "NO_NUMERIC_LIMIT"; rows.append(row); continue
        if lo is None and hi is None:
            tol = _tol(unit, typ)
            if kind in ("vos", "ib", "ios", "ioh", "vol", "tresp", "ioff", "imin", "zka", "dvref_dvka", "en", "vdisch_on", "idisch_off", "tr555", "tf555"):
                ok = (val <= typ + tol)
            elif kind in ("aol_db", "avd_db", "cmrr_db", "psrr_db", "iol"):
                ok = (val >= typ - tol)
            else:
                ok = abs(val - typ) <= tol
            row["result"] = "PASS_TYP" if ok else "FAIL_TYP"
            row["residual"] = val - typ
            row["diagnostic"] = f"{kind}: measured {fmt(val, unit)} vs typ {fmt(typ, unit)} (±{fmt(tol, unit)} band)"
            rows.append(row); continue
        ok = (lo is None or val >= lo) and (hi is None or val <= hi)
        row["result"] = "PASS" if ok else "FAIL"
        if not ok:
            row["residual"] = (lo - val) if (lo is not None and val < lo) else (val - hi)
            bound = f"min {fmt(lo, unit)}" if (lo is not None and val < lo) else f"max {fmt(hi, unit)}"
            row["diagnostic"] = f"{kind}: measured {fmt(val, unit)} violates {bound}"
        else:
            row["diagnostic"] = f"{kind}: measured {fmt(val, unit)} within [{fmt(lo, unit)}, {fmt(hi, unit)}]"
        rows.append(row)

    def cnt(*st):
        return sum(r["result"] in st for r in rows)
    planned = cnt("PASS", "FAIL", "PASS_TYP", "FAIL_TYP", "SIM_ERROR", "NOT_OBSERVED", "NO_FIXTURE", "NOT_RUN", "NO_NUMERIC_LIMIT")
    measured = cnt("PASS", "FAIL", "PASS_TYP", "FAIL_TYP")
    hard = cnt("PASS", "FAIL")

    # Compute deduplicated unique-kind pass rate (so 12 rows of VOL count as 1 parameter kind)
    kinds_rows: dict[str, list[str]] = {}
    for r in rows:
        if r["result"] in ("PASS", "FAIL", "PASS_TYP", "FAIL_TYP") and r.get("kind"):
            kinds_rows.setdefault(r["kind"], []).append(r["result"])
    unique_kinds_measured = len(kinds_rows)
    unique_kinds_passed = sum(1 for res_list in kinds_rows.values() if all(x in ("PASS", "PASS_TYP") for x in res_list))
    unique_kind_pass_rate_pct = round(100.0 * unique_kinds_passed / unique_kinds_measured, 1) if unique_kinds_measured else 0.0

    summary = {
        "total_rows": len(rows),
        "electrical_rows": sum(str(r["category"]).upper() == "ELECTRICAL" for r in rows),
        "planned": planned,
        "measured": measured,
        "coverage_pct": round(100 * measured / planned, 1) if planned else 0.0,
        "pass_hard": cnt("PASS"), "fail_hard": cnt("FAIL"),
        "pass_typ": cnt("PASS_TYP"), "fail_typ": cnt("FAIL_TYP"),
        "pass_rate_measured_pct": round(100 * cnt("PASS", "PASS_TYP") / measured, 1) if measured else 0.0,
        "pass_rate_hard_pct": round(100 * cnt("PASS") / hard, 1) if hard else None,
        "unique_kinds_measured": unique_kinds_measured,
        "unique_kinds_passed": unique_kinds_passed,
        "unique_kind_pass_rate_pct": unique_kind_pass_rate_pct,
        "sim_errors": cnt("SIM_ERROR"), "not_observed": cnt("NOT_OBSERVED"), "no_fixture": cnt("NO_FIXTURE"),
        "unsupported_kind": cnt("UNSUPPORTED_KIND"),
        "not_testable": sum(r["result"].startswith("NOT_TESTABLE") for r in rows),
    }
    return {"summary": summary, "rows": rows}


def feedback_text(evaluation: dict[str, Any], max_items: int = 25) -> str:
    """Compact, actionable feedback for the netlist synthesiser."""
    lines = []
    for r in evaluation["rows"]:
        if r["result"] in ("FAIL", "FAIL_TYP"):
            lines.append(f"- [{r['result']}] {r['symbol']} ({r['name']}): {r.get('diagnostic')} | conditions: {r.get('test_conditions')}")
    for r in evaluation["rows"]:
        if r["result"] == "SIM_ERROR":
            lines.append(f"- [SIM_ERROR] {r['symbol']}: {str(r.get('diagnostic'))[:200]}")
    s = evaluation.get("summary", {})
    if not lines:
        if not s.get("measured"):
            return ("NO specification could be measured: every fixture failed to produce a value, i.e. the netlist "
                    "does not simulate. Fix SPICE syntax/topology first (see compile errors).")
        return "All measured specifications passed."
    if s.get("planned"):
        lines.insert(0, f"Coverage {s.get('measured')}/{s.get('planned')} testable specs measured; "
                        f"{s.get('fail_hard', 0) + s.get('fail_typ', 0)} failing:")
    return "\n".join(lines[:max_items])
