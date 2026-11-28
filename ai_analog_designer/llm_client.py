"""
Provider-agnostic OpenAI-compatible chat client.

Supported providers (select with env LLM_PROVIDER):
  - "nim"        : NVIDIA NIM  (https://integrate.api.nvidia.com/v1), key NVIDIA_API_KEY
  - "openrouter" : OpenRouter  (https://openrouter.ai/api/v1),          key OPENROUTER_API_KEY

Features:
  - Streaming with a hard wall-clock timeout (NIM sometimes stalls for minutes)
  - Task-aware fast-first routing with guarded escalation for hard synthesis turns
  - Automatic model fallback chain on timeout / 5xx / 429
  - Per-call latency telemetry (TTFT, total, tokens) collected in LLMClient.call_log
"""
import json
import os
import re
import threading
import time
import urllib.error
import urllib.request
from typing import Any


def _load_env():
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    for p in [".env", os.path.join(root, ".env")]:
        if os.path.exists(p):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith("#") and "=" in line:
                            k, v = line.split("=", 1)
                            k, v = k.strip(), v.strip().strip("'\"")
                            if k not in os.environ and v:
                                os.environ[k] = v
            except Exception:
                pass


_load_env()

def model_extra_body(provider: str, model: str) -> dict[str, Any]:
    """Per-model request knobs. Reasoning ("thinking") is disabled by default for extraction/synthesis:
    on NIM it multiplies latency 5-30x (see benchmark_results/NIM_LATENCY_BENCH.md). Set LLM_THINKING=1 to enable."""
    if provider == "openrouter":
        body: dict[str, Any] = {"usage": {"include": True}}       # returns exact USD cost per call
        if os.environ.get("LLM_THINKING") != "1":
            body["reasoning"] = {"enabled": False}
        elif os.environ.get("LLM_REASONING_EFFORT"):           # 추론을 끌 수 없는 모델(Opus 5.5)의 비용을 줄일 때 (low 등)
            body["reasoning"] = {"effort": os.environ["LLM_REASONING_EFFORT"]}
        return body
    if provider != "nim" or os.environ.get("LLM_THINKING") == "1":
        return {}
    m = model.lower()
    if m.startswith("nvidia/nemotron-3") or m.startswith("z-ai/glm") or m.startswith("qwen/"):
        return {"chat_template_kwargs": {"enable_thinking": False}}
    if m.startswith("deepseek-ai/"):
        return {"chat_template_kwargs": {"thinking": False}}
    return {}


PROVIDERS = {
    "nim": {
        "base_url": lambda: os.environ.get("NIM_BASE_URL", "https://integrate.api.nvidia.com/v1").rstrip("/") + "/chat/completions",
        "key_env": "NVIDIA_API_KEY",
        # Empirical benchmark verified defaults (AgentBaton Capable-to-Efficient & Terminus Subagent architecture)
        "default_model": lambda: os.environ.get("LLM_MODEL", "nvidia/nemotron-3.5-lightning-30b-a3b"),
        "fallback_models": lambda: [m for m in os.environ.get(
            "LLM_FALLBACK_MODELS", "nvidia/nemotron-3.5-lightning-30b-a3b,nvidia/nemotron-3-nano-omni-30b-a3b-reasoning,poolside/laguna-xs-2.1").split(",") if m],
        "fast_model": lambda: os.environ.get("LLM_FAST_MODEL", "nvidia/nemotron-3.5-bolt-e4b"),
        "capable_model": lambda: os.environ.get("LLM_CAPABLE_MODEL", "nvidia/nemotron-3.5-lightning-30b-a3b"),
        "frontier_model": lambda: os.environ.get("LLM_FRONTIER_MODEL", "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning"),
        "supports_json_mode": True,
    },
    "openrouter": {
        "base_url": lambda: os.environ.get("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1/chat/completions"),
        "key_env": "OPENROUTER_API_KEY",
        "default_model": lambda: os.environ.get("LLM_MODEL", "anthropic/claude-haiku-5.5"),
        "fallback_models": lambda: [m for m in os.environ.get(
            "LLM_FALLBACK_MODELS", "openai/gpt-6-luna,deepseek/deepseek-v4.1-flash").split(",") if m],
        "fast_model": lambda: os.environ.get("LLM_FAST_MODEL", "deepseek/deepseek-v4.1-flash"),
        "capable_model": lambda: os.environ.get("LLM_CAPABLE_MODEL", "anthropic/claude-haiku-5.5"),
        "frontier_model": lambda: os.environ.get("LLM_FRONTIER_MODEL", "openai/gpt-6-luna"),
        "supports_json_mode": True,
    },
    "groq": {
        "base_url": lambda: os.environ.get("GROQ_BASE_URL", "https://api.groq.com/openai/v1").rstrip("/") + "/chat/completions",
        "key_env": "GROQ_API_KEY",
        "default_model": lambda: os.environ.get("LLM_MODEL", "openai/gpt-oss-120b"),
        "fallback_models": lambda: [m for m in os.environ.get(
            "LLM_FALLBACK_MODELS", "qwen/qwen3.8-27b,openai/gpt-oss-20b").split(",") if m],
        "fast_model": lambda: os.environ.get("LLM_FAST_MODEL", "qwen/qwen3.8-27b"),
        "capable_model": lambda: os.environ.get("LLM_CAPABLE_MODEL", "openai/gpt-oss-120b"),
        "frontier_model": lambda: os.environ.get("LLM_FRONTIER_MODEL", "openai/gpt-oss-120b"),
        "supports_json_mode": True,
    },
    "wusrouter": {
        "base_url": lambda: os.environ.get("WUSROUTER_BASE_URL", "https://wusrouter.com/v1").rstrip("/") + "/chat/completions",
        "key_env": "WUSROUTER_API_KEY",
        "default_model": lambda: os.environ.get("LLM_MODEL", "mimo-v2.5:free"),
        "fallback_models": lambda: [m for m in os.environ.get(
            "LLM_FALLBACK_MODELS", "mimo-v2.5:free,ws/gpt-5.6-terra:free,zai/glm-5.3-flash:free,cohere/north-mini-code:free,ws/gpt-5.6-luna:free").split(",") if m],
        "fast_model": lambda: os.environ.get("LLM_FAST_MODEL", "zai/glm-5.3-flash:free"),
        "capable_model": lambda: os.environ.get("LLM_CAPABLE_MODEL", "mimo-v2.5:free"),
        "frontier_model": lambda: os.environ.get("LLM_FRONTIER_MODEL", "ws/gpt-5.6-terra:free"),
        "supports_json_mode": True,
    },
}


def repair_truncated_json(raw: str) -> dict[str, Any] | None:
    """Attempts to repair and parse a truncated or malformed JSON string with control-char tolerance."""
    text = raw.strip()
    # Step 1: Direct attempt with strict=False (allows unescaped newlines/tabs in strings)
    try:
        data = json.loads(text, strict=False)
        if isinstance(data, (dict, list)):
            return data
    except Exception:
        pass

    # Step 2: Bracket repair loop with strict=False
    for trim_len in range(len(text), max(10, len(text) - 1000), -1):
        candidate = text[:trim_len].rstrip()
        if candidate.endswith(","):
            candidate = candidate[:-1].rstrip()
        in_str, escape, stack = False, False, []
        for ch in candidate:
            if ch == '\\' and not escape:
                escape = True
                continue
            if ch == '"' and not escape:
                in_str = not in_str
            elif not in_str:
                if ch == '{':
                    stack.append('}')
                elif ch == '[':
                    stack.append(']')
                elif ch in ('}', ']') and stack and stack[-1] == ch:
                    stack.pop()
            escape = False
        if in_str:
            candidate += '"'
        try:
            data = json.loads(candidate + "".join(reversed(stack)), strict=False)
            if isinstance(data, (dict, list)):
                return data
        except Exception:
            continue
    return None


def _strip_think(text: str) -> str:
    """Removes <think>...</think> reasoning blocks some models emit inline."""
    return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()


class LLMTimeout(Exception):
    pass


class LLMBudgetExceeded(Exception):
    pass


# Per-task overrides always take precedence over the scheduler.  They are
# intentionally granular so an operator can tune one expensive stage without
# accidentally moving every other call to the same model.
TASK_MODEL_ENV = [
    ("hkg_specs", "LLM_EXTRACT_MODEL"),
    ("hermes", "LLM_HERMES_MODEL"),
    ("harness2_synth", "LLM_SYNTH_MODEL"),
    ("synth", "LLM_SYNTH_MODEL"),
    ("dyn_tb", "LLM_TB_MODEL"),
    ("tb", "LLM_TB_MODEL"),
]

_COST_LOCK = threading.Lock()
_SPENT_USD = [0.0]


def spent_usd() -> float:
    return _SPENT_USD[0]


# Process-wide cap on in-flight requests (NIM returns HTTP 429 above ~4-6 parallel calls per key).
_GLOBAL_SEM = threading.BoundedSemaphore(int(os.environ.get("LLM_MAX_CONCURRENCY", "4")))
_RATE_LOCK = threading.Lock()
_NEXT_SLOT = [0.0]


def _acquire_slot(min_interval_s: float):
    """Blocks until a concurrency slot is free and the minimum spacing between request starts has elapsed."""
    _GLOBAL_SEM.acquire()
    with _RATE_LOCK:
        now = time.monotonic()
        wait = _NEXT_SLOT[0] - now
        if wait > 0:
            time.sleep(wait)
        _NEXT_SLOT[0] = max(now, _NEXT_SLOT[0]) + min_interval_s


class LLMClient:
    """OpenAI-compatible chat client with task-aware routing and bounded fallback."""

    def __init__(
        self,
        api_key: str | None = None,
        default_model: str | None = None,
        base_url: str | None = None,
        provider: str | None = None,
        request_timeout: float | None = None,
        first_token_timeout: float | None = None,
    ):
        self.provider = (provider or os.environ.get("LLM_PROVIDER") or
                         ("nim" if os.environ.get("NVIDIA_API_KEY") else "openrouter")).lower()
        cfg = PROVIDERS[self.provider]
        self.api_key = (api_key or os.environ.get(cfg["key_env"], "")).strip()
        if not self.api_key:
            raise RuntimeError(
                f"Missing required API key '{cfg['key_env']}' for LLM provider '{self.provider}'. "
                f"Set {cfg['key_env']} in your environment or .env."
            )
        self.base_url = base_url or cfg["base_url"]()
        self.scheduler_mode = os.environ.get("LLM_SCHEDULER", "adaptive").strip().lower()
        if self.scheduler_mode not in {"adaptive", "legacy"}:
            raise ValueError("LLM_SCHEDULER must be 'adaptive' or 'legacy'")

        # LLM_MODEL/default_model is an explicit operator choice and therefore
        # overrides automatic routing.  Otherwise we expose the capable tier as
        # the nominal model while each task receives its own route below.
        self._explicit_default_model = default_model or os.environ.get("LLM_MODEL")
        self.legacy_default_model = cfg["default_model"]()
        self.model_tiers = {
            "fast": cfg["fast_model"](),
            "capable": cfg["capable_model"](),
            "frontier": cfg["frontier_model"](),
        }
        self.default_model = self._explicit_default_model or self.model_tiers["capable"]
        self._legacy_fallback_models = cfg["fallback_models"]()
        self._explicit_fallback_models = [
            m.strip() for m in os.environ.get("LLM_FALLBACK_MODELS", "").split(",") if m.strip()
        ]
        self.fallback_models = self._dedupe_models([
            self.model_tiers["fast"], self.model_tiers["capable"], self.model_tiers["frontier"]
        ], exclude=self.default_model)
        self.supports_json_mode = cfg["supports_json_mode"]
        self.request_timeout = float(request_timeout or os.environ.get("LLM_TIMEOUT_S", 240))
        self.first_token_timeout = float(first_token_timeout or os.environ.get("LLM_TTFT_TIMEOUT_S", 90))
        self._tier_request_timeouts = {
            "fast": float(os.environ.get("LLM_FAST_TIMEOUT_S", 35)),
            "capable": float(os.environ.get("LLM_CAPABLE_TIMEOUT_S", 60)),
            "frontier": float(os.environ.get("LLM_FRONTIER_TIMEOUT_S", 90)),
        }
        self._tier_ttft_timeouts = {
            "fast": float(os.environ.get("LLM_FAST_TTFT_TIMEOUT_S", 12)),
            "capable": float(os.environ.get("LLM_CAPABLE_TTFT_TIMEOUT_S", 15)),
            "frontier": float(os.environ.get("LLM_FRONTIER_TTFT_TIMEOUT_S", 25)),
        }
        # Datasheet table extraction is a bounded, high-value batch operation.
        # It needs more room than a chat/tool turn (a page can contain hundreds
        # of table cells), but only the HKG path receives this longer budget.
        # Keeping this separate prevents a slow extraction request from making
        # every Hermes turn wait several minutes.
        self._extraction_request_timeouts = {
            "fast": float(os.environ.get("LLM_EXTRACT_FAST_TIMEOUT_S", 45)),
            "capable": float(os.environ.get("LLM_EXTRACT_CAPABLE_TIMEOUT_S", 90)),
            "frontier": float(os.environ.get("LLM_EXTRACT_FRONTIER_TIMEOUT_S", 150)),
        }
        self._extraction_ttft_timeouts = {
            "fast": float(os.environ.get("LLM_EXTRACT_FAST_TTFT_TIMEOUT_S", 15)),
            "capable": float(os.environ.get("LLM_EXTRACT_CAPABLE_TTFT_TIMEOUT_S", 25)),
            "frontier": float(os.environ.get("LLM_EXTRACT_FRONTIER_TTFT_TIMEOUT_S", 40)),
        }
        self.hermes_escalate_after = max(1, int(os.environ.get("LLM_HERMES_ESCALATE_AFTER", "3")))
        self.min_interval_s = float(os.environ.get("LLM_MIN_INTERVAL_S", 0.5))
        self.call_log: list[dict[str, Any]] = []
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    @staticmethod
    def _dedupe_models(models: list[str], exclude: str | None = None) -> list[str]:
        result: list[str] = []
        for model in models:
            model = (model or "").strip()
            if model and model != exclude and model not in result:
                result.append(model)
        return result

    def _task_override(self, tag: str) -> str | None:
        for prefix, env in TASK_MODEL_ENV:
            if tag.startswith(prefix) and os.environ.get(env):
                return os.environ[env]
        return None

    def _tier_for_model(self, model: str) -> str:
        for tier, tier_model in self.model_tiers.items():
            if model == tier_model:
                return tier
        return "capable"

    def _tiers_for_tag(self, tag: str) -> list[str]:
        """Return the smallest model sequence that fits this workflow step.

        Structured per-page extraction and generated test benches are bounded
        tasks, so they begin on the fast tier.  A full circuit netlist is the
        only task that can earn the frontier model, and only after earlier
        Hermes repair turns failed to converge.
        """
        tag = tag or ""
        # Retry is deliberately a single frontier attempt.  Routine pages
        # retain the economical fast/capable path; only a page that exhausted
        # both gets the larger availability/quality fallback.
        if tag.startswith("hkg_specs_retry"):
            return ["frontier"]
        if tag.startswith("hkg_specs"):
            return ["fast", "capable"]
        if tag.startswith("hkg_pins"):
            return ["capable", "frontier", "fast"]
        if tag.startswith("hkg") or tag == "chat":
            return ["fast", "capable"]
        if tag.startswith(("dyn_tb", "tb", "verifier_", "harness2_propose")):
            return ["fast", "capable"]
        if tag.startswith("hermes_turn"):
            match = re.search(r"(\d+)$", tag)
            turn = int(match.group(1)) if match else 1
            if turn >= self.hermes_escalate_after:
                return ["frontier", "capable", "fast"]
            # Early turns remain fast-first, but synthesis must not terminate
            # merely because both smaller remote models are temporarily slow.
            # The frontier tier is a last-resort availability fallback here,
            # not the default model.
            return ["capable", "fast", "frontier"]
        if tag.startswith(("harness2_synth", "synth")):
            return ["capable", "fast"]
        return ["fast", "capable"]

    def model_chain_for(self, tag: str = "", model: str | None = None) -> list[str]:
        """Resolve a deterministic, de-duplicated model chain for one call."""
        explicit = model or self._task_override(tag) or self._explicit_default_model
        if explicit:
            return self._dedupe_models([explicit] + self._explicit_fallback_models)
        if self.scheduler_mode == "legacy":
            return self._dedupe_models([self.legacy_default_model] + self._legacy_fallback_models)
        return self._dedupe_models(
            [self.model_tiers[tier] for tier in self._tiers_for_tag(tag)] + self._explicit_fallback_models
        )

    def routing_config(self) -> dict[str, Any]:
        """Safe, display-ready routing metadata for the Studio API."""
        return {
            "scheduler": self.scheduler_mode,
            "tiers": dict(self.model_tiers),
            "hermes_escalate_after": self.hermes_escalate_after,
            "routes": {
                "extract_specs": self.model_chain_for("hkg_specs_p1"),
                "extract_specs_recovery": self.model_chain_for("hkg_specs_retry_p1"),
                "extract_pins": self.model_chain_for("hkg_pins"),
                "hermes_initial": self.model_chain_for("hermes_turn_1"),
                "hermes_repair": self.model_chain_for(f"hermes_turn_{self.hermes_escalate_after}"),
                "testbench": self.model_chain_for("dyn_tb"),
            },
        }

    def _timeouts_for_model(self, model: str, timeout_profile: str = "default") -> tuple[float, float]:
        tier = self._tier_for_model(model)
        if timeout_profile == "extraction":
            request_limits = self._extraction_request_timeouts
            ttft_limits = self._extraction_ttft_timeouts
        elif timeout_profile == "default":
            request_limits = self._tier_request_timeouts
            ttft_limits = self._tier_ttft_timeouts
        else:
            raise ValueError(f"Unknown LLM timeout profile: {timeout_profile}")
        return (
            min(self.request_timeout, request_limits[tier]),
            min(self.first_token_timeout, ttft_limits[tier]),
        )

    def _stream_call(
        self,
        payload: dict[str, Any],
        request_timeout: float | None = None,
        first_token_timeout: float | None = None,
    ) -> dict[str, Any]:
        payload = dict(payload, stream=True)
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        }
        if self.provider == "openrouter":
            headers.update({"HTTP-Referer": "https://github.com/eethsc/analogverifier", "X-Title": "AnalogVerifier"})
        req = urllib.request.Request(self.base_url, data=json.dumps(payload).encode("utf-8"), headers=headers)

        t0 = time.perf_counter()
        ttft = None
        parts: list[str] = []
        reasoning_parts: list[str] = []
        usage = None
        finish_reason = None
        # socket timeout bounds the wait for each chunk (incl. first token)
        request_timeout = request_timeout or self.request_timeout
        first_token_timeout = first_token_timeout or self.first_token_timeout
        with urllib.request.urlopen(req, timeout=first_token_timeout) as resp:
            for raw in resp:
                now = time.perf_counter()
                if now - t0 > request_timeout:
                    raise LLMTimeout(f"total time exceeded {request_timeout:.0f}s")
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
                for ch in obj.get("choices", []) or []:
                    d = ch.get("delta") or {}
                    piece = d.get("content") or ""
                    r_piece = d.get("reasoning_content") or d.get("reasoning") or ""
                    if r_piece:
                        reasoning_parts.append(r_piece)
                    if (piece or r_piece) and ttft is None:
                        ttft = now - t0
                    if piece:
                        parts.append(piece)
                    if ch.get("finish_reason"):
                        finish_reason = ch["finish_reason"]
        total = time.perf_counter() - t0
        text = "".join(parts)
        if not text.strip() and reasoning_parts:
            # Resilient fallback if reasoning model truncated before emitting formal content
            text = "".join(reasoning_parts)
        return {
            "text": text,
            "ttft_s": round(ttft if ttft is not None else total, 2),
            "total_s": round(total, 2),
            "completion_tokens": (usage or {}).get("completion_tokens") or len(text) // 4,
            "prompt_tokens": (usage or {}).get("prompt_tokens"),
            "cost_usd": (usage or {}).get("cost"),
            "finish_reason": finish_reason,
        }

    def complete(
        self,
        prompt: str = "",
        system_prompt: str | None = None,
        model: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 8192,
        response_format: dict[str, str] | None = None,
        retries: int = 3,
        tag: str = "",
        messages: list[dict[str, Any]] | None = None,
        model_chain: list[str] | None = None,
        timeout_profile: str = "default",
    ) -> str:
        if messages is not None:
            messages_payload = list(messages)
            if system_prompt and not any(m.get("role") == "system" for m in messages_payload):
                messages_payload.insert(0, {"role": "system", "content": system_prompt})
        else:
            messages_payload = []
            if system_prompt:
                messages_payload.append({"role": "system", "content": system_prompt})
            if prompt:
                messages_payload.append({"role": "user", "content": prompt})

        if self.provider == "groq":
            groq_cap = int(os.environ.get("GROQ_MAX_TOKENS", "2048"))
            max_tokens = min(max_tokens, groq_cap)

        budget = float(os.environ.get("LLM_BUDGET_USD", "0") or 0)
        if budget and _SPENT_USD[0] >= budget:
            raise LLMBudgetExceeded(f"LLM budget exhausted: spent ${_SPENT_USD[0]:.3f} >= LLM_BUDGET_USD=${budget}")
        chain = self._dedupe_models(model_chain) if model_chain is not None else self.model_chain_for(tag, model)
        if not chain:
            raise RuntimeError("LLM model chain is empty")
        from .tracing.phoenix_tracer import debug_breakpoint, set_span_output, trace_span

        with trace_span(
            f"llm.{tag or 'complete'}",
            span_kind="LLM",
            attributes={
                "llm.provider": self.provider,
                "llm.model_name": chain[0],
                "llm.invocation_parameters": {"temperature": temperature, "max_tokens": max_tokens},
                "llm.input_messages": messages_payload,
            },
            input_data=messages_payload,
        ) as otel_span:
            last_err = None
            for m in chain:
                for attempt in range(1, retries + 1):
                    payload: dict[str, Any] = {"model": m, "messages": messages_payload,
                                               "temperature": temperature, "max_tokens": max_tokens}
                    payload.update(model_extra_body(self.provider, m))
                    if response_format and self.supports_json_mode:
                        payload["response_format"] = response_format
                    t0 = time.perf_counter()
                    _acquire_slot(self.min_interval_s)
                    try:
                        request_timeout, first_token_timeout = self._timeouts_for_model(m, timeout_profile)
                        res = self._stream_call(
                            payload,
                            request_timeout=request_timeout,
                            first_token_timeout=first_token_timeout,
                        )
                        text = _strip_think(res["text"])
                        if not text.strip():
                            raise RuntimeError("empty completion")
                        self._log(tag, m, attempt, "ok", res)
                        usage = res.get("usage") or {}
                        set_span_output(otel_span, text, {
                            "llm.model_name": m,
                            "llm.token_count.prompt": usage.get("prompt_tokens"),
                            "llm.token_count.completion": usage.get("completion_tokens"),
                        })
                        debug_breakpoint("llm", tag or m, {
                            "provider": self.provider,
                            "model": m,
                            "tag": tag,
                            "messages": messages_payload,
                            "response": text,
                        })
                        return text
                    except urllib.error.HTTPError as e:
                        body = e.read().decode("utf-8", errors="ignore")[:300]
                        last_err = f"HTTP {e.code}: {body}"
                        self._log(tag, m, attempt, f"http_{e.code}", {"total_s": round(time.perf_counter() - t0, 2)}, last_err)
                        if e.code == 400 and "response_format" in payload and response_format:
                            # some models reject json mode; retry without it
                            response_format = None
                            continue
                        if e.code == 413:
                            # Request too large (TPM limit exceeded due to prompt + max_tokens upfront reservation)
                            if payload.get("max_tokens", 0) > 1024:
                                payload["max_tokens"] = 1024
                                continue
                        if e.code in (401, 403, 404):
                            break  # model unavailable for this key -> next model
                        wait_s = 2 * attempt
                        if e.code == 429:
                            m_wait = re.search(r"try again in ([0-9.]+)s", body)
                            if m_wait:
                                wait_s = min(float(m_wait.group(1)) + 0.5, 20.0)
                            else:
                                wait_s = min(8.0 * attempt, 20.0)
                        time.sleep(wait_s)
                    except LLMBudgetExceeded:
                        raise
                    except Exception as e:
                        last_err = f"{type(e).__name__}: {e}"
                        err_lower = str(e).lower()
                        self._log(tag, m, attempt, "timeout" if "timed out" in err_lower or isinstance(e, LLMTimeout) else "error",
                                  {"total_s": round(time.perf_counter() - t0, 2)}, last_err)
                        if isinstance(e, LLMTimeout) or "timed out" in err_lower:
                            break  # stalled model -> fall back immediately instead of retrying
                        is_net_drop = isinstance(e, urllib.error.URLError) or any(
                            k in err_lower for k in ("getaddrinfo", "name or service not known", "temporary failure in name resolution", "network is unreachable")
                        )
                        if is_net_drop:
                            recovery_budget = float(os.environ.get("LLM_NETWORK_RECOVERY_S", "180"))
                            waited = 0.0
                            step_wait = 10.0
                            while waited < recovery_budget:
                                time.sleep(step_wait)
                                waited += step_wait
                                try:
                                    import socket
                                    from urllib.parse import urlparse
                                    host = urlparse(self.base_url).hostname or "integrate.api.nvidia.com"
                                    socket.getaddrinfo(host, 443)
                                    break
                                except Exception:
                                    continue
                        else:
                            time.sleep(2 * attempt)
                    finally:
                        _GLOBAL_SEM.release()
            raise RuntimeError(f"LLM call failed on all models {chain}: {last_err}")

    def _log(self, tag, model, attempt, status, res, error=None):
        entry = {"ts": time.time(), "tag": tag, "provider": self.provider, "model": model, "attempt": attempt,
                 "status": status, **{k: v for k, v in res.items() if k != "text"}}
        if entry.get("cost_usd"):
            with _COST_LOCK:
                _SPENT_USD[0] += float(entry["cost_usd"])
            entry["spent_total_usd"] = round(_SPENT_USD[0], 4)
        if error:
            entry["error"] = error[:300]
        with self._lock:
            self.call_log.append(entry)
        cost = f" cost=${entry['cost_usd']:.4f} spent=${entry['spent_total_usd']:.3f}" if entry.get("cost_usd") else ""
        print(f"[LLM] {tag or 'call'} model={model} status={status} ttft={entry.get('ttft_s')}s "
              f"total={entry.get('total_s')}s tokens={entry.get('completion_tokens')}{cost}", flush=True)

    def latency_summary(self) -> dict[str, Any]:
        ok = [c for c in self.call_log if c["status"] == "ok"]
        tot = sorted(c["total_s"] for c in ok)
        return {
            "calls": len(self.call_log),
            "ok": len(ok),
            "failed_or_timed_out": len(self.call_log) - len(ok),
            "total_llm_seconds": round(sum(c.get("total_s", 0) for c in self.call_log), 1),
            "median_s": tot[len(tot) // 2] if tot else None,
            "max_s": tot[-1] if tot else None,
            "cost_usd": round(sum(c.get("cost_usd") or 0 for c in self.call_log), 4),
            "by_tag": {t: round(sum(c["total_s"] for c in ok if c["tag"] == t), 1) for t in {c["tag"] for c in ok}},
        }

    # ------------------------------------------------------------------
    def complete_json(
        self,
        prompt: str,
        system_prompt: str | None = None,
        model: str | None = None,
        temperature: float = 0.1,
        max_tokens: int = 8192,
        tag: str = "",
        timeout_profile: str = "default",
    ) -> dict[str, Any]:
        if self.provider == "groq":
            groq_cap = int(os.environ.get("GROQ_MAX_TOKENS", "2048"))
            max_tokens = min(max_tokens, groq_cap)
        json_sys_prompt = (system_prompt or "") + "\n\nCRITICAL: Respond ONLY with a valid JSON object. Do NOT enclose in markdown formatting or backticks."
        # Transport fallback alone is insufficient for extraction: a fast model
        # can answer successfully yet emit unusable JSON.  In that case retry on
        # the next scheduled tier, rather than failing the whole PDF workflow.
        chain = self.model_chain_for(tag, model)
        last_error: Exception | None = None
        for idx, selected_model in enumerate(chain, start=1):
            try:
                raw_text = self.complete(
                    prompt,
                    system_prompt=json_sys_prompt,
                    model=selected_model,
                    model_chain=[selected_model],
                    temperature=temperature,
                    max_tokens=max_tokens,
                    response_format={"type": "json_object"},
                    tag=tag,
                    timeout_profile=timeout_profile,
                )
            except Exception as exc:
                # A transport failure on one tier is not terminal for a JSON
                # task.  Continue to the next scheduled model just as we do
                # when a response fails schema validation below.
                last_error = exc
                continue
            try:
                return self.parse_json_text(raw_text)
            except ValueError as exc:
                last_error = exc
                self._log(
                    tag,
                    selected_model,
                    idx,
                    "invalid_json",
                    {"total_s": 0.0, "completion_tokens": len(raw_text) // 4},
                    str(exc),
                )
        raise last_error or ValueError("Failed to parse JSON from all scheduled models")

    @staticmethod
    def parse_json_text(raw_text: str) -> dict[str, Any]:
        cleaned = raw_text.strip()
        m = re.search(r"```(?:json)?\s*(.*?)```", cleaned, re.DOTALL)
        if m:
            cleaned = m.group(1).strip()
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            start, end = cleaned.find("{"), cleaned.rfind("}")
            if start != -1 and end != -1:
                try:
                    return json.loads(cleaned[start:end + 1])
                except json.JSONDecodeError:
                    pass
            repaired = repair_truncated_json(cleaned[start:] if start != -1 else cleaned)
            if repaired is not None:
                return repaired
            raise ValueError(f"Failed to parse JSON from LLM response:\n{raw_text[:500]}")

    # Backwards-compat helpers used by extract_specs_from_prompt
    def chat_completion(self, messages: list[dict[str, str]], temperature: float = 0.1, **kw) -> str:
        sys_p = "\n".join(m["content"] for m in messages if m["role"] == "system") or None
        user_p = "\n".join(m["content"] for m in messages if m["role"] != "system")
        return self.complete(user_p, system_prompt=sys_p, temperature=temperature, tag=kw.get("tag", "chat"))

    def parse_json_response(self, text: str) -> dict[str, Any] | None:
        try:
            return self.parse_json_text(text)
        except Exception:
            return None
