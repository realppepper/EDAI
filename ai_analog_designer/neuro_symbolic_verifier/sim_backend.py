"""
Simulator backend switch (EDAI ngspice port).

All deterministic testbenches in this package are written in LTspice syntax and read back from an LTspice-style
``.log`` (``parse_meas_log`` / ``ltspice_errors``). ``run_spice`` keeps that contract:

    AV_SIMULATOR=ltspice  -> run LTspice as before
    AV_SIMULATOR=ngspice  -> translate the deck to ngspice, run ngspice (optionally inside WSL),
                             then write an LTspice-style ``<deck>.log`` so every existing parser keeps working.

ngspice uses the original GF180MCU PDK models (BSIM4 via the PDK subcircuits ``nfet_06v0`` / ``pfet_06v0``)
instead of the LTspice level-14 conversion (``*_bsim0``).

Environment
    AV_SIMULATOR   ltspice | ngspice                      (default: ngspice on this branch)
    AV_NGSPICE     ngspice executable. Prefix ``wsl:`` to run it inside WSL (default: wsl:~/ngspice/bin/ngspice)
    AV_PDK_DIR     GF180 ngspice model folder as the simulator sees it
                   (default: ~/pdk/gf180mcu_fd_pr/models/ngspice inside WSL)
"""
from __future__ import annotations

import math
import os
import re
import subprocess

SIMULATOR = os.environ.get("AV_SIMULATOR", "ngspice").lower()
NGSPICE = os.environ.get("AV_NGSPICE", "wsl:~/ngspice/bin/ngspice")
PDK_DIR = os.environ.get("AV_PDK_DIR", "~/pdk/gf180mcu_fd_pr/models/ngspice")

# LTspice level-14 GF180 conversion (EDAI ltspice_models.py) and the PDK device names it stands for
_GF180_MODEL = re.compile(r"^(nfet|pfet)_(03v3|06v0)(_bsim\d+)?$", re.I)
_LTSPICE_GF180_LIB = re.compile(r"gf180.*\.lib", re.I)
_KEEP_OPTIONS = {"reltol", "abstol", "vntol", "gmin", "itl1", "itl2", "itl4", "method", "chgtol", "trtol"}
_NUM = r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?"
_KEYWORDS = ("from", "to", "at", "td", "rise", "fall", "cross", "val")


# ---------------------------------------------------------------- paths
def _wsl() -> bool:
    return NGSPICE.startswith("wsl:")


def _to_sim_path(path: str) -> str:
    """Windows path -> path the simulator sees (``/mnt/d/...`` inside WSL)."""
    if not _wsl():
        return path
    p = os.path.abspath(path).replace("\\", "/")
    m = re.match(r"^([A-Za-z]):/(.*)$", p)
    return f"/mnt/{m.group(1).lower()}/{m.group(2)}" if m else p


def _pdk_lines() -> list[str]:
    d = PDK_DIR.rstrip("/")
    return [f".include {d}/design.ngspice", f".lib {d}/sm141064.ngspice typical"]


# ---------------------------------------------------------------- deck translation
def _meas_expr(expr: str, ac: bool, diffs: list[str]) -> str:
    """LTspice expression -> ngspice measure vector. V(a,b) becomes a unity VCVS node (ngspice measure takes one node)."""
    def diff(m):
        a, b = m.group(1).strip(), m.group(2).strip()
        node = f"__d{len(diffs)}"
        diffs.append(f"E{node} {node} 0 {a} {b} 1")
        return f"V({node})"
    expr = re.sub(r"V\(\s*([^,()]+)\s*,\s*([^()]+?)\s*\)", diff, expr, flags=re.I)
    if ac:
        expr = re.sub(r"mag\(\s*V\(([^()]+)\)\s*\)", r"vm(\1)", expr, flags=re.I)
        expr = re.sub(r"db\(\s*V\(([^()]+)\)\s*\)", r"vdb(\1)", expr, flags=re.I)
        expr = re.sub(r"ph(?:ase)?\(\s*V\(([^()]+)\)\s*\)", r"vp(\1)", expr, flags=re.I)
    return expr


def _kw(tokens: list[str]) -> str:
    """'FROM 1 TO 2 RISE=1' -> 'from=1 to=2 rise=1'."""
    out, i = [], 0
    while i < len(tokens):
        t = tokens[i]
        low = t.lower()
        if low in _KEYWORDS and i + 1 < len(tokens) and tokens[i + 1] != "=":
            out.append(f"{low}={tokens[i + 1]}")
            i += 2
            continue
        m = re.match(r"^([A-Za-z]+)=(.*)$", t)
        if m and m.group(1).lower() in _KEYWORDS:
            out.append(f"{m.group(1).lower()}={m.group(2)}")
        else:
            out.append(t)
        i += 1
    return " ".join(out)


def _translate_meas(line: str, diffs: list[str], complex_names: dict[str, str]) -> list[str]:
    """One LTspice .meas line -> ngspice .meas line(s). AC FIND of a complex V() becomes a dB and a phase measure."""
    m = re.match(r"^\.meas(?:ure)?\s+(\w+)\s+(\w+)\s+(.*)$", line.strip(), re.I)
    if not m:
        return [line]
    kind, name, rest = m.group(1).lower(), m.group(2), m.group(3)
    ac = kind == "ac"
    rest = re.sub(r"\s*=\s*", "=", rest)
    # split "FIND <expr> WHEN <expr>=v ..." / "<FUNC> <expr> FROM.." keeping parentheses together
    tokens = re.findall(r"\S+\([^()]*(?:\([^()]*\)[^()]*)*\)\S*|\S+", rest)
    head = tokens[0].upper() if tokens else ""
    if ac and head == "FIND" and len(tokens) > 1 and re.fullmatch(r"V\([^()]+\)", tokens[1], re.I):
        node = _meas_expr(tokens[1], True, diffs)[2:-1]
        tail = _kw([_meas_expr(t, True, diffs) for t in tokens[2:]])
        complex_names[name.lower()] = "ac"
        return [f".meas ac {name}__db find vdb({node}) {tail}", f".meas ac {name}__ph find vp({node}) {tail}"]
    if kind == "noise":
        complex_names[name.lower()] = "noise"
        expr = tokens[1] if len(tokens) > 1 else ""
        vec = "inoise_spectrum" if "inoise" in expr.lower() else "onoise_spectrum"
        at = _kw(tokens[2:])
        complex_names[name.lower() + "__noise"] = f"{vec} {at}"
        return []                                      # handled in the .control block
    parts = [_meas_expr(t, ac, diffs) for t in tokens]
    return [f".meas {kind} {name} {_kw(parts)}"]


def _tran(line: str) -> str:
    t = line.split()
    args = [a for a in t[1:] if a.lower() not in ("startup", "uic", "steady", "nodiscard")]
    uic = " uic" if any(a.lower() == "uic" for a in t[1:]) else ""
    if len(args) == 1:
        return f".tran {_div(args[0], 1000)} {args[0]}{uic}"
    step, stop = args[0], args[1]
    start = args[2] if len(args) > 2 else "0"
    tmax = args[3] if len(args) > 3 else None
    if _val(step) == 0:
        step = tmax or _div(stop, 1000)
    return f".tran {step} {stop} {start}" + (f" {tmax}" if tmax else "") + uic


def _val(s: str) -> float:
    mult = {"f": 1e-15, "p": 1e-12, "n": 1e-9, "u": 1e-6, "µ": 1e-6, "m": 1e-3, "k": 1e3, "meg": 1e6, "g": 1e9, "t": 1e12}
    m = re.match(r"^([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)(meg|[fpnuµmkgt])?", s.strip().lower())
    if not m:
        return float("nan")
    return float(m.group(1)) * mult.get(m.group(2) or "", 1.0)


def _div(s: str, n: float) -> str:
    return f"{_val(s) / n:.6g}"


def translate(text: str) -> tuple[str, dict[str, str]]:
    """LTspice deck -> (ngspice deck, measures that need special read-back)."""
    lines = text.splitlines()
    out, diffs, special = [lines[0] if lines else "* deck"], [], {}
    noise_cmd = None
    # GF180 이름(nfet_06v0_bsim0 등)을 쓴 소자는 항상 PDK 원본 모델로 돌린다. 하네스 LLM 이 모델 파일 줄을 빼고
    # 같은 이름을 간단한 레벨 1 .model 로 정의한 회로도 있어서, PDK 를 안 넣은 회로에는 PDK 를 넣어 준다
    # (넣지 않으면 'unknown subckt' 로 멈춤: LM358B·LM324B, 2026-11-23). 그런 .model 줄은 쓰이지 않고 남는다
    pdk_added = needs_pdk = False
    for raw in lines[1:]:
        s = raw.strip()
        low = s.lower()
        if not s:
            out.append(raw)
            continue
        if low.startswith(".option"):
            kept = [t for t in s.split()[1:] if t.split("=")[0].lower() in _KEEP_OPTIONS]
            if kept:
                out.append(".options " + " ".join(kept))
            continue
        if low.startswith((".backanno", ".save", ".probe", ".plot", ".step", ".wave", ".net ")):
            continue
        if low.startswith((".include", ".inc ", ".lib")):
            m = re.match(r'^\.(?:include|inc|lib)\s+"?([^"\s]+)"?\s*(\S*)', s, re.I)
            path = m.group(1) if m else ""
            if _LTSPICE_GF180_LIB.search(os.path.basename(path)):
                out += _pdk_lines()                      # the LTspice conversion -> original PDK models
                pdk_added = True
                continue
            section = m.group(2) if m else ""
            kw = ".lib" if low.startswith(".lib") else ".include"
            out.append(f"{kw} {_to_sim_path(path)}" + (f" {section}" if section else ""))
            continue
        if low.startswith(".meas"):
            out += _translate_meas(s, diffs, special)
            continue
        if low.startswith(".tran"):
            out.append(_tran(s))
            continue
        if low.startswith(".noise"):
            noise_cmd = re.sub(r"^\.noise", "noise", s, flags=re.I)
            continue
        if low == ".end":
            continue
        tok = s.split()
        if tok[0][0] in "Mm" and len(tok) >= 6 and _GF180_MODEL.match(tok[5]):
            needs_pdk = True
            base = _GF180_MODEL.match(tok[5])
            model = f"{base.group(1).lower()}_{base.group(2)}"
            out.append(" ".join(["X" + tok[0]] + tok[1:5] + [model] + tok[6:]))
            continue
        out.append(raw)
    if needs_pdk and not pdk_added:                  # GF180 이름을 썼는데 모델 파일을 안 넣은 회로: PDK 를 넣어 줌
        out[1:1] = _pdk_lines()
    out += diffs
    if noise_cmd:
        # ngspice needs an AC value on the noise input source (LTspice does not)
        src = noise_cmd.split()[2] if len(noise_cmd.split()) > 2 else ""
        for i, line in enumerate(out):
            t = line.split()
            if t and t[0].lower() == src.lower() and not re.search(r"ac", line, re.I):
                out[i] = line + " AC 1"
        # ngspice .meas does not work on the noise plot: print the spectrum and interpolate in _write_log
        ctl = [".control", noise_cmd, "setplot noise1"]
        for name, how in special.items():
            if name.endswith("__noise"):
                vec, at = how.split(" ", 1)
                f = re.search(r"at=(\S+)", at)
                ctl += [f"echo __NOISE_BEGIN {name[:-7]} {_val(f.group(1)) if f else 1e3}",
                        f"print frequency {vec}", "echo __NOISE_END"]
        ctl.append(".endc")
        out += ctl
    else:
        # plain batch mode does not keep AC vectors for .meas ("no such vector as v(out)"); run from .control instead
        out += [".control", "run", ".endc"]
    out.append(".end")
    return "\n".join(out) + "\n", special


# ---------------------------------------------------------------- run + LTspice-style log
_NG_ERR = re.compile(r"(?i)(^\s*error\b|singular matrix|timestep too small|no convergence|could not find|"
                     r"unknown subckt|unknown model|undefined|syntax error|simulation\(s\) aborted|"
                     r"doanalyses:|iteration limit)")


def _write_log(log_path: str, stdout: str, special: dict[str, str]) -> None:
    vals: dict[str, float] = {}
    not_meas = {"stack", "temp", "tnom"}          # ngspice status lines that look like "name = value"
    for line in stdout.splitlines():
        m = re.match(rf"^\s*([A-Za-z_]\w*)\s*=\s*({_NUM})", line)
        if m and m.group(1).lower() not in not_meas:
            vals[m.group(1).lower()] = float(m.group(2))
    # noise spectra printed between __NOISE_BEGIN <name> <f> / __NOISE_END: log-log interpolation at f
    for block in re.finditer(r"__NOISE_BEGIN (\w+) (\S+)(.*?)__NOISE_END", stdout, re.S):
        name, f0 = block.group(1).lower(), float(block.group(2))
        pts = [(float(a), float(b)) for a, b in re.findall(rf"^\s*\d+\s+({_NUM})\s+({_NUM})", block.group(3), re.M)]
        for (fa, va), (fb, vb) in zip(pts, pts[1:]):
            if fa <= f0 <= fb and fa > 0 and va > 0 and vb > 0:
                w = (math.log(f0) - math.log(fa)) / (math.log(fb) - math.log(fa)) if fb > fa else 0.0
                vals[name] = math.exp(math.log(va) + w * (math.log(vb) - math.log(va)))
                break
    lines = ["ngspice (EDAI AV_SIMULATOR=ngspice)"]
    done = set()
    for name, kind in special.items():
        if kind == "ac" and f"{name}__db" in vals and f"{name}__ph" in vals:
            lines.append(f"{name}: V()=({vals[name + '__db']}dB,{math.degrees(vals[name + '__ph'])}°)")
            done |= {f"{name}__db", f"{name}__ph"}
    for name, v in vals.items():
        if name not in done and not name.endswith(("__db", "__ph")):
            lines.append(f"{name}: v={v}")
    # .four: ngspice "Fourier analysis for v(x): ... THD: t %" + (harm, freq, mag, phase, norm.mag, norm.phase)
    #        -> LTspice "Fourier components of V(x)", "DC component:", (harm, freq, mag, norm.mag, phase, norm.phase), THD
    for four in re.finditer(r"Fourier analysis for (\S+?):.*?THD:\s*(" + _NUM + r")\s*%(.*?)(?=Fourier analysis for|\Z)", stdout, re.S):
        table_text = four.group(3).split("Norm. Phase", 1)[-1]
        rows = []
        for ln in table_text.splitlines():
            m = re.match(rf"^\s*(\d+)\s+({_NUM})\s+({_NUM})\s+({_NUM})\s+({_NUM})\s+({_NUM})\s*$", ln)
            if m:
                rows.append(m.groups())
            elif rows and ln.strip():
                break
        lines.append(f"Fourier components of {four.group(1).upper().replace('V(', 'V(')}")
        dc = next((r[2] for r in rows if r[0] == "0"), "0")
        lines.append(f"DC component:{dc}")
        lines.append("Harmonic\tFrequency\tFourier\tNormalized\tPhase\tNormalized")
        for h, f, mag, ph, nmag, nph in rows:
            if h != "0":
                lines.append(f"    {h}\t{f}\t{mag}\t{nmag}\t{ph}\t{nph}")
        lines.append(f"Total Harmonic Distortion: {four.group(2)}%({four.group(2)}%)")
    for line in stdout.splitlines():
        low = line.lower()
        if _NG_ERR.search(line) and "warning" not in low and "meas" not in low:   # a failed .meas is not a fatal error
            lines.append(f"Error: {line.strip()}")
    with open(log_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def run_spice(path: str, timeout: float, ltspice_exe: str | None = None) -> None:
    """Runs one deck. Writes ``<deck>.log`` in LTspice format. Raises subprocess.TimeoutExpired like before."""
    if SIMULATOR != "ngspice":
        subprocess.run([ltspice_exe, "-b", path], capture_output=True, text=True, timeout=timeout)
        return
    path = os.path.abspath(path)
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        text = f.read()
    ng_text, special = translate(text)
    ng_path = path[:-4] + ".ng.cir"
    with open(ng_path, "w", encoding="utf-8") as f:
        f.write(ng_text)
    exe = NGSPICE[4:] if _wsl() else NGSPICE
    if _wsl():
        cmd = ["wsl.exe", "-e", "bash", "-lc", f"{exe} -b '{_to_sim_path(ng_path)}'"]
    else:
        cmd = [exe, "-b", ng_path]
    done = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, encoding="utf-8", errors="ignore")
    out = (done.stdout or "") + "\n" + (done.stderr or "")
    with open(path[:-4] + ".ng.out", "w", encoding="utf-8") as f:
        f.write(out)
    _write_log(path[:-4] + ".log", out, special)
