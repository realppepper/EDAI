"""
이득을 더 내기 위한 구조 규칙: 이득 노드(gain_path.py)를 캐스코드로 바꾼다 (시험 중).

학습 구조 243개에는 이득 노드 3개 이상인 구조가 없어서, 목표 AVD 가 100 dB 를 넘으면 학습 구조만으로는 닿기 어렵다.
이득 노드 X 에 드레인이 붙은 소자 M 마다 위에 같은 종류의 캐스코드 소자 MC 를 쌓는다.
    전:  X ── M(드레인)
    후:  X ── MC(드레인, 게이트 = 새 바이어스 단자 VBCN/VBCP, 소스 = X_M) ── M(드레인 = X_M)
노드 출력 저항이 약 gm·ro 배 커져 노드 하나당 약 +30 dB (L 1~2 µm).
새 바이어스 단자는 bias_convert 가 '게이트에만 붙은 VB, 캐스코드' 로 보고 다이오드 두 개를 쌓아 전압을 만든다.
출력 노드(OUT)는 출력 스윙이 줄어서 기본으로는 바꾸지 않는다 (include_out=True 로 바꿀 수 있음).

사용법: python cascode.py data/selection_cmp_tlv271_v3.json    선택된 구조를 바꾼 표를 보여 줌
"""

import json
import sys
from pathlib import Path

import gain_path
import netlist_table as nt

RAILS = ("VDD", "VSS")


def gain_path_nodes(table: dict) -> set:
    """입력에서 OUT 까지 가는 경로에 있는 고임피던스 노드."""
    mos = [r for r in table["rows"] if r["kind"] in ("nmos", "pmos")]
    hz = gain_path.high_z_nodes(table)
    nxt = {}
    for r in mos:
        g, d = r["pins"]["G"], r["pins"]["D"]
        if d not in RAILS and d != g:
            nxt.setdefault(g, set()).add(d)
        elif d in RAILS and r["pins"]["S"] not in RAILS and r["pins"]["S"] != g:
            nxt.setdefault(g, set()).add(r["pins"]["S"])     # 소스 팔로워 (AB급 출력단): 게이트 -> 소스
        if g.startswith("VB") and r["pins"]["S"] not in RAILS and d not in RAILS:
            nxt.setdefault(r["pins"]["S"], set()).add(d)     # 공통 게이트(폴디드 캐스코드): 소스 -> 드레인 (gain_path.gain_nodes 와 같게)
    reach_out = {}

    def to_out(node, seen):
        if node == "OUT":
            return True
        return any(to_out(d, seen | {d}) for d in nxt.get(node, ()) if d not in seen)

    on_path, stack, seen = set(), ["IN1", "IN2"], set()
    while stack:
        n = stack.pop()
        if n in seen:
            continue
        seen.add(n)
        if n in hz and to_out(n, {n}):
            on_path.add(n)
        stack += list(nxt.get(n, ()))
    return on_path


def cascode(table: dict, include_out: bool = False, input_side=None) -> tuple:
    """(새 구조 표, 바꾼 노드 목록).
    input_side: 입력쌍 드레인 위에도 캐스코드를 쌓을지. None 이면 공통모드 입력 범위 전체에서 입력쌍이
    포화에 남을 수 있을 때만 쌓는다 (auto_size.input_cascode_ok). 못 쌓으면 이득 노드의 부하 쪽만 캐스코드."""
    import auto_size
    rows = [dict(r, pins=dict(r["pins"])) for r in table["rows"]]
    ports = list(table["ports"])
    mos = [r for r in rows if r["kind"] in ("nmos", "pmos")]
    sources = {r["pins"]["S"] for r in mos}

    def already_cascoded(x):
        """노드에 붙은 드레인 소자가 모두 소스가 전원이 아닌 소자(캐스코드 또는 입력쌍)면 더 쌓지 않는다."""
        devs = [r for r in mos if r["pins"]["D"] == x]
        return bool(devs) and all(r["pins"]["S"] not in RAILS for r in devs)

    # 다른 소자의 소스인 노드(폴디드 캐스코드의 접는 노드)는 저임피던스라 캐스코드 대상이 아니다
    targets = sorted(n for n in gain_path_nodes(table) if (include_out or n != "OUT")
                     and n not in sources and not already_cascoded(n))
    # 입력 차동쌍 한쪽 드레인을 바꾸면 반대쪽 드레인 노드도 같이 바꿔 좌우를 맞춘다 (다이오드 부하는 게이트를 그대로 둠)
    inputs = [r for r in rows if r["kind"] in ("nmos", "pmos") and r["pins"]["G"] in ("IN1", "IN2")]
    for r in inputs:
        if r["pins"]["D"] in targets:
            for other in inputs:
                if other is not r and other["pins"]["S"] == r["pins"]["S"] and other["pins"]["D"] not in targets \
                        and other["pins"]["D"] not in RAILS:
                    targets.append(other["pins"]["D"])
    if input_side is None:
        input_side = all(auto_size.input_cascode_ok(r["kind"]) for r in inputs)
    count = 0
    for x in targets:
        for r in [r for r in rows if r["kind"] in ("nmos", "pmos") and r["pins"]["D"] == x]:
            if not input_side and r["pins"]["G"] in ("IN1", "IN2"):
                continue
            count += 1
            mid = f"{x}_{r['name']}"
            vb = "VBCN" if r["kind"] == "nmos" else "VBCP"          # 같은 종류 캐스코드는 게이트 전압 하나를 같이 씀
            r["pins"]["D"] = mid
            prefix = "NM" if r["kind"] == "nmos" else "PM"
            rows.append({"name": f"{prefix}C{count}", "kind": r["kind"],
                         "pins": {"D": x, "G": vb, "S": mid, "B": "VSS" if r["kind"] == "nmos" else "VDD"}})
            if vb not in ports:
                ports.append(vb)
    return dict(table, rows=rows, ports=ports), targets


def main() -> None:
    sel = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    e = sel["entries"][sel["summary"]["selected"]]
    table = nt.parse_table_text("\n".join(p.strip() for p in e["table"].split(";") if p.strip()))
    new, nodes = cascode(table)
    print(f"이득 노드 {gain_path.gain_nodes(table)}개, 캐스코드로 바꾼 노드 {nodes}")
    print(nt.table_text(new))


if __name__ == "__main__":
    main()
