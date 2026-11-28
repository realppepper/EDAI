"""
pipeline.py 6단계: 우리 회로(final.json)를 설계도로 넣고 박준석 시스템 하네스를 서버 없이 직접 돌린다.

    1. final.json 회로 -> 설계도(EXPERIENCE.json, make_blueprint.convert) -> analogverifier/harness2_library 에 넣음
    2. AutonomousAnalogDesignAgent(...).run(pdf) : Web Studio 의 "Generate" 와 같은 일
       데이터시트 추출은 1단계 결과(hkg.json)를 다시 써서 같은 스펙으로 돈다
       기본(EDAI_HARNESS_MODE=verify)은 하네스 LLM 합성·개선을 건너뛰고 우리 회로 채점만 한다 (use_verify_only).
       원래 흐름 전체를 돌리려면 EDAI_HARNESS_MODE=full
    3. 결과: <실행 폴더>/harness/result.json (통과율, 반복 기록, 최종 회로)
하네스가 남긴 경험 기록은 harness2_library 에 그대로 쌓인다 (박준석 시스템의 기록 방식). 넣었던 설계도 폴더만 지운다.

사용법: python run_harness.py <실행 폴더>
"""

import json
import re
import os
import shutil
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from extract_datasheet import AV_DIR     # noqa: E402  박준석 시스템 폴더 (저장소 루트)
ITERATIONS = 5                          # 비교 실험과 같은 반복 수 (Studio "5 Iterations (Standard)")
MODEL_FILE = "gf180_6v_typical.lib"     # ngspice 판은 이 이름을 GF180 PDK 원본 모델로 바꾼다 (sim_backend)
SEED_PREFIX = "EDAI_"


def find_netlist(out_dir: Path) -> str:
    """Studio 와 같은 순서로 결과 파일에서 최종 회로를 찾는다. 파일 이름 대소문자가 실행마다 달라서 소문자로 비교."""
    from file_find import find_files
    files = [p for p in find_files(out_dir, "*.cir")
             if not p.name.lower().endswith("_dyn.cir") and "testbench" not in p.name.lower()]
    for key in ("final_hermes_harness2", "_turn", "_iter"):
        for path in sorted(p for p in files if key in p.name.lower()):
            text = path.read_text(encoding="utf-8", errors="ignore")
            if ".subckt" in text.lower():
                return text
    return ""


def use_verify_only(agent, seed_code: str, seed_name: str) -> None:
    """하네스를 '검증만' 하게 바꾼다 (EDAI_HARNESS_MODE=full 이면 부르지 않음).

    하네스 원래 흐름은 1) LLM 직접 합성(최대 10번) 2) 설계도(우리 회로) 채점 3) LLM 개선 라운드인데, LM358·TLV271
    실행에서 1)·3)은 모두 0% 였고 최종 회로는 늘 우리 회로였다 (7단계 10분 중 실제 점수는 2) 의 1분 남짓).
    그래서 1) 자리에 '우리 회로를 칩 핀에 맞추고 하네스 검증기로 채점' 만 넣고, 3)·검증기 진화·하네스 FLAN-T5 씨앗은 끈다.
    채점(결정적 테스트벤치 + PDG 관문), 리포트, 하네스 기록 저장은 하네스 코드 그대로 쓴다.

    동적 테스트벤치(왜곡·채널 분리 등, LLM 이 측정 회로를 씀)도 끈다. 그런 줄은 '측정 방법 없음'(UNSUPPORTED_KIND)으로 남는다.
    LM358·LM324·LM6172 에서 한 번도 끝까지 돌지 못했고, 고쳐 돌려 보니 LLM 이 쓴 회로가 틀려 있었다
    (전원 줄 문법 오류로 0 V, GND 단락, 피드백 없는 개루프: 2026-11-27). 다시 켜려면 EDAI_HARNESS_DYNAMIC=1
    """
    os.environ["ANALOG_HARNESS2_ROUNDS"] = "0"        # 3) LLM 개선 라운드 끔
    os.environ["ANALOG_EVOLVE_VERIFIER"] = "0"        # 검증 항목 제안 LLM (Golden Oracle Gatekeeper) 끔
    if os.environ.get("EDAI_HARNESS_DYNAMIC") != "1":
        agent.dynamic_harness.identify_dynamic_specs = lambda *args, **kwargs: []
    from ai_analog_designer.circuit_synthesis import flan_t5_topology
    flan_t5_topology.synthesize_flan_t5_seed = lambda **kw: {"ok": False}   # 하네스 쪽 FLAN-T5 씨앗: 우리 회로만 잰다
    from ai_analog_designer.hermes_core.hermes_tools import HermesAnalogTools

    # 같은 회로를 두 번 재지 않게 (설계도 채점 뒤 하네스가 최종 회로를 한 번 더 잼)
    original_eval = agent._evaluate_netlist_unified
    cache: dict[str, dict] = {}

    def cached_eval(netlist_code, *args, **kwargs):
        # 하네스는 넘겨받은 회로를 한 번 더 정리해서 글자가 조금 달라진다 -> 최종 재측정은 우리 회로 채점 결과를 그대로 씀
        if kwargs.get("tag") == "final_hermes_eval" and "seed" in cache:
            return cache["seed"]
        result = original_eval(netlist_code, *args, **kwargs)
        cache.setdefault("seed", result)
        return result
    agent._evaluate_netlist_unified = cached_eval

    runner = agent.hermes_runner

    def seed_only_flow(ic_info, pins, specifications, pdg_schedule, measurement_plan=None, user_prompt=None,
                       verify_fn=None, progress_callback=None, base_harness_tree=None):
        part = ic_info.get("part_name") or ic_info.get("name") or "ANALOG_IC"
        subckt = make_subckt_name(part)
        category = ic_info.get("category", "analog_ic")
        if progress_callback:
            progress_callback(3, "EDAI 회로 검증", "우리 회로를 칩 핀에 맞추고 데이터시트 전체 항목으로 채점 (LLM 합성 없음)")
        t0 = time.time()
        workspace = os.path.join(runner.output_dir, "hermes_workspace")
        tools = HermesAnalogTools(output_dir=runner.output_dir, dut_name=subckt, pins=pins,
                                  specifications=specifications, pdg_schedule=pdg_schedule,
                                  measurement_plan=measurement_plan, verify_fn=verify_fn,
                                  skills_dir=os.path.join(workspace, "skills"),
                                  memory_file=os.path.join(workspace, "memories", "MEMORY.md"),
                                  llm_client=runner.llm_client, harness_tree=base_harness_tree)
        adapted = tools.adapt_blueprint_to_dut(seed_code, subckt)
        cleaned = tools.validate_netlist_syntax(adapted).get("cleaned_netlist", adapted)
        ev = tools.verify_circuit_pdg_gate(cleaned, tag="edai_seed", use_given_netlist=True)
        rate = float(ev.get("pass_rate_percent") or 0.0)
        print(f"[EDAI 검증] 우리 회로 통과율 {rate:.1f}% ({ev.get('passed_specs')}/{ev.get('total_specs')}), "
              f"관문 {ev.get('pdg_gate_stage') or ev.get('status')}, {time.time() - t0:.0f} s", flush=True)
        final_path = os.path.join(runner.output_dir, f"{subckt}_FINAL_HERMES_HARNESS2.cir")
        with open(final_path, "w", encoding="utf-8") as f:
            f.write(cleaned)
        if rate > 0 and base_harness_tree is not None:   # 하네스 기록: 이 칩 이름으로 우리 회로 하나만 남긴다
            tree = base_harness_tree.clone()
            tree.c5_skills = {seed_name: {"description": f"EDAI verified op-amp core for {part} (GF180 6V)",
                                          "subckt_code": cleaned}}
            runner.tuner.library.record_experience(
                task_id=part, category=category,
                cue=f"Transistor-level {part} ({category}) from EDAI structure pipeline, verified only (no LLM synthesis)",
                lesson=f"Start from blueprint '{seed_name}' (GF180MCU 6V, gm/ID sized).",
                evidence=f"Harness verifier pass rate {rate:.1f}% on the EDAI circuit.",
                tree=tree, score_before=0.0, score_after=rate)
        return {"subcircuit_name": subckt, "best_netlist": cleaned, "final_cir_path": final_path,
                "pass_rate_percent": rate, "passed_specs": ev.get("passed_specs", 0),
                "total_specs": len(specifications), "elapsed_seconds": round(time.time() - t0, 1),
                "turns_executed": 1, "workspace_dir": workspace,
                "trajectory": [{"turn": 1, "pass_rate": rate, "tools_called": ["edai_seed_verify"]}]}
    runner.run_design_flow = seed_only_flow


def target_rows_only(hkg: dict) -> tuple:
    """대상 칩 줄만 남긴 hkg 와 뺀 줄 수.

    한 데이터시트에 여러 칩이 있으면(LMV321/LMV358/LMV324) 하네스는 우리 회로 하나의 측정값을 모든 칩 줄과 비교했다.
    LMV321 2026-11-26: 공급 전류 525.6 µA 를 LMV358(앰프 2개)·LMV324(4개) 줄과도 비교해 실패 3개·통과 4개가 잘못 셈.
    조건이나 이름에 다른 칩 이름만 적힌 줄을 뺀다. 칩 이름이 없는 줄은 그대로 둔다 (스펙 고르기 spec_from_plan 과 같은 규칙)."""
    import spec_from_plan
    part = str(hkg.get("ic_device", {}).get("name") or "").upper()
    if not part:
        return hkg, 0
    kept = []
    for row in hkg.get("electrical_parameters", []):
        text = f"{row.get('test_conditions') or ''} {row.get('conditions') or ''} {row.get('name') or ''}"
        named = set(spec_from_plan.PART_NAME.findall(text))     # 대문자로 바꾸지 않는다: "LM324xx"(계열 전체)는 LM324 로 읽혀야 함
        if named and not any(spec_from_plan.same_part(n, part) for n in named):
            continue
        kept.append(row)
    dropped = len(hkg.get("electrical_parameters", [])) - len(kept)
    return {**hkg, "electrical_parameters": kept}, dropped


# 하네스 판정 결과(status) -> 결과 화면에 보여 줄 묶음
COUNT_GROUPS = {
    "PASS": "passed", "FAIL": "failed",
    # 보통값만 있는 줄: 데이터시트가 정한 합격 기준이 없어 판정하지 않고 참고로만 (2026-11-28 결정)
    "PASS_TYP": "typ_only", "FAIL_TYP": "typ_only",
    "NOT_TESTABLE_SUPPLY": "supply", "NOT_MEASURED_SIM_ERROR": "sim_error",
    "NO_NUMERIC_LIMIT": "no_limit", "UNSUPPORTED_KIND": "no_method",
}


def spec_counts(out_dir: Path) -> dict:
    """하네스 채점 파일(*_SPEC_EVALUATION.json)의 줄을 묶음별로 센다. judged = 통과 + 실패 (통과율의 분모).
    not_testable 은 열·ESD·절대최대·권장 조건처럼 시뮬레이션으로 확인할 수 없는 줄, supply 는 전원 조건이 판정 범위(AV_SUPPLY_BAND_V, 4.5~5.5 V) 밖인 줄."""
    from file_find import find_files
    files = find_files(out_dir, "*_SPEC_EVALUATION.json")
    if not files:
        return {}
    rows = json.loads(files[0].read_text(encoding="utf-8")).get("spec_evaluations") or []
    counts = {"total": len(rows), "passed": 0, "failed": 0, "not_testable": 0, "supply": 0, "sim_error": 0,
              "no_limit": 0, "no_method": 0, "typ_only": 0}
    for row in rows:
        status = str(row.get("status") or "")
        group = COUNT_GROUPS.get(status, "not_testable" if status.startswith("NOT_TESTABLE") else "no_method")
        counts[group] += 1
    counts["judged"] = counts["passed"] + counts["failed"]
    return counts


TABLE_TITLE = r"electrical characteristics|unless otherwise noted"
LISTED_SUPPLIES = r"=\s*±?\d+(?:\.\d+)?\s*V\s*,\s*±?\d"      # "VDD = 2.7 V, 5 V, and ±5 V" 처럼 표 하나에 전원 여러 개


def page_title_supplies(pages: dict | None) -> dict:
    """쪽 번호 -> 그 쪽 표 제목의 전체 전원 [V]. 제목 전원이 하나로 분명한 쪽만 (여러 개면 줄마다 어느 것인지 몰라 뺀다)."""
    import re
    sys.path.insert(0, str(AV_DIR))
    from ai_analog_designer.neuro_symbolic_verifier.spec_planner import condition_supply
    found = {}
    for key, text in (pages or {}).items():
        if not isinstance(text, str):
            continue
        titles = [line for line in text.splitlines() if re.search(TABLE_TITLE, line, re.I)]
        if any(re.search(LISTED_SUPPLIES, line) for line in titles):
            continue
        values = {condition_supply(line) for line in titles} - {None}
        if len(values) == 1:
            found[int(key)] = values.pop()
    return found


def with_title_supply(hkg: dict, pages: dict | None) -> tuple:
    """조건에 전원이 없는 줄에 그 쪽 표 제목의 전원을 붙인다. 붙인 줄 수도 돌려준다.

    하네스는 전원이 안 적힌 줄을 기본 전원(공정 한계 5 V)으로 재고 데이터시트 기준과 비교했다.
    LM6172 2026-11-27: '±15 V 표' 줄 다수가 조건에 전원이 없어 5 V 로 재고 ±15 V 기준과 비교됨.
    전원이 붙으면 판정 범위(4.5~5.5 V) 밖인 줄은 다른 전원 조건으로 빠진다 (spec_planner)."""
    sys.path.insert(0, str(AV_DIR))
    from ai_analog_designer.neuro_symbolic_verifier.spec_planner import condition_supply
    titles = page_title_supplies(pages)
    rows, added = [], 0
    for row in hkg.get("electrical_parameters", []):
        supply = titles.get(row.get("page"))
        if supply is not None and condition_supply(row.get("test_conditions") or "") is None:
            row = {**row, "test_conditions": f"{row.get('test_conditions') or ''}, VS = {supply:g} V (table title)".lstrip(", ")}
            added += 1
        rows.append(row)
    return {**hkg, "electrical_parameters": rows}, added


def drop_temperature_rows(hkg: dict) -> tuple:
    """온도 범위만 적힌 줄("TA = -40°C to +125°C", "Full range")을 뺀 hkg 와 뺀 줄 수.
    시뮬레이션은 25°C 하나라 온도 범위 전체의 한계는 확인할 수 없다 (2026-11-28 결정: 온도 줄은 무시).
    25°C 가 같이 적힌 줄은 25°C 줄로 보고 남긴다 (spec_from_plan.AT_25C)."""
    import spec_from_plan
    kept = []
    for row in hkg.get("electrical_parameters", []):
        text = f"{row.get('test_conditions') or ''} {row.get('conditions') or ''}"
        if spec_from_plan.TEMPERATURE_RANGE.search(text) and not spec_from_plan.AT_25C.search(text):
            continue
        kept.append(row)
    return {**hkg, "electrical_parameters": kept}, len(hkg.get("electrical_parameters", [])) - len(kept)


# 추출 값 점검 (2026-11-28, spec_from_plan.check_values 와 같은 생각). 이름으로 좋은 방향을 정한다.
# 크기(절댓값)로 본다: 바이어스 전류처럼 음수로 적힌 줄(-10 / -35 nA)은 크기 10 -> 35 가 정상 순서
LOWER_BETTER_NAME = re.compile(r"swing from rail|supply current|quiescent|bias current|offset current|noise", re.I)
HIGHER_BETTER_NAME = re.compile(r"gain|rejection|bandwidth|slew|output current", re.I)
# 제거비·이득을 µV/V, mV/V 처럼 비로 적으면 작을수록 좋아 방향이 거꾸로다. 단락 전류(short-circuit)는 한계라 뺀다
RATIO_UNIT = re.compile(r"V\s*/\s*V|µ|μ|u|ppm|%", re.I)
NOT_DIRECTED = re.compile(r"short.circuit", re.I)


def direction(row: dict):
    """'lower' / 'higher' / None (모름: 손대지 않음)."""
    name, unit = str(row.get("name") or ""), str(row.get("unit") or "")
    if NOT_DIRECTED.search(name):
        return None
    if LOWER_BETTER_NAME.search(name):
        return "lower"
    if HIGHER_BETTER_NAME.search(name):
        ratio = re.search(r"rejection|gain", name, re.I) and RATIO_UNIT.search(unit) and "dB" not in unit
        return "lower" if ratio else "higher"
    return None
NUMBER = re.compile(r"[-+−–]?\d+(\.\d+)?")


def check_rows(hkg: dict) -> tuple:
    """칸이 밀린 줄을 바로잡고, 바로잡을 수 없는 줄(기호가 숫자, 최소=보통=최대, 크기 순서가 거꾸로)은 뺀다.
    돌려주는 값: (hkg, 바로잡은 줄 수, 뺀 줄 [{"symbol", "name", "why"}])."""
    kept, fixed, dropped = [], 0, []
    for row in hkg.get("electrical_parameters", []):
        lo, typ, hi = (row.get(k) if isinstance(row.get(k), (int, float)) else None for k in ("min", "typ", "max"))
        name = str(row.get("name") or "")
        why = None
        if NUMBER.fullmatch(str(row.get("symbol") or "").strip()):
            why = "기호 자리에 숫자"
        elif lo is not None and lo == typ == hi:
            why = "최소 = 보통 = 최대"
        way = direction(row)
        if why is None and way == "lower" and lo is not None and hi is None:
            row = dict(row, min=None, typ=lo if typ is not None else row.get("typ"), max=typ if typ is not None else lo,
                       value_fix="작을수록 좋은 항목에 최소값만 있어 보통/최대로 읽음")
            fixed += 1
        elif why is None and way == "higher" and hi is not None and lo is None:
            row = dict(row, min=typ if typ is not None else hi, typ=hi if typ is not None else row.get("typ"), max=None,
                       value_fix="클수록 좋은 항목에 최대값만 있어 최소/보통으로 읽음")
            fixed += 1
        values = [row.get(k) for k in ("min", "typ", "max") if isinstance(row.get(k), (int, float))]
        if why is None and len({v > 0 for v in values if v}) == 1:      # 부호가 같을 때만 크기 순서를 본다
            mags = [abs(v) for v in values]
            if way and any(a > b for a, b in zip(mags, mags[1:])):
                why = "최소 ≤ 보통 ≤ 최대 순서가 아님"
        if why:
            dropped.append({"symbol": row.get("symbol"), "name": name, "why": why,
                            "values": [row.get("min"), row.get("typ"), row.get("max")]})
            continue
        kept.append(row)
    return {**hkg, "electrical_parameters": kept}, fixed, dropped


def make_subckt_name(part: str) -> str:
    """하네스와 같은 규칙의 subckt 이름 (hermes_workflow: 영숫자·_ 외는 _ , 대문자)."""
    import re
    return re.sub(r"[^a-zA-Z0-9_]", "_", part).upper()


def main() -> None:
    run_dir = Path(sys.argv[1]).resolve()
    sys.path.insert(0, str(HERE))
    import extract_datasheet
    import make_blueprint
    extract_datasheet.load_keys()

    final = json.loads((run_dir / "final.json").read_text(encoding="utf-8"))
    hkg = json.loads((run_dir / "hkg.json").read_text(encoding="utf-8"))
    part = make_blueprint.re.sub(r"\W", "_", str(hkg["ic_device"]["name"])).upper()
    code, mapping = make_blueprint.convert(final["subckt"], hkg["pins"], part, MODEL_FILE)
    seed_name = f"{SEED_PREFIX}{part}"
    seed_dir = AV_DIR / "harness2_library" / "operational_amplifier" / seed_name
    experience = {
        "task_id": seed_name, "category": "operational_amplifier",
        "cue": f"Initial transistor-level topology for {part} proposed by EDAI (FLAN-T5 + rules: {final['rules'] or 'none'})",
        "lesson": (f"Start from blueprint '{seed_name}': GF180MCU 6V transistor-level op-amp sized by gm/ID "
                   f"(ngspice pre-check {final['passed']}/{final['judged']} specs). "
                   f"Keep the .include model line; devices use nfet_06v0_bsim0 / pfet_06v0_bsim0."),
        "evidence": {"table": final["table"], "pin_map": mapping, "output_scale": final["output_scale"]},
        "score_before": 0.0, "score_after": 0.0, "delta_score": 0.0,
        "harness_tree": {"c5_skills": {seed_name: {
            "description": f"EDAI FLAN-T5 initial op-amp core for {part} (GF180 6V)", "subckt_code": code}}},
    }
    out_dir = run_dir / "harness"
    out_dir.mkdir(exist_ok=True)
    (out_dir / "blueprint.json").write_text(json.dumps(experience, ensure_ascii=False, indent=1), encoding="utf-8")
    target_hkg, dropped = target_rows_only(hkg)
    target_hkg, temp_dropped = drop_temperature_rows(target_hkg)
    target_hkg, value_fixed, bad_rows = check_rows(target_hkg)
    pages_file = run_dir / "pages.json"
    pages = json.loads(pages_file.read_text(encoding="utf-8")) if pages_file.exists() else None
    target_hkg, titled = with_title_supply(target_hkg, pages)
    hkg_file = out_dir / "hkg_target.json"
    hkg_file.write_text(json.dumps(target_hkg, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"하네스에 넘기는 항목: {len(target_hkg['electrical_parameters'])}줄 (다른 칩 줄 {dropped}개, 온도 범위 줄 {temp_dropped}개, "
          f"추출 오류 줄 {len(bad_rows)}개 뺌, 칸을 바로잡은 줄 {value_fixed}개, 표 제목 전원을 붙인 줄 {titled}개)", flush=True)

    sys.path.insert(0, str(AV_DIR))
    os.chdir(AV_DIR)                    # 하네스는 harness2_library 를 현재 폴더 기준으로 찾는다
    from ai_analog_designer.autonomous_design_agent import AutonomousAnalogDesignAgent

    def progress(phase: int, title: str, message: str) -> None:
        print(f"[하네스 {phase}] {title}: {message}", flush=True)

    t0 = time.time()
    seed_dir.mkdir(parents=True, exist_ok=True)
    (seed_dir / "EXPERIENCE.json").write_text(json.dumps(experience, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        agent = AutonomousAnalogDesignAgent(output_dir=str(out_dir), max_iterations=ITERATIONS,
                                            reuse_hkg_path=str(hkg_file))
        # PDF 읽기: 하네스는 원래 PDF 를 처음부터 다시 읽는다 (NVIDIA Nemotron-Parse, 서비스가 붐비면 20분 넘게,
        # LM358 2026-11-28). 이 실행의 1단계가 읽은 결과(pdf_parsed.json)를 그대로 쓴다. 없으면 같은 PDF 의 저장본
        parsed = extract_datasheet.read_parsed(run_dir / "pdf_parsed.json") or extract_datasheet.load_parsed(run_dir / "datasheet.pdf")
        if parsed is not None:
            agent.pdf_parser.parse_pdf = lambda *args, **kwargs: parsed
            print("PDF 읽기: 1단계에서 읽은 결과를 씀", flush=True)
        mode = os.environ.get("EDAI_HARNESS_MODE", "verify")
        print(f"하네스 방식: {mode} ({'우리 회로 채점만' if mode == 'verify' else '하네스 LLM 합성·개선 포함'})", flush=True)
        if mode == "verify":
            use_verify_only(agent, code, seed_name)
        result = agent.run(datasheet_pdf_path=str(run_dir / "datasheet.pdf"), progress_callback=progress)
    finally:
        shutil.rmtree(seed_dir, ignore_errors=True)
    summary = result.get("summary", {}) if isinstance(result, dict) else {}
    netlist = (result or {}).get("final_netlist") or ""
    if ".subckt" not in netlist.lower():
        netlist = find_netlist(out_dir)
    iterations = summary.get("iterations") or []
    record = {"pass_rate_percent": summary.get("pass_rate_percent"), "part_name": summary.get("part_name"),
              "iterations_count": len(iterations),
              "iterations": [{k: it.get(k) for k in ("iteration", "pass_rate_percent", "status") if k in it}
                             for it in iterations if isinstance(it, dict)],
              "final_netlist": netlist, "pin_map": {k: v for k, v in mapping.items() if isinstance(v, str)},
              "seed": seed_name, "seconds": round(time.time() - t0), "other_part_rows_dropped": dropped, "temperature_rows_dropped": temp_dropped,
              "title_supply_rows": titled, "extract_error_rows": bad_rows, "value_fixed_rows": value_fixed}
    record["counts"] = spec_counts(out_dir)
    if record["counts"]:                        # 통과율도 최소·최대가 있는 줄로만 다시 계산 (하네스 원래 값은 보통값 줄 포함)
        c = record["counts"]
        record["pass_rate_harness_percent"] = record["pass_rate_percent"]
        record["pass_rate_percent"] = round(100 * c["passed"] / c["judged"], 1) if c["judged"] else None
    (out_dir / "result.json").write_text(json.dumps(record, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    print(f"하네스 끝: 통과율 {record['pass_rate_percent']}%, 반복 {record['iterations_count']}번, {record['seconds']} s", flush=True)


if __name__ == "__main__":
    main()
