"""
아무 OP-Amp 구조에나 "동작하는 크기"를 정한다 (학습 데이터에 성능 값을 붙이기 위한 도구).

목표는 스펙을 맞추는 것이 아니라, 모든 트랜지스터가 증폭하는 영역(포화 영역)에서 동작하는
크기를 찾는 것이다. 그러면 테스트벤치로 성능을 재서 "이 구조를 이렇게 만들면 성능이 이렇다"는
학습 데이터 한 줄이 된다.

순서
    1. 연결만 보고 트랜지스터 역할을 정한다: 입력쌍, 다이오드 연결, 전류원, 캐스코드, 이득단
    2. 역할마다 gm/ID(전류 대비 효율) 목표와 채널 길이를 정한다
    3. 바이어스 단자를 회로 안에서 만든다: VB# 는 목표 gm/ID 에 맞는 게이트 전압, IB# 는 기준 전류
    4. 동작점 시뮬레이션 -> 트랜지스터마다 실제 전류 -> 특성표(devices_gf180.json)로 폭 다시 계산을 반복
    5. 모든 트랜지스터가 포화 영역인지 확인한다

사용법 (WSL, 프로젝트 폴더에서):
    ~/.venvs/edai/bin/python auto_size.py opamp_gen.cir     # 우리 회로의 크기를 지우고 처음부터 다시 정해 보기
"""

import json
import math
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np

import netlist_table as nt
import run_sim

TABLE_FILE = run_sim.HERE / "devices_gf180.json"
WORK_DIR = run_sim.OUT_DIR / "auto_size"
VDD = run_sim.OPAMP_VDD
VCM = VDD / 2
RAILS = ("VDD", "VSS")
# 역할 -> (gm/ID 목표 [1/V], 채널 길이 [um])
ROLE_TARGETS = {"input": (12.0, 1.0), "diode": (8.0, 2.0), "source": (8.0, 2.0),
                "cascode": (12.0, 1.0), "gain": (10.0, 1.0), "other": (10.0, 1.0)}
UNIT_CURRENT = 20e-6        # 바이어스 단자로 정해지는 전류원 하나의 전류 [A]
BIAS_CURRENT = 20e-6        # IB# 단자에 넣는 기준 전류 [A]
CASCODE_HEADROOM = 0.25     # 캐스코드 게이트 전압: 아래 소자의 포화 전압 + 이 여유 [V]
BODY_EFFECT_MARGIN = 0.2    # 소스가 전원이 아닌 소자의 문턱전압 상승분 대략값 [V]
SAT_MARGIN = 0.05           # |Vds| >= |Vdsat| + 이 값이면 포화 영역으로 본다 [V]
OFF_CURRENT = 1e-9          # 이보다 작은 전류는 꺼진 것으로 본다 [A]
OUTPUT_TOLERANCE = 0.5      # 전압 팔로워로 묶었을 때 출력이 VCM 에서 이만큼 안에 있어야 한다 [V]
W_MIN_UM, W_MAX_UM = 0.5, 100.0   # 이보다 넓으면 같은 소자를 여러 개(m) 병렬로 둔다
INITIAL_WIDTH_UM = 10.0
MAX_ITERATIONS = 8
CONVERGED_CHANGE = 0.05     # 폭 변화가 모두 5% 안이면 멈춘다


# ---------------------------------------------------------------- 특성표
def _load_device_table() -> dict:
    return json.loads(TABLE_FILE.read_text(encoding="utf-8"))["devices"]


DEVICE_TABLE = _load_device_table()


def lookup(kind: str, length_um: float, gm_id: float, field: str) -> float:
    """특성표에서 gm/ID 에 해당하는 값을 읽는다 (j: 정사각형 하나의 전류, vgs, vdsat)."""
    data = DEVICE_TABLE["n" if kind == "nmos" else "p"][str(float(length_um))]
    return float(np.interp(gm_id, data["gm_id"], data[field]))


# ---------------------------------------------------------------- 역할
def mos_rows(table: dict) -> list:
    return [row for row in table["rows"] if row["kind"] in ("nmos", "pmos")]


def assign_roles(table: dict) -> dict:
    """트랜지스터마다 역할을 정한다: {소자 이름: 역할}"""
    diode_nets = {row["pins"]["G"] for row in mos_rows(table) if row["pins"]["G"] == row["pins"]["D"]}
    bias_nets = {net for net in table["ports"] if net.startswith(("VB", "IB"))}
    mirror_nets = diode_nets | bias_nets
    roles = {}
    for row in mos_rows(table):
        gate, drain, source = row["pins"]["G"], row["pins"]["D"], row["pins"]["S"]
        if gate in ("IN1", "IN2"):
            roles[row["name"]] = "input"
        elif gate == drain:
            roles[row["name"]] = "diode"
        elif gate in mirror_nets:
            roles[row["name"]] = "source" if source in RAILS else "cascode"
        elif source in RAILS:
            roles[row["name"]] = "gain"
        else:
            roles[row["name"]] = "other"
    return roles


def mirror_groups(table: dict, roles: dict) -> dict:
    """게이트와 소스를 함께 쓰는 같은 종류 트랜지스터는 길이와 gm/ID 목표를 맞춘다 (전류 미러 비율 유지).

    돌려주는 값: {소자 이름: (gm/ID, 길이)}
    """
    groups = {}
    for row in mos_rows(table):
        key = (row["kind"], row["pins"]["G"], row["pins"]["S"])
        groups.setdefault(key, []).append(row["name"])
    targets = {}
    for members in groups.values():
        member_roles = [roles[name] for name in members]
        lead = "diode" if "diode" in member_roles else member_roles[0]
        gm_id, _ = ROLE_TARGETS[lead]
        length = max(ROLE_TARGETS[role][1] for role in member_roles)
        for name in members:
            targets[name] = (gm_id, length)
    return targets


# ---------------------------------------------------------------- 바이어스
def bias_lines(table: dict, targets: dict) -> tuple:
    """바이어스 단자를 회로 안에서 만드는 줄과, 전류가 단자 전압으로 정해지는 소자 목록을 돌려준다."""
    lines, fixed = [], set()
    rows = mos_rows(table)
    for port in table["ports"]:
        if port.startswith("VB"):
            gated = [row for row in rows if row["pins"]["G"] == port]
            if not gated:
                continue
            row = gated[0]
            gm_id, length = targets[row["name"]]
            vgs = abs(lookup(row["kind"], length, gm_id, "vgs"))
            if row["pins"]["S"] in RAILS:
                level = vgs
                fixed.update(r["name"] for r in gated if r["pins"]["S"] in RAILS)
            else:
                below = abs(lookup(row["kind"], ROLE_TARGETS["source"][1], ROLE_TARGETS["source"][0], "vdsat"))
                level = vgs + below + CASCODE_HEADROOM + BODY_EFFECT_MARGIN
            if row["kind"] == "nmos":
                lines.append(f"VBIAS_{port} {port} VSS dc {level:.4f}")
            else:
                lines.append(f"VBIAS_{port} VDD {port} dc {level:.4f}")
        elif port.startswith("IB"):
            touching = [(row, pin) for row in rows for pin, net in row["pins"].items() if net == port and pin != "B"]
            sinks = any((row["kind"] == "nmos" and pin == "S") or (row["kind"] == "pmos" and pin == "D")
                        for row, pin in touching)
            if sinks:
                lines.append(f"IBIAS_{port} {port} VSS dc {BIAS_CURRENT}")
            else:
                lines.append(f"IBIAS_{port} VDD {port} dc {BIAS_CURRENT}")
    return lines, fixed


# ---------------------------------------------------------------- 크기
def size_text(width_um: float, length_um: float) -> dict:
    count = max(1, math.ceil(width_um / W_MAX_UM))
    width = min(max(width_um / count, W_MIN_UM), W_MAX_UM)
    size = {"w": f"{width:.3g}u", "l": f"{length_um:g}u"}
    if count > 1:
        size["m"] = str(count)
    return size


def total_width(size: dict) -> float:
    return float(size["w"].rstrip("u")) * int(size.get("m", 1))


def width_for_current(kind: str, current: float, gm_id: float, length_um: float) -> float:
    """목표 gm/ID 에서 이 전류를 흘리는 폭 [um]. j 는 정사각형(W=L) 하나의 전류다."""
    return current / lookup(kind, length_um, gm_id, "j") * length_um


# ---------------------------------------------------------------- 동작점
PRINT_FIELDS = ("id", "vds", "vdsat")


def run_op(subckt: str, table: dict, polarity: tuple) -> dict:
    """전압 팔로워로 묶어 동작점을 잰다. 돌려주는 값: {"vout": .., "devices": {이름: {id, vds, vdsat}}}"""
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    names = [row["name"] for row in mos_rows(table)]
    prints = [f"print " + " ".join(f"@m.x1.x{name.lower()}.m0[{field}]" for field in PRINT_FIELDS) for name in names]
    deck = "\n".join([
        "* auto_size 동작점",
        f".include {run_sim.PDK_DIR}/design.ngspice",
        f".lib {run_sim.PDK_DIR}/sm141064.ngspice typical",
        subckt,
        "X1 VCM INN OUT VDD 0 opamp",
        f"VDD VDD 0 {VDD}",
        f"VCM VCM 0 {VCM}",
        "LFB OUT INN 1G",
        f"RL OUT VCM {run_sim.OPAMP_AVD_RL}",
        ".control", "op", "print v(out)", *prints, ".endc", ".end", ""])
    with tempfile.NamedTemporaryFile("w", suffix=".cir", dir=WORK_DIR, delete=False, encoding="utf-8") as handle:
        handle.write(deck)
        path = Path(handle.name)
    try:
        done = subprocess.run([run_sim.NGSPICE_EXE, "-b", str(path)], capture_output=True, text=True, timeout=120)
    except subprocess.TimeoutExpired:
        return {"vout": None, "devices": {}, "error": "동작점 시뮬레이션 시간 초과 (120 s)"}
    finally:
        path.unlink(missing_ok=True)
    values = dict(re.findall(r"^(\S+) = (\S+)$", done.stdout, flags=re.MULTILINE))
    if "v(out)" not in values:
        return {"vout": None, "devices": {}, "error": (done.stdout + done.stderr)[-400:]}
    devices = {}
    for name in names:
        try:
            devices[name] = {field: abs(float(values[f"@m.x1.x{name.lower()}.m0[{field}]"])) for field in PRINT_FIELDS}
        except KeyError:
            devices[name] = None
    return {"vout": float(values["v(out)"]), "devices": devices}


def saturation_report(op: dict) -> dict:
    off = [n for n, d in op["devices"].items() if d is None or d["id"] < OFF_CURRENT]
    triode = [n for n, d in op["devices"].items() if d and d["id"] >= OFF_CURRENT and d["vds"] < d["vdsat"] + SAT_MARGIN]
    return {"off": off, "triode": triode}


# ---------------------------------------------------------------- 전체
def auto_size(table: dict, passive_values: dict = None, unit_current: float = UNIT_CURRENT,
              output_scale: float = 1.0) -> dict:
    """구조 표 하나에 동작하는 크기를 찾는다.

    passive_values : {소자 이름: {"value": ..}} 저항·커패시터 값 (없으면 netlist_table 기본값)
    unit_current   : 바이어스 단자로 정해지는 전류원 하나의 전류 [A]
    output_scale   : 드레인이 OUT 에 붙은 트랜지스터의 전류 배율. 처음 폭을 이만큼 넓게 두면
                     반복하면서도 전류 미러 비율이 유지되어 출력단 전류가 커진다
    돌려주는 값: {"ok", "subckt", "sizes", "polarity", "roles", "vout", "off", "triode", "iterations", "reason"}
    """
    roles = assign_roles(table)
    targets = mirror_groups(table, roles)
    extra, fixed = bias_lines(table, targets)
    at_output = {row["name"] for row in mos_rows(table) if row["pins"]["D"] == "OUT"}
    scale = {name: output_scale if name in at_output else 1.0 for name in targets}
    sizes = {name: size_text(INITIAL_WIDTH_UM * scale[name], targets[name][1]) for name in targets}
    for name in fixed:
        row = next(r for r in table["rows"] if r["name"] == name)
        gm_id, length = targets[name]
        sizes[name] = size_text(width_for_current(row["kind"], unit_current * scale[name], gm_id, length), length)
    sizes.update(passive_values or {})
    kinds = {row["name"]: row["kind"] for row in mos_rows(table)}

    def build(polarity):
        return nt.to_ngspice(table, sizes, polarity=polarity, extra_lines=extra)

    polarity, op = None, None
    for candidate in (("IN1", "IN2"), ("IN2", "IN1")):
        trial = run_op(build(candidate), table, candidate)
        if trial["vout"] is not None and (op is None or op["vout"] is None
                                          or abs(trial["vout"] - VCM) < abs(op["vout"] - VCM)):
            polarity, op = candidate, trial
    if polarity is None:
        return {"ok": False, "reason": "동작점 계산 실패", "roles": roles}
    iterations = 0
    for iterations in range(1, MAX_ITERATIONS + 1):
        change = 0.0
        for name, info in op["devices"].items():
            if name in fixed or info is None or info["id"] < OFF_CURRENT:
                continue
            gm_id, length = targets[name]
            width = min(max(width_for_current(kinds[name], info["id"], gm_id, length), W_MIN_UM), 20 * W_MAX_UM)
            old = total_width(sizes[name])
            change = max(change, abs(width - old) / old)
            sizes[name] = size_text(width, length)
        op = run_op(build(polarity), table, polarity)
        if op["vout"] is None:
            return {"ok": False, "reason": "반복 중 동작점 계산 실패", "roles": roles, "iterations": iterations}
        if change < CONVERGED_CHANGE:
            break
    report = saturation_report(op)
    output_ok = abs(op["vout"] - VCM) <= OUTPUT_TOLERANCE
    ok = output_ok and not report["off"] and not report["triode"]
    reason = "" if ok else ("출력이 VCM 에서 벗어남" if not output_ok else "포화 영역이 아닌 소자 있음")
    return {"ok": ok, "reason": reason, "subckt": build(polarity), "sizes": sizes, "polarity": polarity,
            "roles": roles, "vout": op["vout"], "iterations": iterations, **report}


def main() -> None:
    if len(sys.argv) != 2:
        print(__doc__)
        return
    circuit = nt.parse_ngspice(Path(sys.argv[1]).read_text(encoding="utf-8"))
    table = nt.to_table(circuit)
    passives = {row["name"]: row["params"] for row in table["rows"] if row["kind"] in ("res", "cap")}
    result = auto_size(table, passives)
    print(f"결과: {'동작' if result['ok'] else '실패'} {result.get('reason', '')}")
    print(f"  출력 {result.get('vout')} V, 반복 {result.get('iterations')}회, 입력 방향 {result.get('polarity')}")
    print(f"  꺼진 소자 {result.get('off')}, 포화 아닌 소자 {result.get('triode')}")


if __name__ == "__main__":
    main()
