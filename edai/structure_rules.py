"""
LLM 이 만든 구조 규칙 모음 (2026-11-23). 파일: data/structure_rules.json

규칙 하나 = "이런 구조 특징 + 이런 실패면 -> 이 블록 변환을 차례로 한다"
    {"id": "R3", "if": {"failure": "포화 영역", "own_bias": true, "failed_blocks": ["bias"]},
     "then": [{"type": "replace_bias", "params": {}}], "text": "설명 (한국어)",
     "status": "candidate|confirmed|retired", "tries": 4, "wins": 3, "chips": ["LM324B", "TLV271"], ...}

    조건(if) 은 structure_blocks.features 가 계산하는 값만 쓴다 (칩·소자 이름과 무관해서 다른 칩에도 그대로 적용됨).
    변환(then) 은 소자 이름이 없는 방법만 쓴다 (RULE_ACTIONS).

생애
    1. LLM 이 고쳐서 동작하면, LLM 에게 그 고치기를 규칙으로 쓰게 한다 -> status "candidate"
    2. 다음 칩부터 structure_doctor 가 LLM 을 부르기 전에 맞는 규칙을 먼저 적용한다 (confirmed 먼저)
    3. 서로 다른 칩 PROMOTE_CHIPS 개에서 통하면 "confirmed" (정식 규칙)
    4. RETIRE_MISSES 번 이상 안 통했고 통한 비율이 RETIRE_RATE 보다 낮으면 "retired" (더 쓰지 않음, 기록은 남김)
"""

import json
import os
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
RULES_FILE = Path(os.environ.get("EDAI_RULES_FILE") or HERE / "data" / "structure_rules.json")   # 시험할 때만 바꿈
PROMOTE_CHIPS = 2          # 이만큼 다른 칩에서 통하면 정식 규칙
RETIRE_MISSES = 4          # 이만큼 이상 안 통했고
RETIRE_RATE = 0.3          # 통한 비율이 이보다 낮으면 쓰지 않음
RULE_ACTIONS = ("replace_bias", "replace_input_stage", "replace_output_stage", "set_compensation", "rebuild",
                "flip", "cascode", "set_unit_current", "set_output_scale")
FEATURE_TEXT = {
    "failure": "failure kind",
    "input_pair": "input pair type (nmos / pmos / both)",
    "input_covers_range": "whether the input pair type covers the datasheet common-mode range",
    "input_stage": "input stage type (five_transistor / folded_cascode / telescopic / symmetric / rail_to_rail / other)",
    "output_stage": "output stage type (none / common_source_nmos / common_source_pmos / push_pull / other)",
    "gain_nodes": "number of high-impedance gain nodes from input to OUT",
    "has_compensation": "whether a compensation capacitor exists",
    "own_bias": "whether the model drew its own bias network",
    "failed_blocks": "blocks that contain OFF/TRIODE devices (rule matches if all listed blocks are among them)",
}


def load() -> list:
    try:
        return json.loads(RULES_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []


def save(rules: list) -> None:
    RULES_FILE.parent.mkdir(exist_ok=True)
    RULES_FILE.write_text(json.dumps(rules, ensure_ascii=False, indent=1), encoding="utf-8")


def matches(rule: dict, feats: dict) -> bool:
    for key, want in (rule.get("if") or {}).items():
        have = feats.get(key)
        if key == "failed_blocks":
            if not set(want or ()) <= set(have or ()):
                return False
        elif have != want:
            return False
    return True


def matching(rules: list, feats: dict) -> list:
    """적용할 규칙 (정식 먼저, 그다음 통한 횟수가 많은 순)."""
    usable = [r for r in rules if r.get("status") != "retired" and matches(r, feats)]
    return sorted(usable, key=lambda r: (r.get("status") != "confirmed", -r.get("wins", 0), r.get("tries", 0)))


def record(rule: dict, worked: bool, chip: str) -> str:
    """적용 결과를 규칙에 반영하고 상태 변화를 글로 돌려준다."""
    rule["tries"] = rule.get("tries", 0) + 1
    rule["last_used"] = time.strftime("%Y-%m-%d %H:%M")
    before = rule.get("status")
    if worked:
        rule["wins"] = rule.get("wins", 0) + 1
        if chip and chip not in rule.setdefault("chips", []):
            rule["chips"].append(chip)
        if len(rule["chips"]) >= PROMOTE_CHIPS:
            rule["status"] = "confirmed"
    elif rule["tries"] - rule.get("wins", 0) >= RETIRE_MISSES and rule.get("wins", 0) / rule["tries"] < RETIRE_RATE:
        rule["status"] = "retired"
    return "" if rule.get("status") == before else f"{rule['id']}: {before} -> {rule['status']}"


def same_rule(a: dict, b: dict) -> bool:
    return (json.dumps(a.get("if"), sort_keys=True) == json.dumps(b.get("if"), sort_keys=True)
            and json.dumps(a.get("then"), sort_keys=True) == json.dumps(b.get("then"), sort_keys=True))


def generalizable(actions: list) -> bool:
    return bool(actions) and all(a.get("type") in RULE_ACTIONS for a in actions)


def validate_if(cond: dict, feats: dict) -> dict:
    """LLM 이 고른 조건이 이번 경우에 실제로 맞는 값만 남긴다 (모르는 특징·틀린 값은 버림)."""
    out = {}
    for key, value in (cond or {}).items():
        if key not in FEATURE_TEXT:
            continue
        if key == "failed_blocks":
            value = sorted(set(value or ()) & set(feats.get(key) or ()))
            if value:
                out[key] = value
        elif feats.get(key) == value:
            out[key] = value
    return out


def add(rules: list, cond: dict, actions: list, text: str, chip: str, source: dict) -> tuple:
    """새 규칙 후보를 넣는다. 같은 규칙이 있으면 그 규칙에 통한 기록만 더한다. (규칙, 새로 만들었는지)"""
    new = {"if": cond, "then": actions}
    for r in rules:
        if same_rule(r, new):
            record(r, True, chip)
            return r, False
    rule = {"id": f"R{len(rules) + 1}", **new, "text": text, "status": "candidate", "tries": 1, "wins": 1,
            "chips": [chip] if chip else [], "created": time.strftime("%Y-%m-%d %H:%M"), "source": source}
    rules.append(rule)
    return rule, True


def rule_text(rule: dict) -> str:
    cond = ", ".join(f"{k}={json.dumps(v, ensure_ascii=False)}" for k, v in rule["if"].items()) or "always"
    then = " -> ".join(f"{a['type']} {json.dumps(a.get('params') or {})}" for a in rule["then"])
    return f"{rule['id']} [{rule.get('status')}, {rule.get('wins', 0)}/{rule.get('tries', 0)}]: IF {cond} THEN {then}"


WRITE_PROMPT = """A structural fix just made a failing op-amp work. Turn it into a reusable rule for OTHER chips.
Pick only the features that explain WHY the fix was needed (a rule with too many conditions never matches again,
a rule with too few conditions fires where it does not help). Use the exact feature values given.

FEATURES OF THE FAILING STRUCTURE:
{features}

FEATURE MEANINGS:
{meanings}

THE FIX THAT WORKED (in order):
{actions}

DIAGNOSIS AT THE TIME: {diagnosis}

Answer JSON: {{"if": {{"<feature>": <value>, ...}}, "text": "<one Korean sentence: when this happens, do this, because ...>"}}"""


def write_prompt(feats: dict, actions: list, diagnosis: str) -> str:
    return WRITE_PROMPT.format(
        features=json.dumps(feats, ensure_ascii=False, indent=1),
        meanings="\n".join(f"  {k}: {v}" for k, v in FEATURE_TEXT.items()),
        actions="\n".join(f"  {a['type']} {json.dumps(a.get('params') or {})}" for a in actions),
        diagnosis=diagnosis or "none")


def main() -> None:
    rules = load()
    print(f"규칙 {len(rules)}개 ({RULES_FILE})")
    for r in rules:
        print(" ", rule_text(r))
        print("    ", r.get("text"), "| 통한 칩:", ", ".join(r.get("chips") or []))


if __name__ == "__main__":
    main()
