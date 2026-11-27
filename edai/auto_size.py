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
# 계산한 폭이 W_MIN_UM 보다 좁으면 W/L 을 그대로 두고 길이를 늘린다 (같은 전류 밀도, 긴 채널 근사). 초저전력 튜닝에서
# 전류원 100 nA 쯤이면 폭이 0.1 µm 로 계산되는데 0.5 µm 로 묶여 전류 밀도가 틀어지고 캐스코드가 포화 영역을 벗어났다
# (2026-11-27). 길이는 모델(nfet/pfet_06v0, BSIM 0.7~50 µm 구간)이 맞는 L_MAX_UM 까지
L_MAX_UM = 50.0
INITIAL_WIDTH_UM = 10.0
MAX_ITERATIONS = 8
CONVERGED_CHANGE = 0.05     # 폭 변화가 모두 5% 안이면 멈춘다
# 바이어스 방식: "ideal" = 바이어스 단자에 이상적인 전원 (예전 방식, 학습 데이터 성능 값이 이 기준)
#                "devices" = bias_convert.py 로 실제 소자를 채움 (박준석 시스템 첫 관문 통과용)
BIAS_MODE = "ideal"
POWERUP_RAMP_S = 10e-6      # 전원 켜기 검사: 시간 간격 기준 (간격 = 이 값 / 200) [s]
POWERUP_END_S = 60e-6       # 끝 시각 [s]. 마지막 10 µs 평균을 동작점과 비교
POWERUP_VOUT_TOL = 0.1      # 출력 차이 허용 [V]
POWERUP_IDD_TOL = 0.1       # 공급 전류 차이 허용 (비율)
MAX_STARTUP_TRIALS = 12
# 입력 공통모드 범위 (run_sim 의 CMRR 측정 범위와 같음). 입력쌍 위 캐스코드 전압은 VCM 이 아니라
# 이 범위에서 가장 불리한 끝으로 정한다: NMOS 입력은 위쪽 끝, PMOS 입력은 아래쪽 끝 (2026-11-22, CMRR 실패 원인)
# 범위는 스펙을 읽을 때 칩마다 바뀌므로(run_sim.set_cm_range_from_spec) 상수가 아니라 함수로 읽는다.
def vic_min() -> float:
    return run_sim.OPAMP_VIC_LOW


def vic_max() -> float:
    return VDD - run_sim.OPAMP_VIC_HIGH_BELOW_VDD



# ---------------------------------------------------------------- 특성표
def _load_device_table() -> dict:
    return json.loads(TABLE_FILE.read_text(encoding="utf-8"))["devices"]


DEVICE_TABLE = _load_device_table()


def lookup(kind: str, length_um: float, gm_id: float, field: str) -> float:
    """특성표에서 gm/ID 에 해당하는 값을 읽는다 (j: 정사각형 하나의 전류, vgs, vdsat)."""
    data = DEVICE_TABLE["n" if kind == "nmos" else "p"][str(float(length_um))]
    return float(np.interp(gm_id, data["gm_id"], data[field]))


def input_cascode_level(kind: str) -> float:
    """입력쌍 위 캐스코드 게이트 전압 (NMOS 는 VSS 에서, PMOS 는 VDD 에서 잰 값).
    공통모드 입력이 가장 불리한 끝(NMOS: 위 끝, PMOS: 아래 끝)에 있어도 입력쌍이 포화 영역에 남도록
    게이트 = 끝 전압 + 입력 소자 Vdsat + 여유. 예전에는 VCM 기준이라 PMOS 입력에서 VIC < 1 V 이면 입력쌍이 선형 영역으로 빠졌다."""
    v_in = abs(lookup(kind, ROLE_TARGETS["input"][1], ROLE_TARGETS["input"][0], "vdsat"))
    edge = vic_max() if kind == "nmos" else VDD - vic_min()
    return edge + v_in + CASCODE_HEADROOM + BODY_EFFECT_MARGIN


def input_cascode_ok(kind: str) -> bool:
    """입력쌍 위에 캐스코드를 쌓을 수 있나: 캐스코드 드레인(이득 노드) 위에 반대쪽 부하 소자가 들어갈 자리가 남아야 한다.
    이득 노드 최저 전압 = 게이트 - Vgs(캐스코드) + Vdsat(캐스코드) + 여유, 그 위로 부하 Vgs(다이오드 연결 기준)."""
    g, l = ROLE_TARGETS["cascode"]
    vgs_c = abs(lookup(kind, l, g, "vgs"))
    vdsat_c = abs(lookup(kind, l, g, "vdsat"))
    other = "pmos" if kind == "nmos" else "nmos"
    vgs_load = abs(lookup(other, ROLE_TARGETS["diode"][1], ROLE_TARGETS["diode"][0], "vgs"))
    node = input_cascode_level(kind) - vgs_c + vdsat_c + CASCODE_HEADROOM
    return node + vgs_load <= VDD


def input_pair_covers_range(kinds: set) -> bool:
    """입력쌍 종류가 공통모드 입력 범위(vic_min() ~ vic_max())를 덮나.
    NMOS 입력쌍은 VIC >= Vgs(입력) + Vdsat(꼬리 전류원) 이어야 켜지고, PMOS 는 VIC <= VDD - 같은 값.
    두 종류가 다 있으면(레일 투 레일 입력) 덮는 것으로 본다."""
    if {"nmos", "pmos"} <= kinds:
        return True
    ok = False
    for kind in kinds:
        need = abs(lookup(kind, ROLE_TARGETS["input"][1], ROLE_TARGETS["input"][0], "vgs")) \
            + abs(lookup(kind, ROLE_TARGETS["source"][1], ROLE_TARGETS["source"][0], "vdsat"))
        ok |= vic_min() >= need if kind == "nmos" else VDD - vic_max() >= need
    return ok


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


# 소자별 목표 바꾸기 {소자 이름: (gm/ID, 길이 um)}. structure_doctor(LLM 고치기)가 잠깐 넣는다.
# 같은 미러 묶음(같은 종류·게이트·소스) 전체에 적용해서 미러 비율이 깨지지 않게 한다.
TARGET_OVERRIDES = {}
DEVICE_LENGTHS_UM = (0.7, 1.0, 2.0, 4.0)     # 특성표(devices_gf180.json)에 있는 길이
GM_ID_RANGE = (4.0, 19.0)                    # 특성표 gm/ID 범위 안


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
        override = next((TARGET_OVERRIDES[n] for n in members if n in TARGET_OVERRIDES), None)
        for name in members:
            targets[name] = override or (gm_id, length)
    return targets


# ---------------------------------------------------------------- 바이어스
def bias_lines(table: dict, targets: dict, unit_current: float = UNIT_CURRENT) -> tuple:
    """바이어스 단자를 회로 안에서 만드는 줄과, 전류가 단자 전압으로 정해지는 소자 목록을 돌려준다.
    IB# 단자 전류는 전류원 하나의 전류에 맞춘다 (BIAS_CURRENT x unit_current / UNIT_CURRENT, 기본 20 µA)."""
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
                # 아래 소자가 입력 차동쌍이면 그 소스는 전원이 아니라 입력 공통 전압 근처에 있다 (cascode.py 가 만드는 모양).
                # 게이트 = VCM + 입력 소자 Vdsat + 여유 (PMOS 는 전원 기준이라 VDD - VCM 을 더함)
                under = next((r for r in rows if r["pins"]["D"] == row["pins"]["S"] and r["kind"] == row["kind"]), None)
                if under is not None and under["pins"]["G"] in ("IN1", "IN2"):
                    level = input_cascode_level(row["kind"])
            if row["kind"] == "nmos":
                lines.append(f"VBIAS_{port} {port} VSS dc {level:.4f}")
            else:
                lines.append(f"VBIAS_{port} VDD {port} dc {level:.4f}")
        elif port.startswith("IB"):
            touching = [(row, pin) for row in rows for pin, net in row["pins"].items() if net == port and pin != "B"]
            sinks = any((row["kind"] == "nmos" and pin == "S") or (row["kind"] == "pmos" and pin == "D")
                        for row, pin in touching)
            if sinks:
                lines.append(f"IBIAS_{port} {port} VSS dc {BIAS_CURRENT * unit_current / UNIT_CURRENT:.4g}")
            else:
                lines.append(f"IBIAS_{port} VDD {port} dc {BIAS_CURRENT * unit_current / UNIT_CURRENT:.4g}")
    return lines, fixed


# ---------------------------------------------------------------- 크기
def size_text(width_um: float, length_um: float) -> dict:
    if width_um < W_MIN_UM:
        length_um = min(L_MAX_UM, math.ceil(length_um * W_MIN_UM / max(width_um, 1e-6) * 10) / 10)
        width_um = W_MIN_UM
    count = max(1, math.ceil(width_um / W_MAX_UM))
    width = min(max(width_um / count, W_MIN_UM), W_MAX_UM)
    size = {"w": f"{width:.3g}u", "l": f"{length_um:g}u"}
    if count > 1:
        size["m"] = str(count)
    return size


def total_width(size: dict) -> float:
    return float(size["w"].rstrip("u")) * int(size.get("m", 1))


def nominal_width(size: dict, length_um: float) -> float:
    """길이를 늘린 소자(size_text)의 폭을 원래 길이 기준 폭으로 (같은 W/L). 크기 반복의 수렴 비교에 쓴다."""
    return total_width(size) * length_um / float(size["l"].rstrip("u"))


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
    # 노드 전압 (실패 원인 진단용). 단자는 이름이 바뀌어 들어가므로 안쪽 노드만
    nets = sorted({net for row in table["rows"] for net in row["pins"].values()} - {"IN1", "IN2", "OUT", "VDD", "VSS"})
    prints += [f"print v(x1.{net.lower()})" for net in nets]
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
        done = subprocess.run([run_sim.NGSPICE_EXE, "-b", str(path)], capture_output=True, text=True,
                              timeout=run_sim.sim_timeout(120))
    except subprocess.TimeoutExpired:
        run_sim.check_deadline()
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
    nodes = {}
    for net in nets:
        try:
            nodes[net] = float(values[f"v(x1.{net.lower()})"])
        except (KeyError, ValueError):
            pass
    return {"vout": float(values["v(out)"]), "devices": devices, "nodes": nodes}


def startup_devices(table: dict) -> set:
    """기동 회로(start-up) 소자를 연결 모양으로 찾는다.

    정상 상태에서 기동 스위치는 꺼지고, 감시 소자는 포화 영역 밖에 있도록 설계되므로 포화 검사에서 뺀다.
    모양: 안쪽 노드 X 에 (전원으로 가는 저항) + (드레인 하나 = 감시 소자) + (게이트들) 만 붙어 있고,
    X 가 게이트인 소자 중 드레인이나 소스가 다이오드 연결 노드(바이어스)에 붙은 것이 기동 스위치다.
    """
    mos = mos_rows(table)
    diode_nets = {row["pins"]["G"] for row in mos if row["pins"]["G"] == row["pins"]["D"]}
    by_net = {}
    for row in table["rows"]:
        for pin, net in row["pins"].items():
            by_net.setdefault(net, []).append((row, pin))
    found = set()
    for net, links in by_net.items():
        if net in RAILS or net in table["ports"] or net in diode_nets:
            continue
        pull = [r for r, _ in links if r["kind"] == "res" and set(r["pins"].values()) - {net} <= set(RAILS)]
        drains = [r for r, p in links if r["kind"] in ("nmos", "pmos") and p == "D"]
        gates = [r for r, p in links if r["kind"] in ("nmos", "pmos") and p == "G"]
        if not pull or len(drains) != 1 or len(pull) + len(drains) + len(gates) != len(links):
            continue
        switches = [r for r in gates if r["pins"]["D"] in diode_nets or r["pins"]["S"] in diode_nets]
        if switches:
            found |= {r["name"] for r in switches} | {drains[0]["name"]}
    return found


def diode_nodes(subckt: str) -> dict:
    """회로 파일에서 다이오드 연결(게이트 = 드레인) 노드: {노드: "nmos"/"pmos"}."""
    found = {}
    for line in subckt.splitlines():
        t = line.split()
        if len(t) > 5 and t[0][0].upper() == "X" and t[5] in ("nfet_06v0", "pfet_06v0") and t[1] == t[2] \
                and t[1] not in RAILS:
            found[t[1]] = "nmos" if t[5] == "nfet_06v0" else "pmos"
    return found


def powerup(subckt: str) -> dict:
    """전원 켜기 검사 (최악 조건): 전압 팔로워로 묶고, 모든 다이오드 노드를 꺼진 상태 전압
    (NMOS 다이오드 0 V, PMOS 다이오드 VDD)에 둔 채 과도 해석을 시작한다. 끝의 출력·공급 전류가
    동작점과 같으면 스스로 켜진 것, 다르면 꺼진 상태에 갇힌 것 (startup 필요)."""
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    t0 = POWERUP_END_S - 10e-6
    ic = " ".join(f"v(x1.{n.lower()})={0 if k == 'nmos' else VDD}" for n, k in diode_nodes(subckt).items())
    deck = "\n".join([
        "* auto_size 전원 켜기 (꺼진 상태에서 시작)",
        f".include {run_sim.PDK_DIR}/design.ngspice",
        f".lib {run_sim.PDK_DIR}/sm141064.ngspice typical",
        subckt,
        "X1 VCM OUT OUT VDD 0 opamp",
        f"VDD VDD 0 {VDD}",
        f"VCM VCM 0 {VCM}",
        f"RL OUT VCM {run_sim.OPAMP_AVD_RL}",
        *([f".ic {ic}"] if ic else []),
        ".control", "op", "print v(out) i(vdd)",
        f"tran {POWERUP_RAMP_S / 200} {POWERUP_END_S} uic",
        f"meas tran vfin avg v(out) from={t0} to={POWERUP_END_S}",
        f"meas tran ifin avg i(vdd) from={t0} to={POWERUP_END_S}",
        ".endc", ".end", ""])
    with tempfile.NamedTemporaryFile("w", suffix=".cir", dir=WORK_DIR, delete=False, encoding="utf-8") as handle:
        handle.write(deck)
        path = Path(handle.name)
    try:
        done = subprocess.run([run_sim.NGSPICE_EXE, "-b", str(path)], capture_output=True, text=True,
                              timeout=run_sim.sim_timeout(300))
    except subprocess.TimeoutExpired:
        run_sim.check_deadline()
        return {"ok": False, "error": "시간 초과"}
    finally:
        path.unlink(missing_ok=True)
    values = {k.lower(): v for k, v in re.findall(r"^\s*(\S+)\s*=\s*([-+0-9.eE]+)", done.stdout, flags=re.MULTILINE)}
    try:
        v_op, i_op = float(values["v(out)"]), abs(float(values["i(vdd)"]))
        v_on, i_on = float(values["vfin"]), abs(float(values["ifin"]))
    except KeyError:
        return {"ok": False, "error": (done.stdout + done.stderr)[-300:]}
    ok = abs(v_on - v_op) <= POWERUP_VOUT_TOL and abs(i_on - i_op) <= POWERUP_IDD_TOL * i_op
    return {"ok": ok, "vout_op": v_op, "vout_on": v_on, "idd_op": i_op, "idd_on": i_on}


def saturation_report(op: dict, table: dict) -> dict:
    """꺼진 소자와 포화 영역 밖 소자. 기동 회로 소자는 빼고 따로 적는다."""
    startup = startup_devices(table)
    checked = {n: d for n, d in op["devices"].items() if n not in startup}
    off = [n for n, d in checked.items() if d is None or d["id"] < OFF_CURRENT]
    triode = [n for n, d in checked.items() if d and d["id"] >= OFF_CURRENT and d["vds"] < d["vdsat"] + SAT_MARGIN]
    return {"off": off, "triode": triode, "startup": sorted(startup)}


# ---------------------------------------------------------------- 전체
def auto_size(table: dict, passive_values: dict = None, unit_current: float = UNIT_CURRENT,
              output_scale: float = 1.0, bias_mode: str = None) -> dict:
    """구조 표 하나에 동작하는 크기를 찾는다.

    passive_values : {소자 이름: {"value": ..}} 저항·커패시터 값 (없으면 netlist_table 기본값)
    unit_current   : 바이어스 단자로 정해지는 전류원 하나의 전류 [A]
    output_scale   : 드레인이 OUT 에 붙은 트랜지스터의 전류 배율. 처음 폭을 이만큼 넓게 두면
                     반복하면서도 전류 미러 비율이 유지되어 출력단 전류가 커진다
    bias_mode      : "ideal" 또는 "devices" (없으면 BIAS_MODE). devices 면 bias_convert 로 바이어스 소자를 채운 뒤
                     크기를 정하고, 전원 켜기 검사(필요하면 startup 추가)까지 한다
    돌려주는 값: {"ok", "subckt", "sizes", "polarity", "roles", "vout", "off", "triode", "iterations", "reason",
                  devices 면 추가로 "bias", "powerup"}
    """
    bias_mode = bias_mode or BIAS_MODE
    bias = None
    if bias_mode == "devices":
        import bias_convert
        table, extra, bias = bias_convert.convert(table, unit_current)
        if bias["unresolved"]:
            return {"ok": False, "reason": f"바이어스 미해결: {', '.join(bias['unresolved'])}", "bias": bias}
    roles = assign_roles(table)
    targets = mirror_groups(table, roles)
    if bias_mode == "devices":
        _, fixed = bias_lines(table, targets, unit_current)       # 전원 줄은 버리고, 게이트 전압으로 전류가 정해지는 소자 목록만 씀
    else:
        extra, fixed = bias_lines(table, targets, unit_current)
    at_output = {row["name"] for row in mos_rows(table) if row["pins"]["D"] == "OUT"}
    scale = {name: output_scale if name in at_output else 1.0 for name in targets}
    sizes = {name: size_text(INITIAL_WIDTH_UM * scale[name], targets[name][1]) for name in targets}
    for name in fixed:
        row = next(r for r in table["rows"] if r["name"] == name)
        gm_id, length = targets[name]
        sizes[name] = size_text(width_for_current(row["kind"], unit_current * scale[name], gm_id, length), length)
    if bias:
        sizes.update(bias["fixed"])                # 기준 전류 미러: 기준 회로와 같은 길이·gm/ID 의 폭 (전류 비 고정)
        fixed = set(fixed) | set(bias["fixed"])
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
            width = min(max(width_for_current(kinds[name], info["id"], gm_id, length), 1e-3), 20 * W_MAX_UM)
            old = nominal_width(sizes[name], length)
            change = max(change, abs(width - old) / old)
            sizes[name] = size_text(width, length)
        op = run_op(build(polarity), table, polarity)
        if op["vout"] is None:
            return {"ok": False, "reason": "반복 중 동작점 계산 실패", "roles": roles, "iterations": iterations}
        if change < CONVERGED_CHANGE:
            break
    report = saturation_report(op, table)
    output_ok = abs(op["vout"] - VCM) <= OUTPUT_TOLERANCE
    ok = output_ok and not report["off"] and not report["triode"]
    reason = "" if ok else ("출력이 VCM 에서 벗어남" if not output_ok else "포화 영역이 아닌 소자 있음")
    result = {"ok": ok, "reason": reason, "subckt": build(polarity), "sizes": sizes, "polarity": polarity,
              "roles": roles, "vout": op["vout"], "iterations": iterations, "table": table, **report,
              "op_devices": op["devices"], "op_nodes": op.get("nodes")}   # 동작점. 실패 원인 진단(structure_doctor)에 씀
    if bias is not None:
        result["bias"] = bias
        if ok:
            result.update(_powerup_with_startup(table, extra, sizes, polarity))
            if not result["powerup"]["ok"]:
                result["ok"], result["reason"] = False, "전원 켜기 실패 (꺼진 상태에 갇힘)"
    return result


def _powerup_with_startup(table: dict, extra: list, sizes: dict, polarity: tuple) -> dict:
    """전원 켜기 검사. 실패하면 회로 자체 바이어스 고리에 startup 을 붙여 본다 (다이오드 노드 짝마다)."""
    import bias_convert
    subckt = nt.to_ngspice(table, sizes, polarity=polarity, extra_lines=extra)
    check = powerup(subckt)
    if check["ok"]:
        return {"powerup": check, "startup_added": None}
    tried = []
    for p_node, q_node in bias_convert.startup_candidates(table)[:MAX_STARTUP_TRIALS]:
        trial = nt.to_ngspice(table, sizes, polarity=polarity,
                              extra_lines=extra + bias_convert.startup_lines(p_node, q_node))
        result = powerup(trial)
        tried.append({"p": p_node, "q": q_node, "ok": result["ok"]})
        if result["ok"]:
            return {"powerup": result, "startup_added": {"p": p_node, "q": q_node}, "startup_tried": tried,
                    "subckt": trial}
    return {"powerup": check, "startup_added": None, "startup_tried": tried}


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
