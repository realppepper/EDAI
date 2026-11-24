"""
비교 실험 C·D: 우리 쪽에서 고른 구조(select_structure.py 결과)를 박준석 시스템의 설계도(Harness² c5 skill)로 바꾼다.

바꾸는 것 (정해진 규칙만, 크기·연결은 그대로)
    1. 단자 INP INN OUT VDD VSS -> HKG 핀 이름 (핀 역할 role 과 설명으로 정함, pin_map 참고)
       .subckt 첫 줄은 HKG 핀 전체 (NC 등 안 쓰는 핀도 둔다)
    2. XPM.. pfet_06v0 / XNM.. nfet_06v0 (GF180 감싸는 회로) -> M 소자 + LTspice 모델(ltspice_models.py 결과)
       시스템 검사가 첫 .subckt 를 칩 회로로 보므로 감싸는 회로를 쓰지 않는다
    3. 맨 앞에 모델 파일 .include (설계도는 앞 4000자만 읽히므로 모델 카드를 넣지 않는다)
결과: <harness2_library>/operational_amplifier/<이름>/EXPERIENCE.json

사용법:
    python make_blueprint.py <selection.json> <knowledge_graph.json> <설계도 이름> <harness2_library 폴더> <모델 파일 경로>
"""

import json
import re
import sys
from pathlib import Path

MODEL_OF = {"nfet_06v0": "nfet_06v0_bsim0", "pfet_06v0": "pfet_06v0_bsim0"}   # L 0.7~50 µm 구간 (우리 L = 1, 2 µm)


def _desc(p: dict) -> str:
    return (p.get("description") or "").lower()


def channel_of(p: dict):
    """핀이 속한 채널 (다채널 칩). 이름 끝 _A.._D, 이름 앞 숫자(1IN+, 2OUT), IN/OUT 뒤 숫자(IN2_P, OUT2),
    설명의 channel X. 없으면 None."""
    m = (re.search(r"_([A-D])$", p["name"]) or re.match(r"^([1-4])(?=[A-Z])", p["name"])
         or re.match(r"^V?(?:IN|OUT)([1-4])(?=_|[+-]|$)", p["name"], re.I)
         or re.search(r"channel\s*([a-d1-4])", _desc(p)))
    return m.group(1).upper() if m else None


def signal_of(p: dict):
    """INP / INN / OUT / None. 원래 이름의 +/- , 이름 끝 _P/_N, 설명(non-inverting, positive input ...) 순으로 본다."""
    role, raw, d = str(p.get("role")).upper(), str(p.get("raw_name") or p["name"]), _desc(p)
    if role == "OUTPUT":
        return "OUT"
    if role != "SIGNAL":
        return None
    if raw.endswith("+") or re.search(r"IN_?P(_[A-D])?$", p["name"]) or re.search(r"non-?inverting|positive input|\+", d):
        return "INP"
    if raw.endswith("-") or re.search(r"IN_?N(_[A-D])?$", p["name"]) or re.search(r"inverting|negative input|–|-", d):
        return "INN"
    return None


def pin_groups(pins: list) -> tuple:
    """(대표 한 벌 {INP, INN, OUT}, 복사할 채널 {접미사: {INP, INN, OUT}}).
    채널 표시가 없는 입출력 핀이 다 있으면 그것이 대표, 아니면 첫 채널이 대표이고 나머지 채널은 복사한다."""
    groups = {}
    for p in pins:
        sig = signal_of(p)
        if sig:
            groups.setdefault(channel_of(p), {}).setdefault(sig, p["name"])
    full = {k: v for k, v in groups.items() if {"INP", "INN", "OUT"} <= set(v)}
    found = [(sig, name) for g in groups.values() for sig, name in g.items()]
    if not full and sorted(sig for sig, _ in found) == ["INN", "INP", "OUT"]:
        # 1채널 칩인데 여러 칩을 묶은 데이터시트라 입력만 1IN+/1IN- 처럼 번호가 붙은 경우 (LMV321): 한 벌로 본다
        full = {None: dict(found)}
    if None in full:
        main = full.pop(None)
    elif full:
        main = full.pop(sorted(full)[0])
    else:
        raise ValueError("데이터시트 핀에서 입력(+, -)과 출력을 찾지 못함: "
                         + ", ".join(f"{p['name']}({p.get('role')}, {p.get('description')})" for p in pins))
    return main, dict(sorted(full.items()))


def pin_map(pins: list) -> dict:
    """우리 단자 -> HKG 핀 이름."""
    power = [p for p in pins if str(p.get("role")).upper() == "POWER"]
    vdd = next((p for p in power if "positive" in _desc(p) or "+" in _desc(p)), power[0] if power else None)
    vss = next((p for p in pins if str(p.get("role")).upper() == "GROUND"), None) or         next((p for p in power if p is not vdd and ("–" in _desc(p) or "-" in _desc(p) or "negative" in _desc(p))), None)
    if vdd is None or vss is None:
        raise ValueError("데이터시트 핀에서 전원(VDD, VSS)을 찾지 못함")
    main, _ = pin_groups(pins)
    return {"VDD": vdd["name"], "VSS": vss["name"], **main}


def channel_maps(pins: list) -> dict:
    """[5] 핀 기능 조립 (채널 복사): 대표 한 벌 말고 남은 채널마다 {INP, INN, OUT}."""
    return pin_groups(pins)[1]


def convert(subckt: str, pins: list, name: str, model_file: str) -> str:
    mapping = pin_map(pins)
    core = []
    for line in subckt.strip().splitlines()[1:-1]:          # .subckt / .ends 줄 제외
        tokens = line.split()
        if not tokens or tokens[0].startswith("*"):
            continue                                       # 주석 (설계도는 4000자 제한이라 뺀다)
        if tokens[0][0].upper() == "X" and len(tokens) > 5 and tokens[5] in MODEL_OF:
            tokens = ["M" + tokens[0][1:]] + tokens[1:5] + [MODEL_OF[tokens[5]]] + tokens[6:]
        core.append(tokens)

    def place(chan_map: dict, suffix: str) -> list:
        """코어 회로 한 벌: 단자는 chan_map 핀으로, 내부 노드·소자 이름에는 접미사를 붙인다."""
        out = []
        for tokens in core:
            n_nodes = 4 if tokens[0][0].upper() == "M" else 2
            nodes = [chan_map.get(t) or mapping.get(t) or (t + suffix if t not in ("0",) else t)
                     for t in tokens[1:1 + n_nodes]]
            out.append(" ".join([tokens[0] + suffix] + nodes + tokens[1 + n_nodes:]))
        return out

    body = place({}, "")
    channels = channel_maps(pins)
    for suffix, chan in channels.items():                   # 다채널 칩: 채널마다 코어를 복사 (전원은 같이 씀)
        body += place(chan, f"_{suffix}")
    header = " ".join(p["name"] for p in pins)
    mapping = dict(mapping, channels=channels) if channels else mapping
    return "\n".join([f'.include "{model_file}"', f".subckt {name} {header}"] + body + [f".ends {name}"]) + "\n", mapping


def main() -> None:
    sel_file, hkg_file, bp_name, library, model_file = sys.argv[1:6]
    sel = json.loads(Path(sel_file).read_text(encoding="utf-8"))
    hkg = json.loads(Path(hkg_file).read_text(encoding="utf-8"))
    part = hkg["ic_device"]["name"]
    if "subckt_after" in sel:      # bias_to_devices.py 결과: 바이어스 전원을 소자로 바꾼 회로
        subckt = sel["subckt_after"]
        entry = {"how": sel.get("how"), "table": sel["table"],
                 "best": {"passed": sel["passed_after"], "judged": sel["judged"], "output_scale": sel["output_scale"]}}
    else:
        entry = sel["entries"][sel["summary"]["selected"]]
        variant = next(v for v in entry["variants"] if v["valid"] and v["output_scale"] == entry["best"]["output_scale"])
        subckt = variant["subckt"]
    code, mapping = convert(subckt, hkg["pins"], re.sub(r"\W", "_", part).upper(), model_file)
    method = {"retrieval": "학습 데이터 찾기", "llm_fix": "FLAN-T5 + LLM 블록 고치기",
              "rule_fix": "FLAN-T5 + 구조 규칙"}.get(entry.get("how"), "FLAN-T5")
    experience = {
        "task_id": bp_name, "category": "operational_amplifier",
        "cue": f"Initial transistor-level topology for {part} proposed by EDAI ({method})",
        "lesson": (f"Start from blueprint '{bp_name}': GF180MCU 6V transistor-level op-amp sized by gm/ID "
                   f"(ngspice pre-check {entry['best']['passed']}/{entry['best']['judged']} specs). "
                   f"Keep the .include model line; devices use nfet_06v0_bsim0 / pfet_06v0_bsim0."),
        "evidence": {"selection": Path(sel_file).name, "table": entry["table"], "pin_map": mapping,
                     "output_scale": entry["best"]["output_scale"]},
        "score_before": 0.0, "score_after": 0.0, "delta_score": 0.0,
        # 시스템은 경험 파일에서 c5_skills 만 꺼내 쓴다 (나머지 칸은 기본값 유지를 위해 넣지 않음)
        "harness_tree": {"c5_skills": {bp_name: {"description": f"EDAI {method} initial op-amp core for {part} (GF180 6V, LTspice models)",
                                                 "subckt_code": code}}},
    }
    out_dir = Path(library) / "operational_amplifier" / bp_name
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "EXPERIENCE.json").write_text(json.dumps(experience, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{part}: {mapping} -> {out_dir / 'EXPERIENCE.json'} ({len(code)} 자)")
    print(code)


if __name__ == "__main__":
    main()
