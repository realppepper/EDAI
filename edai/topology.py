"""
회로 구조 만들기: 블록 모음에서 블록을 찾아(retrieve) 조립(assemble)해 넷리스트를 만든다.

AMSnet-KG 논문(구조설정.pdf)의 흐름 중 LLM 이 맡지 않는 부분이다.
    LLM 의 설계 전략 -> 관계 쌍(triplet) -> [여기] 블록 찾기 -> 조립 -> 넷리스트 -> 시뮬레이션
LLM 을 부르는 쪽은 llm_topology.py 에 있다. 이 파일은 LLM 없이도 쓸 수 있다:

    ~/.venvs/edai/bin/python topology.py                 # 블록 모음과 만들 수 있는 구조 보기
    ~/.venvs/edai/bin/python topology.py folded_cascode class_ab miller_rz   # 조립해서 opamp_gen.cir 만들기
    ~/.venvs/edai/bin/python topology.py folded_cascode class_ab miller_rz nmos   # 입력쌍을 NMOS 로
    ~/.venvs/edai/bin/python topology.py --sweep         # 조립되는 구조를 모두 시뮬레이션 (10분쯤)

블록은 blocks/ 에 있다. 넷리스트 조각은 <이름>.cir, 주석(고를 때 쓰는 것, 조립할 때 쓰는 것)은 cards.json.
조각 파일에서 대문자 이름은 단자, 소문자 이름은 블록 안에서만 쓰는 노드다.
"""

import json
import sys
from pathlib import Path

import run_sim

BLOCK_DIR = run_sim.HERE / "blocks"
CARD_FILE = BLOCK_DIR / "cards.json"
DESIGN_NAME = "opamp_gen"
SWEEP_NAME = "opamp_sweep"                             # 전체 구조를 훑을 때 쓰는 임시 회로 이름
SWEEP_FILE = run_sim.OUT_DIR / "topology_sweep.json"
SUBCKT_PINS = ("INP", "INN", "OUT", "VDD", "VSS")
ROLES = ("stage1", "stage2", "compensation")        # LLM 이 고르는 역할. bias 는 필요한 것을 자동으로 넣는다
NONE = "none"
# 바이어스 전압 이름 -> 조립한 회로에서 쓰는 노드 이름
BIAS_NETS = {"nb": "nb", "pb": "pb", "vbn": "vbn2", "vbp": "vbp2", "vbt": "vbt"}
# 단자가 하는 일 -> 고정으로 이어지는 핀
FIXED_NETS = {"supply_p": "VDD", "supply_n": "VSS", "in_plus": "INP", "in_minus": "INN", "out": "OUT", "comp_b": "OUT"}
# 소자 종류(첫 글자) -> 노드가 적힌 칸 수
NODE_COUNT = {"X": 4, "R": 2, "C": 2}
ROLE_TITLES = {"stage1": "1단", "stage2": "2단", "compensation": "보상", "bias": "바이어스"}
# 성능 요구를 나타내는 관계. 블록을 찾을 때 구현 방식(type, input_pair, load, complexity)보다 무겁게 친다
REQUIREMENT_RELATIONS = {"input_range", "gain", "power", "drives", "needs", "source_current", "sink_current", "zero"}
REQUIREMENT_WEIGHT = 2
MAX_CLOSEST = 2          # 맞는 블록이 없을 때 알려 주는 가까운 블록의 수
MIN_CONNECTIONS = 2      # 안쪽 노드 하나에 이어져야 하는 단자 수의 최소


def load_library() -> dict:
    """블록 카드를 읽는다. 돌려주는 값: {"relations": ..., "blocks": {이름: 카드}}"""
    data = json.loads(CARD_FILE.read_text(encoding="utf-8"))
    return {"relations": data["relations"], "blocks": {card["name"]: card for card in data["blocks"]}}


def block_lines(name: str) -> list:
    """블록 조각 파일에서 소자 줄만 꺼낸다."""
    text = (BLOCK_DIR / f"{name}.cir").read_text(encoding="utf-8")
    return [line.split() for line in text.splitlines() if line.strip() and not line.lstrip().startswith("*")]


# ---------------------------------------------------------------- 블록 찾기
def retrieve(triplets: list, library: dict) -> dict:
    """관계 쌍으로 역할마다 블록을 하나씩 찾는다. (논문의 지식 그래프 질의에 해당)

    triplets: [[역할, 관계, 값], ...]   예: ["stage1", "gain", "high"]
    돌려주는 값: {"selection": {역할: 블록 이름 또는 None}, "matches": {역할: [(블록, 점수)]}, "notes": [...], "errors": [...]}

    역할마다 쌍에 가장 잘 맞는 블록을 고른다 (논문도 질의 결과를 순위로 정렬해 고른다).
    성능 요구를 나타내는 쌍(REQUIREMENT_RELATIONS)은 구현 방식을 나타내는 쌍보다 무겁게 친다.
    LLM 이 "0 V 를 포함하는 입력 범위"와 "NMOS 입력쌍"처럼 함께 가질 수 없는 쌍을 적었을 때 요구 쪽을 따르기 위해서다.
    고른 블록과 어긋나는 쌍은 notes 에 남긴다. 값이 none 인 쌍이 있으면 그 역할은 비운다.
    """
    selection, matches, notes, errors = {}, {}, [], []
    known = library["relations"]
    triplets = [[str(part).strip().lower() for part in item] for item in triplets]
    for role in ROLES:
        wanted = [(relation, value) for subject, relation, value in triplets if subject == role]
        unknown = [(relation, value) for relation, value in wanted
                   if relation not in known[role] or value not in known[role][relation]]
        for relation, value in unknown:
            errors.append(f"{ROLE_TITLES[role]}: 모음에 없는 관계 쌍입니다 ({relation}: {value})")
        if not wanted:
            errors.append(f"{ROLE_TITLES[role]}: 관계 쌍이 하나도 없습니다")
        if unknown or not wanted:
            continue
        if any(value == NONE for _, value in wanted):
            selection[role], matches[role] = None, []
            continue

        def mismatches(card: dict) -> list:
            return [f"{relation} 는 {value} 가 아니라 {card['annotations'].get(relation, '없음')}"
                    for relation, value in wanted if card["annotations"].get(relation) != value]

        scores = []
        for card in library["blocks"].values():
            if card["role"] == role:
                score = sum(REQUIREMENT_WEIGHT if relation in REQUIREMENT_RELATIONS else 1
                            for relation, value in wanted if card["annotations"].get(relation) == value)
                scores.append((card["name"], score))
        scores.sort(key=lambda item: -item[1])
        matches[role] = scores
        best = [library["blocks"][name] for name, score in scores if score == scores[0][1]] if scores else []
        if not scores or scores[0][1] == 0:
            errors.append(f"{ROLE_TITLES[role]}: 관계 쌍에 맞는 블록이 없습니다")
        elif len(best) > 1:
            listed = " / ".join(f"'{card['title']}'" + (f" ({', '.join(mismatches(card))})" if mismatches(card) else "")
                                for card in best[:MAX_CLOSEST])
            errors.append(f"{ROLE_TITLES[role]}: 적은 쌍에 똑같이 잘 맞는 블록이 여러 개입니다: {listed}. "
                          "쌍을 더 적거나 어긋나는 쌍을 고쳐 하나로 좁히세요")
        else:
            selection[role] = best[0]["name"]
            if mismatches(best[0]):
                notes.append(f"{ROLE_TITLES[role]}: 적은 쌍을 모두 가진 블록이 없어 가장 가까운 '{best[0]['title']}'을 골랐습니다 "
                             f"({', '.join(mismatches(best[0]))})")
    return {"selection": selection, "matches": matches, "notes": notes, "errors": errors}


def selection_from_types(stage1: str, stage2: str, compensation: str, input_pair: str = "pmos") -> dict:
    """type 값 세 개(와 입력쌍 종류)로 블록을 고른다 (시험과 명령줄에서 쓴다)."""
    library = load_library()
    found = retrieve([["stage1", "type", stage1], ["stage1", "input_pair", input_pair], ["stage2", "type", stage2],
                      ["compensation", "type", compensation]], library)
    if found["errors"]:
        raise ValueError("; ".join(found["errors"]))
    return found["selection"]


# ---------------------------------------------------------------- 조립
def _pins_with(card: dict, prefix: str) -> dict:
    """카드의 단자 중 하는 일이 prefix 로 시작하는 것: {뒤에 붙은 이름: 단자}"""
    return {job.split(":", 1)[1]: pin for pin, job in card["pins"].items() if job.startswith(prefix + ":")}


def assemble(selection: dict, library: dict) -> dict:
    """고른 블록의 단자를 하는 일에 따라 잇는다. (논문의 '노드의 기능을 맞춰 조립'에 해당)

    돌려주는 값: {"instances": [{"id", "block", "nets": {단자: 노드}, "params": {...}}], "notes": [...], "errors": [...]}
    """
    blocks, instances, notes, errors = library["blocks"], [], [], []
    stage1 = blocks.get(selection.get("stage1") or "")
    stage2 = blocks.get(selection.get("stage2") or "")
    comp = blocks.get(selection.get("compensation") or "")
    if stage1 is None:
        return {"instances": [], "notes": notes, "errors": ["1단 블록이 없습니다"]}

    def fixed_nets(card: dict) -> dict:
        nets = {}
        for pin, job in card["pins"].items():
            if job in FIXED_NETS:
                nets[pin] = FIXED_NETS[job]
            elif job.startswith("bias_in:") or job.startswith("bias_out:"):
                nets[pin] = BIAS_NETS[job.split(":", 1)[1]]
        return nets

    # 1단의 출력과 2단의 입력을 잇는다
    drives, stage1_nets = _pins_with(stage1, "drive_out"), fixed_nets(stage1)
    comp_nets = []
    if stage2 is None:
        for pin in drives.values():
            stage1_nets[pin] = "OUT"
        notes.append("2단이 없어 1단의 출력을 출력 핀에 바로 이었습니다")
        if comp is not None:
            notes.append("2단이 없어 Miller 보상을 걸 곳이 없으므로 보상 블록은 넣지 않았습니다")
            comp = None
    else:
        needs, stage2_nets = _pins_with(stage2, "drive_in"), fixed_nets(stage2)
        missing = [level for level in needs if level not in drives]
        if missing:
            errors.append(f"2단({stage2['title']})에는 {'·'.join('NMOS' if m == 'n' else 'PMOS' for m in missing)} 게이트를 "
                          f"구동하는 입력이 필요한데, 1단({stage1['title']})에는 그 출력이 없습니다")
        else:
            link = {"n": "gn", "p": "gp"} if len(needs) > 1 else {level: "o1" for level in needs}
            for level, pin in needs.items():
                stage2_nets[pin] = link[level]
                stage1_nets[drives[level]] = link[level]
                comp_nets.append(link[level])
            unused = [level for level in drives if level not in needs]
            if unused and not stage1.get("tie_unused_drive"):
                errors.append(f"{stage1['title']}의 출력 중 쓰이지 않는 것이 있습니다")
            for level in unused:
                stage1_nets[drives[level]] = next(iter(link.values()))
                notes.append(f"{stage1['title']}의 위·아래 출력을 한 노드로 묶었습니다")
        instances.append({"id": "s2", "block": stage2["name"], "nets": stage2_nets, "params": {}})
    instances.insert(0, {"id": "s1", "block": stage1["name"], "nets": stage1_nets, "params": {}})

    # 보상: 2단의 입력 노드마다 하나씩
    if stage2 is not None and comp is None:
        notes.append("2단 구조인데 보상 블록이 없습니다 (안정성은 시뮬레이션으로 확인됩니다)")
    if comp is not None:
        for index, net in enumerate(sorted(comp_nets), start=1):
            params = dict(comp.get("params", {}))
            if "comp_cc" in stage2:
                params["cc"] = stage2["comp_cc"]
            nets = {pin: (net if job == "comp_a" else FIXED_NETS[job]) for pin, job in comp["pins"].items()}
            instances.append({"id": f"c{index}", "block": comp["name"], "nets": nets, "params": params})

    # 바이어스: 쓰이는 바이어스 전압을 만드는 블록을 자동으로 넣는다 (그 블록이 또 필요로 하는 것까지)
    bias_ids = {}
    while True:
        needed = {name for item in instances for name in _pins_with(blocks[item["block"]], "bias_in")}
        made = {name for item in instances for name in _pins_with(blocks[item["block"]], "bias_out")}
        lacking = sorted(needed - made)
        if not lacking:
            break
        provider = next((card for card in blocks.values() if card["role"] == "bias"
                         and lacking[0] in _pins_with(card, "bias_out")), None)
        if provider is None:
            errors.append(f"바이어스 전압 {lacking[0]} 을(를) 만드는 블록이 모음에 없습니다")
            break
        bias_ids[provider["name"]] = f"b{len(bias_ids) + 1}"
        instances.insert(len(bias_ids) - 1, {"id": bias_ids[provider["name"]], "block": provider["name"],
                                             "nets": fixed_nets(provider), "params": {}})
        notes.append(f"바이어스 전압 {lacking[0]} 이 필요해 블록을 자동으로 넣었습니다: {provider['title']}")
    return {"instances": instances, "notes": notes, "errors": errors}


# ---------------------------------------------------------------- 넷리스트 만들기와 점검
def expand(instances: list, library: dict) -> list:
    """조립 결과를 소자 줄 목록으로 펼친다: [(블록 이름, [소자 이름, 노드..., 나머지...])]"""
    devices = []
    for item in instances:
        card = library["blocks"][item["block"]]
        params = {**card.get("params", {}), **item.get("params", {})}
        for tokens in block_lines(item["block"]):
            count = NODE_COUNT[tokens[0][0].upper()]
            nodes = [item["nets"][node] if node in card["pins"] else f"{node}_{item['id']}"
                     for node in tokens[1:1 + count]]
            rest = [token.format(**params) for token in tokens[1 + count:]]
            devices.append((item["block"], [f"{tokens[0]}_{item['id']}"] + nodes + rest))
    return devices


def check(devices: list) -> list:
    """조립한 넷리스트의 연결을 점검한다. 문제를 글 목록으로 돌려준다 (없으면 빈 목록)."""
    counts = {}
    for _, tokens in devices:
        for node in tokens[1:1 + NODE_COUNT[tokens[0][0].upper()]]:
            counts[node] = counts.get(node, 0) + 1
    errors = [f"핀 {pin} 에 아무것도 이어지지 않았습니다" for pin in SUBCKT_PINS if pin not in counts]
    errors += [f"노드 {node} 에 단자가 하나만 이어져 있습니다 (떠 있는 노드)"
               for node, count in sorted(counts.items()) if node not in SUBCKT_PINS and count < MIN_CONNECTIONS]
    return errors


def structure_text(selection: dict, library: dict) -> str:
    """고른 블록을 한 줄 설명으로 만든다."""
    blocks = library["blocks"]
    parts = [f"{blocks[selection['stage1']]['title']} 1단"]
    if selection.get("stage2"):
        parts.append(blocks[selection["stage2"]]["title"])
    if selection.get("compensation") and selection.get("stage2"):
        parts.append(blocks[selection["compensation"]]["title"])
    return " + ".join(parts)


def netlist_text(selection: dict, instances: list, library: dict) -> str:
    """조립 결과를 회로 파일 내용으로 만든다. 형식은 opamp_a.cir, opamp_b.cir 과 같다."""
    lines = [
        "* OP-Amp - 블록 모음에서 조립한 회로 본체 (자동 생성. topology.py 가 다시 만들면 덮어쓴다)",
        f"* 구조: {structure_text(selection, library)}",
        "* 공정: GF180MCU 6 V 소자 (nfet_06v0, pfet_06v0). 모델은 테스트벤치가 불러온다.",
        "*",
        "* 핀: INP(비반전 입력) INN(반전 입력) OUT VDD VSS",
        "",
        f".subckt opamp {' '.join(SUBCKT_PINS)}",
    ]
    current = None
    for block, tokens in expand(instances, library):
        if block != current:
            card = library["blocks"][block]
            lines += ["", f"* --- {ROLE_TITLES[card['role']]}: {card['title']} ({block}) ---"]
            current = block
        lines.append(" ".join(tokens))
    return "\n".join(lines + ["", ".ends opamp", ""])


def build(selection: dict, name: str = "") -> dict:
    """블록 선택 하나를 조립해 NAME.cir 을 쓴다.

    돌려주는 값: {"selection", "structure", "instances", "notes", "errors", "netlist", "transistors"}
    errors 가 비어 있지 않으면 파일을 쓰지 않는다.
    """
    name = name or DESIGN_NAME
    library = load_library()
    result = assemble(selection, library)
    record = {"selection": selection, "instances": result["instances"], "notes": result["notes"],
              "errors": list(result["errors"]), "structure": "", "netlist": "", "transistors": 0}
    if record["errors"]:
        return record
    devices = expand(result["instances"], library)
    record["errors"] = check(devices)
    record["structure"] = structure_text(selection, library)
    if record["errors"]:
        return record
    record["netlist"] = netlist_text(selection, result["instances"], library)
    record["transistors"] = sum(tokens[0].upper().startswith("XM") for _, tokens in devices)
    (run_sim.HERE / f"{name}.cir").write_text(record["netlist"], encoding="utf-8")
    return record


def all_structures() -> list:
    """모음으로 조립되는 구조를 모두 돌려준다: [(선택, 조립 결과)] (조립에 실패하는 조합도 포함)."""
    library = load_library()
    by_role = {role: [c["name"] for c in library["blocks"].values() if c["role"] == role] for role in ROLES}
    combos = []
    for stage1 in by_role["stage1"]:
        for stage2 in by_role["stage2"] + [None]:
            for comp in (by_role["compensation"] + [None]) if stage2 else [None]:
                selection = {"stage1": stage1, "stage2": stage2, "compensation": comp}
                result = assemble(selection, library)
                if not result["errors"]:
                    result["errors"] = check(expand(result["instances"], library))
                combos.append((selection, result))
    return combos


def sweep() -> list:
    """조립되는 구조를 모두 시뮬레이션해 통과 수를 센다. LLM 의 선택이 얼마나 좋은지 견줄 기준이 된다.

    결과는 sim_out/topology_sweep.json 에 남긴다. 구조 하나에 15초쯤 걸린다.
    """
    library = load_library()
    spec_file = next(path for path in sorted(run_sim.HERE.glob(f"{run_sim.SPEC_PREFIX}*.json"))
                     if run_sim.load_spec(path).get("circuit") == "opamp")
    spec, records = run_sim.load_spec(spec_file), []
    try:
        for selection, result in all_structures():
            record = {"selection": selection, "structure": structure_text(selection, library),
                      "errors": result["errors"], "passed": None, "judged": None, "failed": []}
            if not result["errors"]:
                record["transistors"] = build(selection, SWEEP_NAME)["transistors"]
                try:
                    rows = run_sim.judge(run_sim.evaluate(SWEEP_NAME), spec)
                except Exception as error:  # 수렴 실패 등
                    record["errors"] = [f"시뮬레이션 실패: {error}"]
                else:
                    judged = [row for row in rows if row["status"] in (run_sim.STATUS_PASS, run_sim.STATUS_FAIL)]
                    record["failed"] = [row["label"] for row in judged if row["status"] == run_sim.STATUS_FAIL]
                    record.update(judged=len(judged), passed=len(judged) - len(record["failed"]))
            records.append(record)
            print(f"  {'-' if record['passed'] is None else record['passed']:>2} / {record['judged'] or '-':>2}  {record['structure']}"
                  + (f"  <- {record['errors'][0]}" if record["errors"] else ""))
    finally:
        (run_sim.HERE / f"{SWEEP_NAME}.cir").unlink(missing_ok=True)
        for leftover in run_sim.OUT_DIR.glob(f"{SWEEP_NAME}*"):
            leftover.unlink()
    SWEEP_FILE.write_text(json.dumps({"spec_file": spec_file.name, "structures": records}, ensure_ascii=False, indent=2),
                          encoding="utf-8")
    return records


def main() -> None:
    library = load_library()
    if sys.argv[1:] == ["--sweep"]:
        sweep()
        print(f"기록 저장: {SWEEP_FILE}")
        return
    if len(sys.argv) in (4, 5):
        record = build(selection_from_types(*sys.argv[1:]))
        for note in record["notes"]:
            print("  참고:", note)
        if record["errors"]:
            print("조립 실패:", "; ".join(record["errors"]))
            return
        print(f"{DESIGN_NAME}.cir 을 만들었습니다: {record['structure']} (트랜지스터 {record['transistors']}개)")
        return
    print("블록 모음")
    for card in library["blocks"].values():
        print(f"  [{ROLE_TITLES[card['role']]}] {card['title']} ({card['name']}) - {card['summary']}")
    print("\n조립되는 구조")
    for selection, result in all_structures():
        text = structure_text(selection, library)
        print(f"  {'가능' if not result['errors'] else '불가'}  {text}"
              + (f"  <- {result['errors'][0]}" if result["errors"] else ""))


if __name__ == "__main__":
    main()
