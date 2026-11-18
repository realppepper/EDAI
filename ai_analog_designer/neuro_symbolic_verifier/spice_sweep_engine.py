"""
Local SPICE Runner & Bounded Parameter Sweep Optimizer.
Integrates seungcheol's deterministic SPICE runner (LTspice & ngspice),
with P0 fixes for `.meas` parsing (distinguishing WHEN vs FIND ... AT,
TRIG/TARG, failed measurements, and complex AC output).
"""
from __future__ import annotations

import hashlib
import itertools
import json
import math
import os
import re
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any, Callable

NUMBER = r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?"
NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,40}$")
ALLOWED_DOTS = {
    ".param", ".model", ".subckt", ".ends", ".func", ".options", ".option", ".temp",
    ".ic", ".nodeset", ".save", ".tran", ".ac", ".dc", ".op", ".meas", ".measure", ".end",
}


def finite(value: Any) -> float:
    n = float(value)
    if not math.isfinite(n):
        raise ValueError("Numeric values must be finite.")
    return n


def extract_meas_kinds(netlist: str) -> dict[str, str]:
    """
    Inspects `.meas` / `.measure` definitions in a SPICE netlist and classifies each
    measurement name as 'when', 'find', 'trig_targ', or 'scalar'.
    """
    kinds: dict[str, str] = {}
    for raw in netlist.replace("\r", "").splitlines():
        line = raw.strip()
        if not line or line.startswith("*"):
            continue
        parts = line.split()
        if len(parts) < 4 or parts[0].lower() not in (".meas", ".measure"):
            continue
        mname = parts[2].lower()
        rest = " ".join(parts[3:]).upper()
        if re.search(r"\bFIND\b", rest):
            kinds[mname] = "find"
        elif re.search(r"\bWHEN\b", rest):
            kinds[mname] = "when"
        elif re.search(r"\bTRIG\b", rest) and re.search(r"\bTARG\b", rest):
            kinds[mname] = "trig_targ"
        else:
            kinds[mname] = "scalar"
    return kinds


def validate_netlist(text: str) -> list[str]:
    """Validates a single-file SPICE netlist for local bounded simulation."""
    if not isinstance(text, str) or not text.strip() or len(text) > 100_000:
        raise ValueError("Netlist must be a non-empty string under 100,000 chars.")
    if "\x00" in text:
        raise ValueError("Null bytes are not allowed in netlists.")
    lines = text.replace("\r", "").splitlines()
    if len(lines) > 2000:
        raise ValueError("Netlist exceeds maximum 2,000 lines.")
    if not lines[0].strip() or lines[0].lstrip().startswith("."):
        raise ValueError("First line must be a circuit title or * comment.")
    analyses = 0
    measures: list[str] = []
    has_end = False
    for line in lines[1:]:
        s = line.strip()
        if not s or s.startswith("*"):
            continue
        if any(c in s for c in ("`", "$", "\\")):
            raise ValueError("Shell substitution or external path characters (` $ \\) are forbidden.")
        token = s.split()[0].lower()
        if token.startswith("."):
            if token not in ALLOWED_DOTS:
                raise ValueError(f"Unsupported directive '{token}'. Inline models and remove .control/.include/.lib/.step.")
            if token in (".tran", ".ac", ".dc", ".op"):
                analyses += 1
            if token in (".meas", ".measure"):
                parts = s.split()
                if len(parts) < 4 or parts[1].lower() not in ("tran", "ac", "dc") or not NAME.fullmatch(parts[2]):
                    raise ValueError(f"Invalid .meas syntax: {s}")
                measures.append(parts[2].lower())
            if token == ".end":
                has_end = True
        elif s[0] != "+" and s[0].upper() not in "RCLVIDQMBEGFHXKSWT":
            raise ValueError(f"Unsupported SPICE element/statement: {token}")
        if re.search(r"\b(?:file|pwlfile|load|source|shell)\s*=", s, re.I):
            raise ValueError("External file references are not permitted in single-file sweep mode.")
    if analyses != 1:
        raise ValueError("Exactly one analysis (.tran, .ac, .dc, or .op) is required per sweep deck.")
    if not measures:
        raise ValueError("At least one .meas statement is required.")
    if len(measures) != len(set(measures)):
        raise ValueError("Duplicate .meas names are not allowed.")
    if not has_end:
        raise ValueError("Missing trailing .end statement.")
    return measures


def validate_project(netlist: str, settings: dict[str, Any]) -> dict[str, Any]:
    """Validates sweep parameters, pass/fail goals, and optimization objective."""
    measures = validate_netlist(netlist)
    s = json.loads(json.dumps(settings, allow_nan=False))
    params = s.get("parameters", [])
    if not 1 <= len(params) <= 6:
        raise ValueError("Optimization parameters must have 1 to 6 entries.")
    seen: set[str] = set()
    for p in params:
        n = p.get("name", "")
        if not NAME.fullmatch(n) or n.lower() in seen:
            raise ValueError(f"Invalid or duplicate parameter name: {n}")
        seen.add(n.lower())
        for k in ("min", "max", "initial", "step"):
            p[k] = finite(p[k])
        if not p["min"] < p["max"] or not p["min"] <= p["initial"] <= p["max"] or p["step"] <= 0:
            raise ValueError(f"{n}: invalid min/max/initial/step bounds.")
        pattern = r"(?im)^\s*\.param\s+" + re.escape(n) + r"\s*=\s*([^\n;]+)"
        hits = re.findall(pattern, netlist)
        if len(hits) != 1 or re.search(r"\s\w+\s*=", hits[0]):
            raise ValueError(f"Declare '.param {n}=<value>' on its own line once.")
    goals = s.get("goals", [])
    if not 1 <= len(goals) <= 12:
        raise ValueError("Goals must have 1 to 12 entries.")
    for g in goals:
        g["measure"] = str(g.get("measure", "")).lower()
        if g["measure"] not in measures or g.get("op") not in (">=", "<="):
            raise ValueError("Each goal must reference a defined .meas name with op '>=' or '<='.")
        g["value"] = finite(g["value"])
    obj = s.get("objective", {})
    obj["measure"] = str(obj.get("measure", "")).lower()
    if obj["measure"] not in measures or obj.get("sense") not in ("min", "max"):
        raise ValueError("Objective must reference a defined .meas name with sense 'min' or 'max'.")
    s["max_runs"] = int(s.get("max_runs", 32))
    s["timeout_s"] = finite(s.get("timeout_s", 20))
    if not 1 <= s["max_runs"] <= 128 or not 1 <= s["timeout_s"] <= 60:
        raise ValueError("max_runs must be 1..128 and timeout_s must be 1..60.")
    if s.get("method") not in ("single", "grid", "feedback"):
        raise ValueError("method must be 'single', 'grid', or 'feedback'.")
    return s


def resolve_simulator(config: dict[str, Any] | None = None) -> tuple[str, str]:
    """Resolves either LTspice or ngspice executable path."""
    cfg = config or {}
    engine = str(cfg.get("simulator") or ("ltspice" if os.name == "nt" else "ngspice")).lower()
    if engine not in ("ngspice", "ltspice"):
        raise ValueError("simulator must be 'ngspice' or 'ltspice'.")
    explicit = str(cfg.get("simulator_path", "")).strip()
    if explicit:
        path = Path(explicit).expanduser()
        if not path.is_file():
            raise ValueError(f"Configured simulator_path not found: {explicit}")
        return engine, str(path.resolve())
    if engine == "ngspice":
        candidates = [
            os.environ.get("EDAI_NGSPICE"),
            shutil.which("ngspice"),
            shutil.which("ngspice_con"),
            r"C:\Spice64\bin\ngspice_con.exe",
            r"C:\Spice64\bin\ngspice.exe",
        ]
    else:
        candidates = [
            os.environ.get("LTSPICE_EXE"),
            str(Path(os.environ.get("LOCALAPPDATA", "")) / "Programs/ADI/LTspice/LTspice.exe"),
            r"C:\Program Files\ADI\LTspice\LTspice.exe",
            r"C:\Program Files\LTC\LTspiceXVII\XVIIx64.exe",
            shutil.which("LTspice"),
        ]
    for p in candidates:
        if p and Path(p).is_file():
            return engine, str(Path(p).resolve())
    raise ValueError(f"Could not locate {engine} executable. Set simulator_path in config.")


def render_netlist(source: str, params: dict[str, float]) -> str:
    text = source
    for n, v in params.items():
        pat = r"(?im)^(\s*\.param\s+" + re.escape(n) + r"\s*=\s*)[^\n;]+"
        text, count = re.subn(pat, lambda m: m.group(1) + format(v, ".12g"), text)
        if count != 1:
            raise ValueError(f"Failed to substitute parameter {n}")
    return text


def read_text(path: Path) -> str:
    b = Path(path).read_bytes()
    if b.startswith((b"\xff\xfe", b"\xfe\xff")) or b[:200].count(b"\0") > 20:
        return b.decode("utf-16", errors="replace")
    return b.decode("utf-8", errors="replace")


def parse_measurements(
    log: str,
    names: list[str],
    *,
    netlist_source: str | None = None,
    meas_kinds: dict[str, str] | None = None,
) -> dict[str, float]:
    """
    Parses `.meas` output values from LTspice/ngspice logs.

    P0 Fix: Distinguishes `WHEN` (returns X-axis value after `AT`) from `FIND ... AT`
    (returns Y-axis value after `=`), rejects failed measurements (`Measurement ... FAIL'ED`),
    and skips complex `(dB, deg)` pairs rather than silently corrupting scalar metrics.
    """
    kinds = dict(meas_kinds or {})
    if netlist_source:
        for k, v in extract_meas_kinds(netlist_source).items():
            kinds.setdefault(k, v)

    result: dict[str, float] = {}
    for name in names:
        key = name.lower()
        kind = kinds.get(key)
        line_pat = re.compile(r"(?im)^\s*" + re.escape(name) + r"(?:\s*:([^\r\n]*)|(\s*=[^\r\n]*))")
        m = line_pat.search(log)
        if not m:
            continue
        full_line = m.group(0)
        if re.search(r"\bFAIL(?:ED|'ED)?\b", full_line, re.I):
            continue
        # Reject complex AC log formats like `(20.1dB, -45.2deg)`
        if re.search(r"\([^)]*dB[^)]*,[^)]*\)", full_line, re.I):
            continue

        val_str: str | None = None
        if kind == "when":
            m_at = re.search(r"\bAT\s*=?\s*(" + NUMBER + r")(?=\s|$)", full_line, re.I)
            if m_at:
                val_str = m_at.group(1)
        elif kind == "find":
            m_eq = re.search(r"=\s*(" + NUMBER + r")(?=\s|$)", full_line)
            if m_eq:
                val_str = m_eq.group(1)
        else:
            # Auto-detect when netlist_source was not supplied:
            # LTspice WHEN prints `<name>: <expr>=<threshold> AT <event_time>`.
            m_when_auto = re.search(
                r":\s*[A-Za-z_][A-Za-z0-9_]*\([^)]*\)\s*=\s*" + NUMBER + r"\s+AT\s*=?\s*(" + NUMBER + r")(?=\s|$)",
                full_line,
                re.I,
            )
            if m_when_auto and kind is None:
                val_str = m_when_auto.group(1)
            else:
                m_eq = re.search(r"(?::[^\r\n=]*)?=\s*(" + NUMBER + r")(?=\s|$)", full_line)
                if m_eq:
                    val_str = m_eq.group(1)

        if val_str is not None:
            v = float(val_str)
            if math.isfinite(v):
                result[key] = v
    return result


def parse_raw(path: Path, limit: int = 900) -> dict[str, Any] | None:
    path = Path(path)
    if not path.exists() or path.stat().st_size > 40_000_000:
        return None
    text = read_text(path)
    if "Values:" not in text or re.search(r"Flags:.*complex", text):
        return None
    sections = text.split("Values:", 1)
    if "Variables:" not in sections[0]:
        return None
    variables: list[str] = []
    for line in sections[0].split("Variables:", 1)[1].splitlines():
        m = re.match(r"\s*\d+\s+(\S+)\s+(\S+)", line)
        if m:
            variables.append(m.group(1))
    n = len(variables)
    if n < 2 or n > 200:
        return None
    data: list[list[float]] = []
    point: list[float] = []
    for line in sections[1].splitlines():
        fields = line.split()
        if not fields:
            continue
        try:
            point.append(float(fields[-1]))
        except ValueError:
            continue
        if len(point) == n:
            if all(math.isfinite(x) for x in point):
                data.append(point)
            point = []
    if not data:
        return None
    stride = max(1, math.ceil(len(data) / limit))
    sample = data[::stride]
    if sample[-1] != data[-1]:
        sample.append(data[-1])
    return {"variables": variables, "points": sample, "total_points": len(data), "decimated": stride > 1}


def run_spice(
    source: str,
    params: dict[str, float],
    config: dict[str, Any],
    folder: Path,
    timeout: float = 20.0,
    cancel: Any = None,
) -> dict[str, Any]:
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=False)
    names = validate_netlist(source)
    engine, exe = resolve_simulator(config)
    clean = render_netlist(source, params)
    (folder / "circuit.cir").write_text(clean, encoding="utf-8")
    actual = clean
    if engine == "ngspice":
        control = ".control\nset filetype=ascii\nrun\nwrite waveform.raw all\nquit\n.endc\n.end"
        actual = re.sub(r"(?im)^\s*\.end\s*(?:;[^\n]*)?$", lambda _m: control, clean)
        (folder / "execute.cir").write_text(actual, encoding="utf-8")
        cmd = [exe, "-n", "-b", "-o", "simulation.log", "execute.cir"]
    else:
        cmd = [exe, "-b", "-ascii", str((folder / "circuit.cir").resolve())]

    started = time.monotonic()
    failure: str | None = None
    with (folder / "console.log").open("wb") as out:
        proc = subprocess.Popen(
            cmd,
            cwd=folder,
            stdout=out,
            stderr=subprocess.STDOUT,
            shell=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0,
        )
        while proc.poll() is None:
            if cancel and cancel.is_set():
                failure = "cancelled"
            elif time.monotonic() - started > timeout:
                failure = "timeout"
            elif sum(p.stat().st_size for p in folder.iterdir() if p.is_file()) > 100_000_000:
                failure = "output_limit"
            if failure:
                proc.terminate()
                try:
                    proc.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()
                break
            time.sleep(0.04)

    log = "\n".join(read_text(p) for p in [folder / "simulation.log", folder / "circuit.log", folder / "console.log"] if p.exists())
    metrics = parse_measurements(log, names, netlist_source=clean)
    if not failure and proc.returncode != 0:
        failure = "simulator_error"
    raw = folder / ("waveform.raw" if engine == "ngspice" else "circuit.raw")
    waveform = parse_raw(raw)
    return {
        "engine": engine,
        "parameters": params,
        "metrics": metrics,
        "error": failure,
        "returncode": proc.returncode,
        "elapsed_s": round(time.monotonic() - started, 3),
        "source_sha256": hashlib.sha256(clean.encode()).hexdigest(),
        "executed_sha256": hashlib.sha256(actual.encode()).hexdigest(),
        "log_tail": log[-14000:],
        "waveform": waveform,
        "directory": folder.name,
    }


def assess(result: dict[str, Any], settings: dict[str, Any]) -> tuple[float, float]:
    checks: list[dict[str, Any]] = []
    missing: list[str] = []
    violation = 0.0
    for goal in settings["goals"]:
        m = goal["measure"]
        actual = result["metrics"].get(m)
        target = goal["value"]
        passed = actual is not None and (actual >= target if goal["op"] == ">=" else actual <= target)
        if actual is None:
            missing.append(m)
        else:
            violation += max(0.0, (target - actual) if goal["op"] == ">=" else (actual - target)) / max(abs(target), 1e-9)
        checks.append({**goal, "actual": actual, "passed": passed})
    objective = result["metrics"].get(settings["objective"]["measure"])
    if objective is None:
        missing.append(settings["objective"]["measure"])
    valid = not result["error"] and not missing
    rank = (violation, objective if settings["objective"]["sense"] == "min" else -objective) if valid else (math.inf, math.inf)
    result.update({
        "checks": checks,
        "valid": valid,
        "feasible": valid and all(c["passed"] for c in checks),
        "violation": violation if valid else None,
        "missing_measures": sorted(set(missing)),
    })
    if not valid:
        result["feedback"] = "Measurement/run failed: " + (", ".join(sorted(set(missing))) or str(result["error"]))
    elif result["feasible"]:
        result["feedback"] = "All goals satisfied; comparing objective metric."
    else:
        result["feedback"] = " | ".join(
            f"{c['measure']}={c['actual']:.5g} (target {c['op']} {c['value']:.5g})" for c in checks if not c["passed"]
        )
    return rank


def grid_values(p: dict[str, Any]) -> list[float]:
    count = math.floor((p["max"] - p["min"]) / p["step"] + 1e-8) + 1
    if count > 2000:
        raise ValueError("Grid step too small (>2000 points per variable). Use 'feedback' method.")
    return sorted(set([round(p["min"] + i * p["step"], 12) for i in range(count)] + [p["initial"], p["max"]]))


def optimize(
    source: str,
    settings: dict[str, Any],
    config: dict[str, Any],
    folder: Path | str,
    on_result: Callable[[dict[str, Any], dict[str, Any] | None], None] = lambda _r, _b: None,
    cancel: Any = None,
) -> dict[str, Any]:
    """Runs bounded single/grid/coordinate-descent parameter sweep in LTspice or ngspice."""
    s = validate_project(source, settings)
    engine, _ = resolve_simulator(config)
    out_folder = Path(folder)
    out_folder.mkdir(parents=True, exist_ok=True)
    (out_folder / "project.json").write_text(json.dumps({"netlist": source, "settings": s}, ensure_ascii=False, indent=2), encoding="utf-8")

    specs = s["parameters"]
    start = {p["name"]: p["initial"] for p in specs}
    history: list[dict[str, Any]] = []
    seen: set[tuple[float, ...]] = set()
    best: dict[str, Any] | None = None
    best_rank = (math.inf, math.inf)

    def evaluate(params: dict[str, float], reason: str) -> bool:
        nonlocal best, best_rank
        key = tuple(round(params[p["name"]], 12) for p in specs)
        if key in seen or len(history) >= s["max_runs"] or (cancel and cancel.is_set()):
            return False
        seen.add(key)
        index = len(history)
        r = run_spice(source, dict(params), config, out_folder / f"run_{index:03d}", s["timeout_s"], cancel)
        r["iteration"] = index
        r["reason"] = reason
        rank = assess(r, s)
        improved = rank < best_rank
        if improved:
            best_rank = rank
            best = r
        r["new_best"] = improved
        history.append(r)
        (out_folder / f"run_{index:03d}" / "result.json").write_text(json.dumps(r, ensure_ascii=False, indent=2), encoding="utf-8")
        on_result(r, best)
        return improved

    if s["method"] == "grid":
        values = [grid_values(p) for p in specs]
        size = math.prod(len(v) for v in values)
        if size > s["max_runs"]:
            raise ValueError(f"Grid combinations ({size}) exceed max_runs ({s['max_runs']}).")
        evaluate(start, "Initial design")
        for vals in itertools.product(*values):
            evaluate(dict(zip(start, vals)), "Grid candidate")
    else:
        evaluate(start, "Initial design")
        steps = {p["name"]: p["step"] for p in specs}
        for _cycle in range(24):
            if s["method"] == "single" or len(history) >= s["max_runs"] or (cancel and cancel.is_set()):
                break
            center = dict(best["parameters"] if best else start)
            improved = False
            for p in specs:
                n = p["name"]
                for sign in (1, -1):
                    trial = dict(center)
                    trial[n] = round(min(p["max"], max(p["min"], center[n] + sign * steps[n])), 12)
                    improved = evaluate(trial, f"Sweep {n}: {center[n]:.6g} -> {trial[n]:.6g}") or improved
            if not improved:
                steps = {n: v / 2.0 for n, v in steps.items()}
                if all(steps[p["name"]] < p["step"] / 16.0 for p in specs):
                    break

    best_netlist = (out_folder / best["directory"] / "circuit.cir").read_text(encoding="utf-8") if best else None
    if best:
        shutil.copyfile(out_folder / best["directory"] / "circuit.cir", out_folder / "best.cir")

    summary = {
        "schema_version": "edai-spice-loop-1.0",
        "kind": "actual_spice_runs",
        "settings": s,
        "engine": engine,
        "runs": history,
        "best_iteration": best["iteration"] if best else None,
        "best_netlist": best_netlist,
        "feasible_count": sum(1 for r in history if r["feasible"]),
        "cancelled": bool(cancel and cancel.is_set()),
    }
    (out_folder / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary
