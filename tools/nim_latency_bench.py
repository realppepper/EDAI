"""
NVIDIA NIM latency benchmark.
Measures TTFT (time-to-first-token), total latency, output tokens/s and JSON validity
for candidate chat models using a realistic datasheet-extraction style prompt.

Usage:
  python tools/nim_latency_bench.py [--models m1,m2] [--runs 2] [--timeout 180]
"""
import argparse
import concurrent.futures as cf
import json
import os
import sys
import time
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from ai_analog_designer.llm_client import _load_env

_load_env()

URL = os.environ.get("NIM_BASE_URL", "https://integrate.api.nvidia.com/v1") + "/chat/completions"
KEY = os.environ.get("NVIDIA_API_KEY", "")

DEFAULT_MODELS = [
    "deepseek-ai/deepseek-v4.1-flash",
    "z-ai/glm-5.3",
    "z-ai/glm-5.3-flash",
    "moonshotai/kimi-k2.6",
    "nvidia/nemotron-3-super-120b-a12b",
    "nvidia/nemotron-3-ultra-550b-a55b",
    "nvidia/nemotron-3.5-lightning-30b-a3b",
    "google/gemma-4-31b-it",
    "mistralai/mistral-large-2-instruct",
    "openai/gpt-oss-20b",
    "stepfun-ai/step-5-preview",
]

PROMPT = """Extract from this datasheet excerpt a JSON object with keys "pins" (list of {name, pin_number, role})
and "electrical_parameters" (list of {symbol, name, min, typ, max, unit, test_conditions}).

LM358 PIN FUNCTIONS: 1 OUT1 Output, 2 IN1- Inverting input, 3 IN1+ Noninverting input, 4 GND/V- Negative supply,
5 IN2+ Noninverting input, 6 IN2- Inverting input, 7 OUT2 Output, 8 V+ Positive supply.
ELECTRICAL CHARACTERISTICS VS=5V TA=25C: Input offset voltage VOS typ 0.3 max 3 mV; Input bias current IB typ -10 max -35 nA;
Large-signal voltage gain AOL min 25 typ 100 V/mV RL>=2k; Gain bandwidth product GBW typ 1.2 MHz; Slew rate SR typ 0.5 V/us;
Quiescent current IQ per amplifier typ 300 max 600 uA; CMRR min 70 typ 80 dB; PSRR min 65 typ 100 dB.
Respond ONLY with JSON."""


def large_prompt():
    """Realistic Phase-1 spec-extraction prompt (~60k chars of LM358 spec pages)."""
    from ai_analog_designer.pdf_to_graph import PDFDatasheetParser as P
    from ai_analog_designer.pdf_to_graph.hardware_kg_builder import SPECS_PROMPT
    parsed = P().parse_pdf(os.path.join(os.path.dirname(__file__), "..", "testcases", "lm358.pdf"))
    return SPECS_PROMPT.format(text=P.page_tagged_text(parsed, P.select_pages(parsed, "specs"), 60000), ic="LM358")


def run_once(model: str, timeout: float, thinking: bool = True, prompt: str = None, max_tokens: int = 2048):
    from ai_analog_designer.llm_client import model_extra_body
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt or PROMPT}],
        "temperature": 0.1,
        "max_tokens": max_tokens,
        "stream": True,
    }
    if not thinking:
        os.environ.pop("LLM_THINKING", None)
        payload.update(model_extra_body("nim", model))
    req = urllib.request.Request(
        URL,
        data=json.dumps(payload).encode(),
        headers={"Authorization": f"Bearer {KEY}", "Content-Type": "application/json", "Accept": "text/event-stream"},
    )
    t0 = time.perf_counter()
    ttft = None
    content, reasoning_chars, usage = [], 0, None
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            for raw in resp:
                if time.perf_counter() - t0 > timeout:
                    raise TimeoutError("stream exceeded timeout")
                line = raw.decode("utf-8", "ignore").strip()
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    break
                try:
                    obj = json.loads(data)
                except Exception:
                    continue
                if obj.get("usage"):
                    usage = obj["usage"]
                for ch in obj.get("choices", []):
                    d = ch.get("delta", {}) or {}
                    piece = d.get("content") or ""
                    rpiece = d.get("reasoning_content") or d.get("reasoning") or ""
                    if (piece or rpiece) and ttft is None:
                        ttft = time.perf_counter() - t0
                    content.append(piece)
                    reasoning_chars += len(rpiece)
    except Exception as e:
        return {"model": model, "ok": False, "error": f"{type(e).__name__}: {str(e)[:160]}", "total_s": round(time.perf_counter() - t0, 2)}
    total = time.perf_counter() - t0
    text = "".join(content).strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1].rsplit("```", 1)[0]
    s, e = text.find("{"), text.rfind("}")
    valid, n_params = False, 0
    try:
        j = json.loads(text[s:e + 1])
        valid = True
        n_params = len(j.get("electrical_parameters", []))
    except Exception:
        pass
    out_tokens = (usage or {}).get("completion_tokens") or max(1, (len(text) + reasoning_chars) // 4)
    return {
        "model": model, "ok": True, "ttft_s": round(ttft or total, 2), "total_s": round(total, 2),
        "out_tokens": out_tokens, "tok_per_s": round(out_tokens / max(1e-6, total - (ttft or 0)), 1),
        "reasoning_chars": reasoning_chars, "json_valid": valid, "params_extracted": n_params,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", default=",".join(DEFAULT_MODELS))
    ap.add_argument("--runs", type=int, default=2)
    ap.add_argument("--timeout", type=float, default=180)
    ap.add_argument("--out", default="benchmark_results/NIM_LATENCY_BENCH.json")
    ap.add_argument("--no-thinking", action="store_true", help="disable reasoning via chat_template_kwargs")
    ap.add_argument("--large", action="store_true", help="use the real ~60k-char spec-extraction prompt")
    args = ap.parse_args()
    models = [m.strip() for m in args.models.split(",") if m.strip()]
    prompt = large_prompt() if args.large else None
    mt = 16000 if args.large else 2048

    jobs = [(m, r) for r in range(args.runs) for m in models]
    results = []
    with cf.ThreadPoolExecutor(max_workers=6) as ex:
        futs = {ex.submit(run_once, m, args.timeout, not args.no_thinking, prompt, mt): (m, r) for m, r in jobs}
        for f in cf.as_completed(futs):
            res = f.result()
            res["run"] = futs[f][1]
            res["thinking"] = not args.no_thinking
            res["scenario"] = "large_spec_extraction" if args.large else "small_extraction"
            results.append(res)
            print(json.dumps(res, ensure_ascii=False), flush=True)

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(results, fh, indent=2)

    print("\n| model | ok | TTFT med (s) | total med (s) | tok/s | JSON valid | params (/8) |")
    print("|---|---|---|---|---|---|---|")
    for m in models:
        rs = [r for r in results if r["model"] == m]
        oks = [r for r in rs if r["ok"]]
        if not oks:
            print(f"| {m} | 0/{len(rs)} | - | - | - | - | {rs[0].get('error','')[:60] if rs else ''} |")
            continue
        med = lambda k, _oks=oks: sorted(r[k] for r in _oks)[len(_oks) // 2]
        print(f"| {m} | {len(oks)}/{len(rs)} | {med('ttft_s')} | {med('total_s')} | {med('tok_per_s')} | "
              f"{sum(r['json_valid'] for r in oks)}/{len(oks)} | {med('params_extracted')} |")


if __name__ == "__main__":
    main()
