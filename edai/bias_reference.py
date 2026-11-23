"""
바이어스 변환기의 기준 전류 회로: β-multiplier(정 gm 기준 전류원) + startup. GF180 6 V 소자.

    VDD ──┬────────────┬──────────────┐
         MP3(다이오드)  MP4            MS1 (아주 약함, 늘 켜짐)
          │ PB          │ NB            │ SX
         MN2 (K배)     MN1(다이오드)   MS3 (NB 가 오르면 SX 를 내림 -> startup 꺼짐)
          │ NS          │               │
         RS            VSS            VSS
          │                     MS2: PB 를 VSS 로 끌어내림 (SX 가 높을 때만) -> 고리를 켬
         VSS

    전류 I 는 RS 와 K 로 정해지고 전원 전압에 거의 무관하다 (gm1 = 2(1 - 1/√K) / RS).
    NB: NMOS 미러의 게이트 전압 (I 를 NMOS 로 복사), PB: PMOS 미러의 게이트 전압 (I 를 PMOS 로 복사).

cell(prefix) 는 회로 줄 목록과 노드 이름을 돌려준다. 변환기(bias_to_devices.py)가 이 회로를 끼워 넣고
NB/PB 에 미러 소자를 붙여 각 바이어스 단자에 전류를 나눠 준다.

자체 검사 (WSL, 프로젝트 폴더에서):
    ~/.venvs/edai/bin/python bias_reference.py
    1. RS 를 이분 탐색해 VDD = 5 V 에서 I = IREF 로 맞춤
    2. 전원 1.8 ~ 5.5 V 에서 전류 변화 (전원 무관성)
    3. 전원 켜기: VDD 를 0 -> 5 V 로 올리는 과도 해석에서 전류가 IREF 근처로 올라가는지 (startup)
결과: data/bias_reference.json (크기, RS, 검사 결과)
"""

import json
import re
import subprocess
import tempfile
from pathlib import Path

import auto_size
import run_sim

HERE = Path(__file__).resolve().parent
IREF = 10e-6                # 기준 전류 [A]
K = 4                       # MN2 / MN1 폭 비
L_UM = 2.0                  # 기준 회로 소자 길이 [um] (짝 맞춤을 위해 긴 채널)
GM_ID = 10.0                # MN1, MP3 의 gm/ID [1/V]
STARTUP_WEAK = "w=0.5u l=20u"     # MS1: 늘 켜진 아주 약한 PMOS (정상 동작 때 전류 무시할 만큼)
STARTUP_PULL = "w=2u l=1u"        # MS2
STARTUP_OFF = "w=5u l=1u"         # MS3 (MS1 보다 훨씬 강해 SX 를 확실히 내림)
VDD_NOMINAL = run_sim.OPAMP_VDD
VDD_SWEEP = (1.8, 5.5)      # 전원 무관성 검사 범위 [V]
RAMP_S = 10e-6              # 전원 켜기 시간 [s]
SETTLE_S = 50e-6            # 켠 뒤 기다리는 시간 [s]
STARTUP_OK_RATIO = 0.9      # 켠 뒤 전류가 IREF 의 이 비율 이상이면 켜진 것


def width(kind: str, current: float, scale: float = 1.0) -> str:
    s = auto_size.size_text(auto_size.width_for_current(kind, current, GM_ID, L_UM) * scale, L_UM)
    return " ".join(f"{k}={v}" for k, v in s.items())


def cell(prefix: str = "REF", rs: float = None) -> tuple:
    """(줄 목록, {"NB": 노드, "PB": 노드}). rs 를 안 주면 data/bias_reference.json 의 맞춘 값을 쓴다."""
    if rs is None:
        rs = json.loads((HERE / "data" / "bias_reference.json").read_text(encoding="utf-8"))["rs_ohm"]
    nb, pb, ns, sx = (f"{prefix}_{n}" for n in ("NB", "PB", "NS", "SX"))
    n, p = "nfet_06v0", "pfet_06v0"
    lines = [
        f"* 기준 전류 {IREF * 1e6:g} uA: beta-multiplier + startup (bias_reference.py)",
        f"X{prefix}_MN1 {nb} {nb} VSS VSS {n} {width('nmos', IREF)}",
        f"X{prefix}_MN2 {pb} {nb} {ns} VSS {n} {width('nmos', IREF, K)}",
        f"R{prefix}_S {ns} VSS {rs:.6g}",
        f"X{prefix}_MP3 {pb} {pb} VDD VDD {p} {width('pmos', IREF)}",
        f"X{prefix}_MP4 {nb} {pb} VDD VDD {p} {width('pmos', IREF)}",
        f"X{prefix}_MS1 {sx} VSS VDD VDD {p} {STARTUP_WEAK}",
        f"X{prefix}_MS2 {pb} {sx} VSS VSS {n} {STARTUP_PULL}",
        f"X{prefix}_MS3 {sx} {nb} VSS VSS {n} {STARTUP_OFF}",
    ]
    return lines, {"NB": nb, "PB": pb}


def simulate(lines: list, analysis: list, prints: list) -> str:
    deck = ["* bias_reference 검사", f".include {run_sim.PDK_DIR}/design.ngspice",
            f".lib {run_sim.PDK_DIR}/sm141064.ngspice typical", "VSS VSS 0 0"] + lines + \
           [".control", *analysis, *prints, ".endc", ".end"]
    with tempfile.NamedTemporaryFile("w", suffix=".cir", delete=False) as f:
        f.write("\n".join(deck) + "\n")
    out = subprocess.run([run_sim.NGSPICE_EXE, "-b", f.name], capture_output=True, text=True, timeout=300).stdout
    Path(f.name).unlink()
    return out


def branch_current(rs: float, vdd: float) -> float:
    """MN1 가지 전류 = MP4 전류 (VDD 에서 0 V 전압원으로 잼)."""
    lines, _ = cell("REF", rs)
    lines = [l.replace("X REF_MP4".replace(" ", ""), "XREF_MP4") for l in lines]
    lines = [re.sub(r"^(XREF_MP4 \S+ \S+) VDD VDD", r"\1 VDD_M VDD", l) for l in lines]
    out = simulate([f"VDD VDD 0 {vdd}", "VM VDD VDD_M 0"] + lines, ["op"], ["print i(VM)"])
    m = re.search(r"i\(vm\)\s*=\s*([-0-9.eE+]+)", out, re.I)
    return float(m.group(1)) if m else float("nan")


def tune_rs() -> float:
    """VDD 5 V 에서 전류가 IREF 가 되는 RS. RS 가 크면 전류가 준다."""
    gm1 = GM_ID * IREF
    lo, hi = 0.1 * 2 * (1 - K ** -0.5) / gm1, 10 * 2 * (1 - K ** -0.5) / gm1
    rs = (lo * hi) ** 0.5
    for _ in range(40):
        rs = (lo * hi) ** 0.5
        i = branch_current(rs, VDD_NOMINAL)
        if abs(i - IREF) < 0.005 * IREF:
            break
        if i > IREF:
            lo = rs
        else:
            hi = rs
    return rs


def startup(rs: float) -> dict:
    """VDD 를 0 -> 5 V 로 올린 뒤 전류."""
    lines, _ = cell("REF", rs)
    lines = [re.sub(r"^(XREF_MP4 \S+ \S+) VDD VDD", r"\1 VDD_M VDD", l) for l in lines]
    out = simulate([f"VDD VDD 0 PWL(0 0 {RAMP_S} {VDD_NOMINAL})", "VM VDD VDD_M 0"] + lines,
                   [f"tran {RAMP_S / 100} {RAMP_S + SETTLE_S} uic"],
                   [f"meas tran ifinal find i(VM) at={RAMP_S + SETTLE_S}"])
    m = re.search(r"ifinal\s*=\s*([-0-9.eE+]+)", out, re.I)
    current = float(m.group(1)) if m else float("nan")
    return {"current_a": current, "ok": current >= STARTUP_OK_RATIO * IREF}


def main() -> None:
    rs = tune_rs()
    sweep = {f"{v:g}": branch_current(rs, v) for v in (VDD_SWEEP[0], 2.5, 3.3, VDD_NOMINAL, VDD_SWEEP[1])}
    st = startup(rs)
    lines, nodes = cell("REF", rs)
    result = {"iref_a": IREF, "k": K, "l_um": L_UM, "gm_id": GM_ID, "rs_ohm": round(rs, 1),
              "current_vs_vdd": sweep, "startup": st, "lines": lines, "nodes": nodes}
    (HERE / "data" / "bias_reference.json").write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"RS = {rs:.0f} Ω (VDD {VDD_NOMINAL} V 에서 {IREF * 1e6:g} µA)")
    for v, i in sweep.items():
        print(f"  VDD {v:>4} V: {i * 1e6:7.3f} µA")
    print(f"전원 켜기 (0 -> {VDD_NOMINAL} V, {RAMP_S * 1e6:g} µs): {st['current_a'] * 1e6:.3f} µA, "
          f"{'켜짐' if st['ok'] else '안 켜짐'}")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
