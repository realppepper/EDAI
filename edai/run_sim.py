"""
ngspice 배치(-b) 자동 실행 -> raw 파형 데이터로 측정 -> 스펙 파일과 비교해 판정 -> Bode plot(PNG) 저장

사용법 (WSL Ubuntu 터미널에서):
    sudo apt install -y ngspice python3-venv          # 최초 1회
    python3 -m venv ~/.venvs/edai                     # 최초 1회
    ~/.venvs/edai/bin/pip install spicelib numpy matplotlib   # 최초 1회
    cd /mnt/c/Users/<사용자>/Desktop/예캡
    ~/.venvs/edai/bin/python run_sim.py                     # 기본 설계(cascode) 하나
    ~/.venvs/edai/bin/python run_sim.py cascode cascode_lp  # 여러 설계 비교
    ~/.venvs/edai/bin/python run_sim.py cascode --spec 다른스펙.json

파일 구성:
    NAME.cir            회로 본체 (.subckt <종류> ...). 재설계할 때 고치는 파일
    tb_<종류>_op.cir     테스트벤치 틀 (전원, 입력, 부하, 해석 명령). 회로와 무관하게 고정
    tb_<종류>_ac.cir
    spec_<종류>.json     스펙 (항목, 기준값, 조건). 판정 기준은 코드가 아니라 이 파일에 있다
실행할 때 테스트벤치 틀의 {dut_file} 자리에 회로 파일을 넣은 넷리스트를
sim_out/NAME_<해석>.cir 로 만들어 ngspice에 넘기고, 판정 결과는
sim_out/NAME_result.json 에 남깁니다.

새 회로 종류를 추가하려면: tb_<종류>_*.cir, spec_<종류>.json 을 만들고,
이 파일에 측정 함수를 써서 MEASURERS 에 등록합니다.
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import time
from pathlib import Path

import numpy as np
from spicelib import RawRead

# ngspice 실행 파일: 환경변수 EDAI_NGSPICE > 홈 폴더에 직접 설치한 것(~/ngspice) > 시스템 설치본.
# GF180MCU 모델은 ngspice 37 이상이 필요하다 (apt의 36은 "unknown parameter (mulu0)" 에러).
_LOCAL_NGSPICE = Path.home() / "ngspice" / "bin" / "ngspice"
NGSPICE_EXE = os.environ.get("EDAI_NGSPICE") or (str(_LOCAL_NGSPICE) if _LOCAL_NGSPICE.exists() else "ngspice")
# PDK(GF180MCU) ngspice 모델 폴더. 테스트벤치의 {pdk_dir} 자리에 들어간다.
PDK_DIR = os.environ.get("EDAI_PDK_DIR", str(Path.home() / "pdk" / "gf180mcu_fd_pr" / "models" / "ngspice"))

HERE = Path(__file__).resolve().parent
OUT_DIR = HERE / "sim_out"
SIM_TIMEOUT_S = 300        # ngspice 한 번 실행의 시간 제한. 수렴하지 않고 멈추는 회로를 건너뛰기 위함
OUT_DIR.mkdir(exist_ok=True)

# 후보 하나에 쓰는 시간의 마감 (time.time() 기준, select_structure 가 후보마다 정함. None 이면 제한 없음).
# 수렴이 안 되는 후보 하나가 크기 정하기를 몇 시간씩 붙잡은 일이 있어서 (LMV321 후보 8: 2시간 51분, 2026-11-24) 둔다
CANDIDATE_DEADLINE = None


class CandidateTimeout(BaseException):
    """후보 하나의 시간 제한을 넘김. 수렴 실패를 잡는 'except Exception' 들에 걸리지 않고 후보 반복까지 올라가도록
    BaseException 을 잇는다 (KeyboardInterrupt 와 같은 방식)."""


def sim_timeout(limit: float) -> float:
    """ngspice 한 번에 줄 시간: 원래 제한과 후보 마감까지 남은 시간 중 짧은 쪽. 마감이 지났으면 CandidateTimeout."""
    if CANDIDATE_DEADLINE is None:
        return limit
    left = CANDIDATE_DEADLINE - time.time()
    if left <= 0:
        raise CandidateTimeout()
    return min(limit, left)


def check_deadline() -> None:
    """ngspice 가 시간 초과로 끝난 뒤 부른다. 후보 마감 때문에 끊긴 것이면 CandidateTimeout."""
    if CANDIDATE_DEADLINE is not None and time.time() >= CANDIDATE_DEADLINE - 1:
        raise CandidateTimeout()

TB_PREFIX = "tb_"
SPEC_PREFIX = "spec_"
DUT_PLACEHOLDER = "{dut_file}"
# 테스트벤치에서 회로를 올려놓는 인스턴스 이름. 회로 내부 노드는 v(x1.<노드>)로 기록된다.
DUT_INSTANCE = "x1"

SCOPE_TARGET = "target"
STATUS_PASS = "PASS"
STATUS_FAIL = "FAIL"
STATUS_INFO = "참고"        # typ 값만 있어 합격 기준이 없는 항목
STATUS_EXCLUDED = "제외"    # 스펙 파일에서 범위 외로 표시한 항목
STATUS_UNMEASURED = "미측정"  # 측정 함수가 아직 이 값을 내지 않는 항목
CURVE_MAX_POINTS = 400     # 파형 기록 파일에 남기는 점 수의 상한
BASIS_DATASHEET = "데이터시트"
BASIS_TEAM = "팀 기준"       # typ 값만 있는 항목에 스펙 파일의 typ_rule을 적용한 기준
# 여유를 비율(%)이 아니라 차이로 표시하는 단위
DIFFERENCE_UNITS = ("dB", "°")


# ---------------------------------------------------------------
# 파일 찾기와 넷리스트 만들기
# ---------------------------------------------------------------
def circuit_kind(name: str) -> str:
    """회로 파일의 .subckt 이름. 어떤 테스트벤치·스펙·측정 함수를 쓸지 정한다."""
    for line in (HERE / f"{name}.cir").read_text(encoding="utf-8").splitlines():
        tokens = line.split()
        if tokens and tokens[0].lower() == ".subckt":
            return tokens[1].lower()
    raise ValueError(f"{name}.cir 에 .subckt 정의가 없습니다.")


def testbench_path(name: str, analysis: str) -> Path:
    """설계 NAME을 시험할 테스트벤치 틀 파일 경로."""
    return HERE / f"{TB_PREFIX}{circuit_kind(name)}_{analysis}.cir"


def spec_path(name: str) -> Path:
    """설계 NAME에 기본으로 적용할 스펙 파일.

    spec_<종류>.json 이 있으면 그것을, 없으면 "circuit" 값이 회로 종류와 같은 spec_*.json 을 쓴다.
    """
    kind = circuit_kind(name)
    direct = HERE / f"{SPEC_PREFIX}{kind}.json"
    if direct.exists():
        return direct
    for path in sorted(HERE.glob(f"{SPEC_PREFIX}*.json")):
        if load_spec(path).get("circuit") == kind:
            return path
    raise FileNotFoundError(f"회로 종류 '{kind}' 에 맞는 스펙 파일(spec_*.json)이 없습니다.")


def available_designs() -> list:
    """측정 함수가 등록된 종류의 회로 파일 이름 목록."""
    names = []
    for path in sorted(HERE.glob("*.cir")):
        if path.name.startswith(TB_PREFIX):
            continue
        try:
            kind = circuit_kind(path.stem)
        except ValueError:  # .subckt가 없는 넷리스트
            continue
        if kind in MEASURERS:
            names.append(path.stem)
    return names


def build_netlist(name: str, analysis: str, tag: str = "", **params) -> Path:
    """테스트벤치 틀의 빈칸을 채워, 실제로 실행할 넷리스트를 sim_out에 만든다.

    {dut_file}, {pdk_dir} 는 자동으로 채우고, 나머지 {이름} 자리는 params 로 받는다.
    같은 틀을 조건만 바꿔 여러 번 돌릴 때는 tag 로 결과 파일 이름을 구분한다.
    """
    template_path = testbench_path(name, analysis)
    template = template_path.read_text(encoding="utf-8")
    if DUT_PLACEHOLDER not in template:
        raise ValueError(f"{template_path.name} 에 {DUT_PLACEHOLDER} 자리가 없습니다.")
    # 넷리스트가 sim_out 안에 있으므로 회로 파일은 한 단계 위에서 불러온다.
    values = {"dut_file": f"../{name}.cir", "pdk_dir": PDK_DIR, **params}
    lines = []
    for line in template.splitlines():
        if not line.lstrip().startswith("*"):  # 주석 속 설명용 중괄호는 그대로 둔다
            for key, value in values.items():
                line = line.replace("{" + key + "}", str(value))
            left = re.findall(r"\{\w+\}", line)
            if left:
                raise ValueError(f"{template_path.name} 의 {left} 자리에 넣을 값이 없습니다.")
        lines.append(line)
    suffix = f"_{tag}" if tag else ""
    netlist_path = OUT_DIR / f"{name}_{analysis}{suffix}.cir"
    netlist_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return netlist_path


def run(netlist_path: Path) -> RawRead:
    """ngspice를 배치 모드로 실행하고 결과 raw 파일을 읽어서 돌려준다."""
    raw_path = OUT_DIR / f"{netlist_path.stem}.raw"
    log_path = OUT_DIR / f"{netlist_path.stem}.log"
    try:
        result = subprocess.run(
            [NGSPICE_EXE, "-b", "-r", str(raw_path), "-o", str(log_path), str(netlist_path)],
            capture_output=True,
            text=True,
            timeout=sim_timeout(SIM_TIMEOUT_S),
        )
    except subprocess.TimeoutExpired:
        check_deadline()
        raise RuntimeError(f"{netlist_path.name} 시뮬레이션이 {SIM_TIMEOUT_S}초 안에 끝나지 않음") from None
    if result.returncode != 0 or not raw_path.exists():
        raise RuntimeError(
            f"{netlist_path.name} 시뮬레이션 실패 (exit {result.returncode}). "
            f"{log_path} 내용을 확인하세요."
        )
    return RawRead(str(raw_path), traces_to_read="*", dialect="ngspice")


# ---------------------------------------------------------------
# 측정 (회로 종류마다 함수 하나)
# ---------------------------------------------------------------
def find_f3db(freq: np.ndarray, mag_db: np.ndarray, gain_dc: float) -> float:
    """gain_dc - 3dB 지점의 주파수를 파형 데이터에서 직접(로그축 선형보간) 찾습니다."""
    threshold = gain_dc - 3.0
    below = np.where(mag_db <= threshold)[0]
    if len(below) == 0:
        # 스윕 범위 안에서 -3dB에 도달하지 않음 -> 대역폭이 스윕 최고 주파수보다 큼
        return float(freq[-1])
    idx = below[0]
    if idx == 0:
        return float(freq[0])
    f0, f1 = freq[idx - 1], freq[idx]
    m0, m1 = mag_db[idx - 1], mag_db[idx]
    frac = (threshold - m0) / (m1 - m0)
    log_f3db = np.log10(f0) + frac * (np.log10(f1) - np.log10(f0))
    return float(10 ** log_f3db)


def measure_cascode(name: str) -> dict:
    """캐스코드 증폭기의 DC/AC 시뮬레이션을 돌려 측정값을 모은다 (SI 단위)."""
    op = run(build_netlist(name, "op"))
    # 전원에서 회로로 나가는 전류는 ngspice 부호 규약상 음수로 기록된다.
    i_vdd = float(op.get_trace("i(vdd)").get_wave()[0])
    v_vdd = float(op.get_trace("v(vdd)").get_wave()[0])

    ac = run(build_netlist(name, "ac"))
    freq = np.real(np.array(ac.get_axis()))  # 주파수축은 실수(허수부는 항상 0)
    mag_db = 20 * np.log10(np.abs(ac.get_trace("v(vout)").get_wave()))
    gain_dc = float(mag_db.max())

    return {
        "gain_dc": gain_dc,
        "f3db": find_f3db(freq, mag_db, gain_dc),
        "power": -i_vdd * v_vdd,
        "id": -i_vdd,
        "vout_dc": float(op.get_trace("v(vout)").get_wave()[0]),
        "vx_dc": float(op.get_trace(f"v({DUT_INSTANCE}.vx)").get_wave()[0]),
        "freq": freq,
        "mag_db": mag_db,
    }


# ---- OP-Amp 측정 조건 (spec_tlv271.json 의 condition 과 맞춘 값) ----
OPAMP_VDD = 5.0
OPAMP_NO_LOAD = "1e12"                 # 무부하를 뜻하는 큰 저항
OPAMP_AVD_RL = "10k"                   # 대신호 이득: RL = 10 kΩ
OPAMP_AVD_SWING = 1.25                 # VO(PP) = VDD/2 -> VDD/2 를 중심으로 ±1.25 V
# 공통모드 입력 범위 (CMRR 측정, 크기 정하기의 입력쌍 검사에 씀). 기본은 TLV271 의 0 ~ VDD - 1.35 V.
# 스펙 파일을 읽으면(load_spec) 그 칩의 CMRR 조건 문장으로 바뀐다 (set_cm_range_from_spec, 2026-11-22).
# 예전에는 이 기본값을 모든 칩에 썼다 -> OPA2376·OPA320·MCP6441 의 그 전 CMRR 값은 TLV271 조건으로 잰 값.
OPAMP_VIC_LOW = 0.0                    # VSS 에서 잰 아래 끝 [V] (음수면 VSS 아래)
OPAMP_VIC_HIGH_BELOW_VDD = 1.35        # 위 끝이 VDD 보다 얼마나 아래인가 [V] (음수면 VDD 위)
_DEFAULT_CM_RANGE = (OPAMP_VIC_LOW, OPAMP_VIC_HIGH_BELOW_VDD)
OPAMP_PSRR_VDD = (2.7, 5.5)            # 데이터시트는 2.7 ~ 16 V. 6 V 소자라 5.5 V 까지만 잰다
OPAMP_AC_RL, OPAMP_AC_CL = "2k", "10p"       # 대역폭, 위상여유, 이득여유
OPAMP_SLEW_RL, OPAMP_SLEW_CL = "10k", "50p"  # 슬루율
OPAMP_SLEW_LEVELS = (1.0, 3.5)         # VO(PP) = VDD/2 = 2.5 V, 공통모드 입력 범위 안
OPAMP_SLEW_FALL_TIME = 12e-6           # 테스트벤치의 펄스가 내려오는 시각
OPAMP_SETTLE_RL, OPAMP_SETTLE_CL = "2k", "47p"
OPAMP_SETTLE_BAND = 1e-3               # 0.1% x 1 V 계단
OPAMP_STEP_TIME = 2e-6                 # 테스트벤치의 계단 시작 시각
# 시간 배율: 전류를 줄이면(초저전력 칩 튜닝) 회로가 느려져 µs 단위 측정 창 안에 계단 응답이 끝나지 않는다.
# 슬루율·정착시간의 시간 창과 AC 해석 시작 주파수를 이 배율로 늘린다. 1 이면 예전과 같음 (tune_sizing 이 정함)
TIME_SCALE = 1.0
AC_START_HZ = 1.0                      # AC 해석 시작 주파수 (TIME_SCALE 로 나눔)
# 측정 부하의 기본값. 스펙 파일의 항목 조건(예: 'RL = 2 kΩ', 'CL = 200 pF')이 있으면 그것으로 바뀐다 (set_loads_from_spec)
_DEFAULT_LOADS = {"avd_rl": "10k", "ac_rl": "2k", "ac_cl": "10p", "slew_rl": "10k", "slew_cl": "50p",
                  "settle_rl": "2k", "settle_cl": "47p"}


def ac_start() -> str:
    """AC 해석 시작 주파수 (느린 회로는 더 낮은 주파수부터 봐야 저주파 이득이 보임)."""
    return f"{AC_START_HZ / max(TIME_SCALE, 1.0):.4g}"


def _times(delay: float, width: float, period: float, stop: float) -> dict:
    s = max(TIME_SCALE, 1.0)
    return {"t_delay": f"{delay * s:.4g}", "t_width": f"{width * s:.4g}", "t_period": f"{period * s:.4g}",
            "t_stop": f"{stop * s:.4g}", "t_step": f"{5e-9 * s:.4g}"}
OPAMP_OVERDRIVE = 0.5                  # 출력 구동 시험에서 두 입력을 벌리는 전압
OPAMP_RAIL_OFFSET = 0.5                # 출력 전류: 레일에서 0.5 V 떨어진 지점


def _wave(raw: RawRead, trace: str) -> np.ndarray:
    return np.real(np.array(raw.get_trace(trace).get_wave()))


def _crossing(x: np.ndarray, y: np.ndarray, level: float, log_x: bool = False):
    """y 가 level 을 처음 지나는 x 를 선형보간으로 찾는다. 지나지 않으면 None."""
    above = y > level
    change = np.where(above[1:] != above[:-1])[0]
    if len(change) == 0:
        return None
    i = change[0]
    frac = (level - y[i]) / (y[i + 1] - y[i])
    if log_x:
        return float(10 ** (np.log10(x[i]) + frac * (np.log10(x[i + 1]) - np.log10(x[i]))))
    return float(x[i] + frac * (x[i + 1] - x[i]))


def _ratio_db(delta_cause: float, vio: np.ndarray) -> float:
    """원인을 delta_cause 만큼 움직였을 때 입력 오프셋이 변한 폭(최댓값-최솟값)에 대한 비 [dB]."""
    return float(20 * np.log10(abs(delta_cause) / (vio.max() - vio.min())))


def measure_opamp(name: str) -> dict:
    """OP-Amp 의 테스트벤치 5종을 조건별로 돌려 측정값을 모은다 (SI 단위, 각도는 도)."""
    vdd = OPAMP_VDD
    result = {}

    def servo(tag: str, analysis: str, rl: str) -> RawRead:
        return run(build_netlist(name, "dc", tag, vdd=vdd, rl=rl, analysis_line=analysis))

    def input_offset(raw: RawRead) -> np.ndarray:
        return _wave(raw, "v(inp)") - _wave(raw, "v(inn)")

    # 공급 전류: 무부하, VO = VDD/2
    raw = servo("idd", ".op", OPAMP_NO_LOAD)
    result["idd"] = float(-_wave(raw, "i(vdd)")[0])
    result["vio_systematic"] = float(input_offset(raw)[0])

    # 대신호 이득: 출력을 VDD/2 ± 1.25 V 로 움직일 때 입력 오프셋의 변화
    swing = OPAMP_AVD_SWING
    raw = servo("avd", f".dc VREF {-swing} {swing} 0.05", OPAMP_AVD_RL)
    result["avd"] = _ratio_db(2 * swing, input_offset(raw))

    # CMRR: 공통모드 입력을 0 ~ VDD - 1.35 V 로 움직일 때 입력 오프셋의 변화
    vic_low, vic_high = OPAMP_VIC_LOW - vdd / 2, vdd / 2 - OPAMP_VIC_HIGH_BELOW_VDD
    raw = servo("cmrr", f".dc VIC {vic_low:.4g} {vic_high:.4g} 0.05", OPAMP_NO_LOAD)
    result["cmrr"] = _ratio_db(vic_high - vic_low, input_offset(raw))

    # PSRR: 전원을 움직일 때 입력 오프셋의 변화 (입력과 출력은 VDD/2 를 따라간다)
    v_low, v_high = OPAMP_PSRR_VDD
    raw = servo("psrr", f".dc VDD {v_low} {v_high} 0.1", OPAMP_NO_LOAD)
    result["psrr"] = _ratio_db(v_high - v_low, input_offset(raw))

    # 개방루프 주파수 응답: 단위이득 대역폭, 위상여유, 이득여유
    raw = run(build_netlist(name, "ac", vdd=vdd, rl=OPAMP_AC_RL, cl=OPAMP_AC_CL, f_start=ac_start()))
    freq = np.real(np.array(raw.get_axis()))
    gain = np.array(raw.get_trace("v(out)").get_wave())
    mag_db = 20 * np.log10(np.abs(gain))
    phase = np.degrees(np.unwrap(np.angle(gain)))
    result.update(freq=freq, mag_db=mag_db, phase=phase, gain_dc=float(mag_db[0]))
    ugbw = _crossing(freq, mag_db, 0.0, log_x=True)
    result["ugbw"] = ugbw
    result["pm"] = None if ugbw is None else float(180 + np.interp(np.log10(ugbw), np.log10(freq), phase))
    f180 = _crossing(freq, phase, -180.0, log_x=True)
    result["gm"] = None if f180 is None else float(-np.interp(np.log10(f180), np.log10(freq), mag_db))

    # 슬루율: 단위이득 버퍼, 출력 계단의 10% ~ 90% 구간 기울기 (오르내림 중 느린 쪽)
    low, high = OPAMP_SLEW_LEVELS
    raw = run(build_netlist(name, "slew", vdd=vdd, rl=OPAMP_SLEW_RL, cl=OPAMP_SLEW_CL, v_low=low, v_high=high,
                            **_times(2e-6, 10e-6, 20e-6, 22e-6)))
    t, out = np.real(np.array(raw.get_axis())), _wave(raw, "v(out)")
    lo10, hi90 = low + 0.1 * (high - low), low + 0.9 * (high - low)
    up = t < OPAMP_SLEW_FALL_TIME * max(TIME_SCALE, 1.0)
    result.update(slew_t=t, slew_out=out, sr_rise=None, sr_fall=None, sr=None)
    rise_edges = (_crossing(t[up], out[up], lo10), _crossing(t[up], out[up], hi90))
    fall_edges = (_crossing(t[~up], out[~up], hi90), _crossing(t[~up], out[~up], lo10))
    if None not in rise_edges and None not in fall_edges:  # 출력이 10% ~ 90% 구간을 다 지난 경우만
        result["sr_rise"] = (hi90 - lo10) / (rise_edges[1] - rise_edges[0])
        result["sr_fall"] = (hi90 - lo10) / (fall_edges[1] - fall_edges[0])
        result["sr"] = min(result["sr_rise"], result["sr_fall"])

    # 정착시간: 반전 증폭기에 1 V 계단, 최종값의 ±0.1% 안으로 들어와 머무는 시각
    raw = run(build_netlist(name, "settle", vdd=vdd, rl=OPAMP_SETTLE_RL, cl=OPAMP_SETTLE_CL,
                            **_times(2e-6, 20e-6, 40e-6, 20e-6)))
    t, out = np.real(np.array(raw.get_axis())), _wave(raw, "v(out)")
    final = float(out[t > 0.9 * t[-1]].mean())
    outside = np.where(np.abs(out - final) > OPAMP_SETTLE_BAND)[0]
    result["ts"] = float(t[min(outside[-1] + 1, len(t) - 1)] - OPAMP_STEP_TIME * max(TIME_SCALE, 1.0))
    result.update(settle_t=t, settle_out=out)

    # 출력 구동: 입력을 벌려 출력을 레일로 몰고 부하를 건다
    def drive(tag: str, vid: float, load: str) -> RawRead:
        return run(build_netlist(name, "drive", tag, vdd=vdd, vid=vid, load=load))

    over = OPAMP_OVERDRIVE
    for tag, current in (("1ma", "1m"), ("5ma", "5m")):
        result[f"voh_{tag}"] = float(_wave(drive(f"voh_{tag}", over, f"ILOAD OUT 0 DC {current}"), "v(out)")[0])
        result[f"vol_{tag}"] = float(_wave(drive(f"vol_{tag}", -over, f"ILOAD OUT 0 DC -{current}"), "v(out)")[0])
    raw = drive("io_source", over, f"VFORCE OUT 0 DC {vdd - OPAMP_RAIL_OFFSET}")
    result["io_source"] = float(_wave(raw, "i(vforce)")[0])
    raw = drive("io_sink", -over, f"VFORCE OUT 0 DC {OPAMP_RAIL_OFFSET}")
    result["io_sink"] = float(-_wave(raw, "i(vforce)")[0])
    return result


# 회로 종류(.subckt 이름) -> 측정 함수. 돌려주는 키가 스펙 파일의 measure와 이어진다.
MEASURERS = {
    "cascode": measure_cascode,
    "opamp": measure_opamp,
}


def evaluate(name: str) -> dict:
    """설계 하나를 시뮬레이션하고 측정값을 돌려준다."""
    kind = circuit_kind(name)
    if kind not in MEASURERS:
        raise ValueError(f"회로 종류 '{kind}' 의 측정 함수가 없습니다. MEASURERS 에 등록하세요.")
    result = MEASURERS[kind](name)
    result["name"] = name
    return result


# ---------------------------------------------------------------
# 스펙 읽기와 판정
# ---------------------------------------------------------------
def load_spec(path: Path) -> dict:
    """스펙 파일을 읽는다. 형식은 spec_cascode.json 의 description 참고.
    OP-Amp 스펙이면 그 칩의 공통모드 입력 범위를 측정 범위로 정한다 (set_cm_range_from_spec)."""
    spec = json.loads(Path(path).read_text(encoding="utf-8"))
    if spec.get("circuit") == "opamp":
        set_cm_range_from_spec(spec)
        set_loads_from_spec(spec)
    return spec


def _spice_value(number: str, prefix: str) -> str:
    """'2', 'k' -> '2k'. SPICE 에서 M 은 밀리라서 메가는 'meg' 로 쓴다."""
    return number + {"M": "meg", "µ": "u", "μ": "u"}.get(prefix, prefix.lower() if prefix in "kKpPnNuU" else prefix)


def parse_load(condition: str) -> tuple:
    """항목 조건 문장 -> (RL, CL) SPICE 값. 없으면 None. 'RL = 2 kΩ' -> '2k', 'RL ≥ 10kΩ' -> '10k', 'CL = 200 pF' -> '200p'."""
    c = (condition or "").replace("Ω", "ohm")
    rl = re.search(r"R\s*L(?:OAD)?\s*(?:=|≥|>=|>)\s*([\d.]+)\s*([kKM]?)\s*(?:ohm)?", c)
    cl = re.search(r"C\s*L(?:OAD)?\s*(?:=|≥|>=|>|≤|<=)?\s*([\d.]+)\s*([pnuµμ]?)\s*F", c)
    return (_spice_value(*rl.groups()) if rl else None, _spice_value(*cl.groups()) if cl else None)


def set_loads_from_spec(spec: dict) -> dict:
    """스펙 항목 조건의 부하로 측정 부하를 정한다 (없으면 기본값 _DEFAULT_LOADS).
    이득은 avd 조건의 RL, 대역폭·위상여유는 ugbw/pm 조건의 RL·CL (CL 만 있으면 RL 은 무부하), 슬루율 sr, 정착시간 ts.
    전에는 모든 칩에 고정 부하를 써서 LMV321 이득을 데이터시트 조건(RL = 2 kΩ)이 아닌 10 kΩ 으로 쟀다
    (우리 85 dB, 하네스 73 dB, 2026-11-27). 초저전력 칩은 2 kΩ 을 구동 못 하므로 데이터시트 부하로 재야 한다."""
    global OPAMP_AVD_RL, OPAMP_AC_RL, OPAMP_AC_CL, OPAMP_SLEW_RL, OPAMP_SLEW_CL, OPAMP_SETTLE_RL, OPAMP_SETTLE_CL
    loads = dict(_DEFAULT_LOADS)
    conds = {s.get("measure"): s.get("condition") or "" for s in spec.get("specs", [])}
    for measure, prefix in (("avd", "avd"), ("ugbw", "ac"), ("pm", "ac"), ("sr", "slew"), ("ts", "settle")):
        if measure not in conds:
            continue
        rl, cl = parse_load(conds[measure])
        if rl is None and cl is None:
            continue
        if prefix == "avd":
            loads["avd_rl"] = rl or loads["avd_rl"]
        elif (rl or cl) and loads[f"{prefix}_rl"] == _DEFAULT_LOADS[f"{prefix}_rl"]:   # ugbw 와 pm 이 다르면 먼저 것
            loads[f"{prefix}_rl"] = rl or OPAMP_NO_LOAD
            loads[f"{prefix}_cl"] = cl or _DEFAULT_LOADS[f"{prefix}_cl"]
    OPAMP_AVD_RL, OPAMP_AC_RL, OPAMP_AC_CL = loads["avd_rl"], loads["ac_rl"], loads["ac_cl"]
    OPAMP_SLEW_RL, OPAMP_SLEW_CL = loads["slew_rl"], loads["slew_cl"]
    OPAMP_SETTLE_RL, OPAMP_SETTLE_CL = loads["settle_rl"], loads["settle_cl"]
    spec["measure_loads"] = loads           # 결과 화면·기록용
    return loads


_V = r"([-+−–]?\s*[\d.]+)\s*V?"


def _num(text: str) -> float:
    return float(re.sub(r"\s", "", text).replace("−", "-").replace("–", "-"))


def parse_cm_range(condition: str):
    """CMRR 조건 문장 -> (아래 끝 [VSS 기준 V], 위 끝이 VDD 보다 아래인 양 [V]). 못 읽으면 None.
    읽는 모양 (데이터시트 4종에서 본 것):
      'VIC = 0 to VDD−1.35V'                         -> (0, 1.35)
      '(V–) < VCM < (V+) – 1.3 V'                    -> (0, 1.3)
      '(V–) – 0.1 V < VCM < (V+) + 0.1 V'            -> (-0.1, -0.1)
      'VCM = -0.3V to 6.3V, VDD = 6.0V'              -> (-0.3, -0.3)  (절대 전압이면 같이 적힌 VDD 로 바꿈)"""
    c = condition or ""
    m = re.search(r"\(V[-–−]\)\s*(?:([-+−–])\s*([\d.]+)\s*V)?\s*<\s*V(?:CM|IC)\s*<\s*\(V\+\)\s*(?:([-+−–])\s*([\d.]+)\s*V)?", c)
    if m:
        low = _num(m.group(1) + m.group(2)) if m.group(2) else 0.0
        high = _num(m.group(3) + m.group(4)) if m.group(4) else 0.0
        return low, -high
    m = re.search(r"V(?:IC|CM)\s*=\s*" + _V + r"\s*to\s*V(?:DD|\+|CC)\s*([-−–])\s*([\d.]+)", c)
    if m:
        return _num(m.group(1)), _num(m.group(3))
    m = re.search(r"V(?:IC|CM)\s*=\s*" + _V + r"\s*to\s*" + _V, c)
    vdd = re.search(r"V(?:DD|S)\s*=\s*\+?([\d.]+)\s*V(?!\s*to)", c)
    if m and vdd:
        return _num(m.group(1)), float(vdd.group(1)) - _num(m.group(2))
    return None


def set_cm_range_from_spec(spec: dict) -> tuple:
    """스펙의 CMRR 조건으로 OPAMP_VIC_LOW / OPAMP_VIC_HIGH_BELOW_VDD 를 정한다. 못 읽으면 기본값(TLV271)."""
    global OPAMP_VIC_LOW, OPAMP_VIC_HIGH_BELOW_VDD
    item = next((s for s in spec.get("specs", []) if s.get("measure") == "cmrr"), None)
    found = parse_cm_range(item.get("condition", "")) if item else None
    OPAMP_VIC_LOW, OPAMP_VIC_HIGH_BELOW_VDD = found or _DEFAULT_CM_RANGE
    return OPAMP_VIC_LOW, OPAMP_VIC_HIGH_BELOW_VDD


def effective_bounds(item: dict, spec: dict) -> tuple:
    """판정에 쓸 (하한, 상한, 근거). 데이터시트에 min/max가 없고 typ만 있으면 팀 기준을 적용한다."""
    low, high = item.get("min"), item.get("max")
    rule = spec.get("typ_rule")
    if low is None and high is None and rule and item.get("typ") is not None:
        if item.get("typ_rule") == "higher":
            return item["typ"] * rule["min_ratio"], None, BASIS_TEAM
        if item.get("typ_rule") == "lower":
            return None, item["typ"] * rule["max_ratio"], BASIS_TEAM
    return low, high, BASIS_DATASHEET


def spec_limit(spec: dict, measure: str, bound: str):
    """스펙 항목의 기준값(min 또는 max)을 SI 단위로 돌려준다. 없으면 None."""
    for item in spec["specs"]:
        if item["measure"] == measure:
            low, high, _ = effective_bounds(item, spec)
            value = low if bound == "min" else high
            if value is not None:
                return value / item.get("scale", 1)
    return None


def target_text(row: dict) -> str:
    """기준을 '≥ 20 dB' 같은 글로 바꾼다."""
    parts = []
    if row.get("min") is not None:
        parts.append(f"≥ {row['min']:g}")
    if row.get("max") is not None:
        parts.append(f"≤ {row['max']:g}")
    if not parts and row.get("typ") is not None:
        parts.append(f"typ {row['typ']:g}")
    return f"{', '.join(parts)} {row['unit']}"


def margin_text(value: float, low, high, unit: str) -> str:
    """스펙 경계까지 남은 여유를 글로 바꾼다."""
    parts = []
    if low is not None:
        if unit in DIFFERENCE_UNITS or low <= 0:
            parts.append(f"{value - low:+.2f} {unit}")
        else:
            parts.append(f"{(value / low - 1) * 100:+.0f}%")
    if high is not None:
        if unit in DIFFERENCE_UNITS or high <= 0:
            parts.append(f"{high - value:+.2f} {unit}")
        else:
            used = value / high * 100
            parts.append(f"{100 - used:.0f}% 남음" if used <= 100 else f"{used - 100:.0f}% 초과")
    return ", ".join(parts)


def judge(result: dict, spec: dict) -> list:
    """스펙 항목마다 측정값을 기준과 비교한다. 판정은 LLM이 아니라 여기서 한다.

    각 행: measure, label, unit, min, typ, max, basis, condition, value(표시 단위), status, margin
    min, max는 판정에 실제로 쓴 값이고, basis는 그 값이 데이터시트 값인지 팀 기준인지를 나타낸다.
    """
    rows = []
    for item in spec["specs"]:
        low, high, basis = effective_bounds(item, spec)
        row = {key: item.get(key) for key in ("measure", "label", "unit", "typ", "condition")}
        row.update(min=low, max=high, basis=basis)
        if item.get("scope", SCOPE_TARGET) != SCOPE_TARGET:
            row.update(value=None, status=STATUS_EXCLUDED, margin=item.get("reason", ""))
        elif result.get(item["measure"]) is None:
            row.update(value=None, status=STATUS_UNMEASURED, margin="")
        else:
            value = result[item["measure"]] * item.get("scale", 1)
            if low is None and high is None:
                status = STATUS_INFO
            else:
                ok = (low is None or value >= low) and (high is None or value <= high)
                status = STATUS_PASS if ok else STATUS_FAIL
            row.update(value=value, status=status, margin=margin_text(value, low, high, item["unit"]))
        rows.append(row)
    return rows


def all_pass(rows: list) -> bool:
    """FAIL이 하나도 없고 PASS가 하나 이상이면 통과."""
    statuses = [row["status"] for row in rows]
    return STATUS_FAIL not in statuses and STATUS_PASS in statuses


def save_result(name: str, spec_file: Path, result: dict, rows: list) -> Path:
    """판정 결과를 sim_out/NAME_result.json 에 남긴다 (재설계 단계와 화면이 읽는 자료)."""
    path = OUT_DIR / f"{name}_result.json"
    record = {
        "design": name,
        "spec_file": Path(spec_file).name,
        "all_pass": all_pass(rows),
        "items": rows,
        "measured": {key: value for key, value in result.items() if isinstance(value, (int, float))},
    }
    path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    # 화면이 그래프를 그릴 수 있도록 파형도 남긴다 (점이 많으면 CURVE_MAX_POINTS 개로 솎는다)
    curves = {}
    for key, value in result.items():
        if isinstance(value, np.ndarray):
            step = max(1, len(value) // CURVE_MAX_POINTS)
            curves[key] = [float(v) for v in value[::step]]
    (OUT_DIR / f"{name}_curves.json").write_text(json.dumps(curves), encoding="utf-8")
    return path


# ---------------------------------------------------------------
# 구조 후보 선택
# ---------------------------------------------------------------
STRUCTURE_COMMENT = "* 구조:"


def structure_note(name: str) -> str:
    """회로 파일 머리말의 '* 구조: ...' 줄에 적힌 구조 설명."""
    for line in (HERE / f"{name}.cir").read_text(encoding="utf-8").splitlines():
        if line.startswith(STRUCTURE_COMMENT):
            return line[len(STRUCTURE_COMMENT):].strip()
    return ""


def select_candidate(judged: list) -> dict:
    """후보별 판정 결과를 모아 구조를 고르고, 후보·선정 결과·근거를 한 기록으로 만든다.

    judged: (설계 이름, 판정 행 목록) 을 단순한 구조부터 적은 목록.
    규칙: 모든 항목을 통과한 후보 중 목록에서 가장 앞선(가장 단순한) 것을 고른다.
    """
    candidates = []
    for name, rows in judged:
        judged_rows = [row for row in rows if row["status"] in (STATUS_PASS, STATUS_FAIL)]
        failed = [row for row in judged_rows if row["status"] == STATUS_FAIL]
        candidates.append({
            "design": name,
            "structure": structure_note(name),
            "all_pass": all_pass(rows),
            "passed": len(judged_rows) - len(failed),
            "judged": len(judged_rows),
            "failed_items": [
                {"label": row["label"], "value": row["value"], "unit": row["unit"],
                 "target": target_text(row), "basis": row["basis"]}
                for row in failed
            ],
        })
    selected = next((c["design"] for c in candidates if c["all_pass"]), None)
    reasons = []
    for c in candidates:
        if c["design"] == selected:
            reasons.append(f"{c['design']}: 판정한 {c['judged']}개 항목을 모두 통과")
        elif c["failed_items"]:
            items = ", ".join(f"{i['label']} {i['value']:.4g} {i['unit']} (목표 {i['target']})" for i in c["failed_items"])
            reasons.append(f"{c['design']}: {len(c['failed_items'])}개 항목 미달 - {items}")
        else:
            reasons.append(f"{c['design']}: 통과했지만 더 단순한 후보가 먼저 선정됨")
    return {"candidates": candidates, "selected": selected, "reasons": reasons}


def print_selection(selection: dict) -> None:
    """구조 선택 과정을 후보, 선정 결과, 근거 순으로 출력한다."""
    print("\n" + "=" * 72)
    print("구조 선택")
    print("=" * 72)
    print("[후보]")
    for c in selection["candidates"]:
        print(f"  {c['design']}: {c['structure']}")
        print(f"      통과 {c['passed']} / {c['judged']}")
    print("[선정 결과]")
    print(f"  {selection['selected'] or '통과한 후보 없음 (재설계 필요)'}")
    print("[근거]")
    for reason in selection["reasons"]:
        print(f"  {reason}")


# ---------------------------------------------------------------
# 출력
# ---------------------------------------------------------------
def print_spec_table(name: str, rows: list) -> bool:
    """스펙 충족 여부 표를 출력하고 전체 PASS 여부를 돌려준다."""
    print("\n" + "=" * 72)
    print(f"[{name}] 스펙 충족 여부")
    print("=" * 72)
    for row in rows:
        value = "-" if row["value"] is None else f"{row['value']:.4g} {row['unit']}"
        print(f"{row['label']:12s}: {value:>14s}  (목표 {target_text(row)})  [{row['status']}]  {row['margin']}")
    print("-" * 72)
    passed = all_pass(rows)
    print("전체 결과:", "PASS (스펙 만족)" if passed else "FAIL (재설계 필요 -> 결과를 LLM에게 다시 보여주고 개선 요청)")
    return passed


def print_comparison(results: list) -> None:
    """여러 설계의 주요 값을 나란히 출력한다. 마지막 열은 첫 설계 대비 비율."""
    rows = [
        ("DC 전압이득 [dB]", "gain_dc", 1),
        ("-3dB 대역폭 [MHz]", "f3db", 1e-6),
        ("소비전력 [mW]", "power", 1e3),
        ("공급전류 [uA]", "id", 1e6),
        ("Vout DC [V]", "vout_dc", 1),
        ("Vx DC [V]", "vx_dc", 1),
    ]
    header = f"{'항목':18s}" + "".join(f"{r['name']:>14s}" for r in results) + f"{'비율':>10s}"
    print("\n" + "=" * len(header))
    print("설계 비교")
    print("=" * len(header))
    print(header)
    for label, key, scale in rows:
        values = [r[key] * scale for r in results]
        ratio = values[-1] / values[0] if values[0] else float("nan")
        print(f"{label:18s}" + "".join(f"{v:>14.4g}" for v in values) + f"{ratio:>10.3g}")


def save_bode(results: list, spec: dict, png_path: Path) -> None:
    """설계별 주파수 응답을 한 그래프에 겹쳐 그리고 스펙 경계선을 표시한다."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(7.5, 4.8))
    for r in results:
        if "f3db" in r:
            label = (f"{r['name']}: {r['gain_dc']:.1f} dB, "
                     f"{r['f3db'] / 1e6:.2f} MHz, {r['power'] * 1e3:.2f} mW")
        else:
            label = f"{r['name']}: {r['gain_dc']:.1f} dB"
        line, = ax.semilogx(r["freq"], r["mag_db"], linewidth=1.8, label=label)
        if "f3db" in r:
            ax.plot(r["f3db"], r["gain_dc"] - 3, "o", color=line.get_color())
    gain_min = spec_limit(spec, "gain_dc", "min")
    bw_min = spec_limit(spec, "f3db", "min")
    if gain_min is not None:
        ax.axhline(gain_min, linestyle="--", linewidth=1, color="gray", label=f"gain spec ({gain_min:g} dB)")
    if bw_min is not None:
        ax.axvline(bw_min, linestyle=":", linewidth=1, color="gray", label=f"BW spec ({bw_min / 1e6:g} MHz)")
    ax.set_xlabel("Frequency (Hz)")
    ax.set_ylabel("Gain (dB)")
    ax.set_title("Frequency Response (o: -3dB point)")
    ax.grid(True, which="both", linewidth=0.3)
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(png_path, dpi=150)
    print(f"\nBode plot 저장: {png_path}")


def main():
    parser = argparse.ArgumentParser(description="회로 스펙 체크 / 설계 비교")
    parser.add_argument("designs", nargs="*", default=["cascode"],
                        help="설계 이름 (NAME.cir 사용). 여러 개면 비교")
    parser.add_argument("--spec", type=Path,
                        help="스펙 파일. 생략하면 회로 종류에 맞는 spec_<종류>.json")
    parser.add_argument("--select", action="store_true",
                        help="설계들을 구조 후보로 보고(단순한 것부터 적는다) 하나를 선정해 근거와 함께 보여준다")
    args = parser.parse_args()

    if shutil.which(NGSPICE_EXE) is None:
        raise FileNotFoundError(
            "ngspice를 찾을 수 없습니다. WSL Ubuntu에서 "
            "`sudo apt install -y ngspice` 로 설치하세요."
        )

    results, judged = [], []
    for name in args.designs:
        spec_file = args.spec or spec_path(name)
        spec = load_spec(spec_file)
        result = evaluate(name)
        rows = judge(result, spec)
        print_spec_table(name, rows)
        print(f"판정 결과 저장: {save_result(name, spec_file, result, rows)}")
        results.append(result)
        judged.append((name, rows))
    if args.select:
        selection = select_candidate(judged)
        print_selection(selection)
        selection_path = OUT_DIR / "selection.json"
        selection_path.write_text(json.dumps(selection, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"선택 기록 저장: {selection_path}")
    if len(results) > 1 and all("f3db" in r for r in results):  # 비교표는 캐스코드 측정값 기준
        print_comparison(results)
    save_bode(results, spec, HERE / "bode_plot.png")


if __name__ == "__main__":
    main()
