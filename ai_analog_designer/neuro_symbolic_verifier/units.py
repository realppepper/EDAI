"""
Unit normalisation for datasheet specification rows.

Every spec limit is converted into the *canonical unit of its measurement kind* so that the oracle compares
like with like (e.g. AOL given as 140 V/mV and a measurement of 103 dB; CMRR given as 20 uV/V vs 94 dB).
"""
import math
import re
from typing import Any

_PREFIX = {"f": 1e-15, "p": 1e-12, "n": 1e-9, "u": 1e-6, "µ": 1e-6, "μ": 1e-6, "m": 1e-3,
           "": 1.0, "k": 1e3, "K": 1e3, "M": 1e6, "G": 1e9, "T": 1e12}

# canonical unit per base quantity
_BASE = {"v": "V", "a": "A", "hz": "Hz", "s": "s", "ohm": "Ohm", "Ω": "Ohm", "ω": "Ohm", "w": "W", "f": "F",
         "°": "deg", "deg": "deg", "degree": "deg", "degrees": "deg", "db": "dB", "%": "%", "v/v": "V/V",
         "v/us": "V/us", "v/µs": "V/us", "v/μs": "V/us", "v/ms": "V/us", "v/s": "V/us",
         "v/mv": "V/V", "mv/v": "V/V", "uv/v": "V/V", "µv/v": "V/V", "μv/v": "V/V", "%/v": "%/V", "ppm/°c": "ppm/C",
         "uv/°c": "uV/C", "µv/°c": "uV/C", "μv/°c": "uV/C", "nv/√hz": "nV/rtHz", "nv/rthz": "nV/rtHz",
         "pa/√hz": "pA/rtHz", "fa/√hz": "fA/rtHz", "uvpp": "uVpp", "µvpp": "uVpp", "uvrms": "uVrms", "µvrms": "uVrms",
         "%vo": "%", "% of fsr": "%", "mw": "W", "dbu": "dBu"}


def normalise_unit_token(u: str) -> str:
    u = (u or "").strip()
    u = u.replace("Ω", "Ohm").replace("ω", "Ohm").replace("Ω", "Ohm").replace("ohms", "Ohm").replace("ohm", "Ohm")
    u = u.replace("µ", "u").replace("μ", "u").replace("°C", "C").replace("°", "deg")
    return u


def to_si(value: float | None, unit: str) -> tuple[float | None, str]:
    """Converts (value, printed unit) into (value in canonical unit, canonical unit).
    Returns (None, unit) when the unit is not understood."""
    if value is None:
        return None, unit or ""
    raw = (unit or "").strip()
    u = raw.replace("µ", "u").replace("μ", "u").replace("Ω", "Ohm").replace("ω", "Ohm")
    ul = u.lower()
    # explicit composite units first
    if ul in ("db",):
        return float(value), "dB"
    if ul in ("dbu",):
        return float(value), "dBu"
    if ul in ("deg", "°", "degree", "degrees"):
        return float(value), "deg"
    if ul in ("%", "%vo", "% of fsr", "%fsr", "%/v".replace("/v", "")):
        return float(value), "%"
    if ul in ("%/v",):
        return float(value), "%/V"
    if ul in ("v/v",):
        return float(value), "V/V"
    if ul in ("v/mv",):
        return float(value) * 1e3, "V/V"
    if ul in ("mv/v",):
        return float(value) * 1e-3, "V/V"
    if ul in ("uv/v",):
        return float(value) * 1e-6, "V/V"
    if ul in ("v/us", "v/usec"):
        return float(value), "V/us"
    if ul in ("v/ms",):
        return float(value) * 1e-3, "V/us"
    if ul in ("v/s",):
        return float(value) * 1e-6, "V/us"
    if ul in ("ppm/c", "ppm/degc", "ppm/deg"):
        return float(value), "ppm/C"
    if ul in ("uv/c", "uv/degc"):
        return float(value), "uV/C"
    if ul in ("nv/rthz", "nv/√hz", "nv/sqrt(hz)"):
        return float(value), "nV/rtHz"
    if ul in ("pa/rthz", "pa/√hz"):
        return float(value), "pA/rtHz"
    if ul in ("fa/rthz", "fa/√hz"):
        return float(value) * 1e-3, "pA/rtHz"
    if ul in ("uvpp",):
        return float(value), "uVpp"
    if ul in ("uvrms",):
        return float(value), "uVrms"
    # simple prefixed units: mV, uA, kHz, MHz, kOhm, ns, pF, mW
    m = re.match(r"^([fpnumkKMGT]?)(V|A|Hz|s|Ohm|W|F)$", u)
    if m:
        return float(value) * _PREFIX[m.group(1)], m.group(2)
    m = re.match(r"^([fpnumkKMGT]?)(v|a|hz|s|ohm|w|f)$", ul)
    if m:
        base = {"v": "V", "a": "A", "hz": "Hz", "s": "s", "ohm": "Ohm", "w": "W", "f": "F"}[m.group(2)]
        return float(value) * _PREFIX.get(m.group(1), _PREFIX.get(m.group(1).lower(), 1.0)), base
    return None, raw


def ratio_to_db(x: float) -> float:
    return 20 * math.log10(abs(x)) if x else float("inf")


def spec_limits_in(kind_unit: str, spec: dict[str, Any]) -> dict[str, float | None]:
    """Converts a spec row's min/typ/max into the canonical unit expected by a measurement kind.

    kind_unit: "V", "A", "dB", "V/us", "Hz", "V/V", "Ohm", "deg", "%", "%/V", "nV/rtHz".
    Special cases:
      * rejection ratios printed as an error ratio (2 uV/V) are converted to a POSITIVE dB figure and only the
        guaranteed bound (the MAX error column) becomes a limit: min_dB = 20*log10(1/max_error).
      * gains printed in V/mV or V/V are converted to dB, keeping the MIN column as the guaranteed limit.
    """
    unit = (spec.get("unit") or "")
    u = unit.replace("µ", "u").replace("μ", "u").strip()
    is_error_ratio = bool(re.match(r"^\s*(u|m|n)?v\s*/\s*v\s*$", u, re.IGNORECASE))
    if kind_unit == "dB" and is_error_ratio:
        pm = re.match(r"^\s*(u|m|n)?v\s*/\s*v\s*$", u, re.IGNORECASE)
        scale = {"u": 1e-6, "m": 1e-3, "n": 1e-9, None: 1.0}[pm.group(1).lower() if pm and pm.group(1) else None]

        def to_db(v):
            return 20.0 * math.log10(1.0 / (abs(v) * scale)) if v else None
        return {"min": to_db(spec.get("max")) if spec.get("max") is not None else None,
                "typ": to_db(spec.get("typ")) if spec.get("typ") is not None else None,
                "max": None}
    out: dict[str, float | None] = {}
    for k in ("min", "typ", "max"):
        v = spec.get(k)
        if v is None:
            out[k] = None
            continue
        si, cu = to_si(float(v), unit)
        if si is None:
            out[k] = None
        elif cu == kind_unit:
            out[k] = si
        elif kind_unit == "dB" and cu == "V/V":
            out[k] = 20.0 * math.log10(abs(si)) if si else None
        elif kind_unit == "V/V" and cu == "dB":
            out[k] = 10 ** (si / 20)
        else:
            out[k] = None
    return out


def fmt(v: float | None, unit: str) -> str:
    if v is None:
        return "-"
    a = abs(v)
    if unit in ("dB", "deg", "%", "%/V", "V/us", "V/V", "nV/rtHz", "pA/rtHz", "uVpp", "uVrms", "uV/C", "ppm/C") or a == 0:
        return f"{v:.4g} {unit}"
    for p, mult in (("G", 1e9), ("M", 1e6), ("k", 1e3), ("", 1), ("m", 1e-3), ("u", 1e-6), ("n", 1e-9), ("p", 1e-12), ("f", 1e-15)):
        if a >= mult:
            return f"{v / mult:.4g} {p}{unit}"
    return f"{v:.4g} {unit}"
