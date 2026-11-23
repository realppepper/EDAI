"""
구조 고르기 순위 규칙 비교 (이미 잰 select_structure.py 결과로, 시뮬레이션 없이).

v1 (지금): 통과 항목 수 -> 같으면 공급 전류가 작은 쪽
v2 (제안): 통과 항목 수 -> 같으면 목표에서 모자란 정도의 합이 작은 쪽
v3 (제안): 목표 AVD 가 GAIN_TARGET_DB 를 넘으면 이득 노드(gain_path.py)가 REQUIRED_GAIN_NODES 개 이상인 구조 먼저 -> v2
v4 (2026-11-22): 입력쌍 종류가 공통모드 입력 범위를 덮는 구조 먼저 (auto_size.input_pair_covers_range) -> v3
    상보 뒤집기로 덮게 되는 구조도 덮는 것으로 본다 (뒤집기는 pipeline.py 5단계 규칙에서 함)
    예: 범위가 0 V 부터인데 NMOS 입력쌍이면 0 V 근처에서 입력쌍이 꺼져 CMRR 이 3 dB 로 나온다 (TLV271·OPA2376 의 C3)
    모자란 정도: dB 단위는 (목표 - 측정)/20, 그 밖은 |log10(측정/목표)|, 못 잰 항목은 1, 통과는 0
    이득 노드 수(gain_path.py)도 함께 보여 준다.

사용법: python rank_v2.py data/selection_cmp_tlv271_dev.json [--write [v3|v4]]   (--write: 그 규칙의 선택을 _v3.json / _v4.json 으로 저장, 기본 v3)
"""

import json
import math
import re
import sys
from pathlib import Path

import auto_size
import gain_path
import netlist_table as nt

UNMEASURED_PENALTY = 1.0
GAIN_TARGET_DB = 60.0        # 목표 AVD 가 이보다 크면 이득 노드가 여럿 필요
REQUIRED_GAIN_NODES = 2      # 이득 노드 하나 약 50 dB (무부하), 둘이면 약 90 dB


def target_value(text: str):
    """'≥ 97 dB' / '≥ 120, ≤ 134 dB' -> (최소, 최대)."""
    lo = re.search(r"≥\s*([-+0-9.eE]+)", text or "")
    hi = re.search(r"≤\s*([-+0-9.eE]+)", text or "")
    return (float(lo.group(1)) if lo else None, float(hi.group(1)) if hi else None)


def shortfall(rows: list) -> float:
    total = 0.0
    for r in rows:
        if r["status"] == "PASS":
            continue
        v = r.get("value")
        if v is None:
            total += UNMEASURED_PENALTY
            continue
        lo, hi = target_value(r["target"])
        t = lo if lo is not None and v < lo else hi
        if t is None:
            continue
        if r["unit"] == "dB":
            total += abs(t - v) / 20
        elif v > 0 and t > 0:
            total += abs(math.log10(v / t))
        else:
            total += UNMEASURED_PENALTY
    return total


def load_chip_spec(sel: dict) -> None:
    """고르기 결과의 후보 파일 이름(cmp_<칩>[_ret]_candidates.json)으로 칩 스펙을 읽어 공통모드 범위를 맞춘다."""
    part = re.sub(r"(_ret)?(_more\d*)?_candidates\.json$", "", sel.get("source", ""))
    path = Path(__file__).resolve().parent / f"spec_{part}.json"
    if path.exists():
        auto_size.run_sim.load_spec(path)


def input_fits(table: dict) -> bool:
    """입력쌍이 공통모드 범위를 덮거나, 상보 뒤집기(complement.py, 구조 규칙 단계에서 함)로 덮게 되는가."""
    import complement
    kinds = complement.input_kinds(table)
    return auto_size.input_pair_covers_range(kinds) or         auto_size.input_pair_covers_range({complement.SWAP_KIND[k] for k in kinds})


def ranked(sel: dict, rule: str) -> list:
    load_chip_spec(sel)
    out = []
    for n, e in enumerate(sel["entries"]):
        if not e.get("best"):
            continue
        v = next(x for x in e["variants"] if x["valid"] and x["output_scale"] == e["best"]["output_scale"])
        if rule in ("v2", "v3", "v4"):               # v2·v3 는 출력단 배율 중에서도 같은 규칙으로 고른다
            v = min((x for x in e["variants"] if x["valid"]), key=lambda x: (-x["passed"], shortfall(x["spec"])))
        table = nt.parse_table_text("\n".join(p.strip() for p in e["table"].split(";") if p.strip()))
        out.append({"index": n, "passed": v["passed"], "judged": v["judged"], "scale": v["output_scale"],
                    "idd": (v.get("measured") or {}).get("idd") or float("inf"), "shortfall": shortfall(v["spec"]),
                    "gain_nodes": gain_path.gain_nodes(table),
                    "input_ok": input_fits(table),
                    "avd": next((r["value"] for r in v["spec"] if r["measure"] == "avd"), None)})
    need = REQUIRED_GAIN_NODES if (avd_target(sel) or 0) > GAIN_TARGET_DB else 0
    keys = {"v1": lambda r: (-r["passed"], r["idd"]),
            "v2": lambda r: (-r["passed"], r["shortfall"]),
            "v3": lambda r: (r["gain_nodes"] < need, -r["passed"], r["shortfall"]),
            "v4": lambda r: (not r["input_ok"], r["gain_nodes"] < need, -r["passed"], r["shortfall"])}
    return sorted(out, key=keys[rule])


def avd_target(sel: dict):
    for e in sel["entries"]:
        for v in e.get("variants") or []:
            for r in v.get("spec") or []:
                if r["measure"] == "avd":
                    return target_value(r["target"])[0]
    return None


def write_selection(sel: dict, pick: dict, out: Path, rule: str = "v3") -> None:
    """v3 로 고른 후보를 select_structure.py 결과 형식으로 저장 (make_blueprint.py, make_schematic_svg.py --dev 가 읽음)."""
    new = json.loads(json.dumps(sel))
    e = new["entries"][pick["index"]]
    v = next(x for x in e["variants"] if x["valid"] and x["output_scale"] == pick["scale"])
    e["best"] = {"output_scale": v["output_scale"], "passed": v["passed"], "judged": v["judged"],
                 "idd": (v.get("measured") or {}).get("idd")}
    new["summary"]["selected"] = pick["index"]
    new["summary"]["rank_rule"] = rule
    out.write_text(json.dumps(new, ensure_ascii=False, indent=1), encoding="utf-8")


def main() -> None:
    sel = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    for rule in ("v1", "v2", "v3", "v4"):
        top = ranked(sel, rule)[:3]
        print(f"  {rule}: " + " | ".join(
            f"후보 {r['index'] + 1} {r['passed']}/{r['judged']} x{r['scale']:g} 이득노드 {r['gain_nodes']} "
            f"AVD {r['avd'] if r['avd'] is None else round(r['avd'], 1)} 부족 {r['shortfall']:.2f}"
            f"{'' if r['input_ok'] else ' 입력쌍X'}" for r in top))
    if "--write" in sys.argv:
        i = sys.argv.index("--write")
        rule = sys.argv[i + 1] if len(sys.argv) > i + 1 else "v3"
        out = Path(sys.argv[1].replace("_dev.json", f"_{rule}.json"))
        write_selection(sel, ranked(sel, rule)[0], out, rule)
        print(f"  -> {out}")


if __name__ == "__main__":
    main()
