import json
import logging
import os
import time
import traceback
from typing import Any

logger = logging.getLogger("ExecutionTracer")

class TraceSpan:
    """Represents a fine-grained execution span for a specific sub-process phase."""
    def __init__(self, phase: int, name: str, inputs: dict[str, Any] | None = None):
        self.phase = phase
        self.name = name
        self.start_time = time.time()
        self.end_time = None
        self.duration_ms = 0.0
        self.status = "RUNNING"  # "SUCCESS", "WARNING", "ERROR"
        self.inputs = inputs or {}
        self.outputs = {}
        self.events = []
        self.error = None

    def log_event(self, event_type: str, message: str, data: Any | None = None):
        self.events.append({
            "timestamp": time.time(),
            "time_str": time.strftime("%H:%M:%S"),
            "type": event_type,
            "message": message,
            "data": data
        })

    def finish(self, outputs: dict[str, Any] | None = None, status: str = "SUCCESS"):
        self.end_time = time.time()
        self.duration_ms = (self.end_time - self.start_time) * 1000.0
        self.status = status
        if outputs:
            self.outputs = outputs

    def fail(self, exc: Exception, remediation_hint: str = ""):
        self.end_time = time.time()
        self.duration_ms = (self.end_time - self.start_time) * 1000.0
        self.status = "ERROR"
        self.error = {
            "type": type(exc).__name__,
            "message": str(exc),
            "traceback": traceback.format_exc(),
            "remediation_hint": remediation_hint
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "phase": self.phase,
            "name": self.name,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "duration_ms": round(self.duration_ms, 2),
            "status": self.status,
            "inputs": self.inputs,
            "outputs": self.outputs,
            "events": self.events,
            "error": self.error
        }

class ExecutionTracer:
    """
    Sub-process telemetry & tracing manager.
    Tracks execution across each phase of the autonomous analog circuit design pipeline.
    """
    def __init__(self, target_name: str = "ANALOG_CIRCUIT"):
        self.target_name = target_name
        self.start_time = time.time()
        self.spans: list[TraceSpan] = []
        self.active_span: TraceSpan | None = None

    def start_span(self, phase: int, name: str, inputs: dict[str, Any] | None = None) -> TraceSpan:
        if self.active_span and self.active_span.status == "RUNNING":
            self.active_span.finish()

        span = TraceSpan(phase=phase, name=name, inputs=inputs)
        self.spans.append(span)
        self.active_span = span
        logger.info(f"[Trace:Phase {phase}] START: {name}")
        return span

    def log(self, event_type: str, message: str, data: Any | None = None):
        if self.active_span:
            self.active_span.log_event(event_type, message, data)
        logger.info(f"[Trace:{event_type}] {message}")

    def end_span(self, outputs: dict[str, Any] | None = None, status: str = "SUCCESS"):
        if self.active_span:
            self.active_span.finish(outputs=outputs, status=status)
            logger.info(f"[Trace:Phase {self.active_span.phase}] END: {self.active_span.name} ({self.active_span.duration_ms:.1f}ms - {status})")
            self.active_span = None

    def record_error(self, exc: Exception, remediation: str = ""):
        if self.active_span:
            self.active_span.fail(exc, remediation_hint=remediation)
            logger.error(f"[Trace:Phase {self.active_span.phase}] ERROR in {self.active_span.name}: {exc}", exc_info=True)
        else:
            span = TraceSpan(phase=0, name="System Error")
            span.fail(exc, remediation_hint=remediation)
            self.spans.append(span)

    def to_dict(self) -> dict[str, Any]:
        total_duration_ms = (time.time() - self.start_time) * 1000.0
        has_error = any(s.status == "ERROR" for s in self.spans)
        return {
            "target_name": self.target_name,
            "total_duration_ms": round(total_duration_ms, 2),
            "status": "FAILED" if has_error else "COMPLETED",
            "span_count": len(self.spans),
            "spans": [s.to_dict() for s in self.spans]
        }

    def export_json(self, output_path: str):
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2)

    def export_html(self, output_path: str) -> str:
        """Exports a rich, interactive HTML trace inspection dashboard."""
        trace_data = self.to_dict()
        trace_json_str = json.dumps(trace_data).replace("</script>", "<\\/script>")

        html = f"""<!DOCTYPE html>
<html lang="en" class="dark">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Execution Trace &amp; Debug Inspector — {self.target_name}</title>
  <script src="https://www.gstatic.com/antigravity/web/dev/tailwindcss.min.js"></script>
  <style>
    body {{
      background-color: #090d16;
      color: #f8fafc;
      font-family: ui-sans-serif, system-ui, -apple-system, sans-serif;
    }}
    .custom-scrollbar::-webkit-scrollbar {{ width: 6px; height: 6px; }}
    .custom-scrollbar::-webkit-scrollbar-thumb {{ background: #334155; border-radius: 4px; }}
  </style>
</head>
<body class="min-h-screen p-4 md:p-8 custom-scrollbar">
  <div class="max-w-6xl mx-auto space-y-6">

    <!-- Header -->
    <header class="bg-slate-900 border border-slate-800 rounded-2xl p-5 shadow flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
      <div>
        <div class="flex items-center gap-3">
          <div class="p-2.5 bg-sky-500/10 border border-sky-500/30 rounded-xl text-sky-400">
            <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-6 9l2 2 4-4"/></svg>
          </div>
          <div>
            <h1 class="text-xl font-bold text-white flex items-center gap-2">
              Execution Trace &amp; Sub-Process Debugger
              <span class="text-xs px-2.5 py-0.5 rounded-full {('bg-rose-500/20 text-rose-300 border border-rose-500/30' if trace_data['status'] == 'FAILED' else 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/30')} font-mono">
                {trace_data['status']}
              </span>
            </h1>
            <p class="text-xs text-slate-400 mt-0.5">Target: <strong class="text-sky-300">{self.target_name}</strong> | Total Elapsed: <span class="font-mono">{trace_data['total_duration_ms']:.1f} ms</span> | Spans: {trace_data['span_count']}</p>
          </div>
        </div>
      </div>
      <div>
        <button onclick="window.print()" class="text-xs bg-slate-800 hover:bg-slate-700 text-slate-300 px-3 py-1.5 rounded-xl border border-slate-700">Print / Save Log</button>
      </div>
    </header>

    <!-- Trace Spans Timeline -->
    <div class="space-y-4" id="spansContainer">
    </div>

  </div>

  <script>
    const TRACE = {trace_json_str};

    function render() {{
      const container = document.getElementById('spansContainer');
      container.innerHTML = '';

      TRACE.spans.forEach((span, idx) => {{
        const card = document.createElement('div');
        const isErr = span.status === 'ERROR';
        const isWarn = span.status === 'WARNING';
        const borderColor = isErr ? 'border-rose-500/50' : (isWarn ? 'border-amber-500/50' : 'border-slate-800');
        const headerBg = isErr ? 'bg-rose-950/20' : 'bg-slate-900/80';

        card.className = `bg-slate-900 border ${{borderColor}} rounded-2xl overflow-hidden shadow transition-all`;

        const badgeClass = isErr ? 'bg-rose-500/20 text-rose-300 border-rose-500/40' : (isWarn ? 'bg-amber-500/20 text-amber-300 border-amber-500/40' : 'bg-emerald-500/20 text-emerald-300 border-emerald-500/40');

        card.innerHTML = `
          <div class="${{headerBg}} p-4 border-b border-slate-800 flex items-center justify-between cursor-pointer" onclick="toggleSpan(${{idx}})">
            <div class="flex items-center gap-3">
              <span class="w-6 h-6 rounded-full flex items-center justify-center font-bold text-xs bg-slate-800 text-slate-300">${{span.phase}}</span>
              <div>
                <h3 class="font-bold text-sm text-white flex items-center gap-2">
                  ${{span.name}}
                  <span class="text-[10px] uppercase font-mono px-2 py-0.5 rounded-md border ${{badgeClass}}">${{span.status}}</span>
                </h3>
              </div>
            </div>
            <div class="flex items-center gap-4 text-xs font-mono text-slate-400">
              <span>${{span.duration_ms}} ms</span>
              <svg id="chevron-${{idx}}" class="w-4 h-4 transform transition-transform" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7"/></svg>
            </div>
          </div>

          <div id="body-${{idx}}" class="p-5 space-y-4 text-xs">
            ${{span.error ? `
              <div class="bg-rose-950/30 border border-rose-500/40 rounded-xl p-4 space-y-2">
                <div class="font-bold text-rose-400 flex items-center gap-2">
                  <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>
                  [${{span.error.type}}] ${{span.error.message}}
                </div>
                ${{span.error.remediation_hint ? `
                  <div class="text-amber-300/90 bg-amber-500/10 p-2.5 rounded-lg border border-amber-500/20">
                    <strong>Suggested Remediation:</strong> ${{span.error.remediation_hint}}
                  </div>
                ` : ''}}
                <pre class="bg-slate-950 p-3 rounded-lg font-mono text-[11px] text-rose-300 overflow-x-auto max-h-48">${{span.error.traceback}}</pre>
              </div>
            ` : ''}}

            <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div class="bg-slate-950 border border-slate-800 rounded-xl p-3">
                <h4 class="font-bold uppercase text-[10px] text-slate-500 mb-1">Inputs</h4>
                <pre class="font-mono text-[11px] text-slate-300 overflow-x-auto max-h-40">${{JSON.stringify(span.inputs, null, 2)}}</pre>
              </div>
              <div class="bg-slate-950 border border-slate-800 rounded-xl p-3">
                <h4 class="font-bold uppercase text-[10px] text-slate-500 mb-1">Outputs</h4>
                <pre class="font-mono text-[11px] text-slate-300 overflow-x-auto max-h-40">${{JSON.stringify(span.outputs, null, 2)}}</pre>
              </div>
            </div>

            ${{span.events && span.events.length > 0 ? `
              <div class="bg-slate-950 border border-slate-800 rounded-xl p-3">
                <h4 class="font-bold uppercase text-[10px] text-slate-500 mb-2">Internal Step Events (${{span.events.length}})</h4>
                <div class="space-y-1 font-mono text-[11px]">
                  ${{span.events.map(ev => `
                    <div class="flex items-start gap-2 text-slate-400">
                      <span class="text-slate-600">[${{ev.time_str}}]</span>
                      <span class="text-sky-400">[${{ev.type}}]</span>
                      <span class="text-slate-300">${{ev.message}}</span>
                    </div>
                  `).join('')}}
                </div>
              </div>
            ` : ''}}
          </div>
        `;
        container.appendChild(card);
      }});
    }}

    function toggleSpan(idx) {{
      const body = document.getElementById(`body-${{idx}}`);
      const chevron = document.getElementById(`chevron-${{idx}}`);
      if (body.classList.contains('hidden')) {{
        body.classList.remove('hidden');
        chevron.classList.remove('rotate-180');
      }} else {{
        body.classList.add('hidden');
        chevron.classList.add('rotate-180');
      }}
    }}

    window.onload = render;
  </script>
</body>
</html>
"""
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(html)
        return output_path
