"""
LLM 으로 회로 구조를 정한다. AMSnet-KG 논문(구조설정.pdf)의 흐름을 따른다.

    1. 설계 전략    LLM 이 스펙을 보고 어떤 구조가 필요한지 따져 본다
    2. 관계 쌍      전략을 [역할, 관계, 값] 쌍으로 적는다 (같은 답 안에서 함께 받는다)
    3. 블록 찾기    관계 쌍에 맞는 블록을 모음에서 찾는다            (topology.retrieve, 코드)
    4. 조립         단자가 하는 일을 맞춰 블록을 잇는다              (topology.build, 코드)
    5. 시뮬레이션   테스트벤치로 측정하고 스펙으로 판정한다           (run_sim, 코드)
    6. 구조 다시 정하기   미달이면 실제 성능을 LLM 에 돌려주고 다른 구조를 받는다

논문과 다른 점: 논문은 조립 뒤에 베이지안 최적화로 소자 크기를 다시 정한다. 여기서는 블록에 들어 있는
크기를 그대로 쓴다. 크기 조정은 llm_design.py (LLM 선택 + SymPy 계산)가 맡는다.

실행 (WSL, .env 에 OPENROUTER_API_KEY 필요):
    ~/.venvs/edai/bin/python llm_topology.py
결과: opamp_gen.cir (가장 많이 통과한 구조), sim_out/topology_log.json (전체 이력)
"""

import json
import time

import llm_design
import run_sim
import topology

LOG_FILE = run_sim.OUT_DIR / "topology_log.json"
MAX_ROUNDS = 4            # 서로 다른 구조를 시뮬레이션해 보는 횟수의 상한
MAX_FIX_ATTEMPTS = 3      # 한 번의 제안에서 블록 찾기·조립 오류를 고치게 하는 횟수의 상한
JUDGED = (run_sim.STATUS_PASS, run_sim.STATUS_FAIL)

# 답의 형식을 보여주는 예시. 논문처럼 숫자가 섞이지 않게 지금 과제와 다른 요구를 예로 쓴다
FORMAT_EXAMPLE = {
    "analysis": "요구는 전류 소모가 작을 것, 이득은 60 dB 정도, 부하는 커패시터뿐이라 큰 출력 전류가 필요 없다. ...",
    "strategy": "이득이 보통이면 되므로 단순한 1단에 공통소스 2단을 붙이고, 2단 구조이므로 Miller 보상을 건다.",
    "triplets": [["stage1", "gain", "medium"], ["stage1", "power", "low"],
                 ["stage2", "type", "class_a"], ["compensation", "type", "miller_rz"]],
}


def vocabulary_text(library: dict) -> str:
    """모음에서 쓸 수 있는 관계 쌍을 LLM 에 보여줄 글로 만든다."""
    lines = []
    for role, relations in library["relations"].items():
        lines.append(f"[{role}] {topology.ROLE_TITLES[role]}")
        for relation, values in relations.items():
            for value, meaning in values.items():
                lines.append(f"  - {relation}: {value}  ({meaning})")
    return "\n".join(lines)


def first_prompt(spec: dict, library: dict) -> str:
    return f"""당신은 아날로그 IC 설계자입니다. 아래 스펙을 만족하는 OP-Amp 의 구조를 정하세요.
공정은 GF180MCU 6 V 소자, 전원은 5 V 단일 전원입니다. 조건: {spec['conditions']}

[스펙]
{llm_design.spec_lines(spec)}

[구조를 적는 방법]
회로는 1단(stage1), 2단(stage2), 보상(compensation) 세 역할의 블록을 조립해 만듭니다. 바이어스 회로는 자동으로 들어갑니다.
원하는 구조를 [역할, 관계, 값] 쌍으로 적으면, 그 쌍에 맞는 블록을 모음에서 찾아 조립합니다.
쓸 수 있는 관계와 값은 아래가 전부입니다. 이 밖의 말은 쓰지 마세요.

{vocabulary_text(library)}

규칙
- 역할마다 쌍을 하나 이상 적습니다. 여러 쌍을 적으면 그 쌍에 가장 잘 맞는 블록을 찾습니다.
- 성질은 블록마다 묶여 있어서 원하는 조합이 모음에 없을 수 있습니다. 스펙을 만족하는 데 꼭 필요한 쌍만 적으세요.
- 1단의 drives 와 2단의 needs 는 서로 맞아야 조립됩니다.
- 2단이나 보상을 쓰지 않으려면 [역할, "type", "none"] 을 적습니다.
- 먼저 스펙의 항목과 조건을 하나씩 보고 구조에 어떤 성질이 필요한지 따져 본 뒤(analysis), 구조를 정하고(strategy), 쌍을 적습니다(triplets).

[답의 형식] 아래와 같은 JSON 하나만 출력합니다. 이 예시는 다른 요구에 대한 것이므로 내용을 따라 하지 마세요.
{json.dumps(FORMAT_EXAMPLE, ensure_ascii=False, indent=2)}"""


def fix_prompt(errors: list) -> str:
    """블록 찾기나 조립에서 난 오류를 LLM 에 돌려주는 글."""
    return ("제안한 구조를 만들 수 없습니다.\n" + "\n".join(f"- {error}" for error in errors)
            + "\n위 문제를 고쳐 같은 형식의 JSON 하나만 다시 출력하세요.")


def feedback_prompt(rounds: list) -> str:
    """지금까지 시도한 구조와 실제 성능을 LLM 에 돌려주는 글. (논문의 '구조 다시 정하기')"""
    lines = ["지금까지 제안한 구조를 실제로 조립해 시뮬레이션한 결과입니다."]
    for record in rounds:
        lines.append(f"\n구조 {record['round']}: {record['structure']}")
        lines.append(f"  쌍: {json.dumps(record['triplets'], ensure_ascii=False)}")
        lines += [f"  참고: {note}" for note in record.get("notes", [])]
        if record.get("error"):
            lines.append(f"  시뮬레이션 실패: {record['error']}")
            continue
        lines.append(f"  판정: {record['judged']}개 중 {record['passed']}개 통과")
        for row in record["rows"]:
            if row["status"] == run_sim.STATUS_FAIL:
                lines.append(f"  미달 - {row['label']}: 측정 {row['value']:.4g} {row['unit']}, "
                             f"목표 {run_sim.target_text(row)} ({row['margin']})")
    lines.append("\n스펙을 모두 만족하도록 구조를 다시 정하세요. 위에서 이미 시도한 구조와 같은 구조는 제안하지 마세요. "
                 "미달 항목이 구조의 어느 부분 때문인지 analysis 에 적고, 같은 형식의 JSON 하나만 출력하세요.")
    return "\n".join(lines)


def propose(messages: list, library: dict, tried: set) -> dict:
    """LLM 에 구조를 묻고, 블록을 찾아 조립까지 한다. 오류가 있으면 고치게 한다.

    돌려주는 값: {"analysis", "strategy", "triplets", "attempts": [...], "built": 조립 결과 또는 None}
    messages 에 주고받은 글을 덧붙인다.
    """
    record = {"analysis": "", "strategy": "", "triplets": [], "attempts": [], "built": None,
              "llm_seconds": 0.0, "llm_tokens": []}
    for attempt in range(1, MAX_FIX_ATTEMPTS + 1):
        started = time.time()
        reply = llm_design.ask_llm(messages)
        record["llm_seconds"] = round(record["llm_seconds"] + time.time() - started, 1)
        record["llm_tokens"].append(reply["usage"])
        messages.append({"role": "assistant", "content": reply["text"]})
        try:
            answer = llm_design.parse_json_answer(reply["text"])
            triplets = [[str(part) for part in item] for item in answer["triplets"] if len(item) == 3]
        except (ValueError, KeyError, TypeError) as error:
            errors, triplets, answer = [f"답을 해석하지 못했습니다 ({error}). 지정한 JSON 형식을 지키세요"], [], {}
        else:
            found = topology.retrieve(triplets, library)
            errors = found["errors"]
            if not errors:
                key = json.dumps(found["selection"], sort_keys=True)
                if key in tried:
                    errors = ["이미 시도한 구조와 같습니다. 다른 구조를 제안하세요"]
                else:
                    built = topology.build(found["selection"])
                    built["notes"] = found["notes"] + built["notes"]
                    errors = built["errors"]
                    if not errors:
                        record["built"] = built
        record.update(analysis=answer.get("analysis", ""), strategy=answer.get("strategy", ""), triplets=triplets)
        record["attempts"].append({"attempt": attempt, "triplets": triplets, "errors": errors})
        if record["built"] is not None:
            return record
        print(f"    만들 수 없음: {'; '.join(errors)}")
        messages.append({"role": "user", "content": fix_prompt(errors)})
    return record


def simulate(record: dict, spec: dict, spec_file) -> None:
    """조립한 회로를 시뮬레이션하고 판정해 record 에 채운다."""
    try:
        result = run_sim.evaluate(topology.DESIGN_NAME)
    except Exception as error:  # 수렴 실패 등. 멈추지 않고 LLM 에 알려 다른 구조를 받는다
        record.update(error=str(error), rows=[], all_pass=False, passed=0, judged=0)
        return
    rows = run_sim.judge(result, spec)
    judged = [row for row in rows if row["status"] in JUDGED]
    record.update(rows=rows, all_pass=run_sim.all_pass(rows), judged=len(judged),
                  passed=sum(row["status"] == run_sim.STATUS_PASS for row in judged),
                  measured={key: value for key, value in result.items() if isinstance(value, (int, float))})
    record["_result"] = result


def topology_loop(max_rounds: int = MAX_ROUNDS) -> dict:
    """스펙을 통과하는 구조가 나오거나 횟수를 다 쓸 때까지 제안 -> 조립 -> 시뮬레이션을 반복한다."""
    spec_file = next(path for path in sorted(run_sim.HERE.glob(f"{run_sim.SPEC_PREFIX}*.json"))
                     if run_sim.load_spec(path).get("circuit") == "opamp")
    spec, library = run_sim.load_spec(spec_file), topology.load_library()
    log = {"model": llm_design.MODEL, "spec_file": spec_file.name, "design": topology.DESIGN_NAME,
           "library": [{key: card[key] for key in ("name", "title", "role", "transistors", "summary", "source")}
                       for card in library["blocks"].values()],
           "rounds": [], "final": None, "best": None}
    messages, tried, results = [{"role": "user", "content": first_prompt(spec, library)}], set(), {}
    for number in range(1, max_rounds + 1):
        print(f"\n===== 구조 {number}: LLM 에 구조를 묻는 중 ({llm_design.MODEL}) =====")
        record = propose(messages, library, tried)
        record["round"] = number
        built = record.pop("built")
        if built is None:
            record.update(structure="", error="구조를 만들지 못했습니다", rows=[], all_pass=False, passed=0, judged=0)
            log["rounds"].append(record)
            print("  구조를 만들지 못해 멈춥니다")
            break
        tried.add(json.dumps(built["selection"], sort_keys=True))
        record.update(structure=built["structure"], selection=built["selection"], notes=built["notes"],
                      transistors=built["transistors"], netlist=built["netlist"])
        print(f"  전략: {record['strategy']}")
        print(f"  구조: {record['structure']} (트랜지스터 {record['transistors']}개)")
        simulate(record, spec, spec_file)
        results[number] = record.pop("_result", None)
        log["rounds"].append(record)
        if record.get("error"):
            print(f"  시뮬레이션 실패: {record['error']}")
        else:
            print(f"  판정: 통과 {record['passed']} / {record['judged']}" + ("  -> 전체 PASS" if record["all_pass"] else ""))
            for row in record["rows"]:
                if row["status"] == run_sim.STATUS_FAIL:
                    print(f"    FAIL {row['label']}: {row['value']:.4g} {row['unit']} (목표 {run_sim.target_text(row)})")
        LOG_FILE.write_text(json.dumps(log, ensure_ascii=False, indent=2), encoding="utf-8")
        if record["all_pass"]:
            log["final"] = number
            break
        messages.append({"role": "user", "content": feedback_prompt(log["rounds"])})

    # 가장 많이 통과한 구조를 opamp_gen.cir 로 남기고 결과 파일도 그 구조의 것으로 맞춘다
    simulated = [r for r in log["rounds"] if r.get("netlist") and not r.get("error")]
    if simulated:
        best = max(simulated, key=lambda r: (r["passed"], -r["round"]))
        log["best"] = best["round"]
        (run_sim.HERE / f"{topology.DESIGN_NAME}.cir").write_text(best["netlist"], encoding="utf-8")
        run_sim.save_result(topology.DESIGN_NAME, spec_file, results[best["round"]], best["rows"])
    LOG_FILE.write_text(json.dumps(log, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n기록 저장: {LOG_FILE}")
    print("결과:", f"구조 {log['final']}에서 전체 PASS" if log["final"] else f"{len(log['rounds'])}번 안에 통과하는 구조를 찾지 못함")
    return log


if __name__ == "__main__":
    topology_loop()
