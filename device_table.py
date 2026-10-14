"""
GF180MCU 6 V 소자의 특성표를 만든다 (devices_gf180.json).

소자 크기를 식으로 계산하려면 "이 공정의 트랜지스터가 gm/ID 가 얼마일 때 전류 밀도와
고유이득이 얼마인가"를 알아야 한다. 그 값을 시뮬레이션으로 한 번 재서 표로 남긴다.
sizing.py 가 이 표를 읽어 W 와 예상 성능을 계산한다.

사용법 (WSL, 프로젝트 폴더에서. 공정 모델이나 채널 길이 목록을 바꿨을 때만 다시 실행):
    ~/.venvs/edai/bin/python device_table.py

표의 내용: 소자 종류(n, p)와 채널 길이 L 마다, 게이트 전압을 훑으면서 잰
    gm_id  : gm / ID  [1/V]
    j      : ID / (W/L)  [A]  (정사각형 하나가 흘리는 전류)
    gm_gds : gm / gds  (고유이득)
    vgs, vdsat [V]
"""

import json
import subprocess
from pathlib import Path

import numpy as np
from spicelib import RawRead

import run_sim

TABLE_FILE = run_sim.HERE / "devices_gf180.json"
DEVICES = {"n": "nfet_06v0", "p": "pfet_06v0"}
LENGTHS_UM = (0.7, 1.0, 2.0, 4.0)
TEST_WIDTH = 10e-6
TEST_VDS = 1.0
VGS_SWEEP = (0.5, 2.0, 0.01)
# 표에 남기는 gm/ID 범위 (약반전 ~ 강반전)
GM_ID_RANGE = (4.0, 20.0)


def characterize(kind: str, length_um: float) -> dict:
    """소자 하나를 게이트 전압으로 훑어 gm/ID 별 특성을 잰다."""
    sign = 1 if kind == "n" else -1
    start, stop, step = (sign * v for v in VGS_SWEEP)
    netlist = f"""* 소자 특성 측정: {DEVICES[kind]} L={length_um}u
.include {run_sim.PDK_DIR}/design.ngspice
.lib {run_sim.PDK_DIR}/sm141064.ngspice typical
VD d 0 {sign * TEST_VDS}
VG g 0 0
XM1 d g 0 0 {DEVICES[kind]} w={TEST_WIDTH} l={length_um}u
.save all @m.xm1.m0[gm] @m.xm1.m0[gds] @m.xm1.m0[vdsat]
.dc VG {start} {stop} {step}
.end
"""
    path = run_sim.OUT_DIR / f"_char_{kind}_{length_um}.cir"
    path.write_text(netlist, encoding="utf-8")
    raw_path = path.with_suffix(".raw")
    subprocess.run([run_sim.NGSPICE_EXE, "-b", "-r", str(raw_path), "-o", str(path.with_suffix(".log")), str(path)],
                   capture_output=True, text=True, check=True)
    raw = RawRead(str(raw_path), traces_to_read="*", dialect="ngspice")

    def wave(name: str) -> np.ndarray:
        return np.abs(np.real(np.array(raw.get_trace(name).get_wave())))

    vgs = np.abs(np.real(np.array(raw.get_axis())))
    current, gm, gds = wave("i(vd)"), wave("@m.xm1.m0[gm]"), wave("@m.xm1.m0[gds]")
    vdsat = wave("v(@m.xm1.m0[vdsat])")
    gm_id = gm / current
    keep = (gm_id >= GM_ID_RANGE[0]) & (gm_id <= GM_ID_RANGE[1])
    order = np.argsort(gm_id[keep])
    squares = TEST_WIDTH / (length_um * 1e-6)
    for leftover in (path, raw_path, path.with_suffix(".log")):
        leftover.unlink(missing_ok=True)
    return {
        "gm_id": [float(v) for v in gm_id[keep][order]],
        "j": [float(v) for v in (current / squares)[keep][order]],
        "gm_gds": [float(v) for v in (gm / gds)[keep][order]],
        "vgs": [float(v) for v in vgs[keep][order]],
        "vdsat": [float(v) for v in vdsat[keep][order]],
    }


def build_table() -> dict:
    table = {
        "process": "GF180MCU 6 V (typical, 27°C)",
        "condition": f"W = {TEST_WIDTH * 1e6:g} um, |Vds| = {TEST_VDS} V",
        "lengths_um": list(LENGTHS_UM),
        "devices": {},
    }
    for kind in DEVICES:
        table["devices"][kind] = {str(length): characterize(kind, length) for length in LENGTHS_UM}
    return table


def load_table() -> dict:
    """특성표를 읽는다. 없으면 만드는 방법을 알려준다."""
    if not TABLE_FILE.exists():
        raise FileNotFoundError(f"{TABLE_FILE.name} 이 없습니다. `python device_table.py` 를 먼저 실행하세요.")
    return json.loads(TABLE_FILE.read_text(encoding="utf-8"))


def lookup(table: dict, kind: str, length_um: float, gm_id: float) -> dict:
    """gm/ID 와 L 이 주어졌을 때의 전류 밀도, 고유이득, 전압을 표에서 보간해 돌려준다."""
    rows = table["devices"][kind][str(float(length_um))]
    return {key: float(np.interp(gm_id, rows["gm_id"], rows[key])) for key in ("j", "gm_gds", "vgs", "vdsat")}


if __name__ == "__main__":
    TABLE_FILE.write_text(json.dumps(build_table()), encoding="utf-8")
    table = load_table()
    print(f"특성표 저장: {TABLE_FILE}")
    for kind in DEVICES:
        for length in LENGTHS_UM:
            at10 = lookup(table, kind, length, 10.0)
            print(f"  {DEVICES[kind]} L={length}u, gm/ID=10: 전류밀도 {at10['j'] * 1e6:.2f} uA, "
                  f"고유이득 {at10['gm_gds']:.0f}, Vgs {at10['vgs']:.2f} V")
