"""
pipeline.py 6단계: 우리 회로(final.json)를 설계도로 넣고 박준석 시스템 하네스를 서버 없이 직접 돌린다.

    1. final.json 회로 -> 설계도(EXPERIENCE.json, make_blueprint.convert) -> analogverifier/harness2_library 에 넣음
    2. AutonomousAnalogDesignAgent(...).run(pdf) : Web Studio 의 "Generate" 와 같은 일
       데이터시트 추출은 1단계 결과(hkg.json)를 다시 써서 같은 스펙으로 돈다
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
