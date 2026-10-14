"""
LLM 이 설계 선택을 내고, SymPy 가 크기를 계산하고, 시뮬레이션이 판정하는 반복 루프.

    LLM: 선택(전류, gm/ID, 채널 길이, 보상 커패시터)과 이유   -- 숫자 계산은 하지 않는다
    sizing.py (SymPy): 소자 크기와 예상 성능 계산
    run_sim.py: 시뮬레이션과 판정
    미달이면 측정값과 미달 항목을 LLM 에 돌려주고 다시 선택하게 한다

사용법 (WSL, 프로젝트 폴더에서. .env 에 OPENROUTER_API_KEY 필요):
    ~/.venvs/edai/bin/python llm_design.py              # 최대 5회 반복
    ~/.venvs/edai/bin/python llm_design.py --max-iter 3

기록: sim_out/design_log.json (회차별 선택, 이유, 소자 크기, 예상 성능, 측정값, 판정)
회로: opamp_llm.cir (회차마다 덮어쓴다. 회차별 넷리스트는 기록 파일에 들어 있다)
"""

import argparse
import json
import time
import urllib.error
import urllib.request

import run_sim
import sizing

API_URL = "https://openrouter.ai/api/v1/chat/completions"
MODEL = "nvidia/nemotron-3-super-120b-a12b:free"
ENV_FILE = run_sim.HERE / ".env"
KEY_NAME = "OPENROUTER_API_KEY"
DESIGN_NAME = "opamp_llm"
LOG_FILE = run_sim.OUT_DIR / "design_log.json"
MAX_ITERATIONS = 5
REQUEST_TIMEOUT_S = 240
MAX_TOKENS = 4000
RETRY_WAIT_S = 20
STRUCTURE = "PMOS 입력 폴디드 캐스코드 1단 + class-AB 출력단 + Miller 보상 (GF180MCU 6 V 소자, VDD = 5 V)"


def read_api_key() -> str:
    """.env 에서 키를 읽는다. 키는 어디에도 출력하지 않는다."""
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            if line.strip().startswith(f"{KEY_NAME}="):
                key = line.split("=", 1)[1].strip().strip('"').strip("'")
                if key:
                    return key
    raise RuntimeError(f".env 파일에 {KEY_NAME} 값이 없습니다.")


def ask_llm(messages: list) -> dict:
    """OpenRouter 에 묻고 (답 글, 사용 토큰)을 돌려준다. 요청 제한(429)이면 한 번 기다렸다 다시 묻는다."""
    body = json.dumps({"model": MODEL, "messages": messages, "max_tokens": MAX_TOKENS, "temperature": 0.2}).encode("utf-8")
    for attempt in (1, 2):
        request = urllib.request.Request(API_URL, data=body, headers={
            "Authorization": f"Bearer {read_api_key()}", "Content-Type": "application/json", "X-Title": "EDAI"})
        try:
            with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_S) as response:
                data = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            if error.code == 429 and attempt == 1:
                time.sleep(RETRY_WAIT_S)
                continue
            raise RuntimeError(f"LLM 요청 실패 (HTTP {error.code})") from error
        if "choices" not in data:
            raise RuntimeError(f"LLM 응답에 내용이 없습니다: {json.dumps(data, ensure_ascii=False)[:200]}")
        return {"text": data["choices"][0]["message"].get("content") or "", "usage": data.get("usage", {})}
    raise RuntimeError("LLM 요청 제한이 풀리지 않았습니다.")


def parse_json_answer(text: str) -> dict:
    """LLM 답에서 JSON 부분만 꺼낸다. (LLM 출력 해석은 여기서만 한다)"""
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("LLM 답에 JSON 이 없습니다.")
    return json.loads(text[start:end + 1])


def spec_lines(spec: dict) -> str:
    """판정 대상 스펙을 LLM 에 보여줄 글로 만든다."""
    lines = []
    for item in spec["specs"]:
        if item.get("scope", run_sim.SCOPE_TARGET) != run_sim.SCOPE_TARGET:
            continue
        low, high, basis = run_sim.effective_bounds(item, spec)
        bound = " / ".join(text for text in (f"{low:g} 이상" if low is not None else "",
                                              f"{high:g} 이하" if high is not None else "") if text)
        lines.append(f"- {item['label']}: {bound} {item['unit']} ({basis}) | 조건: {item.get('condition') or '-'}")
    return "\n".join(lines)


def first_prompt(spec: dict) -> str:
    ranges = "\n".join(
        f"- {key}: {rule['meaning']}. " + (f"다음 중 하나: {list(rule['choices'])}" if "choices" in rule
                                          else f"{rule['min']:g} ~ {rule['max']:g}")
        for key, rule in sizing.CHOICE_RANGES.items())
    equations = "\n".join(f"- {row['meaning']}" for row in sizing.equations_text())
    return f"""당신은 아날로그 IC 설계자입니다. 아래 스펙을 만족하도록 OP-Amp 의 설계 선택을 정하세요.

[회로 구조]
{STRUCTURE}

[판정할 스펙]
{spec_lines(spec)}

[당신이 정할 값]
{ranges}

[계산 방식]
숫자 계산은 당신이 하지 않습니다. 당신이 고른 값으로 계산 프로그램(SymPy)이 소자 크기와 예상 성능을 구하고,
회로 시뮬레이터(ngspice)가 실제 성능을 재서 판정합니다. 계산 프로그램이 쓰는 식:
{equations}
- 공급 전류 = 바이어스 전류(고정 약 60 uA) + 꼬리 전류 + 캐스코드 가지 전류(고정 40 uA) + 출력단 평소 전류

[출력 형식]
아래 JSON 하나만 출력하세요. 다른 글은 쓰지 마세요.
{{"choices": {{"i_tail_ua": 0, "gm_id_in": 0, "l_in_um": 0, "l_casc_um": 0, "cc_pf": 0, "iq_out_ua": 0}},
 "reasons": {{"i_tail_ua": "이 값을 고른 이유 한 문장", "gm_id_in": "...", "l_in_um": "...", "l_casc_um": "...", "cc_pf": "...", "iq_out_ua": "..."}},
 "expectation": "이 선택으로 어떤 스펙이 빠듯할지 한 문장"}}"""


def feedback_prompt(record: dict) -> str:
    """직전 회차의 결과를 LLM 에 돌려주는 글."""
    if record.get("error"):
        return (f"직전 선택은 시뮬레이션이 실패했습니다: {record['error']}\n"
                "선택을 바꿔 같은 JSON 형식으로 다시 출력하세요.")
    lines = []
    for row in record["rows"]:
        if row["status"] in (run_sim.STATUS_PASS, run_sim.STATUS_FAIL):
            lines.append(f"- {row['label']}: 측정 {row['value']:.4g} {row['unit']}, 목표 {run_sim.target_text(row)} "
                         f"-> {row['status']} ({row['margin']})")
    predicted = record["predicted"]
    notes = "\n".join(f"- {note}" for note in record["range_notes"]) or "- 없음"
    return f"""직전 선택의 결과입니다.

[허용 범위에 맞추느라 프로그램이 고친 값]
{notes}

[식으로 계산한 예상]
이득 {predicted['avd']:.1f} dB, 단위이득 대역폭 {predicted['ugbw'] / 1e6:.2f} MHz, 슬루율 {predicted['sr'] / 1e6:.2f} V/us, 공급 전류 {predicted['idd'] * 1e6:.0f} uA

[시뮬레이션 측정과 판정]
{chr(10).join(lines)}

미달(FAIL) 항목을 통과시키도록 선택을 고치세요. 이미 통과한 항목이 미달로 바뀌지 않게 주의하세요.
같은 JSON 형식으로, reasons 에는 직전 대비 무엇을 왜 바꿨는지 적으세요."""


def run_iteration(number: int, answer: dict, spec: dict) -> dict:
    """LLM 의 선택 하나를 계산, 시뮬레이션, 판정해서 기록 한 건으로 만든다."""
    record = {"iteration": number, "llm_choices": answer.get("choices", {}), "reasons": answer.get("reasons", {}),
              "expectation": answer.get("expectation", "")}
    sized = sizing.size_opamp(record["llm_choices"])
    record.update(choices=sized["choices"], range_notes=sized["range_notes"], sizes=sized["sizes"],
                  predicted=sized["predicted"], intermediate=sized["intermediate"])
    circuit_path = sizing.write_circuit(DESIGN_NAME, sized["sizes"])
    record["netlist"] = circuit_path.read_text(encoding="utf-8")
    try:
        result = run_sim.evaluate(DESIGN_NAME)
    except Exception as error:  # 수렴 실패 등. 루프를 멈추지 않고 LLM 에 알려 다시 고르게 한다
        record.update(error=str(error), rows=[], all_pass=False, passed=0, judged=0)
        return record
    rows = run_sim.judge(result, spec)
    judged = [row for row in rows if row["status"] in (run_sim.STATUS_PASS, run_sim.STATUS_FAIL)]
    record.update(
        rows=rows, all_pass=run_sim.all_pass(rows), judged=len(judged),
        passed=sum(row["status"] == run_sim.STATUS_PASS for row in judged),
        measured={key: value for key, value in result.items() if isinstance(value, (int, float))},
    )
    run_sim.save_result(DESIGN_NAME, run_sim.spec_path(DESIGN_NAME), result, rows)
    return record


def design_loop(max_iterations: int = MAX_ITERATIONS) -> dict:
    """통과하거나 횟수를 다 쓸 때까지 LLM 선택 -> 계산 -> 시뮬레이션 -> 판정을 반복한다."""
    spec_file = next(path for path in sorted(run_sim.HERE.glob(f"{run_sim.SPEC_PREFIX}*.json"))
                     if run_sim.load_spec(path).get("circuit") == "opamp")
    spec = run_sim.load_spec(spec_file)
    log = {"model": MODEL, "structure": STRUCTURE, "spec_file": spec_file.name,
           "equations": sizing.equations_text(), "iterations": [], "final": None}
    messages = [{"role": "user", "content": first_prompt(spec)}]
    for number in range(1, max_iterations + 1):
        print(f"\n===== {number}회차: LLM 에 선택을 묻는 중 ({MODEL}) =====")
        started = time.time()
        reply = ask_llm(messages)
        try:
            answer = parse_json_answer(reply["text"])
        except ValueError as error:
            print(f"  LLM 답을 해석하지 못함: {error}")
            messages += [{"role": "assistant", "content": reply["text"]},
                         {"role": "user", "content": "JSON 형식이 아닙니다. 지정한 JSON 하나만 다시 출력하세요."}]
            log["iterations"].append({"iteration": number, "error": f"LLM 답 해석 실패: {error}", "rows": [],
                                      "all_pass": False, "passed": 0, "judged": 0})
            continue
        record = run_iteration(number, answer, spec)
        record["llm_seconds"] = round(time.time() - started, 1)
        record["llm_tokens"] = reply["usage"]
        log["iterations"].append(record)
        print(f"  선택: {json.dumps(record['choices'], ensure_ascii=False)}")
        for key, reason in record["reasons"].items():
            print(f"    {key}: {reason}")
        if record.get("error"):
            print(f"  시뮬레이션 실패: {record['error']}")
        else:
            print(f"  판정: 통과 {record['passed']} / {record['judged']}"
                  + ("  -> 전체 PASS" if record["all_pass"] else ""))
            for row in record["rows"]:
                if row["status"] == run_sim.STATUS_FAIL:
                    print(f"    FAIL {row['label']}: {row['value']:.4g} {row['unit']} (목표 {run_sim.target_text(row)})")
        LOG_FILE.write_text(json.dumps(log, ensure_ascii=False, indent=2), encoding="utf-8")
        if record["all_pass"]:
            log["final"] = number
            break
        messages += [{"role": "assistant", "content": reply["text"]},
                     {"role": "user", "content": feedback_prompt(record)}]
    LOG_FILE.write_text(json.dumps(log, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n기록 저장: {LOG_FILE}")
    print("결과:", f"{log['final']}회차에 전체 PASS" if log["final"] else f"{max_iterations}회 안에 통과하지 못함")
    return log


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="LLM 설계 선택 -> SymPy 계산 -> 시뮬레이션 판정 반복")
    parser.add_argument("--max-iter", type=int, default=MAX_ITERATIONS)
    design_loop(parser.parse_args().max_iter)
