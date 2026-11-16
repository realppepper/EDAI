import math
import re
from typing import Any

import sympy as sp


class SymPyOracleEngine:
    """
    AnalogVerifier Neuro-Symbolic Oracle Engine.
    Transforms datasheet specifications into rigorous SymPy symbolic constraints,
    evaluates simulated measurement outputs, and computes quantitative residual gradients
    for AI circuit synthesis closed-loop repair.
    """

    UNIT_MULTIPLIERS = {
        'f': 1e-15, 'p': 1e-12, 'n': 1e-9, 'u': 1e-6, 'µ': 1e-6,
        'm': 1e-3, 'k': 1e3, 'M': 1e6, 'meg': 1e6, 'g': 1e9, 't': 1e12
    }

    def __init__(self):
        pass

    def parse_numeric(self, val_str: Any) -> float | None:
        """Parses numeric string with engineering suffixes or scientific notation into float."""
        if val_str is None:
            return None
        if isinstance(val_str, (int, float)):
            return float(val_str)
        s = str(val_str).strip()
        if not s or s.lower() in ["-", "n/a", "none"]:
            return None

        # Clean string
        s = s.replace(",", "")
        
        # Match standard float or float with unit prefix
        match = re.search(r'([-+]?[0-9]*\.?[0-9]+(?:[eE][-+]?[0-9]+)?)\s*([a-zA-Zµ]*)', s)
        if match:
            num = float(match.group(1))
            suffix = match.group(2)
            if suffix:
                for k, v in self.UNIT_MULTIPLIERS.items():
                    if suffix.startswith(k) or suffix.lower().startswith(k.lower()):
                        return num * v
            return num
        return None

    def build_oracle(self, spec: dict[str, Any]) -> dict[str, Any]:
        """
        Builds a SymPy symbolic constraint oracle for an individual electrical parameter.
        """
        sym_name = spec.get("symbol", "param")
        clean_sym = re.sub(r'[^a-zA-Z0-9_]', '_', sym_name).lower()
        param_var = sp.Symbol(clean_sym)

        min_val = self.parse_numeric(spec.get("min"))
        typ_val = self.parse_numeric(spec.get("typ"))
        max_val = self.parse_numeric(spec.get("max"))

        unit = spec.get("unit") or ""
        # Adjust for units specified at table level
        multiplier = 1.0
        unit_lower = unit.lower()
        if "mv" in unit_lower:
            multiplier = 1e-3
        elif "uv" in unit_lower or "µv" in unit_lower:
            multiplier = 1e-6
        elif "ma" in unit_lower:
            multiplier = 1e-3
        elif "ua" in unit_lower or "µa" in unit_lower:
            multiplier = 1e-6
        elif "na" in unit_lower:
            multiplier = 1e-9
        elif "pa" in unit_lower:
            multiplier = 1e-12
        elif "mhz" in unit_lower:
            multiplier = 1e6
        elif "khz" in unit_lower:
            multiplier = 1e3
        elif "ghz" in unit_lower:
            multiplier = 1e9
        elif "ns" in unit_lower:
            multiplier = 1e-9
        elif "us" in unit_lower or "µs" in unit_lower:
            multiplier = 1e-6
        elif "ps" in unit_lower:
            multiplier = 1e-12

        # Convert limits if needed
        # Note: if parse_numeric already captured suffix, don't double scale
        if min_val is not None and not any(k in str(spec.get("min", "")) for k in ['u', 'm', 'k', 'M', 'n', 'p']):
            min_val *= multiplier
        if typ_val is not None and not any(k in str(spec.get("typ", "")) for k in ['u', 'm', 'k', 'M', 'n', 'p']):
            typ_val *= multiplier
        if max_val is not None and not any(k in str(spec.get("max", "")) for k in ['u', 'm', 'k', 'M', 'n', 'p']):
            max_val *= multiplier

        # If only typ is given, build standard 20% tolerance interval
        if min_val is None and max_val is None and typ_val is not None:
            if typ_val > 0:
                min_val = typ_val * 0.8
                max_val = typ_val * 1.2
            elif typ_val < 0:
                min_val = typ_val * 1.2
                max_val = typ_val * 0.8
            else:
                min_val = -1e-6
                max_val = 1e-6

        # Symbolic inequalities
        constraints = []
        if min_val is not None:
            constraints.append(param_var >= min_val)
        if max_val is not None:
            constraints.append(param_var <= max_val)

        return {
            "symbol": sym_name,
            "clean_symbol": clean_sym,
            "param_var": param_var,
            "min_val": min_val,
            "typ_val": typ_val,
            "max_val": max_val,
            "unit": unit,
            "constraints": constraints,
            "description": spec.get("description", spec.get("parameter", ""))
        }

    def evaluate(self, oracle: dict[str, Any], measured_val: float | None) -> dict[str, Any]:
        """
        Evaluates a simulation measurement against the SymPy oracle.
        Computes pass/fail, residual distance, and diagnostic direction.
        """
        sym_name = oracle["symbol"]
        min_val = oracle["min_val"]
        typ_val = oracle["typ_val"]
        max_val = oracle["max_val"]
        unit = oracle["unit"]

        if measured_val is None or math.isnan(measured_val):
            return {
                "symbol": sym_name,
                "passed": False,
                "measured": None,
                "min_target": min_val,
                "typ_target": typ_val,
                "max_target": max_val,
                "unit": unit,
                "residual": None,
                "diagnostic": f"Parameter '{sym_name}' was not observed in simulation measurements.",
                "error_margin": None,
                "message": f"Parameter '{sym_name}' was not measured by simulation (missing or NaN)."
            }

        passed = True
        residual = 0.0
        diagnostic = "PASSED"

        if min_val is not None and measured_val < min_val:
            passed = False
            residual = min_val - measured_val
            pct = (residual / abs(min_val)) * 100 if min_val != 0 else 100.0
            diagnostic = f"FAILED: Below MIN bound {min_val:.4g} {unit} by {residual:.4g} ({pct:.1f}% under)"

        elif max_val is not None and measured_val > max_val:
            passed = False
            residual = measured_val - max_val
            pct = (residual / abs(max_val)) * 100 if max_val != 0 else 100.0
            diagnostic = f"FAILED: Exceeds MAX bound {max_val:.4g} {unit} by {residual:.4g} ({pct:.1f}% over)"

        return {
            "symbol": sym_name,
            "passed": passed,
            "measured": measured_val,
            "min_target": min_val,
            "typ_target": typ_val,
            "max_target": max_val,
            "unit": unit,
            "residual": residual,
            "diagnostic": diagnostic
        }
