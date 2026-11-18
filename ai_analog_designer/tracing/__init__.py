"""
Execution Tracing and Diagnostic Telemetry Package.
Enables fine-grained, step-by-step tracing across all 6 autonomous analog synthesis phases.
"""

from .execution_tracer import ExecutionTracer, TraceSpan

__all__ = ["ExecutionTracer", "TraceSpan"]
