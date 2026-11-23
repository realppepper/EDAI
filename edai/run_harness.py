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
    채점(결정적 테스트벤치 + PDG 관문 + 동적 테스트벤치), 리포트, 하네스 기록 저장은 하네스 코드 그대로 쓴다.
    """
    os.environ["ANALOG_HARNESS2_ROUNDS"] = "0"        # 3) LLM 개선 라운드 끔
    os.environ["ANALOG_EVOLVE_VERIFIER"] = "0"        # 검증 항목 제안 LLM (Golden Oracle Gatekeeper) 끔
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
                                            reuse_hkg_path=str(run_dir / "hkg.json"))
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
              "seed": seed_name, "seconds": round(time.time() - t0)}
    (out_dir / "result.json").write_text(json.dumps(record, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    print(f"하네스 끝: 통과율 {record['pass_rate_percent']}%, 반복 {record['iterations_count']}번, {record['seconds']} s", flush=True)


if __name__ == "__main__":
    main()
