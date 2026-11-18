import concurrent.futures
import json
import time
import urllib.error
import urllib.request
from typing import Any

API_KEY = "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"
BASE_URL = "https://integrate.api.nvidia.com/v1/chat/completions"

# Candidate models across size spectrum
MODELS_TO_BENCHMARK = [
    # Small (4B - 8B)
    {"id": "google/gemma-3-4b-it", "category": "SLM (4B)", "params": "4B"},
    {"id": "mistralai/mistral-7b-instruct-v0.3", "category": "SLM (7B)", "params": "7B"},
    {"id": "ibm/granite-3.0-8b-instruct", "category": "SLM (8B)", "params": "8B"},
    {"id": "nvidia/mistral-nemo-minitron-8b-8k-instruct", "category": "SLM (8B)", "params": "8B"},

    # Medium (12B - 34B)
    {"id": "nv-mistralai/mistral-nemo-12b-instruct", "category": "Medium (12B)", "params": "12B"},
    {"id": "openai/gpt-oss-20b", "category": "Medium (20B)", "params": "20B"},
    {"id": "mistralai/codestral-22b-instruct-v0.1", "category": "Medium (22B Code)", "params": "22B"},
    {"id": "nvidia/nemotron-3.5-lightning-30b-a3b", "category": "Medium (30B MoE)", "params": "30B (3B active)"},
    {"id": "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning", "category": "Medium (30B Reasoning)", "params": "30B"},
    {"id": "google/gemma-4-31b-it", "category": "Medium (31B)", "params": "31B"},
    {"id": "z-ai/glm-5.3-flash", "category": "Medium (Flash)", "params": "N/A"},

    # Large / Frontier (70B - 550B)
    {"id": "meta/codellama-70b", "category": "Large (70B Code)", "params": "70B"},
    {"id": "nvidia/llama-3.1-nemotron-70b-instruct", "category": "Large (70B)", "params": "70B"},
    {"id": "nvidia/nemotron-3-super-120b-a12b", "category": "Large (120B MoE)", "params": "120B (12B active)"},
    {"id": "nvidia/nemotron-3-ultra-550b-a55b", "category": "Frontier (550B MoE)", "params": "550B (55B active)"},
]

PROMPT_CIRCUIT = "Write a CMOS operational amplifier SPICE subcircuit with differential input, current mirror active load, and common source output stage. Keep explanations under 20 words."

def call_nim_stream(model: str, prompt: str, max_tokens: int = 250, timeout: float = 60.0) -> dict[str, Any]:
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "You are an analog circuit design assistant."},
            {"role": "user", "content": prompt}
        ],
        "max_tokens": max_tokens,
        "temperature": 0.2,
        "stream": True
    }
    
    req = urllib.request.Request(
        BASE_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": "application/json"
        }
    )
    
    t0 = time.time()
    ttft = None
    chunks = 0
    full_text = []
    status = "OK"
    error_msg = None
    
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            for line in resp:
                line_str = line.decode("utf-8", errors="ignore").strip()
                if line_str.startswith("data: ") and not line_str.startswith("data: [DONE]"):
                    if ttft is None:
                        ttft = time.time() - t0
                    chunks += 1
                    try:
                        chunk_json = json.loads(line_str[6:])
                        choices = chunk_json.get("choices", [])
                        if choices:
                            delta = choices[0].get("delta", {})
                            content = delta.get("content", "")
                            if content:
                                full_text.append(content)
                    except Exception:
                        pass
        total_time = time.time() - t0
    except urllib.error.HTTPError as e:
        total_time = time.time() - t0
        status = f"HTTP_{e.code}"
        try:
            err_body = e.read().decode("utf-8", errors="ignore")
            error_msg = err_body[:200]
        except Exception:
            error_msg = str(e)
    except Exception as e:
        total_time = time.time() - t0
        status = "ERROR"
        error_msg = str(e)[:200]
        
    return {
        "model": model,
        "status": status,
        "ttft_s": round(ttft, 3) if ttft is not None else None,
        "total_time_s": round(total_time, 3),
        "chunks": chunks,
        "generated_chars": len("".join(full_text)),
        "tps": round(chunks / (total_time - ttft), 1) if (ttft is not None and (total_time - ttft) > 0.05) else None,
        "error": error_msg
    }

def run_single_model_benchmarks():
    print("=" * 80)
    print("PHASE 1: NIM MODEL BASELINE BENCHMARKS (Small -> Large)")
    print("=" * 80)
    results = []
    for item in MODELS_TO_BENCHMARK:
        m_id = item["id"]
        cat = item["category"]
        print(f"Testing [{cat}] {m_id} ...", end=" ", flush=True)
        # Warmup / Test call
        res = call_nim_stream(m_id, PROMPT_CIRCUIT, max_tokens=200, timeout=45.0)
        res["category"] = cat
        res["params"] = item["params"]
        results.append(res)
        if res["status"] == "OK":
            print(f"SUCCESS -> TTFT: {res['ttft_s']}s | Total: {res['total_time_s']}s | Chunks: {res['chunks']} | Speed: {res['tps']} tok/s")
        else:
            print(f"FAILED -> {res['status']}: {res['error']}")
        time.sleep(0.5)
    return results

def run_queue_degradation_benchmark(target_models: list[str], num_repeats: int = 10):
    print("\n" + "=" * 80)
    print(f"PHASE 2: QUEUE & RATE DEGRADATION TEST ({num_repeats} Sequential Rapid Calls)")
    print("=" * 80)
    queue_results = {}
    
    for m_id in target_models:
        print(f"\n--- Model: {m_id} ({num_repeats} back-to-back calls without delay) ---")
        history = []
        for i in range(1, num_repeats + 1):
            t_start = time.time()
            res = call_nim_stream(m_id, f"Turn {i}: Describe the gain of an opamp in 15 words.", max_tokens=60, timeout=30.0)
            latency = res["total_time_s"]
            ttft = res["ttft_s"]
            status = res["status"]
            history.append({
                "iteration": i,
                "status": status,
                "ttft_s": ttft,
                "total_s": latency,
                "tps": res.get("tps")
            })
            print(f"  Call #{i:02d}: Status={status:<8} | TTFT={str(ttft)+'s':<7} | Total={latency:.2f}s | Speed={res.get('tps')} tok/s")
            # Minimal gap between calls to stress server queue
            time.sleep(0.1)
        queue_results[m_id] = history
    return queue_results

def run_concurrency_stress_test(m_id: str, concurrency_levels: list[int] | None = None):
    if concurrency_levels is None:
        concurrency_levels = [2, 4, 8]
    print("\n" + "=" * 80)
    print(f"PHASE 3: CONCURRENCY QUEUE STRESS TEST: {m_id}")
    print("=" * 80)
    concurrency_stats = {}
    
    for conc in concurrency_levels:
        print(f"\nTesting Concurrency Level = {conc} simultaneous requests...")
        t0 = time.time()
        with concurrent.futures.ThreadPoolExecutor(max_workers=conc) as executor:
            futures = [
                executor.submit(
                    call_nim_stream,
                    m_id,
                    f"Concurrent request {idx}: Define slew rate in 10 words.",
                    50,
                    30.0
                )
                for idx in range(conc)
            ]
            batch_res = [f.result() for f in futures]
        elapsed = time.time() - t0
        
        ok_count = sum(1 for r in batch_res if r["status"] == "OK")
        ttfts = [r["ttft_s"] for r in batch_res if r["ttft_s"] is not None]
        totals = [r["total_time_s"] for r in batch_res]
        
        avg_ttft = round(sum(ttfts) / len(ttfts), 3) if ttfts else None
        max_ttft = max(ttfts) if ttfts else None
        avg_total = round(sum(totals) / len(totals), 3)
        max_total = max(totals)
        
        print(f"  Results (N={conc}): Success={ok_count}/{conc} | Avg TTFT: {avg_ttft}s (Max: {max_ttft}s) | Avg Total: {avg_total}s (Max: {max_total}s) | Wall time: {elapsed:.2f}s")
        concurrency_stats[f"conc_{conc}"] = {
            "success_rate": f"{ok_count}/{conc}",
            "avg_ttft": avg_ttft,
            "max_ttft": max_ttft,
            "avg_total": avg_total,
            "max_total": max_total,
            "wall_time": round(elapsed, 2)
        }
        time.sleep(1.0)
    return concurrency_stats

if __name__ == "__main__":
    t_start_all = time.time()
    
    # Phase 1: Models spectrum baseline
    baseline_stats = run_single_model_benchmarks()
    
    # Phase 2: Rapid sequential queue test on key models
    # Pick 4 representative models across size spectrum
    target_models = [
        "google/gemma-3-4b-it",                          # Small (4B)
        "nvidia/nemotron-3.5-lightning-30b-a3b",        # Medium MoE (our default workhorse)
        "nvidia/llama-3.1-nemotron-70b-instruct",       # Large (70B)
        "nvidia/nemotron-3-ultra-550b-a55b"             # Frontier (550B MoE)
    ]
    queue_stats = run_queue_degradation_benchmark(target_models, num_repeats=10)
    
    # Phase 3: Concurrency test on our workhorse model
    concurrency_stats = run_concurrency_stress_test("nvidia/nemotron-3.5-lightning-30b-a3b", [2, 4, 8])
    
    out_data = {
        "baseline_benchmarks": baseline_stats,
        "queue_degradation": queue_stats,
        "concurrency_stress": concurrency_stats,
        "total_elapsed_s": round(time.time() - t_start_all, 2)
    }
    
    with open("nim_benchmark_results.json", "w", encoding="utf-8") as f:
        json.dump(out_data, f, indent=2)
        
    print("\n" + "=" * 80)
    print("BENCHMARK COMPLETED! Results saved to nim_benchmark_results.json")
    print("=" * 80)
