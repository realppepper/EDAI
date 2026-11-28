"""
구조 표를 블록으로 나누고, 블록을 바꿔 다시 조합한다 (2026-11-23).
structure_doctor.py 의 블록 단위 고치기와 LLM 이 쓰는 규칙(structure_rules.py)이 쓴다.

블록 나누기 (decompose)
    신호 노드 : IN1/IN2 에서 시작해 게이트 -> 드레인, 공통 게이트(소스 -> 드레인), 소스 팔로워(게이트 -> 소스)로 퍼진 노드
    input_pair: 게이트가 IN1/IN2 인 트랜지스터
    tail      : 입력쌍 소스 노드에 드레인이 붙은 전류원
    stage1    : 입력쌍 드레인과 채널(D-S)로 이어진 소자 (부하, 폴디드 캐스코드). 1단 출력이 OUT 이면 1단 증폭기
    later     : 신호 경로에 있지만 1단이 아닌 소자 (2단, 출력단)
    compensation: 신호 노드 사이의 커패시터 (+ 직렬 저항)
    bias      : 나머지 (모델이 만든 자체 바이어스 회로)

블록 모음 (LIBRARY) 은 NMOS 입력 기준으로 적고, PMOS 입력은 상보 뒤집기로 만든다.
    블록은 표준 op-amp 구조를 Claude Code 가 일반 지식으로 적은 것이고, 같은 구조를 다룬 IEEE 논문을
    docs/블록_출처.md 에 출처로 정리했다 (IEEE Xplore API 로 찾음, 초록 근거와 검증 방법 포함).
    @a  : 블록 안쪽 노드 (새 N 번호)       $VB1, $IB1 : 새 바이어스 단자 (흐름이 실제 소자로 채움)
    X   : 1단 출력 = 2단 입력 노드
"""

import re

import gain_path
import netlist_table as nt

RAILS = ("VDD", "VSS")
INPUTS = ("IN1", "IN2")
MOS = ("nmos", "pmos")
FLIP_TOKEN = {"NM": "PM", "PM": "NM", "VDD": "VSS", "VSS": "VDD"}

INPUT_STAGES = {
    "five_transistor": {
        "text": "differential pair + current-mirror load (one high-gain node X near the load rail)",
        "rows": ["NM D=@a G=IN1 S=$IB1 B=VSS", "NM D=X G=IN2 S=$IB1 B=VSS",
                 "PM D=@a G=@a S=VDD B=VDD", "PM D=X G=@a S=VDD B=VDD"]},
    "folded_cascode": {
        "text": "differential pair folded into opposite-type cascodes + low-voltage cascode mirror "
                "(high gain, X in the middle of the supply)",
        "rows": ["NM D=@a G=IN1 S=$IB1 B=VSS", "NM D=@b G=IN2 S=$IB1 B=VSS",
                 "PM D=@a G=$VB1 S=VDD B=VDD", "PM D=@b G=$VB1 S=VDD B=VDD",
                 "PM D=@c G=$VB2 S=@a B=VDD", "PM D=X G=$VB2 S=@b B=VDD",
                 "NM D=@c G=$VB3 S=@e B=VSS", "NM D=X G=$VB3 S=@f B=VSS",
                 "NM D=@e G=@c S=VSS B=VSS", "NM D=@f G=@c S=VSS B=VSS"]},
    "rail_to_rail": {
        "text": "NMOS and PMOS pairs in parallel folded into one cascode summing stage (input range covers both "
                "rails; input_pair is ignored)",
        "rows": ["PM D=@n1 G=$VB3 S=VDD B=VDD", "PM D=@n2 G=$VB3 S=VDD B=VDD",
                 "PM D=X G=$VB2 S=@n2 B=VDD", "PM D=@n5 G=$VB2 S=@n1 B=VDD",
                 "PM D=@n3 G=IN2 S=$IB2 B=VDD", "PM D=@n4 G=IN1 S=$IB2 B=VDD",
                 "NM D=@n2 G=IN1 S=$IB1 B=VSS", "NM D=@n1 G=IN2 S=$IB1 B=VSS",
                 "NM D=X G=$VB1 S=@n4 B=VSS", "NM D=@n5 G=$VB1 S=@n3 B=VSS",
                 "NM D=@n3 G=@n5 S=VSS B=VSS", "NM D=@n4 G=@n5 S=VSS B=VSS"]},
}
OUTPUT_STAGES = {
    "common_source_pmos": {"text": "PMOS gain device driven by X + NMOS current-source load (X should sit near VDD)",
                           "rows": ["PM D=OUT G=X S=VDD B=VDD", "NM D=OUT G=$VB1 S=VSS B=VSS"]},
    "common_source_nmos": {"text": "NMOS gain device driven by X + PMOS current-source load (X should sit near VSS)",
                           "rows": ["NM D=OUT G=X S=VSS B=VSS", "PM D=OUT G=$VB1 S=VDD B=VDD"]},
    "none": {"text": "no second stage: the first-stage output X is OUT (single-stage op-amp)", "rows": []},
    # 푸시풀(class-AB): 공통 소스 2단 뒤에 소스 팔로워 + X 가 구동하는 싱크/소스 (push_pull_output). 공급 전류를 작게
    # 두면서 mA 단위로 내보내고 받는다. 행은 replace_output_stage 가 공통 소스를 붙인 뒤 push_pull_output 으로 만든다
    "push_pull_nmos": {"text": "NMOS common source driven by X + PMOS load at an inner node, then class-AB output: "
                                "NMOS source follower to OUT plus an NMOS sink driven by X (low quiescent current, "
                                "mA source and sink; X should sit near VSS)", "rows": None, "base": "common_source_nmos"},
    "push_pull_pmos": {"text": "PMOS common source driven by X + NMOS load at an inner node, then class-AB output: "
                                "PMOS source follower to OUT plus a PMOS source driven by X (low quiescent current, "
                                "mA source and sink; X should sit near VDD)", "rows": None, "base": "common_source_pmos"},
}
COMPENSATIONS = {
    "none": {"text": "no compensation", "rows": []},
    "miller": {"text": "Miller capacitor between X and OUT", "rows": ["C P=X N=OUT"]},
    "miller_rz": {"text": "Miller capacitor with series nulling resistor between X and OUT",
                  "rows": ["R P=X N=@z", "C P=@z N=OUT"]},
}
PAIR_TYPES = ("nmos", "pmos")


# ---------------------------------------------------------------- 블록 나누기
def _mos(table: dict) -> list:
    return [r for r in table["rows"] if r["kind"] in MOS]


def _nets(rows) -> set:
    return {n for r in rows for n in r["pins"].values()}


def signal_nets(table: dict) -> set:
    nets = set(INPUTS)
    changed = True
    while changed:
        changed = False
        for r in _mos(table):
            d, g, s = r["pins"]["D"], r["pins"]["G"], r["pins"]["S"]
            if g in nets:
                new = s if d in RAILS else d          # 소스 팔로워는 소스로
            elif s in nets and g != d:
                new = d                               # 공통 게이트 (캐스코드)
            else:
                continue
            if new not in RAILS and new not in nets:
                nets.add(new)
                changed = True
    return nets


def high_z_nodes(table: dict) -> set:
    """고임피던스(이득) 노드: 드레인이 둘 이상, 다이오드·저항·소스 연결이 없는 노드
    (폴디드 캐스코드의 접는 노드처럼 소스가 붙은 노드는 낮은 임피던스라 뺀다)."""
    mos = _mos(table)
    res = {n for r in table["rows"] if r["kind"] == "res" for n in r["pins"].values()}
    sources = {r["pins"]["S"] for r in mos}
    out = set()
    for x in {r["pins"]["D"] for r in mos} - set(RAILS):
        drains = [r for r in mos if r["pins"]["D"] == x]
        if len(drains) >= 2 and not any(r["pins"]["G"] == x for r in drains) and x not in res | sources:
            out.add(x)
    return out


def _flow(table: dict) -> dict:
    """신호가 흐르는 방향: 게이트 -> 드레인, 공통 게이트 소스 -> 드레인, 소스 팔로워 게이트 -> 소스."""
    nxt = {}
    for r in _mos(table):
        d, g, s = r["pins"]["D"], r["pins"]["G"], r["pins"]["S"]
        if d in RAILS:
            if s not in RAILS:
                nxt.setdefault(g, set()).add(s)
            continue
        if d != g:
            nxt.setdefault(g, set()).add(d)
        if s not in RAILS and g != d:
            nxt.setdefault(s, set()).add(d)
    return nxt


def _reach(start: set, nxt: dict) -> list:
    """start 에서 신호 방향으로 퍼지며 단계별 노드 목록."""
    levels, seen, front = [], set(start), set(start)
    while front:
        levels.append(sorted(front))
        front = {d for n in front for d in nxt.get(n, ())} - seen - set(RAILS)
        seen |= front
    return levels


def decompose(table: dict) -> dict:
    """블록마다 소자 이름 목록과 블록 종류. 1단 출력 Y = 입력쌍 드레인에서 신호 방향으로 가며 처음 만나는
    고임피던스 노드 (대칭형 OTA 처럼 다이오드 부하 + 미러면 Y 가 OUT 이 되어 1단 증폭기로 본다)."""
    mos, sig = _mos(table), signal_nets(table)
    pair = [r for r in mos if r["pins"]["G"] in INPUTS]
    tail_nets = {r["pins"]["S"] for r in pair} - set(RAILS)
    tail = [r for r in mos if r not in pair and r["pins"]["D"] in tail_nets]
    # 소스 팔로워(드레인이 전원, 게이트·소스가 신호 노드)도 신호 경로다. 빠지면 AB급 출력단의 팔로워가 '모델이 그린
    # 바이어스'로 잡혀 출력단을 바꿀 때 남았다 (2026-11-28)
    stage = [r for r in mos if r not in pair and r not in tail
             and (r["pins"]["D"] in sig or (r["pins"]["D"] in RAILS and r["pins"]["S"] in sig and r["pins"]["G"] in sig))]
    nxt, hz = _flow(table), high_z_nodes(table) | {"OUT"}
    drains = {r["pins"]["D"] for r in pair} - set(RAILS)
    y = next((hits[0] for hits in ([n for n in level if n in hz] for level in _reach(drains, nxt)) if hits), None)
    if y is None:
        later = []
    else:
        down = {n for level in _reach({y}, nxt) for n in level} - {y}
        later = [r for r in stage if r["pins"]["D"] in down or (r["pins"]["D"] in RAILS and r["pins"]["G"] in down)]
    stage1 = [r for r in stage if r not in later]
    nets1 = {n for r in pair + stage1 for n in (r["pins"]["D"], r["pins"]["S"])} - set(RAILS) - tail_nets

    # 보상: 신호 노드 사이 커패시터 (한쪽이 저항을 거쳐 신호 노드에 닿아도 됨)
    passives = [r for r in table["rows"] if r["kind"] in ("res", "cap")]
    comp = []
    for c in (r for r in passives if r["kind"] == "cap"):
        parts, ok = [c], True
        for net in c["pins"].values():
            if net in sig:
                continue
            series = [r for r in passives if r["kind"] == "res" and net in r["pins"].values()
                      and (set(r["pins"].values()) - {net}) & sig]
            if net in RAILS or not series:
                ok = False
            parts += series[:1]
        if ok:
            comp += [p for p in parts if p not in comp]
    kept = pair + tail + stage
    bias_passives = [r for r in passives if r not in comp and not (set(r["pins"].values()) - set(RAILS)) & sig]
    other_passives = [r for r in passives if r not in comp and r not in bias_passives]
    bias = [r for r in mos if r not in kept] + bias_passives
    bias_nets = sorted({r["pins"]["G"] for r in kept} - sig - set(RAILS))

    outputs = [y] if y else []
    kinds = sorted({r["kind"] for r in pair})
    cg = [r for r in stage1 if r["pins"]["G"] not in sig and r["pins"]["S"] in nets1]
    diode_drains = {n for n in drains if any(r["pins"]["G"] == n == r["pins"]["D"] for r in stage1)}
    if len(kinds) == 2:
        stage1_type = "rail_to_rail"
    elif cg:
        stage1_type = "folded_cascode" if any(r["kind"] not in kinds for r in cg) else "telescopic"
    elif len(drains) == 2 and diode_drains == drains:
        stage1_type = "symmetric"
    elif y in drains and diode_drains:
        stage1_type = "five_transistor"
    else:
        stage1_type = "other"
    out_devs = [r for r in later if r["pins"]["D"] == "OUT" or (r["pins"]["S"] == "OUT" and r["pins"]["D"] in RAILS)]
    driven = [r for r in out_devs if r["pins"]["G"] in sig]
    sinks = [r for r in driven if r["pins"]["D"] == "OUT"]
    if outputs == ["OUT"]:
        output_type = "none"
    elif len(driven) >= 2 and sinks:
        output_type = "push_pull_" + sinks[0]["kind"]          # 블록 모음 이름 (OUTPUT_STAGES)
    elif len(driven) >= 2:
        output_type = "push_pull"
    elif len(driven) == 1:
        output_type = "common_source_" + driven[0]["kind"]
    else:
        output_type = "other"
    names = lambda rows: [r["name"] for r in rows]          # noqa: E731
    return {"input_pair": names(pair), "tail": names(tail), "stage1": names(stage1), "later": names(later),
            "output": names(out_devs), "compensation": names(comp), "other_passives": names(other_passives),
            "bias": names(bias), "bias_nets": bias_nets, "stage1_outputs": outputs,
            "input_kind": "both" if len(kinds) == 2 else (kinds[0] if kinds else "none"),
            "input_stage": stage1_type, "output_stage": output_type, "signal_nets": sorted(sig)}


def blocks_text(table: dict) -> str:
    """LLM 에 넘길 블록 설명."""
    b = decompose(table)
    lines = ["BLOCKS (how the structure splits):",
             f"  input pair ({b['input_kind']}): {', '.join(b['input_pair']) or 'none'}; tail: {', '.join(b['tail']) or 'bias port'}",
             f"  input stage type: {b['input_stage']}; devices: {', '.join(b['stage1']) or 'none'}; "
             f"output node(s) of the input stage: {', '.join(b['stage1_outputs']) or 'none'}",
             f"  later stages: {', '.join(b['later']) or 'none'}; output stage type: {b['output_stage']}",
             f"  compensation: {', '.join(b['compensation']) or 'none'}",
             f"  own bias network made by the model: {', '.join(b['bias']) or 'none'}"
             + (f" (it supplies gate nets {', '.join(b['bias_nets'])})" if b["bias_nets"] else "")]
    if b["other_passives"]:
        lines.append(f"  other passives touching signal nodes: {', '.join(b['other_passives'])}")
    return "\n".join(lines)


def library_text() -> str:
    out = ["BLOCK LIBRARY (for replace_input_stage / replace_output_stage / set_compensation / rebuild):",
           "  input stages (input_pair nmos or pmos):"]
    out += [f"    {k}: {v['text']}" for k, v in INPUT_STAGES.items()]
    out.append("  output stages:")
    out += [f"    {k}: {v['text']}" for k, v in OUTPUT_STAGES.items()]
    out.append("  compensation:")
    out += [f"    {k}: {v['text']}" for k, v in COMPENSATIONS.items()]
    return "\n".join(out)


# ---------------------------------------------------------------- 다시 조합
def free_name(name: str, used: set) -> str:
    """이름이 겹치면 같은 앞글자의 다음 빈 번호."""
    if name not in used:
        return name
    prefix = re.match(r"[A-Z]+", name).group()
    n = 1
    while f"{prefix}{n}" in used:
        n += 1
    return f"{prefix}{n}"


def _new_net(prefix: str, used: set) -> str:
    n = 1
    while f"{prefix}{n}" in used:
        n += 1
    used.add(f"{prefix}{n}")
    return f"{prefix}{n}"


def _table(rows: list) -> dict:
    """행 목록 -> 구조 표 (단자 목록 다시 계산)."""
    text = "\n".join(nt.table_text({"rows": [r]}) for r in rows)
    return nt.parse_table_text(text) if text.strip() else {"ports": [], "rows": []}


def _add(rows: list, block_rows: list, x: str, flip: bool = False) -> list:
    """블록 행을 기존 행 뒤에 붙인다 (안쪽 노드·바이어스 단자·이름은 겹치지 않게 새로)."""
    used_nets, used_names = _nets(rows) | {x}, {r["name"] for r in rows}
    local, out = {}, list(rows)
    for line in block_rows:
        if flip:
            line = re.sub(r"\b(NM|PM|VDD|VSS)\b", lambda m: FLIP_TOKEN[m.group()], line)
        head, *pins = line.split()
        name = free_name(head + "1", used_names)
        used_names.add(name)
        parts = []
        for token in pins:
            pin, net = token.split("=")
            if net[0] in "@$":
                if net not in local:
                    local[net] = _new_net("N" if net[0] == "@" else net[1:3], used_nets)
                net = local[net]
            elif net == "X":
                net = x
            parts.append(f"{pin}={net}")
        out += nt.parse_table_text(f"{name} {' '.join(parts)}")["rows"]
    return out


def _rename(rows: list, mapping: dict, only: set = None) -> list:
    return [dict(r, pins={p: (mapping.get(n, n) if only is None or r["name"] in only else n)
                          for p, n in r["pins"].items()}) for r in rows]


def prune_unused_bias(rows: list) -> list:
    """다른 블록을 바꾼 뒤 남은 찌꺼기를 지운다: 한쪽 끝이 떠 버린 저항·커패시터(지운 블록 안 노드에 걸려 있던 보상 등),
    아무 소자에도 이어지지 않게 된 자체 바이어스 소자."""
    while True:
        count = {}
        for r in rows:
            for n in r["pins"].values():
                count[n] = count.get(n, 0) + 1
        loose = [r for r in rows if r["kind"] in ("res", "cap")
                 and any(count[n] < 2 and not nt._port_rank(n) for n in r["pins"].values())]
        if not loose:
            break
        rows = [r for r in rows if r not in loose]
    b = decompose(_table(rows))
    bias = {r["name"]: r for r in rows if r["name"] in set(b["bias"])}
    frontier = _nets(r for r in rows if r["name"] not in bias) - set(RAILS)
    needed = set()
    while True:
        add = [n for n, r in bias.items() if n not in needed and (_nets([r]) - set(RAILS)) & frontier]
        if not add:
            break
        for n in add:
            needed.add(n)
            frontier |= _nets([bias[n]]) - set(RAILS)
    return [r for r in rows if r["name"] not in bias or r["name"] in needed]


def main_output(table: dict, b: dict = None) -> str:
    """2단을 붙일 1단 출력 노드 (입력쌍에서 처음 만나는 고임피던스 노드)."""
    b = b or decompose(table)
    if not b["stage1_outputs"]:
        raise ValueError("입력쌍에서 이득 노드에 닿지 못해 입력단 출력을 찾을 수 없음 -> rebuild 로 새로 조합하세요")
    return b["stage1_outputs"][0]


def _check(name: str, choices: dict) -> None:
    if name not in choices:
        raise ValueError(f"블록 모음에 없는 이름 {name} ({', '.join(choices)} 중)")


def replace_bias(table: dict) -> dict:
    """모델이 만든 자체 바이어스 회로를 지우고, 그 회로가 주던 게이트 노드를 새 VB 단자로 바꾼다
    (흐름이 기준 전류 미러로 채운다)."""
    b = decompose(table)
    if not b["bias"]:
        raise ValueError("자체 바이어스 회로가 없음")
    rows = [r for r in table["rows"] if r["name"] not in set(b["bias"])]
    used = _nets(table["rows"])
    mapping = {n: _new_net("VB", used) for n in b["bias_nets"] if not re.fullmatch(r"(VB|IB)\d+", n)}
    return _table(_rename(rows, mapping))


def replace_input_stage(table: dict, block: str, input_pair: str = "nmos") -> dict:
    """입력쌍·꼬리·1단을 블록 모음의 입력단으로 바꾼다. 2단 이후는 그대로."""
    _check(block, INPUT_STAGES)
    _check(input_pair, dict.fromkeys(PAIR_TYPES))
    b = decompose(table)
    y = main_output(table, b)
    remove = set(b["input_pair"] + b["tail"] + b["stage1"])
    rows = [r for r in table["rows"] if r["name"] not in remove]
    rows = _add(rows, INPUT_STAGES[block]["rows"], y, flip=input_pair == "pmos" and block != "rail_to_rail")
    return _table(prune_unused_bias(rows))


def replace_output_stage(table: dict, block: str) -> dict:
    """2단 이후(출력단)와 보상을 블록 모음의 출력단으로 바꾼다. 입력단은 그대로."""
    _check(block, OUTPUT_STAGES)
    b = decompose(table)
    y = main_output(table, b)
    rows = [r for r in table["rows"] if r["name"] not in set(b["later"] + b["compensation"])]
    if y == "OUT":                                  # 1단 증폭기: 1단 출력을 안쪽 노드로 옮긴 뒤 출력단을 붙임
        if block == "none":
            raise ValueError("이미 1단 증폭기(출력단 없음)")
        new = _new_net("N", _nets(table["rows"]))
        rows = _rename(rows, {"OUT": new})
        y = new
    if block == "none":
        rows = _rename(rows, {y: "OUT"})
    elif OUTPUT_STAGES[block].get("base"):              # 푸시풀: 공통 소스를 붙이고 출력단을 더함
        rows = _add(rows, OUTPUT_STAGES[OUTPUT_STAGES[block]["base"]]["rows"], y)
        return push_pull_output(_table(prune_unused_bias(rows)))
    else:
        rows = _add(rows, OUTPUT_STAGES[block]["rows"], y)
    return _table(prune_unused_bias(rows))


def push_pull_output(table: dict) -> dict:
    """2단(공통 소스 + 전류원 부하)의 출력에 푸시풀(class-AB) 출력단을 붙인다. 2단이 아니면 ValueError.

    2단이 NMOS 공통 소스면 (PMOS 면 위아래를 뒤집은 모양)
        X -[NMOS 구동]- Y -[PMOS 전류원 부하]- VDD       (지금 OUT 이던 2단 출력을 안쪽 노드 Y 로)
        Y -[NMOS 소스 팔로워]- OUT                          출력이 올라갈 때 전류를 내보냄
        X -[NMOS 싱크]- OUT                                 출력이 내려갈 때 당김 (구동 소자와 게이트가 같아 평소 전류는 배율로 정해짐)
        밀러 보상: X-OUT 사이 -> X-Y 사이
    A급 출력단은 출력 전류만큼 늘 전류를 흘려 공급 전류와 부하 구동을 함께 맞추기 어려웠다. LM358 비교 실험에서
    챗봇 회로가 같은 방식(NMOS 팔로워 + 1단 출력이 구동하는 싱크)으로 192 µA 에 5 mA 출력을 냈다 (2026-11-28)."""
    b = decompose(table)
    if b["output_stage"] not in ("common_source_nmos", "common_source_pmos"):
        raise ValueError(f"2단이 공통 소스가 아님 ({b['output_stage']})")
    out_devs = [r for r in table["rows"] if r["name"] in b["output"]]
    driver = next(r for r in out_devs if r["pins"]["G"] in b["signal_nets"])
    kind = driver["kind"]
    prefix, rail, other_rail = ("NM", "VSS", "VDD") if kind == "nmos" else ("PM", "VDD", "VSS")
    y = _new_net("N", _nets(table["rows"]))
    moved = set(b["output"]) | set(b["compensation"])
    rows = _rename(table["rows"], {"OUT": y}, only=moved)
    names = {r["name"] for r in rows}
    follower = free_name(prefix + "1", names)
    sink = free_name(prefix + "1", names | {follower})
    # 팔로워 바디는 자기 소스(OUT)에 묶는다. 전원에 묶으면 출력이 오를수록 문턱 전압이 커져서(바디 효과)
    # 1 mA 부하에서 출력이 3.1 V까지만 올라갔다. 실제 칩에서는 이 소자를 분리된 웰(NMOS는 deep N-well)에 만들어야 한다
    text = (f"{follower} D={other_rail} G={y} S=OUT B=OUT\n"
            f"{sink} D=OUT G={driver['pins']['G']} S={rail} B={rail}")
    return _table(rows + nt.parse_table_text(text)["rows"])


def set_compensation(table: dict, kind: str) -> dict:
    """보상을 바꾼다 (1단 출력 노드 X 와 OUT 사이)."""
    _check(kind, COMPENSATIONS)
    b = decompose(table)
    y = main_output(table, b)
    if y == "OUT" and kind != "none":
        raise ValueError("1단 증폭기라 밀러 보상을 걸 자리가 없음 (출력단을 먼저 붙이세요)")
    rows = [r for r in table["rows"] if r["name"] not in set(b["compensation"])]
    return _table(_add(rows, COMPENSATIONS[kind]["rows"], y))


def rebuild(input_stage: str, input_pair: str, output_stage: str, compensation: str) -> dict:
    """블록 모음만으로 새 구조를 조합한다 (바이어스는 모두 흐름이 채움)."""
    for name, choices in ((input_stage, INPUT_STAGES), (output_stage, OUTPUT_STAGES), (compensation, COMPENSATIONS)):
        _check(name, choices)
    _check(input_pair, dict.fromkeys(PAIR_TYPES))
    if output_stage == "none" and compensation != "none":
        raise ValueError("출력단이 없으면 보상은 none 이어야 함")
    x = "OUT" if output_stage == "none" else "N1"
    rows = _add([], INPUT_STAGES[input_stage]["rows"], x, flip=input_pair == "pmos" and input_stage != "rail_to_rail")
    if output_stage != "none":
        base = OUTPUT_STAGES[output_stage].get("base") or output_stage
        rows = _add(rows, OUTPUT_STAGES[base]["rows"], x)
        rows = _add(rows, COMPENSATIONS[compensation]["rows"], x)
        if base != output_stage:                      # 푸시풀: 보상까지 붙인 뒤 출력단을 더함 (보상은 X-Y 로 옮겨짐)
            return push_pull_output(_table(rows))
    return _table(rows)


def features(table: dict, failure: str, flagged: set) -> dict:
    """규칙의 조건에 쓰는 구조 특징 (칩·소자 이름과 무관한 값만)."""
    import auto_size
    b = decompose(table)
    names = {k: set(b[k]) for k in ("input_pair", "tail", "stage1", "later", "bias")}
    kinds = {"both": {"nmos", "pmos"}, "none": set()}.get(b["input_kind"], {b["input_kind"]})
    return {"failure": failure, "input_pair": b["input_kind"],
            "input_covers_range": bool(kinds) and auto_size.input_pair_covers_range(kinds),
            "input_stage": b["input_stage"], "output_stage": b["output_stage"],
            "gain_nodes": gain_path.gain_nodes(table), "has_compensation": bool(b["compensation"]),
            "own_bias": bool(b["bias"]),
            "failed_blocks": sorted(k for k, v in names.items() if v & set(flagged or ()))}
