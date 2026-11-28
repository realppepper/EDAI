"""
실패한 구조 고치기 (규칙 + LLM): 모델 후보가 크기 정하기·측정에서 하나도 동작하지 않으면 고쳐 본다.
고친 회로는 시뮬레이션으로 다시 확인해서 동작할 때만 받아들인다.

    1. 후보 고르기: 실패 이유가 가벼운 순서(REASON_WEIGHT, 그다음 문제 소자 수)로 MAX_CANDIDATES 개
    2. 규칙 먼저: data/structure_rules.json 에서 이 구조의 특징(structure_blocks.features)에 맞는 규칙을
       LLM 을 부르지 않고 적용해 본다 (정식 규칙 먼저). 결과는 규칙의 통한 횟수에 반영 (structure_rules.py)
    3. 그래도 실패면 LLM: 실패 정보(블록 나누기, 소자별 동작점과 노드 전압, 바이어스, 스펙) + 지난 시도 + 규칙·경험
       -> LLM 이 {"diagnosis", "action"} 으로 답 -> 적용 -> 크기 정하기·측정 -> 다음 시도에 넘김
       방법은 블록 단위 다시 조합이 중심 (바이어스 회로 바꾸기, 입력단·출력단·보상 바꾸기, 블록 모음으로 새로 조합)
    4. LLM 이 고쳐서 동작하면, LLM 이 그 고치기를 "조건 -> 블록 변환" 규칙으로 써서 규칙 모음에 후보로 넣는다
    5. 동작하는 회로는 selection_dev.json 에 새 후보(how = "rule_fix" 또는 "llm_fix")로 넣고,
       모델 재학습용으로 data/fixed_structures.json 에도 모은다

LLM 은 analogverifier 의 LLMClient (NVIDIA 키, .env) 로 부른다. 모델은 DOCTOR_MODELS 순서로 (안 되면 다음 것).
Claude 는 부르지 않는다. 칩마다 다른 값은 넣지 않는다 (설명은 모든 칩에 같은 일반 지식).

기록: <실행 폴더>/doctor.json (시도 요약), <실행 폴더>/doctor/NN.json (LLM 에 보낸 내용과 받은 답 원문)
"""

import json
import os
import re
import sys
import time
from pathlib import Path

import structure_blocks as sb
import structure_rules

HERE = Path(__file__).resolve().parent
EXPERIENCE_FILE = HERE / "data" / "structure_experience.json"
FIXED_FILE = HERE / "data" / "fixed_structures.json"      # 고쳐서 동작한 구조 (모델 재학습용)
MAX_CANDIDATES = 3          # 고쳐 볼 후보 수
MAX_TRIES = 4               # 후보 하나에 LLM 에 묻는 횟수
MAX_RULES_TRIED = 3         # 후보 하나에 자동으로 적용해 보는 규칙 수
MAX_FIXED = 1               # 이만큼 고치면 멈춤
GOOD_PASS_RATIO = 0.5       # 동작해도 스펙 통과가 이 비율보다 낮으면 더 고쳐 본다 (동작만 하고 0/8 이던 경우, 2026-11-23)
EXPERIENCE_IN_PROMPT = 12   # 프롬프트에 넣는 지난 경험 수
CURRENT_RANGE = (5e-6, 100e-6)     # 전류원 하나의 전류 [A]
SCALE_RANGE = (1.0, 100.0)         # 출력단 배율
LLM_TAG = "edai_structure_doctor"
# 진단은 큰 모델로 (태그만 주면 4B 짜리 빠른 모델로 가서 답이 약했음, 2026-11-22). 쉼표로 바꿀 수 있음
# 공급자(LLM_PROVIDER)마다 큰 모델 먼저, 안 되면 작은 모델. EDAI_DOCTOR_MODELS 를 주면 그것을 쓴다
PROVIDER_DOCTOR_MODELS = {
    "nim": "nvidia/nemotron-3-ultra-550b-a55b,nvidia/nemotron-3.5-lightning-30b-a3b",
    "openrouter": "anthropic/claude-haiku-5.5,deepseek/deepseek-v4.1-flash",
    "groq": "openai/gpt-oss-120b,qwen/qwen3.8-27b",
}


def doctor_models() -> list:
    provider = (os.environ.get("LLM_PROVIDER") or "nim").lower()
    text = os.environ.get("EDAI_DOCTOR_MODELS") or PROVIDER_DOCTOR_MODELS.get(provider, PROVIDER_DOCTOR_MODELS["nim"])
    return [m.strip() for m in text.split(",") if m.strip()]


DOCTOR_MODELS = doctor_models()
NET_NAME = re.compile(r"^(N\d+|IN1|IN2|OUT|VDD|VSS|VB\d+|IB\d+)$")   # 구조 표에 쓸 수 있는 노드 이름
RAIL_VOLTS = {"VDD": 5.0, "VSS": 0.0}
# 실패 이유의 무게 (작을수록 고치기 쉬움): 동작점은 나왔고 소자 몇 개만 문제인 경우부터
REASON_WEIGHT = [("포화 영역", 1), ("무부하 이득", 2), ("출력이 VCM", 3), ("측정 실패", 3), ("꺼진 소자", 4),
                 ("전원 켜기", 5), ("동작점 계산 실패", 7), ("바이어스 미해결", 8)]

ACTIONS = {
    # 블록 단위 다시 조합 (우선)
    "replace_bias": "delete the bias network the model drew itself and turn every gate net it supplied into a new "
                    "VB# port, so the flow biases it from its proven reference mirror. Use when OFF/TRIODE devices or "
                    "an unresolved loop sit in the model's own bias network. params: {}",
    "replace_input_stage": "replace input pair + tail + input stage with a library block; later stages are kept and "
                           "driven from the same node. params: {\"block\": \"" + "|".join(sb.INPUT_STAGES) + "\", "
                           "\"input_pair\": \"nmos|pmos\"}",
    "replace_output_stage": "replace everything after the input stage (and its compensation) with a library output "
                            "stage. params: {\"block\": \"" + "|".join(sb.OUTPUT_STAGES) + "\"}",
    "set_compensation": "replace the compensation between the input-stage output and OUT. "
                        "params: {\"type\": \"" + "|".join(sb.COMPENSATIONS) + "\"}",
    "rebuild": "throw the structure away and compose a new one from library blocks (all bias by the flow). "
               "params: {\"input_stage\": ..., \"input_pair\": \"nmos|pmos\", \"output_stage\": ..., \"compensation\": ...}",
    "flip": "complementary flip of the whole circuit (NMOS<->PMOS, VDD<->VSS). Use when the input pair type cannot "
            "cover the common-mode range, or a node needs headroom from the other rail. params: {}",
    "cascode": "add cascode devices on the high-impedance gain nodes (more gain, less headroom). params: {}",
    "edit_table": "edit single rows of the structure table. params: {\"remove\": [device names], \"add\": [rows like "
                  "\"NM9 D=N3 G=VB3 S=VSS B=VSS\" or \"R2 P=N1 N=N2\" or \"C2 P=N1 N=OUT\"], "
                  "\"change\": {\"NM3\": {\"G\": \"VB2\"}}}. Ports IN1 IN2 OUT VDD VSS; internal nets N<number>; "
                  "a new bias port VB<number> (gate only) or IB<number> (current) is biased by the flow automatically",
    "undo": "go back to the structure before your last change (when the last change made things worse). params: {}",
    # 숫자 바꾸기 (구조가 맞고 여유만 모자랄 때)
    "set_device_target": "change the sizing target of one transistor (applied to its whole mirror group). Longer L or "
                         "higher gm/ID lowers Vdsat and raises gain. params: {\"device\": \"NM2\", \"gm_id\": 4..19, "
                         "\"length_um\": 0.7|1|2|4}",
    "set_unit_current": "change the bias current of every current source (sizes scale with it, so it rarely fixes "
                        "a saturation problem). params: {\"value_ua\": 5..100}",
    "set_output_scale": "change the output-stage current scale (devices whose drain is OUT). params: {\"value\": 1..100}",
    "next_candidate": "give up on this candidate and move to the next one. params: {}",
}

# 모든 칩에 같은 일반 지식: 이 흐름이 하는 일과 실패 종류별로 물리적으로 맞는 방향
FLOW_NOTES = """HOW THE FLOW WORKS (so you know what you can change):
- The structure is split into blocks: input pair + tail, input stage (up to the first high-impedance node X),
  later stages (second stage / output stage), compensation, and the bias network the model drew itself.
- Bias ports: a VB# that only drives gates gets a diode-connected device fed from an on-chip reference mirror
  (beta-multiplier, 10 uA); a VB# driving cascode gates gets a diode stack + resistor at a computed level;
  an IB# gets a mirror current source. These flow-made bias devices are reliable. The model's OWN bias network
  is often the broken part (loops with undefined current, devices pulled into triode).
- "free loop" (unresolved bias): diode-connected nodes feed each other only through mirrors with no resistor and no
  connection to the reference, so the loop current is undefined -> replace_bias is the clean fix.
- Sizing: each transistor gets W from its current and a gm/ID + L target by role (input 12/1um, diode 8/2um,
  source 8/2um, cascode 12/1um, gain 10/1um); mirror groups share the target. Currents scale W, not voltages.
- TRIODE device (Vds < Vdsat): its drain is too close to its source. If it is in the model's bias network, replace the
  bias. If it is in the signal path, the stack is too tall for the supply or a level is wrong: change the block
  (e.g. folded instead of telescopic, other output stage), flip, or lower its Vdsat with set_device_target.
- OFF device (no current): no DC path or its gate is at the wrong level; check its gate net and the path to a rail.
- V(OUT) far from 2.5 V in unity feedback: the loop is broken or has positive feedback (input polarity is already
  tried both ways), the gain path does not reach OUT, or the output stage cannot sink/source the load.
- Unloaded gain < 20 dB: the input signal does not reach OUT through a gain stage (missing or diode-loaded node).
- Input common-mode range: an NMOS pair needs VCM well above VSS, a PMOS pair well below VDD; covering both rails
  needs rail_to_rail.
- Output swing / output current under load with low supply current: a class-A output stage needs its quiescent
  current above the load current; a push_pull (class-AB) output stage drives mA loads at small quiescent current.
- Supply current too high: lower the unit current or the output scale, or use a push_pull output stage.
- PSRR too low (measured as the input offset change while VDD is swept at DC): look for ASYMMETRY between the two
  halves of the input stage. If the input-stage output node sits near one rail while its mirror/diode counterpart
  sits near the other, one cascode device carries a much larger Vds than its partner; at high Vds it leaks
  drain-to-body current (impact ionization), which grows with VDD and unbalances the halves. Keep the input-stage
  output node at about the same level as its mirror counterpart: choose the second-stage device type so that its
  gate naturally sits near that level (e.g. a PMOS mirror load on the input stage -> PMOS second-stage driver).
  Compare the node voltages of the two halves in the transistor list.
- Prefer changing a whole block over tweaking one number: a wrong structure is never fixed by a number."""

SYSTEM_PROMPT = (
    "You are an experienced analog CMOS IC designer (GF180MCU 6 V devices, VDD = 5 V, VCM = 2.5 V). "
    "An automatic flow generated an op-amp topology, filled bias ports with real devices, sized it by gm/ID and checked "
    "the DC operating point with the output in unity-gain feedback. It failed. Diagnose the physical cause from the "
    "operating point and node voltages, decide which BLOCK is wrong, and choose ONE fix from the allowed actions. "
    "Never repeat a fix listed as already tried. Write 'diagnosis' and 'why' in Korean, short and concrete "
    "(name the block, device and node)."
)

# ---------------------------------------------------------------- 실패 정보
def fmt(x) -> str:
    return "none" if x is None else f"{x:.3f}"


def net_v(net: str, nodes: dict, vout) -> str:
    if net in RAIL_VOLTS:
        return f"{net}({RAIL_VOLTS[net]:.1f}V)"
    if net == "OUT":
        return f"OUT({fmt(vout)}V)"
    v = (nodes or {}).get(net)
    return f"{net}({v:.2f}V)" if v is not None else net


def failure_text(variant: dict, state: dict) -> str:
    """LLM 에 넘길 실패 정보 (사람이 읽어도 이해되는 글)."""
    import netlist_table as nt
    table = state["table"]
    roles = variant.get("roles") or {}
    off, triode = set(variant.get("off") or []), set(variant.get("triode") or [])
    devices, nodes, vout = variant.get("op_devices") or {}, variant.get("op_nodes") or {}, variant.get("vout")
    if variant.get("valid"):
        bad = [r for r in variant.get("spec") or [] if r["status"] != "PASS"]
        failure = (f"the circuit WORKS at DC but passes only {variant.get('passed')}/{variant.get('judged')} specs. "
                   "Failing specs (measured vs target): "
                   + "; ".join(f"{r['measure']} {r.get('value')} vs {r.get('target')}" for r in bad)
                   + ". Improve the structure for these specs (gain: cascode / folded input stage / second stage; "
                   "phase margin: compensation; output current: output stage; input range: flip / rail_to_rail)")
    else:
        failure = variant.get("reason") or "unknown"
    lines = ["STRUCTURE TABLE (one device per line):", nt.table_text(table), sb.blocks_text(table),
             f"SETTINGS: unit current {state['unit_current'] * 1e6:.0f} uA, output scale {state['scale']:g}, "
             f"target overrides {json.dumps({k: list(v) for k, v in state['targets'].items()})}",
             f"FAILURE: {failure}",
             f"V(OUT) in unity-gain feedback: {fmt(vout)} V (target 2.5 V)"]
    rows = {r["name"]: r for r in table["rows"] if r["kind"] in ("nmos", "pmos")}
    if devices:
        lines.append("TRANSISTORS (flag, role, Id uA, Vds, Vdsat, margin = Vds-Vdsat, connections with node voltages):")
        flagged = [n for n in devices if n in off or n in triode]
        for name in flagged + [n for n in devices if n not in flagged]:
            d = devices[name]
            flag = "OFF" if name in off else "TRIODE" if name in triode else "ok"
            pins = rows.get(name, {}).get("pins") or {}
            conn = " ".join(f"{p}={net_v(n, nodes, vout)}" for p, n in pins.items() if p != "B") if pins else "(added by flow)"
            if d is None:
                lines.append(f"  {name}: {flag}, no data, {conn}")
            else:
                lines.append(f"  {name}: {flag}, {roles.get(name, 'bias')}, Id {d['id'] * 1e6:.2f}, Vds {d['vds']:.3f}, "
                             f"Vdsat {d['vdsat']:.3f}, margin {d['vds'] - d['vdsat']:+.3f}, {conn}")
    else:
        lines.append("TRANSISTORS: no operating point (the flow stopped before the DC solution)")
    bias = variant.get("bias") or {}
    if bias.get("nodes"):
        lines.append("BIAS PORTS (how the flow filled them): " + ", ".join(
            f"{k}={v.get('kind')}" for k, v in bias["nodes"].items()))
    if bias.get("unresolved"):
        lines.append("UNRESOLVED BIAS: " + "; ".join(bias["unresolved"]))
    return "\n".join(lines)


def spec_text(spec: dict) -> str:
    import run_sim
    rows = [f"  {s['measure']}: min {s.get('min')} typ {s.get('typ')} max {s.get('max')} {s.get('unit')}"
            for s in spec.get("specs", [])]
    return ("TARGET SPECS:\n" + "\n".join(rows)
            + f"\nCOMMON-MODE INPUT RANGE: {run_sim.OPAMP_VIC_LOW} V .. VDD - {run_sim.OPAMP_VIC_HIGH_BELOW_VDD} V")


def reason_weight(reason: str) -> int:
    return next((w for key, w in REASON_WEIGHT if key in (reason or "")), 6)


def severity(variant: dict) -> tuple:
    """실패가 가벼운 순서: 실패 이유의 무게, 그다음 문제 소자 수."""
    return (reason_weight(variant.get("reason")), len(variant.get("off") or []) + len(variant.get("triode") or []))


# ---------------------------------------------------------------- 경험 (규칙 후보)
def load_experience() -> list:
    try:
        return json.loads(EXPERIENCE_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []


def save_experience(items: list) -> None:
    EXPERIENCE_FILE.parent.mkdir(exist_ok=True)
    EXPERIENCE_FILE.write_text(json.dumps(items, ensure_ascii=False, indent=1), encoding="utf-8")


def variant_kind(variant: dict) -> str:
    return "스펙 미달" if variant.get("valid") else failure_kind(variant.get("reason"))


def failure_kind(reason: str) -> str:
    return next((key for key, _ in REASON_WEIGHT if key in (reason or "")), reason or "알 수 없음")


def experience_text(items: list) -> str:
    if not items:
        return "PAST EXPERIENCE: none yet."
    worked = [e for e in items if e.get("worked")][-EXPERIENCE_IN_PROMPT:]
    failed = [e for e in items if not e.get("worked")][-EXPERIENCE_IN_PROMPT // 2:]
    out = ["PAST EXPERIENCE from earlier runs (failure kind -> action -> result):"]
    out += [f"  WORKED: {e['failure']} -> {e['action']} {json.dumps(e.get('params') or {})}" for e in worked]
    out += [f"  DID NOT WORK: {e['failure']} -> {e['action']} {json.dumps(e.get('params') or {})}" for e in failed]
    return "\n".join(out)


# ---------------------------------------------------------------- 방법 적용
free_name = sb.free_name


def _apply_edit(params: dict, state: dict) -> dict:
    import netlist_table as nt
    rows = {r["name"]: dict(r, pins=dict(r["pins"])) for r in state["table"]["rows"]}
    for name in params.get("remove") or []:
        if name not in rows:
            raise ValueError(f"없는 소자 {name}")
        del rows[name]
    for name, pins in (params.get("change") or {}).items():
        if name not in rows:
            raise ValueError(f"없는 소자 {name}")
        rows[name]["pins"].update(pins)
    added = nt.parse_table_text("\n".join(params.get("add") or [])) if params.get("add") else {"rows": []}
    for r in added["rows"]:
        r["name"] = free_name(r["name"], set(rows))
        rows[r["name"]] = r
    bad = sorted({n for r in rows.values() for n in r["pins"].values() if not NET_NAME.match(n)})
    if bad:
        raise ValueError(f"노드 이름 규칙에 안 맞음: {', '.join(bad)} (N숫자, IN1/IN2/OUT/VDD/VSS, VB숫자/IB숫자)")
    return nt.parse_table_text("\n".join(nt.table_text(dict(state["table"], rows=[r])).strip() for r in rows.values()))


def apply(action: dict, state: dict) -> dict:
    """방법 하나를 적용한 새 상태 {table, unit_current, scale, targets, prev}. 잘못된 답이면 ValueError."""
    import auto_size
    import cascode
    import complement
    import select_structure as ss
    kind = action.get("type")
    params = action.get("params") or {}
    new = dict(state, targets=dict(state["targets"]), prev=state)
    table = None
    if kind == "set_unit_current":
        value = float(params.get("value_ua")) * 1e-6
        if not CURRENT_RANGE[0] <= value <= CURRENT_RANGE[1]:
            raise ValueError(f"전류 {value * 1e6:g} uA 는 허용 범위(5~100 uA) 밖")
        new["unit_current"] = value
    elif kind == "set_output_scale":
        value = float(params.get("value"))
        if not SCALE_RANGE[0] <= value <= SCALE_RANGE[1]:
            raise ValueError(f"배율 {value:g} 는 허용 범위(1~100) 밖")
        new["scale"] = value
    elif kind == "set_device_target":
        device = params.get("device")
        if device not in {r["name"] for r in state["table"]["rows"]}:
            raise ValueError(f"구조 표에 없는 소자 {device} (바이어스 소자는 바꿀 수 없음)")
        gm_id, length = float(params.get("gm_id")), float(params.get("length_um"))
        if not auto_size.GM_ID_RANGE[0] <= gm_id <= auto_size.GM_ID_RANGE[1]:
            raise ValueError(f"gm/ID {gm_id:g} 는 허용 범위(4~19) 밖")
        if length not in auto_size.DEVICE_LENGTHS_UM:
            raise ValueError(f"길이 {length:g} um 는 쓸 수 없음 (0.7, 1, 2, 4 중)")
        new["targets"][device] = (gm_id, length)
    elif kind == "undo":
        if not state.get("prev"):
            raise ValueError("되돌릴 이전 구조가 없음")
        return state["prev"]
    elif kind == "flip":
        table = complement.flip(state["table"])
        new["targets"] = {complement.SWAP_PREFIX.get(k[:2], k[:2]) + k[2:]: v for k, v in state["targets"].items()}
    elif kind == "cascode":
        table, nodes = cascode.cascode(state["table"])
        if not nodes:
            raise ValueError("캐스코드를 붙일 이득 노드가 없음")
    elif kind == "replace_bias":
        table = sb.replace_bias(state["table"])
    elif kind == "replace_input_stage":
        table = sb.replace_input_stage(state["table"], params.get("block"), params.get("input_pair", "nmos"))
    elif kind == "replace_output_stage":
        table = sb.replace_output_stage(state["table"], params.get("block"))
    elif kind == "set_compensation":
        table = sb.set_compensation(state["table"], params.get("type"))
    elif kind == "rebuild":
        table = sb.rebuild(params.get("input_stage"), params.get("input_pair", "nmos"),
                           params.get("output_stage"), params.get("compensation", "none"))
    elif kind == "edit_table":
        table = _apply_edit(params, state)
    else:
        raise ValueError(f"메뉴에 없는 방법 {kind}")
    if table is not None:
        problems = ss.rule_problems(table)
        if problems:
            raise ValueError("규칙 검사 실패: " + "; ".join(problems[:3]))
        names = {r["name"] for r in table["rows"]}
        new["table"] = table
        new["targets"] = {k: v for k, v in new["targets"].items() if k in names}
    return new


def evaluate(state: dict, spec: dict) -> dict:
    """상태 하나를 크기 정하기·측정 (소자 목표 바꾸기는 이 동안만 적용)."""
    import auto_size
    import select_structure as ss
    auto_size.TARGET_OVERRIDES = dict(state["targets"])
    try:
        v = ss.evaluate_variant(state["table"], state["unit_current"], state["scale"], spec)
    finally:
        auto_size.TARGET_OVERRIDES = {}
    v.update(unit_current_a=state["unit_current"], target_overrides={k: list(t) for k, t in state["targets"].items()})
    return v


def action_key(action: dict) -> str:
    return json.dumps({"type": action.get("type"), "params": action.get("params") or {}}, sort_keys=True)


def actions_text(actions: list) -> str:
    return " -> ".join(f"{a['type']} {json.dumps(a.get('params') or {}, ensure_ascii=False)}" for a in actions)


def state_features(state: dict, variant: dict) -> dict:
    flagged = set(variant.get("off") or []) | set(variant.get("triode") or [])
    return sb.features(state["table"], variant_kind(variant), flagged)


# ---------------------------------------------------------------- LLM
class Doctor:
    """LLM 호출 (모델을 DOCTOR_MODELS 순서로 시도) 과 원문 기록."""

    def __init__(self, raw_dir: Path, report: dict):
        import extract_datasheet
        extract_datasheet.load_keys()
        sys.path.insert(0, str(extract_datasheet.AV_DIR))
        from ai_analog_designer.llm_client import LLMClient
        global DOCTOR_MODELS
        DOCTOR_MODELS = doctor_models()             # pipeline 이 실행마다 LLM_PROVIDER 를 정한 뒤라 여기서 다시 고른다
        self.llm, self.raw_dir, self.report = LLMClient(), raw_dir, report
        report["llm"] = {"provider": getattr(self.llm, "provider", None), "models": DOCTOR_MODELS, "used": {}}

    def ask(self, prompt: str, system: str, what: dict) -> tuple:
        """(답 dict, 오류 글). 답 원문은 doctor/NN.json 에."""
        t0, answer, errors, used = time.time(), {}, [], None
        for model in DOCTOR_MODELS:
            try:
                answer = self.llm.complete_json(prompt, system_prompt=system, model=model, max_tokens=3000, tag=LLM_TAG)
                used = model
                break
            except Exception as exc:                # 이 모델이 안 되면 다음 모델
                errors.append(f"{model}: {type(exc).__name__}: {str(exc)[:200]}")
        self.report["llm_calls"] += 1
        n = self.report["llm_calls"]
        if used:
            self.report["llm"]["used"][used] = self.report["llm"]["used"].get(used, 0) + 1
        (self.raw_dir / f"{n:02d}.json").write_text(json.dumps(
            {**what, "model": used, "system": system, "prompt": prompt, "answer": answer,
             "error": "; ".join(errors) or None, "seconds": round(time.time() - t0, 1)},
            ensure_ascii=False, indent=1), encoding="utf-8")
        return (answer if isinstance(answer, dict) else {}), (None if used else "; ".join(errors))


def rules_text(rules: list) -> str:
    live = [r for r in rules if r.get("status") != "retired"]
    if not live:
        return "KNOWN STRUCTURE RULES: none yet."
    return "KNOWN STRUCTURE RULES (written from earlier fixes):\n" + "\n".join(
        "  " + structure_rules.rule_text(r) for r in live[-15:])


# ---------------------------------------------------------------- 실행
def good(variant: dict) -> bool:
    """충분히 고쳐졌는지: 동작하고 스펙을 GOOD_PASS_RATIO 이상 통과."""
    return bool(variant.get("valid")) and variant.get("passed", 0) >= GOOD_PASS_RATIO * max(1, variant.get("judged", 1))


def better(a: dict, b) -> bool:
    """측정 a 가 지금까지 가장 나은 b 보다 나은지 (동작하는 것 중 통과 수)."""
    return bool(a.get("valid")) and (b is None or a.get("passed", 0) > b[1].get("passed", 0))


FIX_HOWS = ("llm_fix", "rule_fix")


def needed(sel: dict) -> bool:
    """스펙을 GOOD_PASS_RATIO 이상 통과하는 후보가 없으면 고친다 (동작만 하는 후보로는 충분하지 않음)."""
    return not any(e.get("best") and e["best"]["passed"] >= GOOD_PASS_RATIO * max(1, e["best"]["judged"])
                   for e in sel["entries"])


def save_fixed(chip: str, run_dir: Path, how: str, table_text: str, variant: dict, origin: str) -> None:
    """고쳐서 동작한 구조를 모델 재학습용으로 모은다 (스펙 글은 data/train/<실행 이름>.json)."""
    try:
        items = json.loads(FIXED_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        items = []
    inp_file = run_dir / "input.json"
    inp = json.loads(inp_file.read_text(encoding="utf-8")) if inp_file.exists() else {}
    items.append({"time": time.strftime("%Y-%m-%d %H:%M"), "chip": chip, "run": run_dir.name,
                  "train_spec": f"data/train/{inp.get('name')}.json" if inp.get("name") else None,
                  "how": how, "table": table_text, "from_table": origin,
                  "passed": variant.get("passed"), "judged": variant.get("judged")})
    FIXED_FILE.parent.mkdir(exist_ok=True)
    FIXED_FILE.write_text(json.dumps(items, ensure_ascii=False, indent=1), encoding="utf-8")


def try_rules(state, variant, spec, rules, chip, index, report, log) -> tuple:
    """맞는 규칙을 LLM 없이 적용해 본다. (상태, 측정, 통한 규칙 또는 None)"""
    feats = state_features(state, variant)
    for rule in structure_rules.matching(rules, feats)[:MAX_RULES_TRIED]:
        item = {"candidate": index + 1, "rule": rule["id"], "status": rule.get("status"), "text": rule.get("text"),
                "then": actions_text(rule["then"]), "result": None}
        report["rules_tried"].append(item)
        try:
            new_state = state
            for action in rule["then"]:
                new_state = apply(action, new_state)
        except (ValueError, TypeError, KeyError, AttributeError) as exc:
            item["result"] = f"적용 못 함: {exc}"
            change = structure_rules.record(rule, False, chip)
        else:
            new_variant = evaluate(new_state, spec)
            worked = bool(new_variant.get("valid"))
            item["result"] = (f"동작함 {new_variant['passed']}/{new_variant['judged']}" if worked
                              else f"여전히 실패: {new_variant.get('reason')}")
            change = structure_rules.record(rule, worked, chip)
            if worked and new_variant.get("passed", 0) > variant.get("passed", -1):
                state, variant = new_state, new_variant
        structure_rules.save(rules)
        if change:
            report["rule_changes"].append(change)
        log(f"  후보 {index + 1}: 규칙 {rule['id']} ({rule.get('status')}) {item['then']} -> {item['result']}"
            + (f" [{change}]" if change else ""))
        if good(variant):
            return state, variant, rule
    return state, variant, None


def write_rule(doctor, rules, feats, applied, diagnosis, chip, run_dir, index, report, log) -> None:
    """LLM 이 고친 방법을 LLM 에게 규칙으로 쓰게 한다 (조건은 이번 경우에 맞는 값만 남김)."""
    if not structure_rules.generalizable(applied):
        log(f"  후보 {index + 1}: 고친 방법에 소자 이름이 들어 있어(edit_table/set_device_target) 규칙으로 만들지 않음")
        return
    answer, error = doctor.ask(structure_rules.write_prompt(feats, applied, diagnosis),
                               "You write concise, general analog design rules. Answer JSON only.",
                               {"candidate": index + 1, "purpose": "write_rule"})
    cond = structure_rules.validate_if(answer.get("if"), feats) if not error else {}
    cond.setdefault("failure", feats["failure"])     # 조건 없는 규칙은 어디서나 걸리므로 실패 종류는 꼭 넣음
    rule, new = structure_rules.add(rules, cond, applied, answer.get("text") or diagnosis or "",
                                    chip, {"run": run_dir.name, "candidate": index + 1, "call": report["llm_calls"]})
    structure_rules.save(rules)
    report["rules_written"].append({"rule": rule["id"], "new": new, "text": rule.get("text"),
                                    "rule_text": structure_rules.rule_text(rule)})
    log(f"  규칙 {'새로 씀' if new else '이미 있음(통한 기록 더함)'}: {structure_rules.rule_text(rule)}")


def run(run_dir: Path, log=print) -> dict:
    """실행 폴더의 selection_dev.json 을 고친다. 돌려주는 값은 doctor.json 내용."""
    import auto_size
    import netlist_table as nt
    import run_sim
    import select_structure as ss
    run_dir = Path(run_dir)
    sel_file = run_dir / "selection_dev.json"
    sel = json.loads(sel_file.read_text(encoding="utf-8"))
    # 이 단계부터 다시 돌리면 지난번에 고쳐 넣은 후보를 지우고 처음부터 (지난 결과 때문에 건너뛰던 문제, 2026-11-23)
    old = [e for e in sel["entries"] if e.get("how") in FIX_HOWS]
    if old:
        sel["entries"] = [e for e in sel["entries"] if e.get("how") not in FIX_HOWS]
        log(f"지난번 고치기로 넣은 후보 {len(old)}개를 지우고 다시 고침")
    working = sum(bool(e.get("best")) for e in sel["entries"])
    report = {"needed": needed(sel), "working_before": working, "attempts": [], "fixed": [], "llm_calls": 0,
              "rules_tried": [], "rules_written": [], "rule_changes": []}
    if not report["needed"]:
        log(f"스펙을 절반 이상 통과하는 후보가 있어 고치기 필요 없음 (동작한 후보 {working}개)")
        sel_file.write_text(json.dumps(sel, ensure_ascii=False, indent=1), encoding="utf-8")
        (run_dir / "doctor.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
        return report

    raw_dir = run_dir / "doctor"
    raw_dir.mkdir(exist_ok=True)
    doctor = Doctor(raw_dir, report)
    auto_size.BIAS_MODE = "devices"
    spec = run_sim.load_spec(run_dir / "spec.json")
    chip = (json.loads((run_dir / "hkg.json").read_text(encoding="utf-8")).get("ic_device") or {}).get("name")
    experience, rules = load_experience(), structure_rules.load()
    log(f"규칙 {len(rules)}개 (정식 {sum(r.get('status') == 'confirmed' for r in rules)}개), "
        f"LLM 모델 {', '.join(DOCTOR_MODELS)}")

    # 1. 고쳐 볼 후보: 크기 정하기까지 간 후보 중 실패가 가벼운 순서
    ranked = []
    for i, e in enumerate(sel["entries"]):
        variants = e.get("variants") or []
        if variants:
            lightest = min(variants, key=severity)
            ranked.append((severity(lightest), i, lightest))
    ranked.sort(key=lambda x: x[0])
    picked = ranked[:MAX_CANDIDATES]
    names = ", ".join(f"{i + 1}번({(v.get('reason') or '?')[:20]})" for _, i, v in picked)
    log(f"스펙을 절반 이상 통과하는 후보가 없어 고쳐 봄 (동작한 후보 {working}개): 후보 {len(ranked)}개 중 실패가 가벼운 {len(picked)}개: {names}")

    for _, index, old_variant in picked:
        entry = sel["entries"][index]
        state = {"table": ss.to_table(entry["table"]), "unit_current": auto_size.UNIT_CURRENT,
                 "scale": old_variant.get("output_scale") or 1.0, "targets": {}, "prev": None}
        origin = entry["table"]
        # 진단 정보(동작점, 노드 전압)를 지금 코드로 다시 잰다 (예전 결과에는 없을 수 있음)
        variant = evaluate(state, spec)
        if variant.get("valid"):
            log(f"  후보 {index + 1}: 다시 재 보니 동작함 (진단 정보 다시 잼)")
        how, rule_used = "llm_fix", None
        feats0 = state_features(state, variant)
        if not good(variant):
            state, variant, rule_used = try_rules(state, variant, spec, rules, chip, index, report, log)
        best = (state, variant, rule_used, []) if variant.get("valid") else None
        history, tried_keys, applied, last_diagnosis, rule_actions = [], set(), [], None, None
        for attempt in range(1, MAX_TRIES + 1):
            if good(variant):
                break
            prompt = "\n\n".join([
                FLOW_NOTES, spec_text(spec), failure_text(variant, state), sb.library_text(), rules_text(rules),
                experience_text(experience),
                "ALREADY TRIED ON THIS CANDIDATE (do not repeat):\n" + ("\n".join(history) if history else "  none"),
                "ALLOWED ACTIONS:\n" + "\n".join(f"  {k}: {v}" for k, v in ACTIONS.items()),
                'Answer JSON: {"diagnosis": "...", "action": {"type": "<one action>", "params": {...}}, "why": "..."}'])
            answer, error = doctor.ask(prompt, SYSTEM_PROMPT, {"candidate": index + 1, "attempt": attempt})
            n = report["llm_calls"]
            action = answer.get("action") or {}
            record = {"call": n, "candidate": index + 1, "attempt": attempt, "failure": variant.get("reason"),
                      "diagnosis": answer.get("diagnosis"), "why": answer.get("why"),
                      "action": action.get("type"), "params": action.get("params"), "result": None}
            report["attempts"].append(record)
            if error:
                record["result"] = f"LLM 호출 실패: {error[:120]}"
                log(f"  후보 {index + 1} 시도 {attempt}: {record['result']}")
                break
            if action.get("type") == "next_candidate":
                record["result"] = "LLM 이 이 후보를 포기"
                log(f"  후보 {index + 1} 시도 {attempt}: LLM 이 포기 ({record['diagnosis']})")
                break
            key = action_key(action)
            if key in tried_keys and action.get("type") != "undo":
                record["result"] = "이미 해 본 방법이라 건너뜀"
                history.append(f"  {action.get('type')} {json.dumps(action.get('params') or {})} -> REPEATED, not allowed")
                log(f"  후보 {index + 1} 시도 {attempt}: 같은 방법 반복이라 건너뜀")
                continue
            tried_keys.add(key)
            try:
                new_state = apply(action, state)
            except (ValueError, TypeError, KeyError, AttributeError) as exc:
                record["result"] = f"적용 못 함: {exc}"
                history.append(f"  {action.get('type')} {json.dumps(action.get('params') or {})} -> rejected: {exc}")
                log(f"  후보 {index + 1} 시도 {attempt}: {action.get('type')} 적용 못 함 ({exc})")
                continue
            new_variant = evaluate(new_state, spec)
            worked = bool(new_variant.get("valid"))
            record["result"] = (f"동작함 {new_variant['passed']}/{new_variant['judged']}" if worked
                                else f"여전히 실패: {new_variant.get('reason')}")
            log(f"  후보 {index + 1} 시도 {attempt}: 진단 '{record['diagnosis']}' -> {action.get('type')} "
                f"{json.dumps(action.get('params') or {}, ensure_ascii=False)} -> {record['result']}")
            history.append(f"  {action.get('type')} {json.dumps(action.get('params') or {})} -> "
                           f"{'WORKED' if worked else 'still failed: ' + str(new_variant.get('reason'))}")
            experience.append({"time": time.strftime("%Y-%m-%d %H:%M"), "chip": chip,
                               "failure": variant_kind(variant), "action": action.get("type"),
                               "params": action.get("params"), "worked": worked, "result": record["result"]})
            save_experience(experience)
            if action.get("type") == "undo":
                applied = applied[:-1]
            else:
                applied.append({"type": action.get("type"), "params": action.get("params") or {}})
            state, variant, last_diagnosis = new_state, new_variant, record["diagnosis"]
            if worked and rule_actions is None:
                rule_actions = list(applied)          # 처음 동작하게 만든 고치기 = 규칙으로 남길 것
            if better(variant, best):
                best = (state, variant, None, list(applied))
        if best:                                      # 가장 나은 동작 회로를 후보로 (기준에 못 미쳐도)
            state, variant, rule_used, best_applied = best
            how = "rule_fix" if rule_used and not best_applied else "llm_fix"
            if rule_actions:
                write_rule(doctor, rules, feats0, rule_actions, last_diagnosis, chip, run_dir, index, report, log)
            if not good(variant):
                log(f"  후보 {index + 1}: 동작은 하지만 스펙 {variant['passed']}/{variant['judged']} (기준 미달), "
                    "가장 나은 것으로 남김")
            text = " ; ".join(nt.table_text(state["table"]).splitlines())
            steps = ({"rule": rule_used["id"], "text": rule_used.get("text"), "then": actions_text(rule_used["then"])}
                     if rule_used else {"actions": [a for a in report["attempts"] if a["candidate"] == index + 1]})
            fixed = {"how": how, "from": index + 1, "in_train": False, "llm_calls": report["llm_calls"],
                     "table": text, "steps": {how: steps}, "variants": [dict(variant, output_scale=state["scale"])]}
            ss.finish_entry(fixed)
            sel["entries"].append(fixed)
            report["fixed"].append({"candidate": index + 1, "new_index": len(sel["entries"]), "how": how,
                                    "rule": rule_used["id"] if rule_used else None,
                                    "passed": variant["passed"], "judged": variant["judged"], "good": good(variant)})
            save_fixed(chip, run_dir, how, text, variant, origin)
        if sum(f.get("good") for f in report["fixed"]) >= MAX_FIXED:
            break
    sel_file.write_text(json.dumps(sel, ensure_ascii=False, indent=1), encoding="utf-8")
    (run_dir / "doctor.json").write_text(json.dumps(report, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    log(f"고치기 끝: 규칙 적용 {len(report['rules_tried'])}번, LLM 호출 {report['llm_calls']}번, "
        f"고친 회로 {len(report['fixed'])}개, 새 규칙 {sum(w['new'] for w in report['rules_written'])}개")
    return report


# ---------------------------------------------------------------- 튜닝 뒤 남은 실패 고치기 (2026-11-28)
REFINE_TRIES = 4            # LLM 에 묻는 횟수
REFINE_LIMIT_S = 600        # 전체 시간 [s]
REFINE_TUNE_S = 120         # 구조를 바꾼 뒤 다시 튜닝하는 시간 [s]. 튜닝 때 고른 값 그대로 재면 맞는 방향의 구조도 버려졌다
REFINE_START_CAP_F = 2e-12  # 새 구조에 보상 커패시터가 없을 때 튜닝을 시작하는 값 (0 pF 에서 시작하면 발진해 시간 초과)
REFINE_SYSTEM_PROMPT = (
    "You are an experienced analog CMOS IC designer (GF180MCU 6 V devices, VDD = 5 V, VCM = 2.5 V). "
    "An automatic flow generated an op-amp, sized it by gm/ID and tuned the bias current, output-stage scale and "
    "compensation capacitor. The circuit WORKS but some datasheet specs still fail after tuning, so numbers alone did "
    "not fix them. Find the structural cause of the failing specs and choose ONE fix from the allowed actions. "
    "Do not break specs that already pass. Never repeat a fix listed as already tried. Write 'diagnosis' and 'why' "
    "in Korean, short and concrete (name the block, device and node)."
)


def refine(run_dir: Path, final: dict, table: dict, point: tuple, spec: dict, log=print) -> dict:
    """튜닝 뒤에도 실패한 스펙(최소·최대가 있는 것)을 LLM 에 알려 구조를 바꿔 본다. 통과 수가 늘 때만 받아들인다.
    돌려주는 값: {"needed", "llm_calls", "attempts", "improved", "best": 측정 결과 또는 None, "table", "point"}.
    보상 커패시터는 튜닝에서 고른 값을 구조를 바꾼 뒤의 밀러 노드에 다시 단다 (위상 여유가 모자라면 두 배도 재 봄)."""
    import auto_size
    import run_sim
    import select_structure as ss
    import tune_sizing
    run_dir = Path(run_dir)
    current, scale, cap = point
    report = {"needed": False, "llm_calls": 0, "attempts": [], "improved": False, "best": None}
    failing = [r for r in final.get("spec") or [] if r["status"] == run_sim.STATUS_FAIL]
    if not failing:
        log("튜닝 뒤 실패한 항목이 없어 LLM 구조 개선은 건너뜀")
        return report
    report["needed"] = True
    raw_dir = run_dir / "refine"
    raw_dir.mkdir(exist_ok=True)
    doctor = Doctor(raw_dir, report)
    experience = load_experience()
    end = time.time() + REFINE_LIMIT_S
    targets = {k: tuple(v) for k, v in (final.get("target_overrides") or {}).items()}

    def measure(state, retune=False):
        """retune=False: 지금 값(전류·배율·커패시터)으로 한 번 잼. True: 구조를 바꾼 뒤 짧게 다시 튜닝해서 가장 나은 것.
        돌려주는 측정 결과에 point(전류, 배율, 커패시터) 와 table_with_caps 를 붙인다."""
        auto_size.TARGET_OVERRIDES = dict(state["targets"])
        try:
            if retune:
                left = end + 60 - time.time()
                r = tune_sizing.tune(state["table"], spec, state["unit_current"], state["scale"], log=log,
                                     start_cap=cap or REFINE_START_CAP_F, limit_s=max(30, min(REFINE_TUNE_S, left)))
                v, point, t = r["best"]["variant"], r["best"]["point"], r["best"]["table"]
            else:
                nodes = tune_sizing.miller_nodes(state["table"])
                t, values = tune_sizing.with_caps(state["table"], nodes, cap)
                run_sim.CANDIDATE_DEADLINE = time.time() + tune_sizing.TRIAL_LIMIT_S
                try:
                    with run_sim.hard_limit(tune_sizing.TRIAL_LIMIT_S + 10):
                        v = ss.evaluate_variant(t, state["unit_current"], state["scale"], spec, values)
                except run_sim.CandidateTimeout:
                    v = {"valid": False, "reason": "시간 초과"}
                finally:
                    run_sim.CANDIDATE_DEADLINE = None
                point = (state["unit_current"], state["scale"], cap)
        finally:
            auto_size.TARGET_OVERRIDES = {}
        v = dict(v, point=point, table_with_caps=t, cap_f=point[2], unit_current_a=point[0],
                 target_overrides={k: list(x) for k, x in state["targets"].items()})
        return v

    state = {"table": table, "unit_current": current, "scale": scale, "targets": targets, "prev": None}
    variant = measure(state)                        # 진단 정보(동작점·노드 전압)를 얻으려고 튜닝한 회로를 다시 잰다
    if not variant.get("valid"):
        variant = dict(final, valid=True)
    best = (state, variant)
    failing = [r for r in variant.get("spec") or [] if r["status"] == run_sim.STATUS_FAIL] or failing
    names = ", ".join(r["measure"] for r in failing)
    log(f"튜닝 뒤에도 실패한 항목({names})을 LLM 에 알려 구조를 바꿔 봄 (최대 {REFINE_TRIES}번, {REFINE_LIMIT_S // 60}분)")
    history, tried = [], set()
    for attempt in range(1, REFINE_TRIES + 1):
        if time.time() >= end:
            log("  시간 한도에 닿아 멈춤")
            break
        prompt = "\n\n".join([
            FLOW_NOTES, spec_text(spec), failure_text(best[1], best[0]), sb.library_text(),
            experience_text(experience),
            "ALREADY TRIED (do not repeat):\n" + ("\n".join(history) if history else "  none"),
            "ALLOWED ACTIONS:\n" + "\n".join(f"  {k}: {v}" for k, v in ACTIONS.items()
                                             if k not in ("next_candidate", "undo")),
            'Answer JSON: {"diagnosis": "...", "action": {"type": "<one action>", "params": {...}}, "why": "..."}'])
        answer, error = doctor.ask(prompt, REFINE_SYSTEM_PROMPT, {"attempt": attempt, "failing": names})
        action = answer.get("action") or {}
        record = {"attempt": attempt, "diagnosis": answer.get("diagnosis"), "why": answer.get("why"),
                  "action": action.get("type"), "params": action.get("params"), "result": None}
        report["attempts"].append(record)
        if error:
            record["result"] = f"LLM 호출 실패: {error[:120]}"
            log(f"  시도 {attempt}: {record['result']}")
            break
        key = action_key(action)
        if key in tried:
            record["result"] = "이미 해 본 방법"
            history.append(f"  {action.get('type')} {json.dumps(action.get('params') or {})} -> REPEATED, not allowed")
            log(f"  시도 {attempt}: 같은 방법 반복이라 건너뜀")
            continue
        tried.add(key)
        try:
            new_state = apply(action, best[0])
        except (ValueError, TypeError, KeyError, AttributeError, StopIteration) as exc:
            record["result"] = f"적용 못 함: {exc}"
            history.append(f"  {action.get('type')} {json.dumps(action.get('params') or {})} -> rejected: {exc}")
            log(f"  시도 {attempt}: {action.get('type')} 적용 못 함 ({exc})")
            continue
        new_v = measure(new_state, retune=action.get("type") not in ("set_unit_current", "set_output_scale"))
        ok = bool(new_v.get("valid"))
        fails = [r["measure"] for r in new_v.get("spec") or [] if r["status"] == run_sim.STATUS_FAIL]
        record["result"] = (f"{new_v['passed']}/{new_v['judged']} (실패: {', '.join(fails) or '없음'})" if ok
                            else f"동작 안 함: {new_v.get('reason')}")
        log(f"  시도 {attempt}: 진단 '{record['diagnosis']}' -> {action.get('type')} "
            f"{json.dumps(action.get('params') or {}, ensure_ascii=False)} -> {record['result']}")
        improved = ok and new_v["passed"] > best[1]["passed"]
        history.append(f"  {action.get('type')} {json.dumps(action.get('params') or {})} -> "
                       + (f"passes {new_v['passed']}/{new_v['judged']}, failing {fails}" if ok
                          else f"broke the circuit: {new_v.get('reason')}") + (" (KEPT)" if improved else " (discarded)"))
        experience.append({"time": time.strftime("%Y-%m-%d %H:%M"), "chip": final.get("label"),
                           "failure": "스펙 미달: " + names, "action": action.get("type"),
                           "params": action.get("params"), "worked": bool(improved), "result": record["result"]})
        save_experience(experience)
        if improved:                                # 다시 튜닝한 값(전류·배율)을 다음 시도의 시작점으로
            new_state = dict(new_state, unit_current=new_v["point"][0], scale=new_v["point"][1])
            best = (new_state, new_v)
            record["kept"] = True
            if new_v["passed"] >= new_v["judged"]:
                log("  모두 통과해서 멈춤")
                break
    if best[1] is not variant:
        state, v = best
        report.update(improved=True, best=v, table=v["table_with_caps"],
                      point=(state["unit_current"], state["scale"], v["cap_f"]))
    summary = {k: report[k] for k in ("needed", "llm_calls", "attempts", "improved")}
    summary.update(before=f"{variant['passed']}/{variant['judged']}",
                   after=f"{best[1]['passed']}/{best[1]['judged']}", llm=report.get("llm"))
    (run_dir / "refine.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1, default=str),
                                         encoding="utf-8")
    log(f"LLM 구조 개선 끝: LLM 호출 {report['llm_calls']}번, "
        + (f"{summary['before']} -> {summary['after']}" if report["improved"] else "나아진 구조 없음 (튜닝한 회로 그대로)"))
    return report


if __name__ == "__main__":
    run(Path(sys.argv[1]))
