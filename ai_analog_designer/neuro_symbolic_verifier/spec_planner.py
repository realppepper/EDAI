"""
Spec planner: turns extracted datasheet spec rows into a MEASUREMENT PLAN.

Combines fast structural priors with LLM-based probabilistic semantic inference
to classify device topology, map arbitrary datasheet pin names to fixture roles
(IN+, IN-, OUT, V+, V-, etc.), and map electrical specification rows + test conditions
into canonical SPICE verification fixtures without brittle regex failures.
"""
import hashlib
import json
import os
import re
from typing import Any

DEVICE_KEYWORDS = [
    ("comparator", "comparator"),
    ("timer", r"\btimer|555"),
    ("shunt_ref", r"shunt|programmable reference|tl431|voltage reference"),
    ("ldo", r"regulator|ldo"),
    ("audio_amp", r"audio power|power amplifier|lm386"),
    ("inamp", r"instrumentation"),
    ("opamp", r"op(erational)?[- ]?amp|amplifier"),
]


def detect_device_class(ic_info: dict[str, Any], pins: list[dict[str, Any]]) -> str:
    text = " ".join(str(ic_info.get(k, "")) for k in ("name", "category", "description")).lower()
    names = " ".join(str(p.get("raw_name") or p.get("name") or "") for p in pins).upper()
    if re.search(r"THRES|TRIG|DISCH", names):
        return "timer"
    if re.search(r"CATHODE|ANODE", names):
        return "shunt_ref"
    if re.search(r"\bADJ", names) and len(pins) <= 4:
        return "ldo"
    if re.search(r"BYPASS|GAIN", names):
        return "audio_amp"
    if re.search(r"\bRG\b|RG1|RG8|\bREF\b", names) and re.search(r"VIN|IN", names):
        return "inamp"
    for cls, pat in DEVICE_KEYWORDS:
        if re.search(pat, text):
            return cls
    return "opamp"


# ---------------------------------------------------------------- pin mapping
def _norm(n: str) -> str:
    return str(n or "").upper().replace("−", "-").replace("–", "-").strip()


def _polarity(n: str) -> str | None:
    """Returns 'P', 'N' or None for an input pin name."""
    u = _norm(n)
    if "+" in u or re.search(r"_P\b|_P\d|P$", u) or "NONINV" in u or "NON-INV" in u or u.startswith("+") or re.match(r"^\d?IN\+?P", u):
        if "-" not in u and not re.search(r"_N\b", u):
            return "P"
    if "-" in u or re.search(r"_N\b|_N\d|N$", u) or re.search(r"(?<!NO)(?<!NON)INV", u) or u.startswith("-"):
        return "N"
    return None


def _channel(n: str) -> str:
    u = _norm(n)
    m = re.search(r"(\d)", u)
    if m:
        return m.group(1)
    m = re.search(r"\b([A-D])\b|[_ ]([A-D])$|([A-D])$", u.replace("+", "").replace("-", ""))
    if m:
        return next(g for g in m.groups() if g)
    return "1"


def map_pins(device_class: str, pins: list[dict[str, Any]]) -> dict[str, Any]:
    """Maps datasheet pins to fixture roles. Returns {'vpos','vneg','gnd','channels':[{'inp','inn','out'}], ...}."""
    roles: dict[str, Any] = {
        "vpos": None,
        "vneg": None,
        "channels": [],
        "other": [],
        "pin_order": [p["name"] for p in pins if p.get("name")],
    }
    ins, outs = [], []
    for p in pins:
        node = p["name"]
        raw = _norm(p.get("raw_name") or p["name"])
        role = str(p.get("role") or "").upper()
        if role == "NC" or re.fullmatch(r"NC\d*|NO_CONNECT.*|N/?C", raw):
            continue
        # Check negative supply / ground FIRST so VCC_N or VCC- is never mistaken for positive VCC
        is_neg_rail = (
            re.fullmatch(r"V-|VEE|VSS|GND|V-/GND|GND/V-|VN|VNEG|ANODE|V_N|GND_V_N|V_N_GND|VCC-|VCC_N|VDD-|VDD_N|VS-|VS_N|AVSS|PVSS|PGND|AGND", raw)
            or role == "GROUND"
            or (role == "POWER" and re.search(r"[-–]|EE|SS|_N$|\bNEG", raw))
        )
        if is_neg_rail:
            roles["vneg"] = roles["vneg"] or node
            continue
        is_pos_rail = (
            re.fullmatch(r"V\+|VCC|VDD|VS|V\+?S|VIN|INPUT|V\+_?|VP|VPOS|VCC\+|VCC_P|VDD\+|VDD_P|VS\+|VS_P|V_P|AVDD|PVDD", raw)
            or (role == "POWER" and re.search(r"\+|_P$|CC|DD|^VS$|^VIN$|^INPUT$|\bPOS", raw) and not re.search(r"[-–]|_N$|EE|SS", raw))
        )
        if is_pos_rail:
            roles["vpos"] = roles["vpos"] or node
            continue
        entry = {"node": node, "raw": raw, "role": role}
        if device_class in ("opamp", "comparator", "inamp", "audio_amp"):
            if role == "OUTPUT" or re.search(r"OUT|^VO$|^VOUT$", raw):
                outs.append(entry)
                continue
            if role in ("SIGNAL", "INPUT") or re.search(r"IN", raw):
                ins.append(entry)
                continue
        roles["other"].append(entry)

    if device_class in ("opamp", "comparator"):
        chans: dict[str, dict[str, str]] = {}
        for e in ins:
            pol = _polarity(e["raw"])
            ch = _channel(e["raw"])
            chans.setdefault(ch, {})
            if pol == "P":
                chans[ch]["inp"] = e["node"]
            elif pol == "N":
                chans[ch]["inn"] = e["node"]
        # A channel with one known polarity and a leftover input: the leftover is the other polarity
        # (covers pin names such as "IN1" / "1IN" or "IN" / "IN_P" that carry no +/- suffix on one pin).
        leftovers: dict[str, list[dict[str, str]]] = {}
        for e in ins:
            if _polarity(e["raw"]) is None:
                leftovers.setdefault(_channel(e["raw"]), []).append(e)
        for ch_id, extra in leftovers.items():
            ch = chans.setdefault(ch_id, {})
            for e in extra:
                if "inp" not in ch:
                    ch["inp"] = e["node"]
                elif "inn" not in ch:
                    ch["inn"] = e["node"]
        for e in outs:
            ch = _channel(e["raw"])
            chans.setdefault(ch, {})["out"] = e["node"]
        # single-channel parts without digits
        if len(chans) > 1 and any(set(c.keys()) == {"out"} for c in chans.values()) and sum("inp" in c for c in chans.values()) == 1:
            merged = {}
            for c in chans.values():
                merged.update(c)
            chans = {"1": merged}
        roles["channels"] = [c for _, c in sorted(chans.items()) if {"inp", "inn", "out"} <= set(c)]
        # Soft fallback if channels is still empty but we have at least 2 inputs and 1 output
        if not roles["channels"] and len(ins) >= 2 and len(outs) >= 1:
            inp_cand = next((e["node"] for e in ins if _polarity(e["raw"]) == "P"), None)
            inn_cand = next((e["node"] for e in ins if _polarity(e["raw"]) == "N"), None)
            rem = [e["node"] for e in ins if e["node"] not in (inp_cand, inn_cand)]
            if not inp_cand and rem:
                inp_cand = rem.pop(0)
            if not inn_cand and rem:
                inn_cand = rem.pop(0)
            if inp_cand and inn_cand:
                roles["channels"] = [{"inp": inp_cand, "inn": inn_cand, "out": outs[0]["node"]}]
    elif device_class == "inamp":
        ch = {}
        for e in ins:
            pol = _polarity(e["raw"])
            if pol == "P":
                ch["inp"] = e["node"]
            elif pol == "N":
                ch["inn"] = e["node"]
        for e in ins:
            if "inp" not in ch and e["node"] != ch.get("inn"):
                ch["inp"] = e["node"]
            elif "inn" not in ch and e["node"] != ch.get("inp"):
                ch["inn"] = e["node"]
        if outs:
            ch["out"] = outs[0]["node"]
        for e in roles["other"]:
            if re.search(r"^REF", e["raw"]):
                ch["ref"] = e["node"]
            elif re.search(r"RG", e["raw"]):
                ch.setdefault("rg", []).append(e["node"])
        roles["channels"] = [ch] if {"inp", "inn", "out"} <= set(ch) else []
    elif device_class == "audio_amp":
        ch = {}
        for e in ins:
            pol = _polarity(e["raw"])
            if pol == "P":
                ch["inp"] = e["node"]
            elif pol == "N":
                ch["inn"] = e["node"]
        for e in ins:
            if "inp" not in ch and e["node"] != ch.get("inn"):
                ch["inp"] = e["node"]
            elif "inn" not in ch and e["node"] != ch.get("inp"):
                ch["inn"] = e["node"]
        if outs:
            ch["out"] = outs[0]["node"]
        for e in roles["other"]:
            if "BYPASS" in e["raw"]:
                ch["bypass"] = e["node"]
            elif "GAIN" in e["raw"]:
                ch.setdefault("gain", []).append(e["node"])
        roles["channels"] = [ch] if {"inp", "inn", "out"} <= set(ch) else []
    elif device_class == "timer":
        t = {}
        for p in pins:
            raw = _norm(p.get("raw_name") or p["name"])
            for key, pat in (("trig", r"TRIG"), ("thres", r"THRES"), ("out", r"^OUT"), ("reset", r"RESET"),
                             ("cont", r"CONT|CV"), ("disch", r"DISCH")):
                if re.search(pat, raw):
                    t[key] = p["name"]
        roles["timer"] = t
    elif device_class == "shunt_ref":
        s = {}
        for p in pins:
            raw = _norm(p.get("raw_name") or p["name"])
            if "CATHODE" in raw or raw in ("K", "CATH", "VKA"):
                s["cathode"] = p["name"]
            elif "REF" in raw:
                s["ref"] = p["name"]
            elif "ANODE" in raw or raw in ("A", "GND"):
                s["anode"] = p["name"]
        roles["shunt"] = s
        roles["vneg"] = s.get("anode")
    elif device_class == "ldo":
        l = {}
        for p in pins:
            raw = _norm(p.get("raw_name") or p["name"])
            if re.search(r"ADJ|GND", raw):
                l["adj"] = p["name"]
            elif re.search(r"OUT", raw):
                l["out"] = p["name"]
            elif re.search(r"IN", raw):
                l["in"] = p["name"]
        roles["ldo"] = l
        roles["vpos"] = l.get("in")
    return roles


# ---------------------------------------------------------------- condition parsing
def parse_conditions(text: str) -> dict[str, Any]:
    """Pulls numeric test conditions out of a datasheet condition string."""
    t = (text or "").replace("µ", "u").replace("μ", "u").replace("Ω", "Ohm").replace("−", "-").replace("–", "-")
    c: dict[str, Any] = {}
    m = re.search(r"V(?:S|CC|DD|\+)\s*=\s*±\s*(\d+\.?\d*)\s*V", t, re.IGNORECASE)
    if m:
        c["vs"] = 2 * float(m.group(1))
    else:
        m = re.search(r"V(?:S|CC|DD|IN)\s*=\s*(?:\(V\+\)\s*[-–]\s*\(V[-–]\)\s*=\s*)?(\d+\.?\d*)\s*V(?!\s*(?:to|-|–)\s*\d)", t, re.IGNORECASE)
        if m:
            c["vs"] = float(m.group(1))
        else:
            m = re.search(r"V(?:S|CC|DD)\s*=\s*(\d+\.?\d*)\s*V?\s*(?:to|-|–)\s*(\d+\.?\d*)\s*V", t, re.IGNORECASE)
            if m:
                c["vs_range"] = (float(m.group(1)), float(m.group(2)))
    m = re.search(r"R\s*L\s*[=≥>≤<]+\s*(\d+\.?\d*)\s*([kKmM]?)\s*(?:Ohm|Ω)?", t)
    if m:
        c["rl"] = float(m.group(1)) * {"k": 1e3, "K": 1e3, "m": 1e-3, "M": 1e6, "": 1}[m.group(2)]
    m = re.search(r"C\s*L\s*=\s*(\d+\.?\d*)\s*([pnu]?)F", t, re.IGNORECASE)
    if m:
        c["cl"] = float(m.group(1)) * {"p": 1e-12, "n": 1e-9, "u": 1e-6, "": 1}[m.group(2).lower()]
    m = re.search(r"I\s*(?:OUT|O|OL|OH|L|KA|K)\s*=\s*([-+]?\d+\.?\d*)\s*([munp]?)A", t, re.IGNORECASE)
    if m:
        c["iout"] = float(m.group(1)) * {"m": 1e-3, "u": 1e-6, "n": 1e-9, "p": 1e-12, "": 1}[m.group(2).lower()]
    m = re.search(r"\bG\s*=\s*\+?\s*(\d+\.?\d*)", t)
    if m:
        c["gain"] = float(m.group(1))
    m = re.search(r"\bf\s*=\s*(\d+\.?\d*)\s*([kM]?)Hz", t)
    if m:
        c["freq"] = float(m.group(1)) * {"k": 1e3, "M": 1e6, "": 1}[m.group(2)]
    m = re.search(r"V\s*O(?:UT)?\s*=\s*(\d+\.?\d*)\s*V(?!\s*-)", t)
    if m:
        c["vo"] = float(m.group(1))
    m = re.search(r"V\s*O(?:UT)?\s*=\s*\(?\s*V\s*([-+])\s*\)?\s*(?:\+\s*(\d+\.?\d*)\s*(m?)V)?", t)
    if m:
        c["vo_at"] = "neg" if m.group(1) == "-" else "pos"
        if m.group(2):
            c["vo_offset"] = float(m.group(2)) * (1e-3 if m.group(3) == "m" else 1.0)
    m = re.search(r"V\s*ID\s*=\s*([-+]?\d+\.?\d*)\s*V", t)
    if m:
        c["vid"] = float(m.group(1))
    m = re.search(r"VKA\s*=\s*(\d+\.?\d*)\s*V", t)
    if m:
        c["vka"] = float(m.group(1))
    m = re.search(r"RESET\s+at\s+(VCC|0\s*V|\d+\.?\d*\s*V)", t, re.IGNORECASE)
    if m:
        c["rst_level"] = 0.0 if m.group(1).upper().startswith("0") else ("vcc" if "VCC" in m.group(1).upper() else float(re.findall(r"\d+\.?\d*", m.group(1))[0]))
    if re.search(r"output\s+low", t, re.IGNORECASE):
        c["state"] = "low"
    elif re.search(r"output\s+high", t, re.IGNORECASE):
        c["state"] = "high"
    if re.search(r"positive rail|\(V\+\)|V\+\b.*rail|sourc", t, re.IGNORECASE):
        c["rail"] = "pos"
    elif re.search(r"negative rail|\(V[-–]\)|V[-–]\b.*rail|sink", t, re.IGNORECASE):
        c["rail"] = "neg"
    if re.search(r"connected\s+to\s*\(?\s*V\s*[-–]\s*\)?|connected\s+to\s+GND", t, re.IGNORECASE):
        c["rl_to"] = "vn"
    if re.search(r"-\s*40\s*°?C|0\s*°?C\s*(to|≤)|full\s+range|full operating|T\s*A\s*=\s*T\s*MIN|TMIN|over (the )?(full|rated|operating).*temp|over temperature|full temp", t, re.IGNORECASE) \
            and not re.search(r"25\s*°?C", t):
        c["temp_range"] = True
    return c


# ---------------------------------------------------------------- kind classification
# (device classes, symbol regex, name regex, kind, canonical unit, magnitude-compare)
KIND_RULES = [
    (("opamp", "inamp", "comparator"), r"^V(OS|IO)$", r"offset voltage(?!.*drift)", "vos", "V", True),
    (("opamp", "inamp", "comparator"), r"^I(B|IB)$", r"bias current(?!.*drift)", "ib", "A", True),
    (("opamp", "inamp", "comparator"), r"^I(OS|IO)$", r"offset current(?!.*drift)", "ios", "A", True),
    (("opamp", "inamp", "comparator", "timer", "audio_amp"), r"^I(Q|CC|S|SUPPLY)$", r"quiescent|supply current", "iq", "A", False),
    (("opamp",), r"^A(OL|VOL|VD)$", r"open[- ]loop (voltage )?gain|large[- ]signal (differential )?voltage (gain|amplification)", "aol_db", "dB", False),
    (("comparator",), r"^A(VD|OL|V)$", r"large[- ]signal|voltage (gain|amplification)", "avd_db", "dB", False),
    (("opamp", "inamp"), r"^GBW|^GBP|^UGBW|^f(T|u)$", r"gain[- ]bandwidth|unity[- ]gain", "gbw", "Hz", False),
    (("opamp", "inamp"), r"^(Θ|θ|PM|ΦM|φm|phi)", r"phase margin", "pm", "deg", False),
    (("opamp", "inamp", "audio_amp"), r"^PSRR$|^k?SVR$", r"(power|supply)[- ]supply rejection|supply rejection|ripple rejection", "psrr_db", "dB", False),
    (("opamp", "inamp"), r"^CMRR$|^k?CMR$", r"common[- ]mode rejection", "cmrr_db", "dB", False),
    (("opamp", "inamp"), r"^SR", r"slew rate", "sr", "V/us", False),
    (("opamp", "inamp"), r"^V(O|OUT|OH|OL|OM)\b|^VO[HL]?$", r"output (voltage )?swing|voltage output|output voltage (high|low)|swing from rail", "vswing", "V", False),
    (("opamp", "inamp"), r"^I(SC|OS\(sc\))$", r"short[- ]circuit", "isc", "A", True),
    (("opamp",), r"^IO$|^IOUT$", r"output current(?!.*short)", "iout", "A", True),
    (("opamp", "inamp"), r"^e[nN]$|^V[nN]$", r"(voltage )?noise density", "en", "nV/rtHz", False),
    (("comparator",), r"^VOL$", r"low[- ]level output voltage|output (saturation|low) voltage", "vol", "V", False),
    (("comparator",), r"^IOL$", r"low[- ]level output current|output sink current", "iol", "A", False),
    (("comparator",), r"^IOH$", r"high[- ]level output current|output leakage", "ioh", "A", True),
    (("comparator",), r"^t(resp|PD|PLH|PHL|r)|^t_?r", r"response time|propagation delay", "tresp", "s", False),
    (("timer",), r"^VTH|^V(THRES|THRESH)", r"thres(hold)? voltage", "vth", "V", False),
    (("timer",), r"^VTRIG|^VTR", r"trig(ger)? voltage", "vtrig", "V", False),
    (("timer",), r"^VRESET|^VRES", r"reset voltage", "vreset", "V", False),
    (("timer",), r"^VCONT|^VCV|^VCTL", r"cont(rol)? voltage", "vcont", "V", False),
    (("timer",), r"^ITH|^ITHRES", r"thres(hold)? current", "ith", "A", True),
    (("timer",), r"^ITRIG", r"trig(ger)? current", "itrig", "A", True),
    (("timer",), r"^IRESET", r"reset current", "ireset", "A", True),
    (("timer",), r"^VOL$", r"low[- ]level output voltage", "vol555", "V", False),
    (("timer",), r"^VOH$", r"high[- ]level output voltage", "voh555", "V", False),
    (("timer",), r"^VDISCH", r"disch(arge)? .*on[- ]state voltage|switch on-state voltage", "vdisch_on", "V", False),
    (("timer",), r"^IDISCH", r"disch(arge)? .*off[- ]state current|switch off-state current", "idisch_off", "A", True),
    (("timer",), r"^t[rR]$", r"rise time", "tr555", "s", False),
    (("timer",), r"^t[fF]$", r"fall time", "tf555", "s", False),
    (("shunt_ref",), r"^V(ref|REF|KA)$", r"^reference voltage", "vref", "V", False),
    (("shunt_ref",), r"^I(ref|REF)$", r"^reference (input )?current", "iref", "A", False),
    (("shunt_ref",), r"^I(min|MIN)$", r"minimum cathode current", "imin", "A", False),
    (("shunt_ref",), r"^I(off|OFF)$", r"off[- ]state cathode current", "ioff", "A", False),
    (("shunt_ref",), r"Z(KA|ka)", r"dynamic impedance", "zka", "Ohm", False),
    (("shunt_ref",), r"ΔV(ref|REF)/ΔV(KA|ka)|^dVref", r"ratio of change in reference voltage", "dvref_dvka", "V/V", True),
    (("ldo",), r"^V(REF|ref)$", r"^reference voltage", "vref_ldo", "V", False),
    (("ldo",), r"^I(ADJ|adj)$", r"^adjust(ment)? pin current$", "iadj", "A", False),
    (("ldo",), r"", r"^line regulation", "line_reg", "%/V", False),
    (("ldo",), r"", r"^load regulation", "load_reg", "V", False),
    (("ldo",), r"^I(LIM|lim|SC)", r"current limit|short[- ]circuit current", "ilim", "A", False),
    (("ldo",), r"^I(MIN|min)", r"minimum load current", "imin_ldo", "A", False),
    (("ldo",), r"^PSRR|^k?SVR|RR", r"ripple rejection", "psrr_ldo_db", "dB", False),
    (("audio_amp",), r"^A[Vv]$", r"voltage gain", "av_db", "dB", False),
    (("audio_amp",), r"^BW$", r"bandwidth", "bw", "Hz", False),
    (("audio_amp",), r"^R(IN|in)$", r"input resistance", "rin", "Ohm", False),
    (("audio_amp",), r"^I(BIAS|B)$", r"input bias current", "ib", "A", True),
    (("inamp",), r"^BW$", r"bandwidth", "bw_inamp", "Hz", False),
    (("inamp",), r"", r"^gain error", "gain_err", "%", True),
]

UNSUPPORTED_HINTS = [
    (r"settling|overload recovery|THD|distortion|intermodulation|headroom|channel separation|capacitive load|"
     r"impedance|resistance|noise(?!.*density)|temperature coefficient|drift|stability|sensitivity|"
     r"thermal regulation|long[- ]term|output power|full power|deviation", "UNSUPPORTED_KIND"),
    (r"^(common[- ]mode (input )?voltage|input voltage range|operating supply voltage|supply voltage range|gain equation|safe input|gain$)",
     "NOT_TESTABLE_CONDITION"),
]


def classify_spec(device_class: str, spec: dict[str, Any]) -> tuple[str | None, str | None, bool, str]:
    """Returns (kind, canonical_unit, magnitude_compare, status)."""
    sym = str(spec.get("symbol") or "").strip()
    name = str(spec.get("name") or "").strip()
    cat = str(spec.get("category") or "ELECTRICAL").upper()
    if cat != "ELECTRICAL":
        return None, None, False, f"NOT_TESTABLE_{cat}"
    for pat, status in UNSUPPORTED_HINTS:
        if re.search(pat, name, re.IGNORECASE) and not re.search(r"density", name, re.IGNORECASE):
            if status == "UNSUPPORTED_KIND" and re.search(r"noise density", name, re.IGNORECASE):
                continue
            return None, None, False, status
    for classes, sym_re, name_re, kind, unit, mag in KIND_RULES:
        if device_class not in classes:
            continue
        if (sym_re and re.search(sym_re, sym, re.IGNORECASE)) or (name_re and re.search(name_re, name, re.IGNORECASE)):
            return kind, unit, mag, "PLANNED"
    # values that are not numbers (expressions) are untestable anyway
    if spec.get("min") is None and spec.get("typ") is None and spec.get("max") is None:
        return None, None, False, "NOT_TESTABLE_CONDITION"
    return None, None, False, "UNSUPPORTED_KIND"


def default_vs(device_class: str, specs: list[dict[str, Any]]) -> float:
    """Chooses the fixture supply voltage: most frequent explicit VS in conditions, else class default."""
    votes: dict[float, int] = {}
    for s in specs:
        c = parse_conditions(s.get("test_conditions") or "")
        if "vs" in c:
            votes[c["vs"]] = votes.get(c["vs"], 0) + 1
    if votes:
        return max(votes.items(), key=lambda kv: kv[1])[0]
    return {"opamp": 30.0, "inamp": 30.0, "comparator": 5.0, "timer": 5.0, "ldo": 10.0, "shunt_ref": 0.0,
            "audio_amp": 6.0}.get(device_class, 5.0)


_KIND_META: dict[str, tuple[str, bool]] = {
    kind: (unit, mag) for _, _, _, kind, unit, mag in KIND_RULES
}


def _needs_llm_pin_refinement(device_class: str, pin_map: dict[str, Any], pins: list[dict[str, Any]]) -> bool:
    if not pins:
        return False
    if device_class in ("opamp", "comparator", "inamp", "audio_amp"):
        if not pin_map.get("vpos") or not pin_map.get("vneg") or not pin_map.get("channels"):
            return True
    elif device_class == "timer":
        t = pin_map.get("timer") or {}
        if not {"trig", "thres", "out"} <= set(t):
            return True
    elif device_class == "shunt_ref":
        s = pin_map.get("shunt") or {}
        if not {"cathode", "ref", "anode"} <= set(s):
            return True
    elif device_class == "ldo":
        l = pin_map.get("ldo") or {}
        if not {"in", "out", "adj"} <= set(l):
            return True
    return False


def _llm_probabilistic_plan(
    ic_info: dict[str, Any],
    pins: list[dict[str, Any]],
    specs: list[dict[str, Any]],
    prior_class: str,
    prior_pin_map: dict[str, Any],
    prior_items: list[dict[str, Any]],
) -> tuple[str, dict[str, Any], dict[int, dict[str, Any]]]:
    """
    Uses LLM probabilistic semantic inference to:
      1. Infer/refine device_class and map arbitrary pin names to fixture roles (vpos, vneg, channels, etc.)
      2. Probabilistically classify unmatched/ambiguous electrical specification rows into canonical fixture kinds
         and parse non-standard test condition strings into numeric fixture parameters.
    Never raises an exception; falls back seamlessly to prior values.
    """
    if os.environ.get("ANALOG_DISABLE_LLM_PLANNER") == "1":
        return prior_class, prior_pin_map, {}

    need_pins = _needs_llm_pin_refinement(prior_class, prior_pin_map, pins)
    unmapped_specs = [
        {
            "spec_index": it["spec_index"],
            "symbol": it.get("symbol"),
            "name": it.get("name"),
            "unit": it.get("unit"),
            "min": it.get("min"),
            "typ": it.get("typ"),
            "max": it.get("max"),
            "test_conditions": it.get("test_conditions"),
        }
        for it in prior_items
        if str(it.get("category") or "ELECTRICAL").upper() == "ELECTRICAL"
        and it.get("status") != "PLANNED"
        and any(it.get(k) is not None for k in ("min", "typ", "max"))
    ]

    if not need_pins and not unmapped_specs:
        return prior_class, prior_pin_map, {}

    try:
        from ..llm_client import LLMClient
        llm = LLMClient(role="fast")
        if getattr(llm, "provider", "none") == "none":
            return prior_class, prior_pin_map, {}

        compact_pins = [
            {
                "name": p.get("name"),
                "raw_name": p.get("raw_name"),
                "role": p.get("role"),
                "description": str(p.get("description") or "")[:80],
            }
            for p in pins
        ]
        allowed_kinds = sorted(_KIND_META.keys())
        prompt = (
            "You are a probabilistic neuro-symbolic analog IC verification planner.\n"
            f"IC Metadata: {json.dumps(ic_info, ensure_ascii=False)}\n"
            f"Prior device_class: {prior_class}\n"
            f"Extracted Pins: {json.dumps(compact_pins, ensure_ascii=False)}\n"
            f"Prior Pin Map: {json.dumps({k: v for k, v in prior_pin_map.items() if k != 'other'}, ensure_ascii=False)}\n"
            f"Unmapped Electrical Specs (up to 25): {json.dumps(unmapped_specs[:25], ensure_ascii=False)}\n\n"
            "Tasks:\n"
            "1. Determine `device_class` from: ['opamp', 'comparator', 'timer', 'shunt_ref', 'ldo', 'audio_amp', 'inamp'].\n"
            "2. Map exact pin `name` values from Extracted Pins into `pin_map`:\n"
            "   - `vpos`: positive supply pin name (e.g. VCC, VCC_P, V+, VDD)\n"
            "   - `vneg`: negative supply or ground pin name (e.g. VEE, VCC_N, V-, GND, VSS)\n"
            "   - `channels`: list of `{\"inp\": <non-inverting input pin name>, \"inn\": <inverting input pin name>, \"out\": <output pin name>}`\n"
            "3. For each item in `Unmapped Electrical Specs` that is a testable electrical parameter, probabilistically map it to one of "
            f"`allowed_kinds`: {allowed_kinds} (or null if genuinely untestable like drift/THD/package resistance), and extract numeric "
            "conditions (`vs` in V [if +/-15V then 30.0], `rl` in Ohm, `cl` in F, `iout` in A, `freq` in Hz, `rail` in ['pos','neg']).\n\n"
            "Return ONLY valid JSON:\n"
            "{\n"
            "  \"device_class\": \"opamp\",\n"
            "  \"pin_map\": {\"vpos\": \"...\", \"vneg\": \"...\", \"channels\": [{\"inp\": \"...\", \"inn\": \"...\", \"out\": \"...\"}]},\n"
            "  \"spec_mappings\": [{\"spec_index\": 0, \"kind\": \"vos\", \"conditions\": {\"vs\": 30.0, \"rl\": 2000.0}}]\n"
            "}"
        )
        res = llm.complete_json(
            prompt,
            system="Return only valid JSON matching the requested schema.",
            temperature=0.0,
            max_tokens=1024,
            stage="probabilistic_spec_planner",
        )
        if not isinstance(res, dict):
            return prior_class, prior_pin_map, {}

        valid_classes = {"opamp", "comparator", "timer", "shunt_ref", "ldo", "audio_amp", "inamp"}
        new_class = str(res.get("device_class") or prior_class).lower().strip()
        if new_class not in valid_classes:
            new_class = prior_class

        valid_pin_names = {p.get("name") for p in pins if p.get("name")}
        llm_pm = res.get("pin_map") or {}
        merged_pm = dict(prior_pin_map)
        if isinstance(llm_pm, dict):
            if not merged_pm.get("vpos") and llm_pm.get("vpos") in valid_pin_names:
                merged_pm["vpos"] = llm_pm["vpos"]
            if not merged_pm.get("vneg") and llm_pm.get("vneg") in valid_pin_names:
                merged_pm["vneg"] = llm_pm["vneg"]
            if not merged_pm.get("channels") and isinstance(llm_pm.get("channels"), list):
                clean_ch = []
                for ch in llm_pm["channels"]:
                    if isinstance(ch, dict) and {"inp", "inn", "out"} <= set(ch):
                        if ch["inp"] in valid_pin_names and ch["inn"] in valid_pin_names and ch["out"] in valid_pin_names:
                            clean_ch.append({"inp": ch["inp"], "inn": ch["inn"], "out": ch["out"]})
                if clean_ch:
                    merged_pm["channels"] = clean_ch

        spec_overrides: dict[int, dict[str, Any]] = {}
        for sm in res.get("spec_mappings") or []:
            if not isinstance(sm, dict):
                continue
            s_idx = sm.get("spec_index")
            k = sm.get("kind")
            if isinstance(s_idx, int) and isinstance(k, str) and k in _KIND_META:
                spec_overrides[s_idx] = {
                    "kind": k,
                    "conditions": sm.get("conditions") if isinstance(sm.get("conditions"), dict) else {},
                }
        return new_class, merged_pm, spec_overrides
    except Exception:
        return prior_class, prior_pin_map, {}


def build_plan(ic_info: dict[str, Any], pins: list[dict[str, Any]], specs: list[dict[str, Any]]) -> dict[str, Any]:
    device_class = detect_device_class(ic_info, pins)
    pin_map = map_pins(device_class, pins)
    elec = [s for s in specs if str(s.get("category") or "ELECTRICAL").upper() == "ELECTRICAL"]
    vs_default = default_vs(device_class, elec)
    items = []
    for idx, s in enumerate(specs):
        kind, unit, mag, status = classify_spec(device_class, s)
        cond = parse_conditions(s.get("test_conditions") or "")
        s_min, s_typ, s_max = s.get("min"), s.get("typ"), s.get("max")
        # Upper-bound-only op-amp specs (Vos, Ios, Ib, Iq) never have a lower-bound MIN in datasheets;
        # when 2-column tables (TYP, MAX) shift into (min, typ, None), restore them to (None, typ, max).
        if kind in ("vos", "ios", "ib", "iq") and s_min is not None and s_typ is not None and s_max is None:
            try:
                if float(s_min) >= 0 and float(s_typ) > float(s_min):
                    s_min, s_typ, s_max = None, s_min, s_typ
            except (TypeError, ValueError):
                pass
        item = {"spec_index": idx, "symbol": s.get("symbol"), "name": s.get("name"), "category": s.get("category", "ELECTRICAL"),
                "min": s_min, "typ": s_typ, "max": s_max, "unit": s.get("unit"),
                "test_conditions": s.get("test_conditions"), "kind": kind, "canonical_unit": unit, "magnitude": mag,
                "status": status, "conditions": cond, "note": ""}
        items.append(item)

    # Invoke LLM probabilistic planner to refine pin mappings and recover unmapped electrical specs
    device_class, pin_map, spec_overrides = _llm_probabilistic_plan(
        ic_info, pins, specs, device_class, pin_map, items
    )
    for idx, ov in spec_overrides.items():
        if 0 <= idx < len(items) and items[idx]["status"] != "PLANNED":
            k = ov["kind"]
            unit, mag = _KIND_META[k]
            items[idx]["kind"] = k
            items[idx]["canonical_unit"] = unit
            items[idx]["magnitude"] = mag
            items[idx]["status"] = "PLANNED"
            llm_cond = ov.get("conditions") or {}
            for ck in ("vs", "rl", "cl", "iout", "freq", "vo", "vid", "rail", "state"):
                if llm_cond.get(ck) is not None and ck not in items[idx]["conditions"]:
                    try:
                        items[idx]["conditions"][ck] = float(llm_cond[ck]) if ck not in ("rail", "state") else str(llm_cond[ck])
                    except (ValueError, TypeError):
                        pass

    seen_keys: dict[tuple, int] = {}
    for item in items:
        if item["status"] == "PLANNED":
            cond = item["conditions"]
            kind = item["kind"]
            if cond.get("temp_range"):
                item["note"] = "Full-temperature-range limit evaluated at 25C only (necessary, not sufficient)."
            vs = cond.get("vs", vs_default)
            if "vs_range" in cond and "vs" not in cond:
                lo, hi = cond["vs_range"]
                vs = vs_default if lo <= vs_default <= hi else lo
            rst = cond.get("rst_level")
            if rst == "vcc":
                rst = vs
            item["fixture"] = {"vs": vs, "rl": cond.get("rl"), "rl_to": cond.get("rl_to"), "cl": cond.get("cl"), "iout": cond.get("iout"),
                               "gain": cond.get("gain"), "freq": cond.get("freq"), "rail": cond.get("rail"),
                               "state": cond.get("state"), "vo": cond.get("vo"), "vid": cond.get("vid"), "vka": cond.get("vka"),
                               "vo_at": cond.get("vo_at"), "vo_offset": cond.get("vo_offset"),
                               "rst_level": rst}
            key = (kind, tuple(sorted((k, v) for k, v in item["fixture"].items() if v is not None)))
            item["fixture_key"] = f"{kind}_{hashlib.md5(repr(key).encode(), usedforsecurity=False).hexdigest()[:6]}"
            seen_keys[key] = seen_keys.get(key, 0) + 1
    planned = [i for i in items if i["status"] == "PLANNED"]
    return {"device_class": device_class, "pin_map": pin_map, "vs_default": vs_default, "items": items,
            "summary": {"total_rows": len(items), "electrical_rows": len(elec), "planned": len(planned),
                        "unsupported_kind": sum(i["status"] == "UNSUPPORTED_KIND" for i in items),
                        "not_testable": sum(i["status"].startswith("NOT_TESTABLE") for i in items),
                        "distinct_fixtures": len(seen_keys), "channels": len(pin_map.get("channels", []))}}


KIND_DESC = {
    "vos": "input offset voltage (unity-gain follower, output vs mid-supply)",
    "ib": "input bias current (current into each input pin, input at mid-supply)",
    "ios": "input offset current (difference of the two input currents)",
    "iq": "quiescent supply current (no load, output at mid-supply; divider by channel count)",
    "aol_db": "open-loop gain in dB (AC, DC-servoed loop, 0.1 Hz)",
    "gbw": "unity-gain frequency (AC open loop)",
    "pm": "phase margin at the unity-gain frequency",
    "cmrr_db": "CMRR in dB (common-mode AC gain vs differential open-loop gain)",
    "psrr_db": "PSRR in dB (supply ripple referred to the output, follower)",
    "sr": "slew rate (20-80% of a fast output step, follower)",
    "vswing": "output swing from the loaded rail",
    "isc": "short-circuit output current (output shorted to mid-supply)",
    "iout": "output current with the output forced to V+ or V-",
    "en": "input-referred voltage noise density at 1 kHz",
    "avd_db": "large-signal gain (input delta for a 1.4 V -> 11.4 V output swing)",
    "vol": "output low voltage at the specified sink current",
    "iol": "output sink current with the output forced to the specified VO",
    "ioh": "output leakage current with the output forced high",
    "tresp": "response time for a 100 mV step with 5 mV overdrive",
    "vth": "THRES threshold voltage (slow ramp)",
    "vtrig": "TRIG threshold voltage (slow ramp)",
    "vreset": "RESET threshold voltage (slow ramp)",
    "vcont": "CONT open-circuit voltage",
    "vol555": "output low voltage under the specified sink current",
    "voh555": "output high voltage under the specified source current",
    "ith": "THRES input current", "itrig": "TRIG input current", "ireset": "RESET input current",
    "vdisch_on": "DISCH on-state voltage at the specified current",
    "idisch_off": "DISCH off-state leakage current",
    "tr555": "output rise time (20-80%)", "tf555": "output fall time (80-20%)",
    "vref": "reference voltage with the specified cathode current",
    "iref": "reference input current", "imin": "minimum cathode current for regulation",
    "ioff": "off-state cathode current at VKA = 36 V", "zka": "dynamic impedance",
    "dvref_dvka": "d(Vref)/d(VKA)", "vref_ldo": "reference voltage (VOUT-VADJ)",
    "iadj": "ADJ pin current", "line_reg": "line regulation (%/V)",
    "load_reg": "load regulation", "ilim": "current limit", "imin_ldo": "minimum load current",
    "psrr_ldo_db": "ripple rejection in dB",
    "av_db": "voltage gain in dB", "bw": "bandwidth", "rin": "input resistance",
    "bw_inamp": "bandwidth", "gain_err": "gain error",
}


def fixture_brief(plan: dict[str, Any], limit: int = 24) -> str:
    """Human/LLM-readable list of how the circuit will actually be measured."""
    seen, lines = set(), []
    for it in plan["items"]:
        if it["status"] != "PLANNED":
            continue
        key = (it["kind"], (it.get("fixture") or {}).get("vs"))
        if key in seen:
            continue
        seen.add(key)
        fx = it.get("fixture") or {}
        cond = [f"VS={fx.get('vs')} V"]
        if fx.get("rl"):
            cond.append(f"RL={fx['rl']:.4g} Ohm")
        if fx.get("iout"):
            cond.append(f"IOUT/load={fx['iout']:.4g} A")
        if fx.get("rail"):
            cond.append(f"rail={fx['rail']}")
        lines.append(f"  - {KIND_DESC.get(it['kind'], it['kind'])} [{', '.join(cond)}]")
        if len(lines) >= limit:
            break
    return "\n".join(lines)
