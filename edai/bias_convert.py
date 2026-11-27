"""
바이어스 변환기: 구조 표의 바이어스 단자(VB#, IB#)를 이상적인 전원 대신 실제 소자로 채운다.
auto_size.py 가 크기를 정하기 전에 부른다 (bias_mode="devices"). 그래서 크기와 성능이 처음부터
실제 바이어스가 들어간 상태로 정해진다.

노드 분류 (연결만 보고 정함)
    self      : 다이오드 연결 소자나 저항이 이미 붙어 있음 -> 회로가 스스로 전압을 만듦. 아무것도 안 붙임
    complete  : 다른 소자 드레인이 전류를 넣고 빼는데 받아 줄 다이오드가 없음 (예: 회로 안 β-multiplier 고리의 빈자리)
                -> 다이오드 연결 소자 하나를 채움. 넣는 쪽이 PMOS 드레인이면 NMOS 다이오드, NMOS 드레인이면 PMOS 다이오드
    gate_only : 게이트에만 붙음 -> 기준 전류를 미러로 복사해 다이오드 연결 소자에 흘려 전압을 만듦
                게이트에 붙은 소자의 소스가 전원이 아니면(캐스코드) 다이오드를 두 개 쌓아 전압을 높임
    current   : IB# -> 기준 전류를 미러 출력 소자로 복사해 넣거나 뺌
    unresolved: 위 규칙에 안 맞음 (예: 넣는 소자가 PMOS·NMOS 섞임) -> 하네스로 넘길 대상
gate_only 나 current 가 하나라도 있으면 기준 전류 회로(bias_reference.cell, β-multiplier + startup)를 회로당 하나 넣는다.

더한 소자 이름: 다이오드 NMB#/PMB#, 미러 공급 NMF#/PMF# (회로도에서 NM·PM 기호로 그려지도록 앞 두 글자 유지)
"""

import os

import bias_reference

REF_PREFIX = "REF"
IB_CURRENT = 20e-6          # IB# 에 넣는 전류 [A] (auto_size.BIAS_CURRENT 와 같게)
RAILS = ("VDD", "VSS")


def _mos(table: dict) -> list:
    return [r for r in table["rows"] if r["kind"] in ("nmos", "pmos")]


def _links(table: dict, net: str) -> list:
    return [(r, p) for r in table["rows"] for p, n in r["pins"].items() if n == net and p != "B"]


def classify(table: dict) -> dict:
    """{바이어스 단자: {"kind": 분류, "why": 설명}}"""
    out = {}
    for port in [p for p in table["ports"] if p.startswith(("VB", "IB"))]:
        links = _links(table, port)
        if not links:
            continue
        if port.startswith("IB"):
            out[port] = {"kind": "current", "why": "전류 단자"}
            continue
        mos_links = [(r, p) for r, p in links if r["kind"] in ("nmos", "pmos")]
        diode = [r for r, p in mos_links if p == "D" and r["pins"]["G"] == port]
        passive = [r for r, p in links if r["kind"] == "res"]     # 커패시터는 직류 전압을 못 만듦
        drains = [r for r, p in mos_links if p in ("D", "S") and r["pins"]["G"] != port]
        if diode or passive:
            what = [r["name"] for r in diode + passive]
            out[port] = {"kind": "self", "why": f"이미 {', '.join(what)} 가 전압을 만듦"}
        elif all(p == "G" for _, p in mos_links) and len(mos_links) == len(links):
            out[port] = {"kind": "gate_only", "why": "게이트에만 붙음"}
        elif len({r["kind"] for r in drains}) == 1:
            feed = drains[0]["kind"]
            out[port] = {"kind": "complete", "diode": "nmos" if feed == "pmos" else "pmos",
                         "why": f"{', '.join(r['name'] for r in drains)} 가 전류를 넣는데 받아 줄 다이오드가 없음"}
        else:
            out[port] = {"kind": "unresolved", "why": "전류를 넣는 소자가 PMOS·NMOS 섞임"}
    return out


def free_loops(table: dict) -> list:
    """전류를 정하는 소자(저항)가 없는 미러 고리를 찾는다.
    다이오드 노드 Y 를 게이트로 쓰는 소자가 소스를 전원에 두고 다른 다이오드 노드 X 에 전류를 넣으면 Y -> X.
    이 화살표만으로 돌아오는 고리는 전류가 정해지지 않는다 (이상적인 전원이 붙잡아 주던 것).
    노드에 저항이 붙어 있으면 그 노드에서 전류가 정해지므로 화살표를 만들지 않는다."""
    import networkx as nx
    mos = _mos(table)
    diodes = {r["pins"]["G"] for r in mos if r["pins"]["G"] == r["pins"]["D"] and r["pins"]["G"] not in RAILS}
    with_res = {n for r in table["rows"] if r["kind"] == "res" for n in r["pins"].values()}
    g = nx.DiGraph()
    for r in mos:
        x, y = r["pins"]["D"], r["pins"]["G"]
        if x in diodes and y in diodes and x != y and r["pins"]["S"] in RAILS and x not in with_res:
            g.add_edge(y, x)
    return [sorted(c) for c in nx.simple_cycles(g)]


def _row(name, kind, d, g, s):
    return {"name": name, "kind": kind, "pins": {"D": d, "G": g, "S": s, "B": "VSS" if kind == "nmos" else "VDD"}}


def convert(table: dict, unit_current: float) -> tuple:
    """(새 구조 표, 회로에 덧붙일 줄, 정보).
    정보: {"nodes": classify 결과, "added": [더한 소자 이름], "fixed": {이름: 크기}, "unresolved": [...]}
    fixed 는 기준 전류 미러 소자처럼 크기가 바뀌면 안 되는 것 (기준 회로와 같은 길이·gm/ID 로 전류 비를 정함)."""
    nodes = classify(table)
    rows = [dict(r, pins=dict(r["pins"])) for r in table["rows"]]
    extra, added, fixed = [], [], {}
    count = {"nmos": 0, "pmos": 0}

    def name(kind, tag):
        count[kind] += 1
        return f"{'NM' if kind == 'nmos' else 'PM'}{tag}{count[kind]}"

    need_ref = any(v["kind"] in ("gate_only", "current") for v in nodes.values())
    ref_nodes = {}
    if need_ref:
        # 기준 전류도 전류원 전류에 맞춘다 (기본: 전류원 20 µA 일 때 기준 10 µA)
        lines, ref_nodes = bias_reference.cell(REF_PREFIX, current=bias_reference.IREF * unit_current / 20e-6)
        extra += lines

    def feed(kind, node, current):
        """기준 전류를 node 로 복사하는 미러 출력 소자. kind=pmos 면 VDD 에서 넣고, nmos 면 VSS 로 뺀다."""
        n = name(kind, "F")
        gate = ref_nodes["PB"] if kind == "pmos" else ref_nodes["NB"]
        rows.append(_row(n, kind, node, gate, "VDD" if kind == "pmos" else "VSS"))
        w = bias_reference.width(kind, current)
        fixed[n] = dict(t.split("=") for t in w.split())
        added.append(n)

    for port, info in nodes.items():
        kind = info["kind"]
        if kind == "complete":
            d = info["diode"]
            n = name(d, "B")
            rows.append(_row(n, d, port, port, "VSS" if d == "nmos" else "VDD"))
            added.append(n)
        elif kind == "gate_only":
            gated = [r for r, p in _links(table, port)]
            d = gated[0]["kind"]
            rail = "VSS" if d == "nmos" else "VDD"
            cascode = any(r["pins"]["S"] not in RAILS for r in gated)
            top = name(d, "B")
            level = _input_cascode_level(table, gated[0]) if cascode and LEVEL_STACK else None
            if level is not None:             # 캐스코드 게이트: 기준 노드에서 목표 전압만큼 다이오드 n 개 + 저항을 쌓음
                level, rail = level
                nodes_chain, (n_diodes, r_ohm) = [port], _stack_plan(d, level, unit_current)
                for k in range(n_diodes):
                    nxt = f"{port}_S{k + 1}"
                    dn = top if k == 0 else name(d, "B")
                    rows.append(_row(dn, d, nodes_chain[-1], nodes_chain[-1], nxt))
                    added.append(dn)
                    nodes_chain.append(nxt)
                r_name = f"RBC{port}"
                rows.append({"name": r_name, "kind": "res", "pins": {"P": nodes_chain[-1], "N": rail}})
                fixed[r_name] = {"value": f"{r_ohm:.6g}"}
                added.append(r_name)
            elif cascode:                     # 다이오드 두 개를 쌓아 캐스코드 게이트 전압을 만듦
                mid = f"{port}_LO"
                bottom = name(d, "B")
                rows += [_row(top, d, port, port, mid), _row(bottom, d, mid, mid, rail)]
                added += [top, bottom]
            else:
                rows.append(_row(top, d, port, port, rail))
                added.append(top)
            feed("pmos" if d == "nmos" else "nmos", port, unit_current)
        elif kind == "current":
            links = _links(table, port)
            sinks = any((r["kind"] == "nmos" and p == "S") or (r["kind"] == "pmos" and p == "D") for r, p in links)
            feed("nmos" if sinks else "pmos", port, IB_CURRENT * unit_current / 20e-6)   # 전류원 전류에 맞춰 (초저전력 튜닝)
    new = dict(table, rows=rows)
    unresolved = [p for p, v in nodes.items() if v["kind"] == "unresolved"]
    loops = free_loops(new)
    completed = []
    if COMPLETE_LOOPS:
        for cycle in loops:
            done = _complete_loop(new, cycle, unit_current, fixed, added)
            if done:
                completed.append(done)
        loops = free_loops(new)
    unresolved += [f"전류를 정하는 소자가 없는 고리 ({'-'.join(c)})" for c in loops]
    return new, extra, {"nodes": nodes, "added": added, "fixed": fixed, "reference": need_ref,
                        "free_loops": loops, "completed_loops": completed, "unresolved": unresolved}


# 캐스코드 게이트 전압을 '목표 전압 계산 -> 다이오드 n 개 + 저항' 으로 만든다 (cascode.py 구조용).
# EDAI_LEVEL_STACK=0 이면 예전처럼 다이오드 두 개를 쌓는다 (비교 실험 결과 재현용).
LEVEL_STACK = os.environ.get("EDAI_LEVEL_STACK", "1") != "0"   # 기본 켜짐 (2026-11-22), 0 이면 끔
CASCODE_ALL = True          # LEVEL_STACK 일 때 부하 쪽 캐스코드도 같은 방식
STACK_BODY_V = 0.1          # 쌓은 다이오드 위쪽 소자마다 몸체 효과로 늘어나는 Vgs 어림값 [V]
TAIL_REF = os.environ.get("EDAI_TAIL_REF") == "1"   # 입력쌍 위 캐스코드 바이어스를 꼬리 노드 기준으로 (시험, 크기 정하기 실패)


def _input_cascode_level(table: dict, gated_row: dict):
    """캐스코드 게이트 전압 목표: (기준 노드에서 잰 전압, 기준 노드). 입력쌍 위면 꼬리 노드, 전원 소자 위면 전원 기준. 아니면 None."""
    import auto_size
    # 캐스코드 아래 소자는 같은 종류만 본다. 폴디드 캐스코드는 접히는 노드에 반대 종류 입력쌍도 붙는데,
    # 그걸 아래 소자로 잡으면 입력쌍 기준 전압(4 V 대)을 만들어 버린다 (2026-11-22, 레일 투 레일 앞단 시험)
    under = next((r for r in _mos(table) if r["pins"]["D"] == gated_row["pins"]["S"]
                  and r["kind"] == gated_row["kind"]), None)
    if under is None:
        return None
    t = auto_size.ROLE_TARGETS
    vgs = abs(auto_size.lookup(gated_row["kind"], t["cascode"][1], t["cascode"][0], "vgs"))
    if under["pins"]["G"] in ("IN1", "IN2"):
        v_in = abs(auto_size.lookup(under["kind"], t["input"][1], t["input"][0], "vdsat"))
        if TAIL_REF:
            # 다이오드 줄을 꼬리 노드(입력쌍 소스) 기준으로: 게이트 전압이 입력 공통 전압을 따라감 (CMRR 용, 아직 동작 안 함)
            return vgs + v_in + auto_size.CASCODE_HEADROOM + auto_size.BODY_EFFECT_MARGIN, under["pins"]["S"]
        # 전원 기준 고정값. 예전엔 VCM 기준이라 공통모드 입력이 움직이면 입력쌍이 포화를 벗어나 CMRR 이 나빠졌다.
        # 지금은 공통모드 범위의 불리한 끝 기준 (auto_size.input_cascode_level, 2026-11-22)
        return auto_size.input_cascode_level(gated_row["kind"]), ("VSS" if gated_row["kind"] == "nmos" else "VDD")
    if under["pins"]["S"] in RAILS and CASCODE_ALL:     # 전원에 붙은 소자(부하·전류원) 위 캐스코드
        below = abs(auto_size.lookup(under["kind"], t["source"][1], t["source"][0], "vdsat"))
        return vgs + below + auto_size.CASCODE_HEADROOM + auto_size.BODY_EFFECT_MARGIN, under["pins"]["S"]
    return None


def _stack_plan(kind: str, level: float, current: float) -> tuple:
    """목표 전압 level 을 다이오드 n 개 + 저항으로: (n, R). 다이오드는 크기 정하기에서 diode 역할 gm/ID 로 맞춰진다."""
    import auto_size
    g, l = auto_size.ROLE_TARGETS["diode"]
    vgs = abs(auto_size.lookup(kind, l, g, "vgs"))
    n = 1
    while (n + 1) * vgs + n * STACK_BODY_V <= level:
        n += 1
    drop = n * vgs + (n - 1) * STACK_BODY_V
    return n, max(level - drop, 0.0) / current


COMPLETE_LOOPS = os.environ.get("EDAI_COMPLETE_LOOPS", "1") != "0"   # 저항 없는 2-노드 미러 고리를 β-multiplier 로 완성 (기본 켜짐 2026-11-22, 0 이면 끔)
LOOP_K = 4                  # 완성할 때 NMOS 구동 소자 폭 / 짝 다이오드 폭


def _complete_loop(table: dict, cycle: list, unit_current: float, fixed: dict, added: list):
    """다이오드 노드 두 개가 미러로 서로 전류를 주고받는 고리 = 저항 하나가 빠진 β-multiplier.
        NB(NMOS 다이오드) --NMOS 구동 소자--> PB(PMOS 다이오드) --PMOS 구동 소자--> NB
    NMOS 구동 소자 소스에 저항 R 을 넣고, 폭을 짝 다이오드의 K 배로 고정, PMOS 쪽은 1:1 로 고정.
    R = 2(1 - 1/√K) / gm, gm = gm/ID · I (bias_reference 와 같은 식). 모양이 다르면 None."""
    if len(cycle) != 2:
        return None
    mos = _mos(table)

    def diode(node, kind):
        return next((r for r in mos if r["kind"] == kind and r["pins"]["G"] == node and r["pins"]["D"] == node), None)

    def driver(gate, drain, kind):
        found = [r for r in mos if r["kind"] == kind and r["pins"]["G"] == gate and r["pins"]["D"] == drain
                 and r["pins"]["S"] in RAILS]
        return found[0] if len(found) == 1 else None

    for nb, pb in (cycle, cycle[::-1]):
        dn, dp = diode(nb, "nmos"), diode(pb, "pmos")
        nd, pd = driver(nb, pb, "nmos"), driver(pb, nb, "pmos")
        if dn and dp and nd and pd:
            break
    else:
        return None
    src = f"{nd['name']}_RS"
    nd["pins"]["S"] = src
    r_name = f"RB{len([r for r in table['rows'] if r['kind'] == 'res']) + 1}"
    r_ohm = 2 * (1 - LOOP_K ** -0.5) / (bias_reference.GM_ID * unit_current)
    table["rows"].append({"name": r_name, "kind": "res", "pins": {"P": src, "N": "VSS"}})
    size = lambda kind, scale=1.0: dict(t.split("=") for t in bias_reference.width(kind, unit_current, scale).split())
    fixed[dn["name"]], fixed[nd["name"]] = size("nmos"), size("nmos", LOOP_K)
    fixed[dp["name"]], fixed[pd["name"]] = size("pmos"), size("pmos")
    fixed[r_name] = {"value": f"{r_ohm:.6g}"}
    added.append(r_name)
    return {"nb": nb, "pb": pb, "nmos_driver": nd["name"], "resistor": r_name, "r_ohm": round(r_ohm, 1)}


def startup_lines(p_node: str, q_node: str) -> list:
    """회로 자체 바이어스 고리용 startup (bias_reference 와 같은 방식).
    p_node: PMOS 다이오드 노드 (끌어내리면 고리가 켜짐), q_node: 켜지면 올라가는 NMOS 다이오드 노드."""
    return ["* startup (bias_convert.py)",
            f"XSU_MS2 {p_node} SU_SX VSS VSS nfet_06v0 {bias_reference.STARTUP_PULL}",
            f"XSU_MS3 SU_SX {q_node} VSS VSS nfet_06v0 {bias_reference.STARTUP_OFF}"] + bias_reference.startup_weak("SU_MS1", "SU_SX")


def startup_candidates(table: dict) -> list:
    """(PMOS 다이오드 노드, NMOS 다이오드 노드) 짝 목록."""
    mos = _mos(table)
    pd = sorted({r["pins"]["G"] for r in mos if r["kind"] == "pmos" and r["pins"]["G"] == r["pins"]["D"]})
    nd = sorted({r["pins"]["G"] for r in mos if r["kind"] == "nmos" and r["pins"]["G"] == r["pins"]["D"]})
    return [(p, q) for p in pd for q in nd]
