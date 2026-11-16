"""
Arize Phoenix (OpenInference / OpenTelemetry) tracing & interactive breakpoint helper.

- Sends hierarchical spans (Chain -> Agent -> LLM / Tool) to local Arize Phoenix
  (default: http://localhost:6006/v1/traces, no API key required).
- Gracefully degrades to a no-op if PHOENIX_ENABLED != "1" or OTel packages are missing.
- Supports interactive step-pausing & full state snapshots via DEBUG_BREAKPOINTS
  (comma-separated: phase, turn, tool, llm).
"""
from __future__ import annotations

import contextlib
import json
import logging
import os
import sys
import time
from typing import Any

logger = logging.getLogger("PhoenixTracer")

_TRACER = None
_INIT_ATTEMPTED = False
_STEP_COUNTER = 0


def _get_tracer():
    global _TRACER, _INIT_ATTEMPTED
    if _INIT_ATTEMPTED:
        return _TRACER
    _INIT_ATTEMPTED = True

    if os.environ.get("PHOENIX_ENABLED", "1") != "1":
        return None

    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        endpoint = os.environ.get("PHOENIX_COLLECTOR_ENDPOINT", "http://localhost:6006/v1/traces")
        project_name = os.environ.get("PHOENIX_PROJECT_NAME", "analogverifier")

        resource = Resource.create({
            "service.name": project_name,
            "openinference.project.name": project_name,
        })
        provider = TracerProvider(resource=resource)
        exporter = OTLPSpanExporter(endpoint=endpoint, timeout=2.0)
        provider.add_span_processor(BatchSpanProcessor(exporter))
        trace.set_tracer_provider(provider)
        _TRACER = trace.get_tracer("analogverifier")
        logger.info(f"Arize Phoenix OTel tracer initialized -> {endpoint} (project={project_name})")
    except Exception as e:
        logger.debug(f"Arize Phoenix tracer unavailable ({e}); running without OTel export.")
        _TRACER = None
    return _TRACER


def _safe_json(obj: Any, max_len: int = 20000) -> str:
    try:
        s = obj if isinstance(obj, str) else json.dumps(obj, ensure_ascii=False, default=str)
    except Exception:
        s = str(obj)
    if len(s) > max_len:
        return s[:max_len] + f"... [truncated {len(s) - max_len} chars]"
    return s


@contextlib.contextmanager
def trace_span(
    name: str,
    span_kind: str = "CHAIN",
    attributes: dict[str, Any] | None = None,
    input_data: Any = None,
):
    """OpenInference-compatible span context manager."""
    tracer = _get_tracer()
    if tracer is None:
        yield None
        return

    with tracer.start_as_current_span(name) as span:
        span.set_attribute("openinference.span.kind", span_kind)
        if input_data is not None:
            span.set_attribute("input.value", _safe_json(input_data))
        if attributes:
            for k, v in attributes.items():
                if v is not None:
                    span.set_attribute(k, v if isinstance(v, (bool, int, float, str)) else _safe_json(v))
        try:
            yield span
        except Exception as exc:
            span.record_exception(exc)
            raise


def set_span_output(span: Any, output_data: Any, extra_attrs: dict[str, Any] | None = None) -> None:
    if span is None:
        return
    if output_data is not None:
        span.set_attribute("output.value", _safe_json(output_data))
    if extra_attrs:
        for k, v in extra_attrs.items():
            if v is not None:
                span.set_attribute(k, v if isinstance(v, (bool, int, float, str)) else _safe_json(v))


def flush_traces(timeout_ms: int = 5000) -> None:
    if _TRACER is None:
        return
    try:
        from opentelemetry import trace
        provider = trace.get_tracer_provider()
        if hasattr(provider, "force_flush"):
            provider.force_flush(timeout_ms)
    except Exception:
        pass


def debug_breakpoint(stage: str, label: str, state: dict[str, Any], snapshot_dir: str | None = None) -> None:
    """
    If `stage` is enabled in DEBUG_BREAKPOINTS (e.g. 'phase,turn,tool'),
    writes a full JSON state snapshot and pauses execution for inspection.
    """
    global _STEP_COUNTER
    enabled_raw = os.environ.get("DEBUG_BREAKPOINTS", "").strip()
    if not enabled_raw:
        return
    enabled = {s.strip().lower() for s in enabled_raw.split(",") if s.strip()}
    if stage.lower() not in enabled and "all" not in enabled:
        return

    _STEP_COUNTER += 1
    out_dir = snapshot_dir or os.environ.get("DEBUG_SNAPSHOT_DIR", "debug_snapshots")
    os.makedirs(out_dir, exist_ok=True)
    safe_label = "".join(c if c.isalnum() or c in "-_" else "_" for c in label)[:40]
    snap_path = os.path.join(out_dir, f"step_{_STEP_COUNTER:03d}_{stage}_{safe_label}.json")

    payload = {
        "step": _STEP_COUNTER,
        "stage": stage,
        "label": label,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "state": state,
    }
    with open(snap_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False, default=str)

    logger.warning(f"[BREAKPOINT:{stage}] {label} -> snapshot saved: {snap_path}")
    if sys.stdin and sys.stdin.isatty():
        ans = input(f"\n[BREAKPOINT {stage}:{label}] State saved to {snap_path}\nPress Enter to continue (or 'q' to abort): ")
        if ans.strip().lower() == "q":
            raise RuntimeError(f"Aborted by user at breakpoint {stage}:{label}")
