"""
데이터시트 PDF 하나 -> 최종 회로도까지 한 번에 도는 실행 흐름 (UI 가 부른다, 직접 돌려도 됨).

결과는 실행 폴더 하나(runs/<날짜_시각_이름>/)에 모인다. 단계가 끝날 때마다 status.json 과 report.html 을 새로 쓴다.
    input.json        PDF 경로, 이름 (UI 가 만듦)
    status.json       단계별 상태·걸린 시간·요약
    log.txt           진행 기록
    datasheet.pdf     올린 데이터시트
    hkg.json          1. 데이터시트 분석 결과 (데이터시트 추출)
    spec.json         1. 우리 판정 기준 (측정 항목과 목표값)
    candidates.json   2. 모델(FLAN-T5)이 만든 구조 후보
    selection_dev.json 3. 후보마다 바이어스 채우기·크기 정하기·측정 결과
    selection.json    4. 순위 규칙 v4 로 고른 결과
    final.json        6. 규칙(상보 뒤집기, 캐스코드)을 해 본 결과와 하네스에 넘긴 회로 (7단계가 튜닝한 회로로 바꿈)
    final_rules.json  7. 튜닝 전 6단계 회로 (튜닝을 다시 돌릴 때 이것에서 시작)
    tune.json         7. 스펙 맞추기 튜닝 기록 (전류·출력단 배율·보상 커패시터를 바꿔 잰 결과)
    harness/          8. 하네스 (우리 회로를 데이터시트 전체 줄로 채점만 함, LLM 없음. result.json 의 counts 가 묶음별 개수)
    schematic/        9. 회로도 PNG·SVG (하네스 전 우리 회로, 하네스 후 최종 회로)
    report.html       결과 화면 (파일 하나, 더블클릭으로 열림)

사용법 (WSL 가상환경, 프로젝트 폴더에서):
    ~/.venvs/edai/bin/python pipeline.py runs/<실행 폴더>        (폴더 안에 input.json 이 있어야 함)
    ~/.venvs/edai/bin/python pipeline.py runs/<실행 폴더> --from rules   (그 단계부터 다시)
"""

import json
import re
import shutil
import subprocess
import sys
import time
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
PY = sys.executable
STEPS = [
    ("extract", "1. 데이터시트 분석"),
    ("candidates", "2. 모델 구조 후보"),
    ("select", "3. 바이어스 채우기·크기 정하기·측정"),
    ("fix", "4. 실패한 구조 고치기 (규칙·LLM)"),
    ("rank", "5. 구조 고르기"),
    ("rules", "6. 규칙 적용"),
    ("tune", "7. 스펙 맞추기 튜닝"),
    ("harness", "8. 데이터시트 전체 검증 (하네스 에이전트)"),
    ("schematic", "9. 최종 회로도"),
]
RULE_SCALES = (20.0, 50.0)      # 규칙을 적용한 회로를 잴 때 해 보는 출력단 배율 (구조 선택과 같은 값)


# ---------------------------------------------------------------- LLM 공급자와 호출 기록
# input.json 의 "llm" (nim / openrouter / groq) 으로 이 실행의 LLM 공급자를 정한다. 없으면 NVIDIA(nim).
# "llm_model" 을 주면 1단계(스펙 뽑기·측정 계획)에서 그 모델을 쓴다. 키는 .env (extract_datasheet.ENV_KEYS)
LLM_CALLS = []          # 이 실행에서 부른 LLM 호출 (박준석 LLMClient._log 를 감싸서 모음)


def setup_llm(run) -> None:
    import os
    provider = (run.input.get("llm") or "nim").lower()
    os.environ["LLM_PROVIDER"] = provider
    if run.input.get("llm_model"):
        os.environ["LLM_MODEL"] = run.input["llm_model"]
        os.environ["LLM_CAPABLE_MODEL"] = run.input["llm_model"]     # 1단계 스펙 뽑기는 capable 등급 모델을 부른다
    try:
        import extract_datasheet
        extract_datasheet.load_keys()
        sys.path.insert(0, str(extract_datasheet.AV_DIR))
        from ai_analog_designer.llm_client import LLMClient
    except Exception as error:                      # 기록만 못 할 뿐 실행은 그대로
        run.log(f"LLM 호출 기록 준비 실패: {error}")
        return
    original = LLMClient._log
    if getattr(original, "_edai_wrapped", False):
        return

    def _log(self, tag, model, attempt, status, res, error=None):
        LLM_CALLS.append({"provider": self.provider, "model": model, "tag": tag, "status": status,
                          "seconds": res.get("total_s") or 0, "tokens": res.get("completion_tokens"),
                          "cost_usd": res.get("cost_usd")})
        return original(self, tag, model, attempt, status, res, error)
    _log._edai_wrapped = True
    LLMClient._log = _log
    run.status["llm"] = {"provider": provider, "model": run.input.get("llm_model")}
    run.log(f"LLM 공급자: {provider}" + (f", 모델 {run.input['llm_model']}" if run.input.get("llm_model") else ""))


def llm_summary(calls: list) -> dict:
    """단계 하나의 LLM 호출 요약 (호출들이 동시에 돌기도 해서 seconds 합은 단계 시간보다 클 수 있음)."""
    if not calls:
        return None
    models = {}
    for c in calls:
        models[c["model"]] = models.get(c["model"], 0) + 1
    return {"calls": len(calls), "ok": sum(c["status"] == "ok" for c in calls),
            "seconds": round(sum(c["seconds"] for c in calls), 1),
            "cost_usd": round(sum(c["cost_usd"] or 0 for c in calls), 4), "models": models}


# ---------------------------------------------------------------- 실행 폴더 상태
class Run:
    def __init__(self, run_dir: Path):
        self.dir = run_dir.resolve()
        self.input = json.loads((self.dir / "input.json").read_text(encoding="utf-8"))
        self.name = self.input["name"]          # 데이터 파일 이름에 쓰는 이름 (실행마다 다름)
        self.pdf = self.dir / "datasheet.pdf"
        status_file = self.dir / "status.json"
        self.status = json.loads(status_file.read_text(encoding="utf-8")) if status_file.exists() else {
            "title": self.input.get("title", self.name), "name": self.name,
            "steps": [{"key": k, "title": t, "state": "wait"} for k, t in STEPS]}
        # 단계를 더하거나 이름을 바꿨을 때 예전 실행 폴더도 지금 단계 목록으로 (없던 단계는 '대기'로 끼워 넣음)
        old = {s["key"]: s for s in self.status["steps"]}
        self.status["steps"] = [dict(old.get(k, {"key": k, "state": "wait"}), title=t) for k, t in STEPS]

    def log(self, message: str) -> None:
        line = f"[{time.strftime('%H:%M:%S')}] {message}"
        print(line, flush=True)
        with open(self.dir / "log.txt", "a", encoding="utf-8") as f:
            f.write(line + "\n")

    def step(self, key: str) -> dict:
        return next(s for s in self.status["steps"] if s["key"] == key)

    def save(self) -> None:
        (self.dir / "status.json").write_text(json.dumps(self.status, ensure_ascii=False, indent=1), encoding="utf-8")
        try:
            import make_run_report
            make_run_report.write(self.dir)
        except Exception as error:                 # 결과 화면을 못 만들어도 실행은 계속
            self.log(f"결과 화면 만들기 실패: {error}")

    def copy(self, source: Path, target: str) -> None:
        shutil.copyfile(source, self.dir / target)

    def read(self, file: str):
        return json.loads((self.dir / file).read_text(encoding="utf-8"))


REFRESH_EVERY_S = 30         # 오래 걸리는 단계에서 결과 화면을 다시 만드는 간격 (하네스 진행 표가 바로 보이게)


def sh(run: Run, cmd: list, cwd: Path = HERE) -> None:
    """다른 스크립트를 돌리고 출력을 log.txt 에 남긴다. 실패하면 멈춘다."""
    last = time.time()
    run.log("실행: " + " ".join(str(c) for c in cmd))
    proc = subprocess.Popen([str(c) for c in cmd], cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, encoding="utf-8", errors="replace")
    for line in proc.stdout:
        line = line.rstrip()
        if line and not line.startswith("[LLM]"):
            run.log("  " + line)
        if time.time() - last > REFRESH_EVERY_S:
            run.save()
            last = time.time()
    if proc.wait() != 0:
        raise RuntimeError(f"{Path(str(cmd[1])).name} 실패 (종료 코드 {proc.returncode})")


# ---------------------------------------------------------------- 단계
def step_extract(run: Run) -> dict:
    import extract_datasheet
    # 대상 칩 = 올린 파일 이름 (LMV321.pdf -> LMV321). PDF 본문에 그 이름이 있을 때만 쓰고, 아니면 분석이 고른다
    inp = run.read("input.json")
    target = extract_datasheet.part_from_filename(run.pdf, inp.get("pdf_name"))
    inp["part"] = target or ""
    (run.dir / "input.json").write_text(json.dumps(inp, ensure_ascii=False, indent=1), encoding="utf-8")
    run.log(f"대상 칩: {target} (파일 이름)" if target else "대상 칩: 파일 이름이 칩 이름이 아니어서 분석이 고름")
    hkg_file = extract_datasheet.extract(run.pdf, run.name, log=run.log, target=target)
    spec_file = extract_datasheet.plan_specs(hkg_file, run.name, log=run.log)
    run.copy(hkg_file, "hkg.json")
    run.copy(spec_file, "spec.json")
    run.copy(HERE / "data" / "train" / f"{run.name}.json", "model_input.json")
    pages = HERE / "data" / "extraction" / f"{run.name}_pages.json"
    if pages.exists():
        run.copy(pages, "pages.json")
    extract_datasheet.build_pdg(run.dir / "hkg.json", run.dir, log=run.log, pages_file=run.dir / "pages.json")
    hkg, spec = run.read("hkg.json"), run.read("spec.json")
    part = str(hkg["ic_device"].get("name") or "").strip().upper()
    if part:
        # 제목: 파일 이름이 칩 이름이면 그 이름, 아니면 데이터시트에서 뽑은 부품 이름. 뽑은 이름은 따로 남기고,
        # 둘이 다르면 check_step 이 1단계 결과에 경고를 띄운다 (LMV321 을 LMV358 로 분석한 일, 2026-11-24)
        inp = run.read("input.json")
        inp["title"] = target or part
        inp["extracted_part"] = part
        (run.dir / "input.json").write_text(json.dumps(inp, ensure_ascii=False, indent=1), encoding="utf-8")
    kind = not_opamp_kind(hkg["ic_device"], spec.get("device_class"))
    if kind:
        raise Unsupported(f"생성 불가: op-amp가 아님 ({kind})")
    other = spec.get("other_supply") or {}
    if not spec["specs"] and other.get("rows"):
        # 판정할 5 V 근처 조건 줄이 없음 (예: LM6172 는 ±5 V = 10 V, ±15 V = 30 V 표뿐). 2~9단계를 돌려도 비교할 기준이 없다
        volts = ", ".join(f"{v:g} V" for v in other.get("supplies_v") or [])
        raise Unsupported(f"생성 불가: 전압 조건 (데이터시트 조건 {volts})")
    return {"part": hkg["ic_device"].get("name"), "rows": len(hkg["electrical_parameters"]), "pins": len(hkg["pins"]),
            "judged": len(spec["specs"]), "model_input": run.read("model_input.json")["input"]}


class Unsupported(Exception):
    """이 칩은 우리 공정·전원으로 설계할 수 없음 (실패가 아니라 '생성 불가'로 멈춘다)."""


# op-amp 가 아닌 칩: 칩 종류(1단계 추출의 category·이름) 글에 이 말이 있으면 -> 화면에 쓸 이름. 위에서부터 먼저 맞는 것
NOT_OPAMP_WORDS = [
    (r"fully[- ]differential", "완전 차동 증폭기 (출력 두 개)"), (r"instrumentation", "계측 증폭기"), (r"comparator", "비교기"), (r"front[- ]?end|\bafe\b", "아날로그 프런트엔드"),
    (r"analog[- ]to[- ]digital|\badc\b|converter", "변환기(ADC 등)"), (r"isolat", "절연 증폭기"),
    (r"current[- ]sens|current[- ]shunt|current monitor", "전류 감지 증폭기"), (r"difference amplifier", "차동(디퍼런스) 증폭기"),
    (r"programmable[- ]gain|variable[- ]gain|\bpga\b|\bvga\b", "가변 이득 증폭기"), (r"logarithmic|\blog amp", "로그 증폭기"),
    (r"transconductance|\bota\b", "OTA"), (r"regulator|\bldo\b|dc[- ]dc|buck|boost", "전원 IC"),
    (r"reference", "기준 전압원"), (r"timer", "타이머"), (r"audio power|power amplifier|class[- ]d", "전력 증폭기"),
    (r"driver", "드라이버"), (r"multiplier|integrator|clock|buffer", "op-amp 가 아닌 IC"),
]
# 측정 계획(spec_planner.detect_device_class)의 분류 -> 이름. 'opamp' 는 아무 말에도 안 걸릴 때의 기본값이라 그것만으로는 믿지 않는다
NOT_OPAMP_CLASS = {"inamp": "계측 증폭기", "comparator": "비교기", "ldo": "전원 IC", "timer": "타이머",
                   "shunt_ref": "기준 전압원", "audio_amp": "전력 증폭기"}
OPAMP_WORDS = r"operational amplifier|op[- ]?amp|voltage[- ]feedback amplifier|\bamplifier"


def not_opamp_kind(ic_device: dict, device_class: str = None):
    """op-amp 가 아니면 그 종류 이름, op-amp 면 None. AD8232(심전도 프런트엔드)를 op-amp 처럼 끝까지 돌려
    '판정할 항목 없음'으로 끝난 일 (2026-11-27). LLM 을 더 부르지 않고 1단계 결과(칩 종류 글, 측정 계획 분류)만 본다."""
    kind_text = " ".join(str(ic_device.get(k) or "") for k in ("category", "name")).lower()
    for pattern, label in NOT_OPAMP_WORDS:
        if re.search(pattern, kind_text):
            return label
    if device_class in NOT_OPAMP_CLASS:
        return NOT_OPAMP_CLASS[device_class]
    whole = kind_text + " " + str(ic_device.get("description") or "").lower()
    return None if re.search(OPAMP_WORDS, whole) else "op-amp 가 아닌 IC"


def step_candidates(run: Run) -> dict:
    sh(run, [PY, "generate_candidates.py", run.name])
    run.copy(HERE / "data" / "train" / f"{run.name}_candidates.json", "candidates.json")
    cands = run.read("candidates.json")["candidates"]
    ok = [c for c in cands if not c["problems"]]
    return {"total": len(cands), "rule_ok": len(ok), "new": sum(not c["in_train"] for c in ok)}


def step_select(run: Run) -> dict:
    # --repair: 후보마다 원래 / 바이어스 정리 / 상보 뒤집기 / 쌓인 규칙 모양을 같이 잰다 (select_structure.repair_main)
    sh(run, [PY, "select_structure.py", run.name, "--bias-devices", "--repair"])
    run.copy(HERE / "data" / f"selection_{run.name}_dev.json", "selection_dev.json")
    sel = run.read("selection_dev.json")
    entries = sel["entries"]
    working = [e for e in entries if e.get("best")]
    return {"evaluated": len({e.get("from", i) for i, e in enumerate(entries)}), "forms": len(entries),
            "working": len(working), "forms_working": (sel.get("summary") or {}).get("forms_working"),
            "timed_out": (sel.get("summary") or {}).get("timed_out", 0),     # 후보당 3분 제한에 걸린 후보
            "skipped": (sel.get("summary") or {}).get("skipped", 0),         # 3단계 45분 제한으로 못 잰 후보
            "best_passed": max((f"{e['best']['passed']}/{e['best']['judged']}" for e in working),
                               key=lambda x: int(x.split("/")[0]), default=None)}


def step_fix(run: Run) -> dict:
    """동작한 후보가 없으면 쌓인 규칙을 먼저 적용하고, 안 되면 LLM 이 블록을 바꿔 고친다 (structure_doctor.py). 있으면 건너뜀."""
    import structure_doctor
    report = structure_doctor.run(run.dir, log=run.log)
    return {"needed": report["needed"], "working_before": report["working_before"],
            "llm_calls": report["llm_calls"], "fixed": len(report["fixed"]),
            "rules_tried": len(report.get("rules_tried") or []),
            "rules_written": sum(bool(w.get("new")) for w in report.get("rules_written") or [])}


def step_rank(run: Run) -> dict:
    import rank_v2
    sel = run.read("selection_dev.json")
    top = rank_v2.ranked(sel, "v4")
    if not top:
        raise RuntimeError("동작한 후보가 없습니다")
    rank_v2.write_selection(sel, top[0], run.dir / "selection.json", "v4")
    keep = ("index", "passed", "judged", "scale", "gain_nodes", "input_ok", "avd", "shortfall")
    return {"rule": "v4", "top": [dict({k: r[k] for k in keep}, how=sel["entries"][r["index"]].get("how"))
                                  for r in top[:5]]}


def step_rules(run: Run) -> dict:
    """규칙을 해 보고 가장 나은 회로를 고른다: 상보 뒤집기(입력쌍이 공통모드 범위를 못 덮을 때),
    캐스코드(목표 AVD 에 못 미칠 때). 고른 회로를 final.json 에 쓴다 (하네스가 이것으로 시작)."""
    import auto_size
    import cascode
    import complement
    import rank_v2
    import run_sim
    import select_structure as ss
    auto_size.BIAS_MODE = "devices"
    spec = run_sim.load_spec(run.dir / "spec.json")
    sel = run.read("selection.json")
    entry = sel["entries"][sel["summary"]["selected"]]
    base_v = next(v for v in entry["variants"] if v["valid"] and v["output_scale"] == entry["best"]["output_scale"])
    unit_current = base_v.get("unit_current_a") or auto_size.UNIT_CURRENT   # 4단계에서 LLM 이 바꿨으면 그 값
    # 4단계에서 LLM 이 바꾼 소자 목표(gm/ID, 길이)도 이어서 쓴다. 상보 뒤집기 뒤에는 이름 앞글자(NM/PM)가 바뀐다
    overrides = {k: tuple(v) for k, v in (base_v.get("target_overrides") or {}).items()}
    tried = [{"label": "모델 구조 그대로", "rules": [], "table": entry["table"], "variant": base_v, "overrides": overrides}]
    auto_size.TARGET_OVERRIDES = dict(overrides)
    table = ss.to_table(entry["table"])
    table, flipped = complement.fit_input_range(table)
    rules = []
    if flipped:
        rules.append("상보 뒤집기")
        run.log("입력쌍이 공통모드 범위를 못 덮어 상보 뒤집기")
        auto_size.TARGET_OVERRIDES = {complement.SWAP_PREFIX.get(k[:2], k[:2]) + k[2:]: v for k, v in overrides.items()}
        tried += evaluate(run, ss, unit_current, table, spec, "상보 뒤집기", list(rules))
    target = rank_v2.target_value(next((r["target"] for r in base_v["spec"] if r["measure"] == "avd"), ""))[0]
    best_avd = max((row["value"] or 0) for t in tried for row in t["variant"]["spec"] if row["measure"] == "avd") \
        if target else None
    if target and best_avd < target:
        new, nodes = cascode.cascode(table)
        if nodes:
            rules.append("캐스코드")
            run.log(f"AVD {best_avd:.1f} dB < 목표 {target} dB -> 이득 노드 {nodes} 캐스코드")
            tried += evaluate(run, ss, unit_current, new, spec, " + ".join(rules), list(rules))
    auto_size.TARGET_OVERRIDES = {}
    working = [t for t in tried if t["variant"].get("valid")]
    chosen = min(working, key=lambda t: (-t["variant"]["passed"], rank_v2.shortfall(t["variant"]["spec"])))
    v = chosen["variant"]
    final = {"label": chosen["label"], "rules": chosen["rules"], "table": chosen["table"],
             "output_scale": v["output_scale"], "subckt": v["subckt"], "sizes": v.get("sizes"), "bias": v.get("bias"),
             "spec": v["spec"], "passed": v["passed"], "judged": v["judged"],
             "unit_current": unit_current, "target_overrides": chosen.get("overrides") or {},   # 7단계 튜닝이 이어 씀
             "tried": [{"label": t["label"], "scale": t["variant"]["output_scale"], "valid": t["variant"]["valid"],
                        "reason": t["variant"].get("reason"), "passed": t["variant"].get("passed"),
                        "judged": t["variant"].get("judged"), "spec": t["variant"].get("spec")} for t in tried]}
    (run.dir / "final.json").write_text(json.dumps(final, ensure_ascii=False, indent=1), encoding="utf-8")
    return {"chosen": chosen["label"], "passed": f"{v['passed']}/{v['judged']}", "tried": len(tried)}


def evaluate(run: Run, ss, unit_current: float, table: dict, spec: dict, label: str, rules: list) -> list:
    import auto_size
    import netlist_table as nt
    out = []
    for scale in RULE_SCALES:
        v = ss.evaluate_variant(table, unit_current, scale, spec)
        run.log(f"  {label} x{scale:g}: " + (f"{v['passed']}/{v['judged']}" if v["valid"] else f"실패 ({v['reason'][:50]})"))
        out.append({"label": label, "rules": rules, "variant": v, "overrides": dict(auto_size.TARGET_OVERRIDES),
                    "table": " ; ".join(nt.table_text(table).splitlines())})
    return out


def step_tune(run: Run) -> dict:
    """6단계 회로의 전류·출력단 배율·보상 커패시터를 바꿔 통과 항목을 늘린다 (tune_sizing.py).
    나아졌을 때만 final.json 을 튜닝한 회로로 바꾸고, 튜닝 전 회로는 final_rules.json 에 둔다."""
    import auto_size
    import netlist_table as nt
    import run_sim
    import select_structure as ss
    import tune_sizing
    rules_file = run.dir / "final_rules.json"
    final = run.read("final.json")
    if final.get("tuned") and rules_file.exists():
        final = json.loads(rules_file.read_text(encoding="utf-8"))      # 튜닝을 다시 돌림: 6단계 회로에서 시작
    else:
        rules_file.write_text(json.dumps(final, ensure_ascii=False, indent=1), encoding="utf-8")
    auto_size.BIAS_MODE = "devices"
    auto_size.TARGET_OVERRIDES = {k: tuple(v) for k, v in (final.get("target_overrides") or {}).items()}
    try:
        spec = run_sim.load_spec(run.dir / "spec.json")
        table = tune_sizing.table_from_text(final["table"])
        unit_current = final.get("unit_current") or auto_size.UNIT_CURRENT
        result = tune_sizing.tune(table, spec, unit_current, final["output_scale"], log=run.log)
    finally:
        auto_size.TARGET_OVERRIDES = {}
    start, best = result["start"]["variant"], result["best"]["variant"]
    improved = bool(best.get("valid")) and tune_sizing.score(best) < tune_sizing.score(start)
    current, scale, cap = result["best"]["point"]
    record = {"stopped": result["stopped"], "seconds": result["seconds"], "miller_nodes": result["miller_nodes"],
              "jump_ua": result.get("jump_ua"), "measure_loads": spec.get("measure_loads"),
              "start": {"passed": start.get("passed"), "judged": start.get("judged"), "spec": start.get("spec")},
              "best": {"unit_current_ua": current * 1e6, "scale": scale, "cap_pf": cap * 1e12,
                       "passed": best.get("passed"), "judged": best.get("judged"), "spec": best.get("spec")},
              "improved": bool(improved), "trials": result["trials"]}
    (run.dir / "tune.json").write_text(json.dumps(record, ensure_ascii=False, indent=1), encoding="utf-8")
    if improved:
        tuned = dict(final, label=final["label"] + " + 튜닝", tuned=True,
                     table=" ; ".join(nt.table_text(result["best"]["table"]).splitlines()),
                     unit_current=current, output_scale=scale, compensation_pf=cap * 1e12,
                     subckt=best["subckt"], sizes=best.get("sizes"), bias=best.get("bias"),
                     spec=best["spec"], passed=best["passed"], judged=best["judged"])
        run.dir.joinpath("final.json").write_text(json.dumps(tuned, ensure_ascii=False, indent=1), encoding="utf-8")
    else:
        run.dir.joinpath("final.json").write_text(json.dumps(final, ensure_ascii=False, indent=1), encoding="utf-8")
    before = f"{start.get('passed')}/{start.get('judged')}" if start.get("valid") else "다시 재기 실패"
    return {"before": before, "after": f"{best.get('passed')}/{best.get('judged')}" if improved else before,
            "improved": bool(improved), "trials": len(result["trials"]), "stopped": result["stopped"],
            "unit_current_ua": current * 1e6, "scale": scale, "cap_pf": cap * 1e12}


def step_harness(run: Run) -> dict:
    sh(run, [PY, HERE / "run_harness.py", run.dir])
    result = run.read("harness/result.json")
    return {"pass_rate": result.get("pass_rate_percent"), "counts": result.get("counts"),
            "has_netlist": bool(result.get("final_netlist"))}


def step_schematic(run: Run) -> dict:
    import make_schematic_svg as ms
    out_dir = run.dir / "schematic"
    out_dir.mkdir(exist_ok=True)
    ms.WORK_DIR.mkdir(exist_ok=True)
    skin = ms.make_skin()
    made = []
    try:
        rows, sizes = ms.rows_from_subckt(run.read("final.json")["subckt"])
        ms.render(rows, sizes, out_dir / "before_harness.svg", skin)
        made.append("before_harness")
        harness_file = run.dir / "harness" / "result.json"
        if harness_file.exists():
            result = json.loads(harness_file.read_text(encoding="utf-8"))
            rows, sizes, skipped = harness_rows(result.get("final_netlist") or "", result.get("pin_map") or {})
            if rows:
                ms.render(rows, sizes, out_dir / "after_harness.svg", skin)
                made.append("after_harness")
            if skipped:
                run.log(f"하네스 회로도에서 그리지 않은 소자: {', '.join(skipped[:10])}")
    finally:
        skin.unlink()
    return {"made": made}


def harness_rows(netlist: str, pin_map: dict) -> tuple:
    """하네스 최종 회로(첫 .subckt, M 소자 + LTspice 모델 이름) -> 회로도 행. 칩 핀 이름은 우리 단자 이름으로 되돌린다."""
    import make_schematic_svg as ms
    back = {v: k for k, v in pin_map.items() if isinstance(v, str)}
    lines, inside, skipped = [], False, []
    for raw in netlist.splitlines():
        tokens = raw.split()
        if not tokens:
            continue
        low = tokens[0].lower()
        if low == ".subckt":
            if inside:
                break
            inside = True
            continue
        if low == ".ends":
            break
        if not inside or low.startswith(("*", ".")):
            continue
        name = tokens[0]
        if name[0].upper() == "M" and len(tokens) > 5:
            model = tokens[5].lower()
            kind = "nfet_06v0" if ("nfet" in model or "nmos" in model) else "pfet_06v0" if ("pfet" in model or "pmos" in model) else None
            if kind:
                nets = [back.get(t, t) for t in tokens[1:5]]
                lines.append(" ".join(["X" + name[1:]] + nets + [kind] + tokens[6:]))
                continue
        if name[0].upper() in "RC" and len(tokens) > 2:
            lines.append(" ".join([name, back.get(tokens[1], tokens[1]), back.get(tokens[2], tokens[2])] + tokens[3:]))
            continue
        skipped.append(name)
    rows, sizes = ms.rows_from_subckt("\n".join(lines))
    return rows, sizes, skipped


def same_part(a: str, b: str) -> bool:
    """칩 이름 두 개가 같은 칩인지. 글자·숫자만 비교하고, 한쪽이 다른 쪽을 포함하면 같다고 본다 (LM358 / LM358B)."""
    a, b = (re.sub(r"[^A-Z0-9]", "", s.upper()) for s in (a, b))
    return bool(a and b) and (a in b or b in a)


def check_step(run: Run, key: str) -> list:
    """단계가 끝난 뒤 결과가 앞뒤가 맞는지 본다. 맞지 않으면 회로 문제가 아니라 프로그램 오류일 가능성이 크다
    (예: 하네스 통과율은 있는데 최종 회로 파일이 없음 -> 파일을 못 찾은 것). 결과 화면에 빨갛게 표시한다."""
    d, out = run.dir, []

    def has(name):
        return (d / name).exists()

    if key == "extract":
        hkg = run.read("hkg.json") if has("hkg.json") else {}
        if not hkg.get("electrical_parameters"):
            out.append("데이터시트에서 뽑은 전기적 사양이 0줄")
        if not hkg.get("pins"):
            out.append("데이터시트에서 뽑은 핀이 0개")
        if not has("spec.json") or not run.read("spec.json").get("specs"):
            out.append("판정 항목이 0개")
        if not has("pdg.json"):
            out.append("PDG 파일이 없음")
        target = (run.read("input.json").get("part") or "").strip().upper()
        got = str((hkg.get("ic_device") or {}).get("name") or "").strip().upper()
        if target and got and not same_part(target, got):
            out.append(f"{target} 을(를) 요청했는데 {got} 으로 분석됨 (핀 {len(hkg.get('pins') or [])}개). "
                       "같은 데이터시트의 다른 칩일 수 있음")
    elif key == "candidates":
        if not has("candidates.json") or not run.read("candidates.json").get("candidates"):
            out.append("모델 후보가 0개")
    elif key == "rules":
        final = run.read("final.json") if has("final.json") else {}
        if ".subckt" not in (final.get("subckt") or ""):
            out.append("하네스에 넘길 회로(final.json)에 .subckt 가 없음")
    elif key == "tune":
        final = run.read("final.json") if has("final.json") else {}
        if ".subckt" not in (final.get("subckt") or ""):
            out.append("튜닝 뒤 하네스에 넘길 회로(final.json)에 .subckt 가 없음")
    elif key == "harness":
        result = run.read("harness/result.json") if has("harness/result.json") else None
        if result is None:
            out.append("하네스 결과 파일(harness/result.json)이 없음")
        else:
            counts = result.get("counts") or {}
            if counts and counts.get("judged") == 0:
                out.append(f"하네스가 판정할 항목이 없음: 데이터시트 {counts.get('total')}줄 중 전원 조건이 설계 전원(4.5~5.5 V)과 다른 줄 "
                           f"{counts.get('supply')}개, 시뮬레이션으로 확인할 수 없는 줄 {counts.get('not_testable')}개")
            elif result.get("pass_rate_percent") is None:
                out.append("하네스 통과율이 기록되지 않음")
            if (result.get("pass_rate_percent") or 0) > 0 and ".subckt" not in (result.get("final_netlist") or "").lower():
                out.append("통과율은 있는데 최종 회로를 못 찾음 (파일 이름·경로 문제일 가능성)")
            if result.get("pass_rate_percent") == 0:
                out.append("하네스 통과율 0%: 넘긴 회로가 동작하는데 0% 면 하네스가 회로를 시뮬레이션하지 못했을 수 있음")
            # 하네스가 돌린 시뮬레이션의 오류 (ngspice 출력 *.ng.out): 어느 측정 회로에서 무슨 오류인지 첫 줄을 보여 준다.
            # 이름에 _dyn 이 붙은 것은 하네스 LLM 이 쓴 동적 테스트벤치(왜곡 등), 나머지는 정해진 테스트벤치
            failed = []
            for f in sorted((d / "harness").rglob("*.ng.out")):
                for line in f.read_text(encoding="utf-8", errors="ignore").splitlines():
                    if re.search(r"unknown subckt|could not find|Undefined parameter|fatal error|shorted|"
                                 r"not supported|simulation\(s\) aborted", line, re.I):
                        kind = "동적 측정(LLM 이 쓴 회로)" if "_dyn" in f.name else "정해진 측정"
                        failed.append(f"{kind} {f.name}: {line.strip()[:120]}")
                        break
            if failed:
                out.append(f"하네스 시뮬레이션이 멈춘 측정 회로 {len(failed)}개 (동적 측정 항목은 실패가 아니라 못 잼으로 셈): "
                           + " / ".join(failed[:3]) + (" ..." if len(failed) > 3 else ""))
    elif key == "schematic":
        if not has("schematic/before_harness.png"):
            out.append("하네스 전 회로도가 없음")
        result = run.read("harness/result.json") if has("harness/result.json") else {}
        if result.get("final_netlist") and not has("schematic/after_harness.png"):
            out.append("하네스 최종 회로는 있는데 그 회로도가 없음")
    return out


STEP_FUNCS = {"extract": step_extract, "candidates": step_candidates, "select": step_select, "fix": step_fix, "rank": step_rank,
              "rules": step_rules, "tune": step_tune, "harness": step_harness, "schematic": step_schematic}


def main() -> None:
    run = Run(Path(sys.argv[1]))
    start = sys.argv[sys.argv.index("--from") + 1] if "--from" in sys.argv else None
    keys = [k for k, _ in STEPS]
    todo = keys[keys.index(start):] if start else keys
    run.status["state"] = "running"
    run.status["started"] = run.status.get("started") or time.strftime("%Y-%m-%d %H:%M:%S")
    for key in keys:
        if key in todo:
            run.step(key).update(state="wait", summary=None, error=None)
    setup_llm(run)
    run.save()
    for key in todo:
        step = run.step(key)
        calls_before = len(LLM_CALLS)
        step.update(state="run", started=time.strftime("%H:%M:%S"))
        run.save()
        run.log(f"== {step['title']}")
        t0 = time.time()
        try:
            step["summary"] = STEP_FUNCS[key](run)
            step["state"] = "done"
            step["warnings"] = check_step(run, key)
            for w in step["warnings"]:
                run.log(f"점검: {w}")
        except Unsupported as error:
            step.update(state="fail", error=str(error))
            run.log(str(error))
            run.status["state"] = "unsupported"
        except Exception as error:
            step.update(state="fail", error=f"{type(error).__name__}: {error}")
            run.log(traceback.format_exc())
            run.status["state"] = "failed"
        step["seconds"] = round(time.time() - t0)
        step["llm"] = llm_summary(LLM_CALLS[calls_before:])
        run.status["total_seconds"] = sum(s.get("seconds") or 0 for s in run.status["steps"])   # 단계 시간 합
        run.save()
        if step["state"] == "fail":
            return
    run.status["state"] = "done"
    run.status["finished"] = time.strftime("%Y-%m-%d %H:%M:%S")
    run.save()
    run.log("끝")


if __name__ == "__main__":
    main()
