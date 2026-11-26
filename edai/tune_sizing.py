"""
스펙 맞추기 튜닝: 구조는 그대로 두고 전류·출력단 배율·보상 커패시터를 바꿔 통과 항목을 늘린다 (pipeline.py 7단계).

왜 필요한가
    3단계 크기 정하기는 "모든 트랜지스터가 동작하는 크기"만 찾는다 (전류원 20 µA 고정, 출력단 20/50배).
    그래서 동작은 하는데 전류를 너무 많이 쓰거나 위상 여유가 모자란 회로가 그대로 하네스로 갔다.
    (LMV321 2026-11-24: UGBW 48.6 MHz 로 목표의 60배인데 IDD 1252 µA, PM 15° 로 실패. 보상 커패시터 없음)
    윤다훈 브랜치의 Optuna 사이즈 튜닝과 같은 생각을 우리 ngspice·GF180 흐름에 맞게 새로 만든 것.

하는 일
    1. 6단계 회로(final.json)에서 시작: (전류원 전류, 출력단 배율, 보상 커패시터 0)
    2. 세 값마다 한 칸 위/아래를 재 보고(언덕 오르기), 가장 나아진 쪽으로 옮긴 뒤 같은 방향으로 더 가 본다.
       전류나 배율을 한 칸 낮추면서 보상을 한 칸 키우는 대각선 이동도 같이 본다: 전류를 줄이면 출력단 gm 이 줄어
       위상 여유가 떨어지므로 보상을 같이 늘려야 한다 (LMV321 2026-11-26: x20 -> x10 만 하면 PM 실패로 4/6 에서 멈춤)
    3. 더 나아지지 않거나, 모두 통과하거나, 시간 TUNE_LIMIT_S 를 넘으면 멈춘다
    "나음" = 통과 개수가 많고, 같으면 모자란 정도(rank_v2.shortfall)가 작은 것 (5·6단계와 같은 기준)
    보상 커패시터는 출력 트랜지스터 중 게이트가 내부 신호 노드인 것의 게이트와 OUT 사이에 넣는다 (밀러 보상).
"""

import time

import auto_size
import netlist_table as nt
import rank_v2
import run_sim
import select_structure as ss

CURRENTS_A = (2.5e-6, 5e-6, 10e-6, 20e-6, 40e-6)       # 전류원 하나의 전류 후보 [A]
SCALES = (1.0, 2.0, 5.0, 10.0, 20.0, 50.0)            # 출력단 전류 배율 후보
CAPS_F = (0.0, 0.5e-12, 1e-12, 2e-12, 4e-12, 8e-12)   # 밀러 보상 커패시터 후보 [F] (0 = 없음)
CASCODE_BIAS = ("VBCN", "VBCP")
TUNE_LIMIT_S = 600          # 튜닝 전체 시간 [s]
TRIAL_LIMIT_S = 90          # 한 번 재는 시간 [s]. 보통 20 s 안팎 (3단계 동작 후보 58개 중앙값 19.5 s, 최대 41 s)


def miller_nodes(table: dict) -> list:
    """출력 트랜지스터(드레인 = OUT) 중 게이트가 내부 신호 노드(N#)인 것의 게이트 노드들."""
    nodes = []
    for row in auto_size.mos_rows(table):
        gate = row["pins"]["G"]
        if row["pins"]["D"] == "OUT" and gate.startswith("N") and gate not in nodes:
            nodes.append(gate)
    return nodes


def existing_caps(table: dict, nodes: list) -> dict:
    """이미 있는 보상 커패시터: {노드: 커패시터 이름} (노드와 OUT 사이)."""
    found = {}
    for row in table["rows"]:
        ends = set(row["pins"].values())
        if row["kind"] == "cap" and "OUT" in ends:
            for node in nodes:
                if node in ends:
                    found.setdefault(node, row["name"])
    return found


def with_caps(table: dict, nodes: list, cap_f: float) -> tuple:
    """밀러 노드마다 OUT 과의 커패시터를 cap_f 로 맞춘 새 표와 그 값 {이름: {"value": ..}}.
    이미 있으면 값만 바꾸고, 없으면 더한다. cap_f 가 0 이면 그대로 (이미 있는 것은 0 으로 두지 않는다)."""
    if not cap_f or not nodes:
        return table, {}
    rows = list(table["rows"])
    values = {}
    have = existing_caps(table, nodes)
    used = sum(r["kind"] == "cap" for r in rows)
    for node in nodes:
        name = have.get(node)
        if name is None:
            used += 1
            name = f"C{used}"                               # 표 글 형식(C#)을 지켜야 다시 읽을 수 있다
            rows.append({"name": name, "kind": "cap", "pins": {"P": node, "N": "OUT"}, "source_name": name, "params": {}})
        values[name] = {"value": f"{cap_f * 1e12:g}p"}
    return {"ports": table["ports"], "rows": rows}, values


def score(v: dict) -> tuple:
    """작을수록 좋음. 동작하지 않으면 맨 뒤."""
    if not v or not v.get("valid"):
        return (1, 0, 0.0)
    return (0, -v["passed"], rank_v2.shortfall(v["spec"]))


def _neighbors(values: tuple, current) -> list:
    """후보 목록에 지금 값을 끼워 넣고 그 앞뒤 값."""
    ordered = sorted(set(values) | {current})
    i = ordered.index(current)
    return [ordered[j] for j in (i - 1, i + 1) if 0 <= j < len(ordered)]


def table_from_text(text: str) -> dict:
    """final.json 의 한 줄 표 글을 표로. 6단계 규칙이 붙인 이름(캐스코드 NMC1 등)도 앞 글자로 종류를 정한다."""
    rows = []
    for part in text.split(";"):
        tokens = part.split()
        if not tokens:
            continue
        name = tokens[0]
        kind = next(k for p, k in (("NM", "nmos"), ("PM", "pmos"), ("R", "res"), ("C", "cap")) if name.startswith(p))
        rows.append({"name": name, "kind": kind, "pins": dict(t.split("=", 1) for t in tokens[1:]),
                     "source_name": name, "params": {}})
    nets = {n for r in rows for n in r["pins"].values()}
    ports = sorted((n for n in nets if nt._port_rank(n)), key=nt._port_rank)
    ports += sorted(n for n in nets if n in CASCODE_BIAS)     # 캐스코드 규칙이 단자로 더한 게이트 전압 (cascode.py)
    return {"ports": ports, "rows": rows}


def tune(table: dict, spec: dict, unit_current: float, output_scale: float, log=print) -> dict:
    """언덕 오르기로 (전류, 배율, 커패시터)를 고른다. 돌려주는 값: {"start", "best", "trials", "stopped"}.
    start/best 는 {"point": (전류, 배율, 커패시터), "variant": ss.evaluate_variant 결과, "table"}."""
    nodes = miller_nodes(table)
    started = time.time()
    end = started + TUNE_LIMIT_S
    seen, trials = {}, []

    def measure(point):
        if point in seen:
            return seen[point]
        current, scale, cap = point
        if time.time() >= end:
            return None
        t, values = with_caps(table, nodes, cap)
        run_sim.CANDIDATE_DEADLINE = min(time.time() + TRIAL_LIMIT_S, end)
        t0 = time.time()
        try:
            v = ss.evaluate_variant(t, current, scale, spec, values)
        except run_sim.CandidateTimeout:
            v = {"valid": False, "reason": f"시간 초과 ({time.time() - t0:.0f} s)"}
        finally:
            run_sim.CANDIDATE_DEADLINE = None
        result = {"point": point, "variant": v, "table": t}
        seen[point] = result
        trials.append({"unit_current_ua": current * 1e6, "scale": scale, "cap_pf": cap * 1e12,
                       "valid": v.get("valid"), "reason": v.get("reason"), "passed": v.get("passed"),
                       "judged": v.get("judged"), "shortfall": round(rank_v2.shortfall(v["spec"]), 3) if v.get("valid") else None,
                       "seconds": round(time.time() - t0, 1),
                       "values": {r["measure"]: r["value"] for r in v.get("spec") or []},
                       "failed": [r["measure"] for r in v.get("spec") or [] if r["status"] != run_sim.STATUS_PASS]})
        res = f"{v['passed']}/{v['judged']}" if v.get("valid") else f"실패 ({(v.get('reason') or '')[:40]})"
        log(f"  튜닝 전류 {current * 1e6:g} µA, 출력단 x{scale:g}, 보상 {cap * 1e12:g} pF: {res} ({time.time() - t0:.0f} s)")
        return result

    def better(a, b):
        return a is not None and score(a["variant"]) < score(b["variant"])

    caps = CAPS_F
    start_cap = 0.0
    if existing_caps(table, nodes):             # 이미 있는 보상 커패시터는 기본값(1 pF)에서 시작하고 없애지는 않는다
        start_cap = float(nt.DEFAULT_VALUE["cap"].rstrip("p")) * 1e-12
        caps = tuple(c for c in CAPS_F if c > 0)
    start = measure((unit_current, output_scale, start_cap))
    best, stopped = start, "더 나아지지 않음"
    axes = [(0, CURRENTS_A), (1, SCALES)] + ([(2, caps)] if nodes else [])
    while True:
        v = best["variant"]
        if v.get("valid") and v["passed"] == v["judged"]:
            stopped = "모두 통과"
            break
        if time.time() >= end:
            stopped = f"시간 제한 ({TUNE_LIMIT_S // 60}분)"
            break
        moves = []
        for axis, values in axes:
            for value in _neighbors(values, best["point"][axis]):
                point = tuple(value if k == axis else x for k, x in enumerate(best["point"]))
                trial = measure(point)
                if better(trial, best):
                    moves.append((axis, values, trial))
        if nodes:                                       # 대각선: 전류 또는 배율 한 칸 아래 + 보상 한 칸 위
            ups = [c for c in _neighbors(caps, best["point"][2]) if c > best["point"][2]]
            for axis, values in axes[:2]:
                downs = [v for v in _neighbors(values, best["point"][axis]) if v < best["point"][axis]]
                for down in downs:
                    for up in ups:
                        point = tuple(down if k == axis else up if k == 2 else x for k, x in enumerate(best["point"]))
                        trial = measure(point)
                        if better(trial, best):
                            moves.append((None, None, trial))
        if not moves:
            break
        axis, values, step = min(moves, key=lambda m: score(m[2]["variant"]))
        direction = (1 if step["point"][axis] > best["point"][axis] else -1) if axis is not None else 0
        best = step
        if axis is None:
            continue                                    # 대각선으로 옮겼으면 다음 바퀴에서 다시 둘러본다
        while True:                                     # 나아진 방향으로 한 칸씩 더
            ordered = sorted(set(values) | {best["point"][axis]})
            j = ordered.index(best["point"][axis]) + direction
            if not 0 <= j < len(ordered):
                break
            trial = measure(tuple(ordered[j] if k == axis else x for k, x in enumerate(best["point"])))
            if not better(trial, best):
                break
            best = trial
    log(f"  튜닝 끝 ({stopped}, {len(trials)}번, {time.time() - started:.0f} s): "
        f"전류 {best['point'][0] * 1e6:g} µA, 출력단 x{best['point'][1]:g}, 보상 {best['point'][2] * 1e12:g} pF")
    return {"start": start, "best": best, "trials": trials, "stopped": stopped, "miller_nodes": nodes,
            "seconds": round(time.time() - started)}
