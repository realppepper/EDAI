"""데이터시트 분석 시스템 결과물(팀원)의 핀 정보로 PDG(포트 의존성 그래프)를 만들고,
우리 구조 모델이 쓰는 OP-Amp 단자 5개(IN1, IN2, OUT, VDD, VSS)와 맞는지 확인한다.

PDG 만드는 규칙은 analogverifier 의 pdg_extractor.py 를 따른다 (LLM 추론은 쓰지 않음).
  1. 데이터시트에서 뽑은 핀 연결(port_dependencies)을 그대로 쓴다
  2. 연결이 빠진 핀은 역할 순서 전원 < 바이어스 < 제어 < 신호 < 출력 으로 채운다

확인하는 것 (채널 하나 기준):
  - 출력 핀 하나에 신호 입력 핀 두 개가 연결돼 있다
  - 전원 핀(POWER)과 접지 핀(GROUND)이 있다
  - 그 채널에 바이어스·제어·기준 같은 다른 핀이 없다 (있으면 우리 모델 범위 밖)

사용법 (프로젝트 폴더에서):
    python pdg_check.py data/extraction/LM358B_knowledge_graph.json lm358
    -> data/pdg_lm358.json
"""
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent

# analogverifier pdg_extractor.ROLE_PRECEDENCE 와 같은 값
ROLE_PRECEDENCE = {"GROUND": 0, "POWER": 0, "BIAS": 1, "REFERENCE": 1, "ENABLE": 2, "CONTROL": 2,
                   "SIGNAL": 3, "INPUT": 3, "FEEDBACK": 4, "OUTPUT": 4}
LEVEL_NAMES = ["전원", "바이어스", "제어", "신호 입력", "출력"]
SIGNAL_LEVEL = 3
OUTPUT_LEVEL = 4
POSITIVE_INPUT = re.compile(r"positive|non-?inverting|\+", re.I)
NEGATIVE_INPUT = re.compile(r"negative|inverting|−|-", re.I)


def level(role: str) -> int:
    return ROLE_PRECEDENCE.get(role, SIGNAL_LEVEL)


def build_pdg(hkg: dict) -> dict:
    """핀 = 노드, 핀 사이 의존 = 화살표. origin: datasheet(추출 결과) / rule(순서 규칙으로 채움)."""
    pins = [{"name": p["name"], "number": p.get("pin_number"), "role": str(p.get("role") or "SIGNAL").upper(),
             "description": p.get("description", "")} for p in hkg.get("pins", [])]
    names = {p["name"] for p in pins if p["role"] != "NC"}
    edges = []

    def add(src, tgt, kind, cond, origin):
        if src != tgt and not any(e["source"] == src and e["target"] == tgt for e in edges):
            edges.append({"source": src, "target": tgt, "type": kind, "condition": cond, "origin": origin})

    for dep in hkg.get("port_dependencies", []) or []:
        if dep.get("source") in names and dep.get("target") in names:
            add(dep["source"], dep["target"], dep.get("dependency_type", "DEPENDS_ON"),
                dep.get("condition") or "", "datasheet")

    by_level = {k: [p["name"] for p in pins if p["role"] != "NC" and level(p["role"]) == k] for k in range(5)}

    def complete(targets, sources, kind, cond):
        for t in targets:
            if sources and not any(e["source"] in sources and e["target"] == t for e in edges):
                for s in sources:
                    add(s, t, kind, cond, "rule")

    complete(by_level[1], by_level[0], "POWER_TO_BIAS", "전원이 선 뒤 바이어스 안정")
    complete(by_level[2], by_level[1] or by_level[0], "TO_CONTROL", "제어 문턱 안정")
    complete(by_level[3], by_level[2] or by_level[1] or by_level[0], "TO_SIGNAL", "동작점 안정")
    complete(by_level[4], by_level[0], "POWER_FEED", "출력에 전원 공급")
    signals = by_level[3]
    for o in by_level[4]:
        if signals and not any(e["target"] == o and e["source"] in signals + by_level[2] + by_level[1] for e in edges):
            for s in signals:
                add(s, o, "SIGNAL_PATH", "입력에서 출력으로 (규칙)", "rule")
    return {"pins": pins, "edges": edges, "levels": LEVEL_NAMES}


def input_sign(pin: dict) -> str:
    text = f"{pin['name']} {pin['description']}"
    if re.search(r"_P\b", pin["name"]) or POSITIVE_INPUT.search(pin["description"]):
        return "+"
    if NEGATIVE_INPUT.search(text):
        return "−"
    return "?"


def check(pdg: dict) -> dict:
    """채널(출력 핀 하나와 그 출력으로 신호가 가는 입력 핀들)마다 OP-Amp 5단자와 맞는지 본다."""
    pins = {p["name"]: p for p in pdg["pins"]}
    power =[n for n, p in pins.items() if p["role"] == "POWER"]
    ground = [n for n, p in pins.items() if p["role"] == "GROUND"]
    outputs = [n for n, p in pins.items() if level(p["role"]) == OUTPUT_LEVEL]
    channels = []
    for out in outputs:
        drivers = [e["source"] for e in pdg["edges"] if e["target"] == out and level(pins[e["source"]]["role"]) > 0]
        inputs = [n for n in drivers if level(pins[n]["role"]) == SIGNAL_LEVEL]
        others = [n for n in drivers if level(pins[n]["role"]) in (1, 2)]
        problems = []
        if len(inputs) != 2:
            problems.append(f"신호 입력 핀이 {len(inputs)}개 (2개여야 함)")
        if not power:
            problems.append("전원 핀(POWER)이 없음")
        if not ground:
            problems.append("접지 핀(GROUND)이 없음")
        if others:
            problems.append(f"우리 모델이 만들지 않는 핀이 있음: {', '.join(others)}")
        signs = {n: input_sign(pins[n]) for n in inputs}
        channels.append({"output": out, "inputs": inputs, "signs": signs, "others": others,
                         "ok": not problems, "problems": problems})
    usable = [c for c in channels if c["ok"]]
    chosen = usable[0] if usable else None
    mapping = []
    if chosen:
        for n in sorted(chosen["inputs"], key=lambda n: chosen["signs"][n] != "+"):
            mapping.append({"pin": n, "number": pins[n]["number"], "role": pins[n]["role"],
                            "ours": "IN1 / IN2", "note": f"{chosen['signs'][n]} 입력"})
        mapping.append({"pin": chosen["output"], "number": pins[chosen["output"]]["number"],
                        "role": pins[chosen["output"]]["role"], "ours": "OUT", "note": "출력"})
        for n in power:
            mapping.append({"pin": n, "number": pins[n]["number"], "role": "POWER", "ours": "VDD", "note": "양 전원"})
        for n in ground:
            mapping.append({"pin": n, "number": pins[n]["number"], "role": "GROUND", "ours": "VSS", "note": "음 전원·접지"})
    return {"ok": chosen is not None, "channels": channels,
            "chosen": chosen["output"] if chosen else None, "mapping": mapping,
            "summary": (f"통과: 채널 {len(channels)}개 중 {len(usable)}개가 OP-Amp 5단자와 맞음, "
                        f"출력 {chosen['output']} 채널 사용") if chosen else
                       "탈락: OP-Amp 5단자(입력 2, 출력 1, 전원 2)와 맞는 채널이 없음"}


def main() -> None:
    source, part = Path(sys.argv[1]), sys.argv[2]
    hkg = json.loads(source.read_text(encoding="utf-8"))
    pdg = build_pdg(hkg)
    result = {"file": source.name, "pdg": pdg, "check": check(pdg)}
    out = HERE / "data" / f"pdg_{part}.json"
    out.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    datasheet = sum(e["origin"] == "datasheet" for e in pdg["edges"])
    print(f"핀 {len(pdg['pins'])}개, 화살표 {len(pdg['edges'])}개 (데이터시트 {datasheet}, 규칙 {len(pdg['edges']) - datasheet})")
    for c in result["check"]["channels"]:
        print(f"  채널 {c['output']}: 입력 {c['inputs']} {c['signs']} -> {'맞음' if c['ok'] else c['problems']}")
    print(result["check"]["summary"], "->", out.relative_to(HERE))


if __name__ == "__main__":
    main()
