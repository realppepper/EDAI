"""
구조의 "이득 단 수"를 연결만 보고 센다 (시뮬레이션 없음). 구조 고르기에서 이득이 모자란 구조를 미리 거르기 위한 것.

이득을 내는 노드 (고임피던스 노드)
    전원이 아닌 노드 X 에 트랜지스터 드레인이 2개 이상 붙어 있고, 그중 다이오드 연결(게이트 = 드레인 = X)이 없고,
    저항도 붙어 있지 않으면 X 는 두 전류원 출력 저항이 만나는 곳이라 이득 gm·ro (약 40~55 dB, L 1~2 µm) 가 난다.
    다이오드 부하 노드는 이득이 약 1 배라 세지 않는다.
신호 경로
    입력(IN1, IN2)에서 시작해, 노드 Y 를 게이트로 쓰는 트랜지스터의 드레인 노드로 넘어간다 (공통 소스 증폭).
    전류 미러(다이오드 노드 -> 같은 게이트의 다른 소자 드레인)도 같은 규칙으로 따라간다.
    소스로 넘어가는 경로(소스 팔로워, 차동쌍 꼬리)는 이득이 없어 따라가지 않는다.
    공통 게이트(캐스코드: 게이트가 바이어스 단자 VB*, 소스가 전원 아님)는 소스 -> 드레인으로 따라간다.
    폴디드 캐스코드에서 입력쌍 전류가 캐스코드 소스로 들어가 드레인 노드에서 이득이 나는 경로 (2026-11-22 추가).
결과: 입력에서 OUT 까지 가는 경로 중 고임피던스 노드를 가장 많이 지나는 수 (gain_nodes).

사용법:
    python gain_path.py data/selection_cmp_tlv271_dev.json     후보마다 이득 노드 수와 측정 이득 비교
"""

import json
import sys
from pathlib import Path

import netlist_table as nt

RAILS = ("VDD", "VSS")
INPUTS = ("IN1", "IN2")
DB_PER_GAIN_NODE = 45.0       # 고임피던스 노드 하나가 내는 대략의 이득 [dB] (gm/ID 10~12, L 1~2 µm 기준)


def high_z_nodes(table: dict) -> set:
    mos = [r for r in table["rows"] if r["kind"] in ("nmos", "pmos")]
    res_nodes = {n for r in table["rows"] if r["kind"] == "res" for n in r["pins"].values()}
    out = set()
    nodes = {r["pins"]["D"] for r in mos} - set(RAILS)
    for x in nodes:
        drains = [r for r in mos if r["pins"]["D"] == x]
        diode = any(r["pins"]["G"] == x for r in drains)
        if len(drains) >= 2 and not diode and x not in res_nodes:
            out.add(x)
    return out


def gain_nodes(table: dict) -> int:
    """입력에서 OUT 까지 고임피던스 노드를 가장 많이 지나는 경로의 노드 수. OUT 에 닿지 못하면 0."""
    mos = [r for r in table["rows"] if r["kind"] in ("nmos", "pmos")]
    hz = high_z_nodes(table)
    nxt = {}
    for r in mos:
        g, d = r["pins"]["G"], r["pins"]["D"]
        if d not in RAILS and d != g:
            nxt.setdefault(g, set()).add(d)
        if g.startswith("VB") and r["pins"]["S"] not in RAILS and d not in RAILS:
            nxt.setdefault(r["pins"]["S"], set()).add(d)
    best = {}
    memo = {}

    def walk(node, stack):
        """node 에서 OUT 까지 가며 지나는 고임피던스 노드 최대 수 (node 포함), 못 가면 -1.
        노드마다 결과를 기억한다 (경로를 다 훑으면 폴디드 구조에서 너무 느림). 되돌아오는 고리는 끊는다."""
        if node in memo:
            return memo[node]
        here = 1 if node in hz else 0
        if node == "OUT":
            return here
        result = -1
        for d in nxt.get(node, ()):
            if d in stack:
                continue
            sub = walk(d, stack | {d})
            if sub >= 0:
                result = max(result, here + sub)
        memo[node] = result
        return result

    for i in INPUTS:
        best[i] = walk(i, {i})
    return max(0, max(best.values()))


def main() -> None:
    sel = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    rows = []
    for n, e in enumerate(sel["entries"], 1):
        if not e.get("best"):
            continue
        table = nt.parse_table_text("\n".join(p.strip() for p in e["table"].split(";") if p.strip()))
        v = next(x for x in e["variants"] if x["valid"] and x["output_scale"] == e["best"]["output_scale"])
        m = v.get("measured") or {}
        rows.append((n, gain_nodes(table), m.get("gain_unloaded"), m.get("avd")))
    for n, g, gu, avd in rows:
        print(f"후보 {n:2d}: 이득 노드 {g}  무부하 이득 {gu if gu is None else round(gu, 1)} dB  AVD {avd if avd is None else round(avd, 1)} dB")


if __name__ == "__main__":
    main()
