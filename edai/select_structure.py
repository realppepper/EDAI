"""
FLAN-T5 가 만든 TLV271 후보 구조를 하나씩 검사하고, 크기를 정하고, 시뮬레이션으로 판정해 하나를 고른다.

단계 (후보마다)
    1. 규칙 검사   : 표 형식, 입출력·전원 단자, 입력이 게이트에 붙는지, 한 곳에만 붙은 노드
    2. 크기 정하기 : auto_size (출력단 전류 배율 label_dataset.VARIANTS 마다)
    3. 동작 판정   : label_dataset.judge (출력 VDD/2 근처, 포화 영역, 무부하 이득)
    4. 스펙 판정   : run_sim.judge 로 TLV271 15개 항목 PASS/FAIL
    5. 순위        : 통과 항목 수가 많은 순, 같으면 공급 전류가 작은 순
결과: data/selection_<부품>.json  (단계별 기록. 화면이 이 파일을 읽어 과정을 보여준다)

사용법 (WSL, 프로젝트 폴더에서):
    ~/.venvs/edai/bin/python select_structure.py            # tlv271: data/train/tlv271_candidates.json, spec_tlv271.json
    ~/.venvs/edai/bin/python select_structure.py lm358      # data/train/lm358_candidates.json, spec_lm358.json
"""

import json
import os
import sys
import time
from collections import Counter
from pathlib import Path

import label_dataset
import netlist_table as nt
import run_sim

HERE = Path(__file__).resolve().parent
DEFAULT_PART = "tlv271"
ROW_SEP = ";"
PORTS = ("VDD", "VSS", "IN1", "IN2", "OUT")


def to_table(text: str) -> dict:
    """모델이 쓴 한 줄 글 -> 구조 표. 형식이 틀리면 ValueError."""
    return nt.parse_table_text("\n".join(part.strip() for part in text.split(ROW_SEP) if part.strip()))


def rule_problems(table: dict) -> list:
    """시뮬레이션 전에 걸러낼 문제 목록 (Colab 노트북의 검사와 같은 규칙)."""
    found = []
    names = [row["name"] for row in table["rows"]]
    if len(set(names)) != len(names):
        found.append("같은 이름의 소자가 있음")
    count = Counter(net for row in table["rows"] for net in row["pins"].values())
    found += [f"{port} 단자가 없음" for port in PORTS if port not in count]
    gates = {row["pins"].get("G") for row in table["rows"]}
    found += [f"{port} 가 트랜지스터 게이트에 붙지 않음" for port in ("IN1", "IN2") if port not in gates]
    floating = [net for net, n in count.items() if n < 2 and net not in PORTS and not net.startswith(("VB", "IB"))]
    if floating:
        found.append(f"한 곳에만 붙은 노드: {', '.join(floating)}")
    return found


def spec_rows(measured: dict, spec: dict) -> list:
    """TLV271 목표 항목마다 판정. 재지 못한 항목(예: 이득이 낮아 대역폭이 없음)도 넣어 후보끼리 분모를 같게 한다."""
    rows = run_sim.judge(measured, spec)
    kept = (run_sim.STATUS_PASS, run_sim.STATUS_FAIL, run_sim.STATUS_UNMEASURED)
    return [{"measure": r["measure"], "label": r["label"], "unit": r["unit"], "value": r["value"],
             "target": run_sim.target_text(r), "status": r["status"]}
            for r in rows if r["status"] in kept]


# 구조 선택에서 해 보는 (전류원 전류, 출력단 배율). 학습 데이터(label_dataset.VARIANTS)는 1배·5배만 썼지만,
# 데이터시트 부품은 출력 전류가 mA 단위라 선택할 때는 출력단을 더 크게도 해 본다.
EXTRA_SCALES = (20.0, 50.0)
SELECT_VARIANTS = tuple(label_dataset.VARIANTS) + tuple((label_dataset.VARIANTS[0][0], s) for s in EXTRA_SCALES)


def evaluate_variant(table: dict, unit_current: float, output_scale: float, spec: dict, passives: dict = None) -> dict:
    """크기 정하기 한 번과 스펙 판정. passives: {소자 이름: {"value": ..}} 저항·커패시터 값 (튜닝 단계에서 씀)."""
    record = label_dataset.label(table, passives, unit_current, output_scale, measure_failed=False)
    variant = {"output_scale": output_scale, "op_ok": record["op_ok"], "valid": record["valid"],
               "reason": record["reason"], "off": record.get("off"), "triode": record.get("triode"),
               "startup": record.get("startup"), "sizes": record.get("sizes"), "subckt": record.get("subckt"),
               "bias": record.get("bias"), "powerup": record.get("powerup"), "startup_added": record.get("startup_added"),
               "vout": record.get("vout"), "roles": record.get("roles"), "op_devices": record.get("op_devices"),
               "op_nodes": record.get("op_nodes"),
               "seconds": record["seconds"]}
    if record["valid"]:
        rows = spec_rows(record["measured"], spec)
        variant.update(measured=record["measured"], spec=rows,
                       passed=sum(r["status"] == run_sim.STATUS_PASS for r in rows),
                       judged=len(rows))      # '참고'(보통값만 있는 항목)는 spec_rows 가 이미 뺌
    return variant


def finish_entry(entry: dict) -> dict:
    """변형들 중 가장 좋은 것을 best 로."""
    working = [v for v in entry["variants"] if v["valid"]]
    entry["steps"]["sizing"] = {"ok": bool(working),
                                "reasons": [v["reason"] for v in entry["variants"] if not v["valid"]]}
    entry.pop("best", None)
    if working:
        best = max(working, key=rank_key)
        entry["best"] = {"output_scale": best["output_scale"], "passed": best["passed"], "judged": best["judged"],
                         "idd": best["measured"].get("idd")}
    return entry


def evaluate_candidate(candidate: dict, spec: dict) -> dict:
    """후보 하나를 1~4단계로 평가한 기록."""
    entry = {"how": candidate.get("how"), "in_train": candidate.get("in_train"), "table": candidate["table"],
             "steps": {}, "variants": []}
    try:
        table = to_table(candidate["table"])
    except ValueError as error:
        entry["steps"]["rules"] = {"ok": False, "problems": [f"형식: {error}"]}
        return entry
    problems = rule_problems(table)
    entry["steps"]["rules"] = {"ok": not problems, "problems": problems,
                               "transistors": sum(r["kind"] in ("nmos", "pmos") for r in table["rows"])}
    if problems:
        return entry
    for unit_current, output_scale in SELECT_VARIANTS:
        entry["variants"].append(evaluate_variant(table, unit_current, output_scale, spec))
    return finish_entry(entry)


# ---------------------------------------------------------------- 고쳐 보기 (--repair, 2026-11-23)
# 후보를 그대로만 재면 모델이 직접 그린 바이어스 회로 하나 때문에 전부 탈락하는 일이 많았다 (LM324B: 31개 모두 실패).
# 그래서 후보마다 정해진 변환을 한 모양도 같이 재고, 동작하는 모양은 따로 후보로 남긴다 (how 는 원래 후보와 같고 form 에 모양).
#   원래              : 모델 후보 그대로
#   바이어스 정리     : 자체 바이어스 회로를 지우고 흐름의 검증된 바이어스로 (structure_blocks.replace_bias)
#   + 상보 뒤집기     : 입력쌍이 공통모드 범위를 못 덮으면 (complement.fit_input_range)
#   규칙 R#           : 위 모양이 모두 실패하면 쌓인 구조 규칙 중 맞는 것 (structure_rules, 정식 먼저)
REPAIR_SCALES = (20.0, 50.0)     # 고쳐 보기에서 재는 출력단 배율 (1·5 배는 데이터시트 부품의 출력 전류에 모자람)
REPAIR_RULES = 2                 # 후보 하나에 적용해 보는 규칙 수
# 시간 제한 (2026-11-24). 실행 5번·후보 184개에서 90 % 가 2분 안에 끝났고, 최종으로 뽑힌 후보는 모두 1분 안쪽.
# 3분을 넘긴 후보 8개는 하나도 뽑히지 않았는데 오래 걸린 것은 몇 시간 (LMV321: 3단계 4시간 34분)
CANDIDATE_LIMIT_S = 180          # 후보 하나 (모든 모양 포함). 넘으면 '시간 초과'로 남기고 다음 후보
STAGE_LIMIT_S = 45 * 60          # 3단계 전체. 넘으면 남은 후보는 '시간 부족으로 건너뜀'
# 후보를 동시에 재는 일꾼 수 (2026-11-26). 후보끼리는 서로 상관없어서 나눠 재도 결과는 같고 시간만 준다.
# 일꾼마다 임시 회로 이름(label_dataset.DESIGN_NAME)을 따로 써서 시뮬레이션 파일이 겹치지 않게 한다.
# 1 이면 예전처럼 한 줄로. EDAI_SELECT_WORKERS 로 바꿀 수 있다
SELECT_WORKERS = int(os.environ.get("EDAI_SELECT_WORKERS") or min(4, os.cpu_count() or 1))


def evaluate_form(table: dict, spec: dict) -> list:
    """한 모양을 출력단 배율마다 잰다. 작은 배율에서 동작하지 않으면 큰 배율은 건너뜀 (구조 문제라 같은 결과)."""
    out = []
    for scale in REPAIR_SCALES:
        out.append(evaluate_variant(table, label_dataset.VARIANTS[0][0], scale, spec))
        if not out[-1]["valid"]:
            break
    return out


def forms(table: dict) -> list:
    """(모양 이름, 구조 표, 적용한 변환 목록)."""
    import complement
    import structure_blocks as sb
    out = [("원래", table, [])]
    try:
        cleaned = sb.replace_bias(table)
        if not rule_problems(cleaned):
            out.append(("바이어스 정리", cleaned, ["replace_bias"]))
    except ValueError:
        pass
    for label, t, acts in list(out):
        flipped, did = complement.fit_input_range(t)
        if did:
            out.append((f"{label} + 상보 뒤집기", flipped, acts + ["flip"]))
    return out


def apply_rule_actions(table: dict, actions: list) -> dict:
    """규칙의 블록 변환 (structure_doctor.apply 와 같은 방법, 숫자 바꾸기는 여기서 쓰지 않음)."""
    import cascode
    import complement
    import structure_blocks as sb
    for a in actions:
        kind, params = a.get("type"), a.get("params") or {}
        if kind == "replace_bias":
            table = sb.replace_bias(table)
        elif kind == "replace_input_stage":
            table = sb.replace_input_stage(table, params.get("block"), params.get("input_pair", "nmos"))
        elif kind == "replace_output_stage":
            table = sb.replace_output_stage(table, params.get("block"))
        elif kind == "set_compensation":
            table = sb.set_compensation(table, params.get("type"))
        elif kind == "rebuild":
            table = sb.rebuild(params.get("input_stage"), params.get("input_pair", "nmos"),
                               params.get("output_stage"), params.get("compensation", "none"))
        elif kind == "flip":
            table = complement.flip(table)
        elif kind == "cascode":
            table = cascode.cascode(table)[0]
        else:
            raise ValueError(f"고쳐 보기에서 쓰지 않는 변환 {kind}")
    problems = rule_problems(table)
    if problems:
        raise ValueError("규칙 검사 실패: " + "; ".join(problems[:2]))
    return table


def form_entry(candidate: dict, number: int, label: str, table: dict, acts: list, variants: list) -> dict:
    entry = {"how": candidate.get("how"), "in_train": bool(candidate.get("in_train")) and label == "원래",
             "form": label, "from": number, "form_actions": acts,
             "table": " ; ".join(nt.table_text(table).splitlines()),
             "steps": {"rules": {"ok": True, "problems": [],
                                 "transistors": sum(r["kind"] in ("nmos", "pmos") for r in table["rows"])}},
             "variants": variants}
    return finish_entry(entry)


def cut_entry(candidate: dict, number: int, why: str) -> dict:
    """시간 제한으로 끝까지 재지 못한 후보의 기록 (동작 안 함으로 셈, 이유는 steps.cut)."""
    return {"how": candidate.get("how"), "in_train": candidate.get("in_train"), "table": candidate["table"],
            "form": "원래", "from": number, "variants": [],
            "steps": {"rules": {"ok": True, "problems": []}, "cut": why, "forms": [why]}}


def repair_candidate(candidate: dict, number: int, spec: dict, rules: list, rule_results: dict) -> list:
    """후보 하나의 여러 모양. 돌려주는 값: [원래 모양 기록] + 동작한 다른 모양 기록들."""
    import structure_blocks as sb
    import structure_doctor as sd
    import structure_rules
    first = {"how": candidate.get("how"), "in_train": candidate.get("in_train"), "table": candidate["table"],
             "form": "원래", "from": number, "steps": {}, "variants": []}
    try:
        table = to_table(candidate["table"])
    except ValueError as error:
        first["steps"]["rules"] = {"ok": False, "problems": [f"형식: {error}"]}
        return [first]
    problems = rule_problems(table)
    first["steps"]["rules"] = {"ok": not problems, "problems": problems,
                               "transistors": sum(r["kind"] in ("nmos", "pmos") for r in table["rows"])}
    if problems:
        return [first]
    out, tried = [], []
    for label, t, acts in forms(table):
        variants = evaluate_form(t, spec)
        tried.append(f"{label}: " + ("동작" if any(v["valid"] for v in variants) else (variants[-1]["reason"] or "")[:40]))
        if label == "원래":
            first["variants"] = variants
            out.append(finish_entry(first))
        elif any(v["valid"] for v in variants):
            out.append(form_entry(candidate, number, label, t, acts, variants))
    if not any(e.get("best") for e in out) and rules:      # 모양이 다 실패하면 쌓인 규칙
        failing = first["variants"][-1] if first["variants"] else {}
        flagged = set(failing.get("off") or []) | set(failing.get("triode") or [])
        feats = sb.features(table, sd.variant_kind(failing), flagged)
        for rule in structure_rules.matching(rules, feats)[:REPAIR_RULES]:
            try:
                t = apply_rule_actions(table, rule["then"])
            except (ValueError, TypeError, KeyError, AssertionError) as error:
                tried.append(f"규칙 {rule['id']}: 적용 못 함 ({str(error)[:40]})")
                rule_results.setdefault(rule["id"], False)
                continue
            variants = evaluate_form(t, spec)
            worked = any(v["valid"] for v in variants)
            rule_results[rule["id"]] = rule_results.get(rule["id"], False) or worked
            tried.append(f"규칙 {rule['id']}: " + ("동작" if worked else (variants[-1]["reason"] or "")[:40]))
            if worked:
                out.append(form_entry(candidate, number, f"규칙 {rule['id']}", t, rule["then"], variants))
                break
    out[0]["steps"]["forms"] = tried
    return out


def add_scales(part: str) -> None:
    """이미 판정한 결과에 빠진 출력단 배율만 더 돌려 합친다 (처음부터 다시 돌리지 않음)."""
    out_file = HERE / "data" / f"selection_{part}.json"
    result = json.loads(out_file.read_text(encoding="utf-8"))
    spec = run_sim.load_spec(HERE / f"spec_{part}.json")
    started = time.time()
    for number, entry in enumerate(result["entries"], 1):
        if not entry["steps"]["rules"]["ok"]:
            continue
        table = to_table(entry["table"])
        have = {v["output_scale"] for v in entry["variants"]}
        for unit_current, output_scale in SELECT_VARIANTS:
            if output_scale not in have:
                entry["variants"].append(evaluate_variant(table, unit_current, output_scale, spec))
        finish_entry(entry)
        b = entry.get("best")
        print(f"  후보 {number}: " + (f"{b['passed']}/{b['judged']} (출력단 {b['output_scale']:g}배)" if b else "동작 안 함"), flush=True)
        result["summary"] = summarize(result["entries"])
        out_file.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    s = result["summary"]
    print(f"동작 {s['working']} (학습에 없던 구조 {s['new_working']})  {time.time() - started:.0f} s")
    if s["selected"] is not None:
        e = result["entries"][s["selected"]]
        print(f"선택: 후보 {s['selected'] + 1}, {e['best']['passed']}/{e['best']['judged']} 통과 (출력단 {e['best']['output_scale']:g}배)")


def rank_key(variant: dict) -> tuple:
    return (variant["passed"], -(variant["measured"].get("idd") or float("inf")))


def summarize(entries: list) -> dict:
    stats = {"candidates": len(entries),
             "rules_ok": sum(e["steps"]["rules"]["ok"] for e in entries),
             "working": sum(bool(e.get("best")) for e in entries),
             "new_working": sum(bool(e.get("best")) and not e.get("in_train") for e in entries)}
    ranked = sorted((i for i, e in enumerate(entries) if e.get("best")),
                    key=lambda i: (entries[i]["best"]["passed"], -(entries[i]["best"]["idd"] or float("inf"))),
                    reverse=True)
    stats["ranking"] = ranked
    stats["selected"] = ranked[0] if ranked else None
    return stats


def main() -> None:
    part = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_PART
    if "--add-scales" in sys.argv:
        add_scales(part)
        return
    # --spec <이름>: 다른 후보 파일(예: 찾기 방식 cmp_opa320_ret)을 같은 스펙(spec_cmp_opa320.json)으로 판정
    spec_part = sys.argv[sys.argv.index("--spec") + 1] if "--spec" in sys.argv else part
    source = HERE / "data" / "train" / f"{part}_candidates.json"
    out_file = HERE / "data" / f"selection_{part}.json"
    # --bias-devices: 바이어스 단자를 실제 소자로 채운 상태로 크기를 정한다 (bias_convert.py). 결과는 _dev 를 붙여 따로 저장
    if "--bias-devices" in sys.argv:
        import auto_size
        auto_size.BIAS_MODE = "devices"
        out_file = HERE / "data" / f"selection_{part}_dev.json"
    data = json.loads(source.read_text(encoding="utf-8"))
    spec = run_sim.load_spec(HERE / f"spec_{spec_part}.json")
    result = {"source": source.name, "model": data.get("model"), "input": data.get("input"),
              "model_eval": data.get("eval"), "entries": []}
    # --resume: 중간에 멈춘 경우, 결과 파일에 이미 있는 후보(같은 순서, 같은 표)는 다시 판정하지 않는다
    done = []
    if "--resume" in sys.argv and out_file.exists():
        done = json.loads(out_file.read_text(encoding="utf-8"))["entries"]
    started = time.time()
    if "--repair" in sys.argv:
        repair_main(part, data, spec, result, out_file, started)
        return
    for number, candidate in enumerate(data["candidates"], 1):
        if number <= len(done) and done[number - 1]["table"] == candidate["table"]:
            result["entries"].append(done[number - 1])
            continue
        entry = evaluate_candidate(candidate, spec)
        result["entries"].append(entry)
        if entry.get("best"):
            note = f"동작, {part.upper()} {entry['best']['passed']}/{entry['best']['judged']} 통과"
        elif not entry["steps"]["rules"]["ok"]:
            note = "규칙 검사 탈락: " + "; ".join(entry["steps"]["rules"]["problems"])[:120]
        else:
            note = "크기 정하기 탈락: " + "; ".join(entry["steps"]["sizing"]["reasons"])[:120]
        print(f"  후보 {number}/{len(data['candidates'])} ({candidate.get('how')}"
              f"{', 학습에 있던 구조' if candidate.get('in_train') else ''}) {note}", flush=True)
        result["summary"] = summarize(result["entries"])
        out_file.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    s = result["summary"]
    print(f"후보 {s['candidates']}개 -> 규칙 통과 {s['rules_ok']} -> 동작 {s['working']} "
          f"(학습에 없던 구조 {s['new_working']})  {time.time() - started:.0f} s")
    if s["selected"] is not None:
        best = result["entries"][s["selected"]]["best"]
        print(f"선택: 후보 {s['selected'] + 1}, {part.upper()} {best['passed']}/{best['judged']} 통과 -> {out_file.name}")


_JOB = {}                         # 일꾼 프로세스가 물려받는 값 (spec, rules, stage_end)


def _worker_init() -> None:
    """일꾼마다 임시 회로 이름을 따로 (opamp_p<프로세스 번호>_). run_sim 이 opamp 로 시작하는 이름을 OP-Amp 로 본다."""
    label_dataset.DESIGN_NAME = f"opamp_p{os.getpid()}_"


def _measure_one(job: tuple) -> tuple:
    """후보 하나를 잰다 (일꾼 프로세스 안). 돌려주는 값: (번호, 기록들, 이 후보에서 쓴 규칙 결과)."""
    number, candidate = job
    spec, rules, stage_end = _JOB["spec"], _JOB["rules"], _JOB["stage_end"]
    t0 = time.time()
    rule_results = {}
    if t0 >= stage_end:
        return number, [cut_entry(candidate, number, f"시간 부족으로 건너뜀 (3단계 {STAGE_LIMIT_S // 60}분 제한)")], {}
    run_sim.CANDIDATE_DEADLINE = min(t0 + CANDIDATE_LIMIT_S, stage_end)
    try:
        entries = repair_candidate(candidate, number, spec, rules, rule_results)
    except run_sim.CandidateTimeout:
        entries = [cut_entry(candidate, number, f"시간 초과 ({time.time() - t0:.0f} s, 후보당 {CANDIDATE_LIMIT_S // 60}분 제한)")]
    except Exception as error:                    # 한 후보의 예상 못 한 오류로 전체가 멈추지 않게
        entries = [cut_entry(candidate, number, f"오류: {type(error).__name__}: {str(error)[:150]}")]
    finally:
        run_sim.CANDIDATE_DEADLINE = None
    return number, entries, rule_results


def _measure_all(candidates: list, workers: int):
    """(번호, 기록들, 규칙 결과)를 끝나는 대로 내놓는다. 일꾼이 1명이면 한 줄로."""
    jobs = list(enumerate(candidates, 1))
    if workers <= 1:
        _worker_init()                            # 한 줄로 재도 이름은 따로 (다른 실행과 겹치지 않게)
        for job in jobs:
            yield _measure_one(job)
        return
    import multiprocessing
    with multiprocessing.get_context("fork").Pool(workers, initializer=_worker_init) as pool:
        yield from pool.imap_unordered(_measure_one, jobs)


def repair_main(part: str, data: dict, spec: dict, result: dict, out_file: Path, started: float) -> None:
    """--repair: 후보마다 여러 모양을 재고, 쓴 규칙의 결과를 규칙 모음에 한 번씩 반영한다."""
    import structure_rules
    rules, rule_results = structure_rules.load(), {}
    chip = part
    try:                                          # 규칙의 '통한 칩'에 쓸 부품 이름
        hkg = json.loads((HERE / "data" / "extraction" / f"{part}_hkg.json").read_text(encoding="utf-8"))
        chip = hkg["ic_device"]["name"] or part
    except (OSError, ValueError, KeyError):
        pass
    print(f"고쳐 보기: 원래 / 바이어스 정리 / 상보 뒤집기, 다 실패하면 규칙 {len(rules)}개 중 맞는 것. "
          f"출력단 배율 {', '.join(f'x{s:g}' for s in REPAIR_SCALES)}", flush=True)
    stage_end = started + STAGE_LIMIT_S
    workers = max(1, min(SELECT_WORKERS, len(data["candidates"])))
    print(f"후보 {len(data['candidates'])}개를 일꾼 {workers}명이 나눠 잰다", flush=True)
    _JOB.update(spec=spec, rules=rules, stage_end=stage_end)
    finished = {}                                 # 번호 -> 기록들. 결과 파일에는 번호 순서로 쓴다
    for number, entries, used in _measure_all(data["candidates"], workers):
        candidate = data["candidates"][number - 1]
        for rule_id, worked in used.items():
            rule_results[rule_id] = rule_results.get(rule_id, False) or worked
        finished[number] = entries
        result["entries"] = [e for n in sorted(finished) for e in finished[n]]
        first = entries[0]
        if first["steps"].get("cut"):
            note = first["steps"]["cut"]
        elif not first["steps"]["rules"]["ok"]:
            note = "규칙 검사 탈락: " + "; ".join(first["steps"]["rules"]["problems"])[:100]
        else:
            note = " | ".join(first["steps"].get("forms") or [])
        good = [e for e in entries if e.get("best")]
        best = max(good, key=lambda e: e["best"]["passed"], default=None)
        head = f"동작 {best['best']['passed']}/{best['best']['judged']} ({best['form']})" if best else "실패"
        print(f"  후보 {number}/{len(data['candidates'])} ({candidate.get('how')}) {head} :: {note}"[:400]
              + f"  [{len(finished)}/{len(data['candidates'])} 끝]", flush=True)
        result["summary"] = summarize(result["entries"])
        out_file.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    for rule in rules:                            # 규칙마다 이번 칩에서 한 번만 반영 (후보가 많아도 한 칩 = 한 번)
        if rule["id"] in rule_results:
            change = structure_rules.record(rule, rule_results[rule["id"]], chip)
            print(f"규칙 {rule['id']}: 이번 칩에서 {'통함' if rule_results[rule['id']] else '안 통함'}"
                  + (f" ({change})" if change else ""), flush=True)
    if rule_results:
        structure_rules.save(rules)
    forms_ok = {}
    for e in result["entries"]:
        if e.get("best"):
            forms_ok[e.get("form", "원래")] = forms_ok.get(e.get("form", "원래"), 0) + 1
    cuts = [e["steps"]["cut"] for e in result["entries"] if e["steps"].get("cut")]
    timed_out = sum(c.startswith("시간 초과") for c in cuts)
    result["summary"] = dict(summarize(result["entries"]), forms_working=forms_ok,
                             timed_out=timed_out, skipped=len(cuts) - timed_out)
    out_file.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"후보 {len(data['candidates'])}개 -> 동작한 모양 {result['summary']['working']}개 "
          f"({', '.join(f'{k} {v}' for k, v in forms_ok.items()) or '없음'})  {time.time() - started:.0f} s"
          + (f"  (시간 초과 {timed_out}개, 건너뜀 {len(cuts) - timed_out}개)" if cuts else ""))


if __name__ == "__main__":
    main()
