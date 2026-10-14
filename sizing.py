"""
OP-Amp B 의 소자 크기와 예상 성능을 식으로 계산한다 (SymPy).

역할 분담: 설계 선택(전류, gm/ID, 채널 길이, 보상 커패시터)은 사람이나 LLM 이 정하고,
그 선택에서 W 와 예상 성능을 구하는 계산은 전부 여기서 한다. LLM 은 숫자를 직접 계산하지 않는다.

    선택 (choices)  --SymPy 식 + 소자 특성표-->  소자 크기 (sizes), 예상 성능 (predicted)
    소자 크기       --회로 틀(opamp_b.template)--> 회로 파일 (NAME.cir)

사용법 (WSL, 프로젝트 폴더에서):
    ~/.venvs/edai/bin/python sizing.py          # 기준 선택으로 계산한 값과 식을 출력

예상 성능은 소신호 근사식이라 시뮬레이션과 차이가 난다. 차이는 판정에 쓰지 않고,
"식으로 본 예상"과 "시뮬레이션 결과"를 나란히 보여주는 데 쓴다. 판정은 항상 시뮬레이션으로 한다.
"""

import json
import math
import re
from pathlib import Path

import sympy as sp

import device_table
import run_sim

TEMPLATE_FILE = run_sim.HERE / "opamp_b.template"

# ---- 회로 틀에 고정된 값 (opamp_b.template 과 맞춘다) ----
I_REF = 10e-6            # 기준 전류의 설계값. 미러 한 칸(pfet 24u/2u, nfet 11.5u/2u)이 흘리는 전류
I_CASCODE = 20e-6        # 폴디드 캐스코드 가지 하나의 전류 (위쪽 미러 pfet 48u/2u)
BIAS_BRANCHES = 6        # 기준 전류 회로 2 + 캐스코드 바이어스 2 + class-AB 바이어스 2
I_STARTUP = 1.5e-6       # 기동 회로 저항이 쓰는 전류
L_MIRROR_UM = 2.0        # 전류원·미러 소자의 채널 길이
GM_ID_CASCODE = 10.0     # 캐스코드 소자의 gm/ID
OUTPUT_N = {"squares": 129.0, "length_um": 1.0}    # MON: 평소 전류 150 uA 기준 W/L
OUTPUT_P = {"squares": 228.6, "length_um": 0.7}    # MOP
MAX_FINGER_UM = 50.0     # 한 소자의 최대 폭. 이보다 넓으면 같은 소자 여러 개(m)로 나눈다 (모델의 폭 한계 100 um)
IQ_NOMINAL = 150e-6      # class-AB 바이어스 복제 소자가 맞춰 둔 평소 전류
LOAD_AVD = 10e3          # 이득 조건의 부하 저항

# ---- 설계 선택의 허용 범위 (LLM 이 낸 값은 이 안으로 맞춘 뒤 계산한다) ----
CHOICE_RANGES = {
    # label 은 화면에 보여줄 쉬운 말 이름, meaning 은 LLM 에 알려주는 정확한 뜻
    "i_tail_ua": {"choices": (20, 40, 60, 80), "meaning": "입력단 꼬리 전류 [uA]",
                  "label": "입력단에 흘리는 전류", "unit": "uA"},
    "gm_id_in": {"min": 8.0, "max": 18.0, "meaning": "입력 트랜지스터의 gm/ID [1/V]",
                 "label": "입력 트랜지스터의 효율 (gm/ID)", "unit": "1/V"},
    "l_in_um": {"choices": (0.7, 1.0, 2.0, 4.0), "meaning": "입력 트랜지스터의 채널 길이 [um]",
                "label": "입력 트랜지스터의 길이", "unit": "um"},
    "l_casc_um": {"choices": (1.0, 2.0, 4.0), "meaning": "캐스코드 트랜지스터의 채널 길이 [um]",
                  "label": "이득을 높이는 보조 트랜지스터의 길이", "unit": "um"},
    "cc_pf": {"min": 1.0, "max": 8.0, "meaning": "Miller 보상 커패시터 하나의 값 [pF] (위, 아래 2개)",
              "label": "안정화용 커패시터", "unit": "pF"},
    "iq_out_ua": {"min": 80.0, "max": 300.0, "meaning": "출력단 평소 전류 [uA] (출력 소자의 폭이 이 값에 비례)",
                  "label": "출력단에 평소 흘리는 전류", "unit": "uA"},
}
# opamp_b.cir (손으로 설계한 값)에 해당하는 선택
BASELINE_CHOICES = {"i_tail_ua": 40, "gm_id_in": 12.6, "l_in_um": 1.0, "l_casc_um": 2.0, "cc_pf": 3.0, "iq_out_ua": 150.0}

# ---- 식 (SymPy 기호) ----
I_tail, gmid_in, L_in, J_in, W_in = sp.symbols("I_tail gmid_in L_in J_in W_in", positive=True)
C_c, R_L, I_q, I_c = sp.symbols("C_c R_L I_q I_c", positive=True)
A_in, A_nc, A_pc, A_sink, A_top, A_on, A_op = sp.symbols("A_in A_nc A_pc A_sink A_top A_on A_op", positive=True)
gmid_sink, gmid_top, gmid_on, gmid_op = sp.symbols("gmid_sink gmid_top gmid_on gmid_op", positive=True)

gm_in = gmid_in * I_tail / 2                         # 입력 트랜지스터의 gm
g_in = gm_in / A_in                                  # 입력 트랜지스터의 출력 컨덕턴스 (gm / 고유이득)
g_sink = gmid_sink * (I_tail / 2 + I_c) / A_sink     # 아래 전류원
g_top = gmid_top * I_c / A_top                       # 위 미러
R_n = A_nc / (g_sink + g_in)                         # 아래에서 본 저항 (캐스코드가 고유이득만큼 키움)
R_p = A_pc / g_top                                   # 위에서 본 저항
gm_out = (gmid_on + gmid_op) * I_q                   # 출력 소자 둘의 gm 합
g_out = gmid_on * I_q / A_on + gmid_op * I_q / A_op + 1 / R_L

EQUATIONS = {
    # 이름: (식, 설명)
    "w_in": (sp.Eq(I_tail / 2, J_in * W_in / L_in), "입력 트랜지스터 폭: 전류 = 전류밀도 x (W/L)"),
    "a1": (gm_in * R_n * R_p / (R_n + R_p), "1단 이득 = gm x (위, 아래 저항의 병렬)"),
    "a2": (gm_out / g_out, "2단 이득 = 출력 소자 gm 합 / (출력 컨덕턴스 + 1/RL)"),
    "ugbw": (gm_in / (2 * sp.pi * 2 * C_c), "단위이득 대역폭 = gm / (2π x 보상 커패시터 합)"),
    "sr": (I_tail / (2 * C_c), "슬루율 = 꼬리 전류 / 보상 커패시터 합"),
}


def normalize_choices(raw: dict) -> tuple:
    """선택값을 허용 범위 안으로 맞춘다. (맞춘 선택, 고친 내용 목록)을 돌려준다."""
    choices, notes = {}, []
    for key, rule in CHOICE_RANGES.items():
        if key not in raw:
            choices[key] = BASELINE_CHOICES[key]
            notes.append(f"{key}: 값이 없어 기준값 {BASELINE_CHOICES[key]} 사용")
            continue
        try:
            value = float(raw[key])
        except (TypeError, ValueError):
            choices[key] = BASELINE_CHOICES[key]
            notes.append(f"{key}: 숫자가 아니어서 기준값 {BASELINE_CHOICES[key]} 사용")
            continue
        if "choices" in rule:
            fixed = min(rule["choices"], key=lambda allowed: abs(allowed - value))
        else:
            fixed = min(max(value, rule["min"]), rule["max"])
        if not math.isclose(fixed, value):
            notes.append(f"{key}: {value:g} -> {fixed:g} (허용 범위에 맞춤)")
        choices[key] = fixed
    return choices, notes


def size_opamp(raw_choices: dict) -> dict:
    """선택에서 소자 크기와 예상 성능을 계산한다."""
    choices, notes = normalize_choices(raw_choices)
    table = device_table.load_table()
    i_tail, i_q, cc = choices["i_tail_ua"] * 1e-6, choices["iq_out_ua"] * 1e-6, choices["cc_pf"] * 1e-12

    look_in = device_table.lookup(table, "p", choices["l_in_um"], choices["gm_id_in"])
    look_nc = device_table.lookup(table, "n", choices["l_casc_um"], GM_ID_CASCODE)
    look_pc = device_table.lookup(table, "p", choices["l_casc_um"], GM_ID_CASCODE)

    def fixed_device(kind: str, squares: float, length_um: float, current: float) -> tuple:
        """크기가 고정된 소자가 current 를 흘릴 때의 (gm/ID, 고유이득). 전류 밀도로 표를 거꾸로 찾는다."""
        rows = table["devices"][kind][str(float(length_um))]
        density = current / squares
        # 전류 밀도 j 는 gm/ID 가 커질수록 작아지므로, 뒤집어서 보간한다
        gm_id = float(sp.Float(_interp_descending(density, rows["j"], rows["gm_id"])))
        return gm_id, device_table.lookup(table, kind, length_um, gm_id)["gm_gds"]

    sink_gmid, sink_gain = fixed_device("n", 11.5 / L_MIRROR_UM, L_MIRROR_UM, I_REF)
    top_gmid, top_gain = fixed_device("p", 24.0 / L_MIRROR_UM, L_MIRROR_UM, I_REF)
    on_gmid, on_gain = fixed_device("n", OUTPUT_N["squares"], OUTPUT_N["length_um"], IQ_NOMINAL)
    op_gmid, op_gain = fixed_device("p", OUTPUT_P["squares"], OUTPUT_P["length_um"], IQ_NOMINAL)

    # 입력 트랜지스터 폭: 식을 W 에 대해 푼다
    width_in = sp.solve(EQUATIONS["w_in"][0], W_in)[0].subs(
        {I_tail: i_tail, J_in: look_in["j"], L_in: choices["l_in_um"] * 1e-6})
    values = {
        I_tail: i_tail, gmid_in: choices["gm_id_in"], C_c: cc, R_L: LOAD_AVD, I_q: i_q, I_c: I_CASCODE,
        A_in: look_in["gm_gds"], A_nc: look_nc["gm_gds"], A_pc: look_pc["gm_gds"],
        A_sink: sink_gain, A_top: top_gain, A_on: on_gain, A_op: op_gain,
        gmid_sink: sink_gmid, gmid_top: top_gmid, gmid_on: on_gmid, gmid_op: op_gmid,
    }
    a1 = float(EQUATIONS["a1"][0].subs(values))
    a2 = float(EQUATIONS["a2"][0].subs(values))
    scale = i_q / IQ_NOMINAL
    total_widths_um = {
        "in": float(width_in) * 1e6,
        "nc": I_CASCODE / look_nc["j"] * choices["l_casc_um"],
        "pc": I_CASCODE / look_pc["j"] * choices["l_casc_um"],
        "on": OUTPUT_N["squares"] * OUTPUT_N["length_um"] * scale,
        "op": OUTPUT_P["squares"] * OUTPUT_P["length_um"] * scale,
    }
    sizes = {
        "m_tail": int(round(i_tail / I_REF)),
        "m_sink": int(round((i_tail / 2 + I_CASCODE) / I_REF)),
        "l_in": choices["l_in_um"],
        "l_casc": choices["l_casc_um"],
        "cc": round(choices["cc_pf"], 3),
    }
    for key, total in total_widths_um.items():
        fingers = max(1, math.ceil(total / MAX_FINGER_UM))
        sizes[f"w_{key}"], sizes[f"m_{key}"] = round(total / fingers, 2), fingers
    predicted = {
        "avd": 20 * math.log10(a1 * a2),
        "ugbw": float(EQUATIONS["ugbw"][0].subs(values)),
        "sr": float(EQUATIONS["sr"][0].subs(values)),
        "idd": BIAS_BRANCHES * I_REF + I_STARTUP + i_tail + 2 * I_CASCODE + i_q,
    }
    return {
        "choices": choices,
        "range_notes": notes,
        "sizes": sizes,
        "predicted": predicted,
        "intermediate": {"gm_in": float(gm_in.subs(values)), "a1_db": 20 * math.log10(a1), "a2_db": 20 * math.log10(a2),
                         "vgs_in": look_in["vgs"],
                         "total_widths_um": {key: round(value, 2) for key, value in total_widths_um.items()}},
    }


def _interp_descending(x: float, xs: list, ys: list) -> float:
    """xs 가 내림차순일 때의 선형 보간."""
    import numpy as np
    return float(np.interp(x, xs[::-1], ys[::-1]))


def write_circuit(name: str, sizes: dict) -> Path:
    """회로 틀의 빈칸에 소자 크기를 채워 NAME.cir 을 만든다."""
    lines = []
    for line in TEMPLATE_FILE.read_text(encoding="utf-8").splitlines():
        if not line.lstrip().startswith("*"):
            for key, value in sizes.items():
                line = line.replace("{" + key + "}", f"{value:g}")
            left = re.findall(r"\{\w+\}", line)
            if left:
                raise ValueError(f"{TEMPLATE_FILE.name} 의 {left} 자리에 넣을 값이 없습니다.")
        lines.append(line)
    text = "\n".join(lines) + "\n"
    text = text.replace("* OP-Amp 후보 B - 회로 틀 (중괄호 자리의 소자 크기는 sizing.py 가 계산해서 채운다)",
                        f"* {name} - OP-Amp 후보 B 구조에 sizing.py 가 계산한 소자 크기를 채운 회로")
    text = text.replace("* 이 파일을 직접 시뮬레이션하지 않는다. sizing.py 가 값을 채워 만든 .cir 파일을 쓴다.\n",
                        "* 이 파일은 자동으로 만들어진다. 손으로 고치면 다음 실행에서 덮어쓴다.\n")
    path = run_sim.HERE / f"{name}.cir"
    path.write_text(text, encoding="utf-8")
    return path


def equations_text() -> list:
    """화면과 기록에 보여줄 식 목록 (이름, 식, 설명)."""
    rows = []
    for key, (expr, meaning) in EQUATIONS.items():
        text = f"{sp.sstr(expr.lhs)} = {sp.sstr(expr.rhs)}" if isinstance(expr, sp.Equality) else sp.sstr(expr)
        rows.append({"name": key, "equation": text, "meaning": meaning})
    return rows


if __name__ == "__main__":
    result = size_opamp(BASELINE_CHOICES)
    print("[식]")
    for row in equations_text():
        print(f"  {row['name']:5s} {row['meaning']}\n        {row['equation']}")
    print("[선택]", json.dumps(result["choices"], ensure_ascii=False))
    print("[소자 크기]", json.dumps(result["sizes"], ensure_ascii=False))
    p = result["predicted"]
    print(f"[예상 성능] 이득 {p['avd']:.1f} dB, 대역폭 {p['ugbw'] / 1e6:.2f} MHz, "
          f"슬루율 {p['sr'] / 1e6:.2f} V/us, 공급 전류 {p['idd'] * 1e6:.0f} uA")
    print("[중간값]", json.dumps(result["intermediate"], ensure_ascii=False))
