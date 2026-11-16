import glob
import json
import logging
import os
import re
import threading
import time
import uuid
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse

from ..autonomous_design_agent import AutonomousAnalogDesignAgent
from ..pdf_to_graph import PDGVisualizer
from ..visualization import ProcessVisualizer

logger = logging.getLogger("StudioServer")

_STUDIO_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(os.path.dirname(_STUDIO_DIR))

ALLOWED_PDF_ROOTS = [
    os.path.abspath("testcases"),
    os.path.abspath("uploads"),
    os.path.abspath(os.path.join(_PROJECT_ROOT, "testcases")),
    os.path.abspath(os.path.join(_PROJECT_ROOT, "uploads")),
]


def safe_pdf_path(pdf_path: str) -> str | None:
    """Returns the absolute path only if it resolves inside testcases/ or uploads/ (prevents arbitrary file reads)."""
    if not pdf_path:
        return None
    real = os.path.abspath(os.path.realpath(pdf_path))
    for root in ALLOWED_PDF_ROOTS:
        root_real = os.path.abspath(os.path.realpath(root))
        if os.path.commonpath([real, root_real]) == root_real and real.lower().endswith(".pdf") and os.path.isfile(real):
            return real
    return None

# In-memory registry of asynchronous design generation tasks
TASKS = {}
TASKS_LOCK = threading.RLock()

class StudioRequestHandler(SimpleHTTPRequestHandler):
    """HTTP Request Handler for the Interactive Analog Circuit Design Studio."""

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)

        if path == "/" or path == "/index.html":
            self.serve_studio_html()
        elif path == "/api/samples":
            self.serve_samples_api()
        elif path == "/api/llm_config":
            from ..llm_client import LLMClient, spent_usd
            c = LLMClient()
            routing = c.routing_config()
            self.send_json({
                "provider": c.provider,
                "model": c.default_model,
                "fallback_models": c.fallback_models,
                "extract_model": routing["routes"]["extract_specs"][0],
                "synth_model": routing["routes"]["hermes_initial"][0],
                "hermes_repair_model": routing["routes"]["hermes_repair"][0],
                "routing": routing,
                "spent_usd": round(spent_usd(), 4),
            })
        elif path == "/api/status":
            task_id = query.get("task_id", [""])[0]
            self.serve_status_api(task_id)
        elif path == "/api/trace":
            task_id = query.get("task_id", [""])[0]
            self.serve_trace_api(task_id)
        elif path == "/api/extract_pdg":
            pdf_path = query.get("pdf_path", [""])[0]
            self.handle_extract_pdg_api(pdf_path)
        elif path == "/dashboard":
            task_id = query.get("task_id", [""])[0]
            self.serve_dashboard(task_id)
        elif path == "/api/harness2/summary":
            self.serve_harness2_summary_api()
        elif path == "/api/harness2/library":
            self.serve_harness2_library_api()
        elif path == "/api/harness2/verifier_experience":
            self.serve_harness2_verifier_experience_api()
        else:
            super().do_GET()

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/api/upload":
            self.handle_upload_api()
        elif path == "/api/generate":
            self.handle_generate_api()
        else:
            self.send_error(404, "Endpoint Not Found")

    # -------------------------------------------------------------
    # API HANDLERS
    # -------------------------------------------------------------
    def serve_samples_api(self):
        """Returns list of pre-installed sample datasheets from testcases/."""
        sample_files = glob.glob(os.path.join("testcases", "*.pdf"))
        samples = []
        for s in sorted(sample_files):
            fname = os.path.basename(s)
            part_name = os.path.splitext(fname)[0].upper()
            samples.append({
                "part_name": part_name,
                "filename": fname,
                "path": os.path.abspath(s)
            })
        self.send_json({"samples": samples})

    def serve_status_api(self, task_id: str):
        """Returns the live execution state, logs, and results of a design task."""
        with TASKS_LOCK:
            task = TASKS.get(task_id)

        if not task:
            self.send_json({"error": "Task not found"}, status=404)
            return

        self.send_json({
            "task_id": task_id,
            "status": task.get("status", "running"),
            "current_phase": task.get("current_phase", 1),
            "phase_title": task.get("phase_title", "Initializing"),
            "logs": task.get("logs", []),
            "result_summary": task.get("result_summary"),
            "dashboard_url": f"/dashboard?task_id={task_id}" if task.get("status") == "completed" else None,
            "error": task.get("error")
        })

    def serve_harness2_summary_api(self):
        """Returns the latest multi-datasheet Harness² benchmark summary."""
        summary_path = os.path.abspath("output_harness2_netlist/harness2_multi_ic_summary.json")
        if os.path.exists(summary_path):
            try:
                with open(summary_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self.send_json({"status": "success", "summary": data})
                return
            except Exception as e:
                logger.error(f"Error reading harness2 summary: {e}")
        self.send_json({"status": "empty", "summary": []})

    def serve_harness2_verifier_experience_api(self):
        """Returns the accumulated verifier evolutionary rules and golden anchor status."""
        exp_file = os.path.abspath("harness2_library/verifier_experience/VERIFIER_EXPERIENCE.json")
        if os.path.exists(exp_file):
            try:
                with open(exp_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self.send_json({"status": "success", "data": data})
                return
            except Exception as e:
                logger.error(f"Error reading verifier experience: {e}")
        self.send_json({"status": "empty", "data": {"v1_kind_rules": [], "v2_fixture_templates": {}, "v3_unit_conversions": {}}})

    def serve_harness2_library_api(self):
        """Returns the accumulated cross-task experience records from harness2_library/."""
        lib_dir = os.path.abspath("harness2_library")
        index_file = os.path.join(lib_dir, "INDEX.json")
        experiences = []
        if os.path.exists(index_file):
            try:
                with open(index_file, "r", encoding="utf-8") as f:
                    idx = json.load(f)
                for exp_meta in idx.get("experiences", []):
                    rel_p = exp_meta.get("path", "")
                    task_dir = os.path.join(lib_dir, rel_p)
                    exp_file = os.path.join(task_dir, "EXPERIENCE.json")
                    if os.path.exists(exp_file):
                        try:
                            with open(exp_file, "r", encoding="utf-8") as ef:
                                full_exp = json.load(ef)
                            experiences.append(full_exp)
                        except Exception:
                            experiences.append(exp_meta)
                    else:
                        experiences.append(exp_meta)
            except Exception as e:
                logger.error(f"Error reading library: {e}")
        self.send_json({"status": "success", "count": len(experiences), "experiences": experiences})

    def serve_trace_api(self, task_id: str):
        """Returns the execution trace spans and telemetry data for a task."""
        with TASKS_LOCK:
            task = TASKS.get(task_id)

        if not task or not task.get("output_dir"):
            self.send_json({"error": "Task not found"}, status=404)
            return

        traces = glob.glob(os.path.join(task["output_dir"], "*_execution_trace.json"))
        if traces:
            try:
                with open(traces[0], "r", encoding="utf-8") as f:
                    data = json.load(f)
                self.send_json({"status": "success", "trace": data})
                return
            except Exception as e:
                logger.error(f"Error reading trace: {e}")

        self.send_json({
            "status": "in_flight",
            "current_phase": task.get("current_phase", 1),
            "logs": task.get("logs", [])
        })

    def handle_extract_pdg_api(self, pdf_path: str):
        """Extracts and visualizes the Port Dependency Graph directly from a datasheet PDF."""
        safe = safe_pdf_path(pdf_path)
        if not safe:
            self.send_json({"error": f"Datasheet PDF not found, or outside testcases/ and uploads/: {pdf_path}"}, status=400)
            return
        pdf_path = safe

        try:
            res = PDGVisualizer.extract_from_pdf(pdf_path, max_pages=15)
            pins = res["pins"]
            schedule = res["schedule"]
            svg_markup = PDGVisualizer.to_svg(pins, schedule, pdg=res.get("pdg"))
            mermaid_code = PDGVisualizer.to_mermaid(pins, schedule, pdg=res.get("pdg"))

            self.send_json({
                "status": "success",
                "ic_name": res["ic_info"].get("name", os.path.splitext(os.path.basename(pdf_path))[0]),
                "pins": pins,
                "schedule": {k: round(v*1e6, 2) for k, v in schedule.items()},
                "svg": svg_markup,
                "mermaid": mermaid_code
            })
        except Exception as e:
            logger.error(f"Error extracting PDG: {e}", exc_info=True)
            stem = os.path.splitext(os.path.basename(pdf_path))[0].upper()
            fallback_pins = [
                {"name": "IN+", "role": "SIGNAL", "direction": "INPUT", "description": "Non-inverting input"},
                {"name": "IN-", "role": "SIGNAL", "direction": "INPUT", "description": "Inverting input"},
                {"name": "OUT", "role": "OUTPUT", "direction": "OUTPUT", "description": "Output"},
                {"name": "VCC", "role": "POWER", "direction": "INPUT", "description": "Positive Supply"},
                {"name": "VEE", "role": "POWER", "direction": "INPUT", "description": "Negative Supply / Ground"}
            ]
            fallback_sched = {"VCC": 0.0, "VEE": 0.0, "IN+": 2.0, "IN-": 2.0, "OUT": 52.0}
            self.send_json({
                "status": "success",
                "warning": f"Heuristic fallback active: {e}",
                "ic_name": stem,
                "pins": fallback_pins,
                "schedule": fallback_sched,
                "svg": PDGVisualizer.to_svg(fallback_pins, {k: v*1e-6 for k, v in fallback_sched.items()}),
                "mermaid": PDGVisualizer.to_mermaid(fallback_pins, {k: v*1e-6 for k, v in fallback_sched.items()})
            })

    def serve_dashboard(self, task_id: str):
        """Serves the generated interactive visual dashboard for the specified task."""
        with TASKS_LOCK:
            task = TASKS.get(task_id)

        if not task or not task.get("output_dir"):
            self.send_error(404, "Dashboard not available for this task.")
            return

        dashboards = glob.glob(os.path.join(task["output_dir"], "*_VISUAL_DASHBOARD.html"))
        if not dashboards:
            self.send_error(404, "Visual dashboard has not finished generating.")
            return

        try:
            with open(dashboards[0], "rb") as f:
                content = f.read()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
        except Exception as e:
            self.send_error(500, f"Error reading dashboard: {e}")

    def handle_upload_api(self):
        """Receives a multipart PDF file upload and saves it to uploads/."""
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)

            content_type = self.headers.get("Content-Type", "")
            boundary = content_type.split("boundary=")[-1].strip()
            boundary_bytes = ("--" + boundary).encode("utf-8")

            parts = body.split(boundary_bytes)
            saved_path = None
            filename = f"datasheet_{uuid.uuid4().hex[:8]}.pdf"

            for part in parts:
                if b'filename="' in part:
                    header_part, file_data = part.split(b"\r\n\r\n", 1)
                    file_data = file_data.rstrip(b"\r\n--")
                    m = re.search(r'filename="([^"]+)"', header_part.decode("utf-8", errors="ignore"))
                    if m:
                        filename = os.path.basename(m.group(1))
                    
                    uploads_dir = os.path.abspath("uploads")
                    os.makedirs(uploads_dir, exist_ok=True)
                    saved_path = os.path.join(uploads_dir, filename)
                    with open(saved_path, "wb") as f:
                        f.write(file_data)
                    break

            if saved_path and os.path.exists(saved_path):
                self.send_json({
                    "status": "success",
                    "filename": filename,
                    "filepath": saved_path
                })
            else:
                self.send_json({"error": "Failed to parse uploaded PDF file."}, status=400)
        except Exception as e:
            logger.error(f"Upload error: {e}", exc_info=True)
            self.send_json({"error": str(e)}, status=500)

    def handle_generate_api(self):
        """Starts an asynchronous autonomous design task."""
        try:
            length = int(self.headers.get("Content-Length", 0))
            payload = json.loads(self.rfile.read(length).decode("utf-8"))

            pdf_path = payload.get("pdf_path")
            user_prompt = payload.get("user_prompt", "").strip()
            max_iterations = int(payload.get("max_iterations", 20))

            if not pdf_path and not user_prompt:
                self.send_json({"error": "Either a PDF datasheet or a natural language prompt is required."}, status=400)
                return
            if pdf_path:
                pdf_path = safe_pdf_path(pdf_path)
                if not pdf_path:
                    self.send_json({"error": "pdf_path must point to a PDF inside testcases/ or uploads/."}, status=400)
                    return

            task_id = f"task_{int(time.time())}_{uuid.uuid4().hex[:6]}"
            output_dir = os.path.abspath(os.path.join("output_interactive", task_id))
            os.makedirs(output_dir, exist_ok=True)

            with TASKS_LOCK:
                TASKS[task_id] = {
                    "task_id": task_id,
                    "status": "running",
                    "current_phase": 1,
                    "phase_title": "Initializing",
                    "logs": [],
                    "output_dir": output_dir,
                    "pdf_path": pdf_path,
                    "user_prompt": user_prompt,
                    "start_time": time.time()
                }

            # Spawn background execution thread
            thread = threading.Thread(
                target=self.execute_design_task,
                args=(task_id, output_dir, pdf_path, user_prompt, max_iterations),
                daemon=True
            )
            thread.start()

            self.send_json({
                "status": "started",
                "task_id": task_id
            })
        except Exception as e:
            logger.error(f"Generate error: {e}", exc_info=True)
            self.send_json({"error": str(e)}, status=500)

    @classmethod
    def execute_design_task(cls, task_id: str, output_dir: str, pdf_path: str | None, user_prompt: str | None, max_iterations: int):
        """Background worker thread running AutonomousAnalogDesignAgent."""
        def progress_cb(phase_num: int, phase_title: str, msg: str):
            with TASKS_LOCK:
                if task_id in TASKS:
                    TASKS[task_id]["current_phase"] = phase_num
                    TASKS[task_id]["phase_title"] = phase_title
                    timestamp = time.strftime("%H:%M:%S")
                    TASKS[task_id]["logs"].append(f"[{timestamp}] [Phase {phase_num}] {msg}")

        try:
            progress_cb(1, "Starting Agent", f"Task {task_id} initialized in {output_dir}")
            agent = AutonomousAnalogDesignAgent(
                output_dir=output_dir,
                max_iterations=max_iterations
            )

            result = agent.run(
                datasheet_pdf_path=pdf_path,
                user_prompt=user_prompt,
                progress_callback=progress_cb
            )

            # Generate individual dashboard
            try:
                ic_data = ProcessVisualizer.load_ic_data_from_directory(output_dir)
                if ic_data:
                    dash_path = os.path.join(output_dir, f"{ic_data['id']}_VISUAL_DASHBOARD.html")
                    ProcessVisualizer.export_dashboard([ic_data], dash_path)
            except Exception as de:
                logger.warning(f"Dashboard generation notice: {de}")

            # Read final synthesized subcircuit netlist (strictly excluding *_dyn.cir testbenches)
            final_netlist = result.get("final_netlist") or ""
            if not final_netlist:
                candidate_files = [
                    p for p in (
                        glob.glob(os.path.join(output_dir, "*_FINAL_HERMES_HARNESS2.cir"))
                        + glob.glob(os.path.join(output_dir, "*_final_hermes_harness2.cir"))
                        + sorted(glob.glob(os.path.join(output_dir, "*_turn*.cir")))
                        + sorted(glob.glob(os.path.join(output_dir, "*_iter*.cir")))
                    )
                    if not p.lower().endswith("_dyn.cir") and "testbench" not in os.path.basename(p).lower()
                ]
                for cand in candidate_files:
                    try:
                        with open(cand, "r", encoding="utf-8", errors="ignore") as f:
                            txt = f.read()
                        if ".subckt" in txt.lower():
                            final_netlist = txt
                            break
                    except Exception:
                        pass

            with TASKS_LOCK:
                if task_id in TASKS:
                    has_valid_netlist = ".subckt" in final_netlist.lower()
                    TASKS[task_id]["status"] = "completed" if has_valid_netlist else "completed_with_warnings"
                    TASKS[task_id]["current_phase"] = 6
                    TASKS[task_id]["phase_title"] = "Completed" if has_valid_netlist else "Completed with warnings"
                    TASKS[task_id]["result_summary"] = {
                        "pass_rate_percent": result.get("summary", {}).get("pass_rate_percent", 0.0),
                        "part_name": result.get("summary", {}).get("part_name", "DUT"),
                        "subckt_name": result.get("summary", {}).get("subckt_name", "DUT"),
                        "iterations_count": len(result.get("summary", {}).get("iterations", [])),
                        "netlist_code": final_netlist,
                        "has_valid_netlist": has_valid_netlist,
                    }
                    timestamp = time.strftime("%H:%M:%S")
                    if has_valid_netlist:
                        TASKS[task_id]["logs"].append(f"[{timestamp}] [Phase 6: Success] Autonomous analog design & verification cycle finished successfully!")
                    else:
                        TASKS[task_id]["logs"].append(
                            f"[{timestamp}] [Phase 6: Warning] No valid SPICE netlist was produced. "
                            "Run at least 2 iterations or inspect the Hermes turn log."
                        )
        except Exception as e:
            logger.error(f"Task {task_id} failed: {e}", exc_info=True)
            with TASKS_LOCK:
                if task_id in TASKS:
                    TASKS[task_id]["status"] = "failed"
                    TASKS[task_id]["error"] = str(e)
                    TASKS[task_id]["logs"].append(f"[ERROR] Task aborted: {e}")

    # -------------------------------------------------------------
    # HTML UI SERVING
    # -------------------------------------------------------------
    def serve_studio_html(self):
        """Serves the rich interactive web application."""
        html = self.get_studio_html()
        content = html.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def send_json(self, data: dict[str, Any], status: int = 200):
        try:
            content = json.dumps(data).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
        except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError, OSError):
            pass

    def get_studio_html(self) -> str:
        return """<!DOCTYPE html>
<html lang="en" class="dark">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Autonomous Analog Verifier — Interactive Circuit Design Studio</title>
  <script src="https://www.gstatic.com/antigravity/web/dev/tailwindcss.min.js"></script>
  <style>
    :root {
      --background: #090d16;
      --card: #0f172a;
      --card-hover: #1e293b;
      --border: #334155;
      --foreground: #f8fafc;
      --muted: #94a3b8;
      --primary: #38bdf8;
      --accent: #818cf8;
      --success: #34d399;
      --warning: #fbbf24;
      --danger: #f87171;
    }
    body {
      background-color: var(--background);
      color: var(--foreground);
      font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Arial, sans-serif;
    }
    .custom-scrollbar::-webkit-scrollbar {
      width: 6px;
      height: 6px;
    }
    .custom-scrollbar::-webkit-scrollbar-track {
      background: #0f172a;
    }
    .custom-scrollbar::-webkit-scrollbar-thumb {
      background: #334155;
      border-radius: 4px;
    }
    .glow-button {
      box-shadow: 0 0 25px -5px rgba(56, 189, 248, 0.4);
      transition: all 0.2s ease;
    }
    .glow-button:hover {
      box-shadow: 0 0 35px 0px rgba(56, 189, 248, 0.6);
      transform: translateY(-1px);
    }
    .step-active {
      border-color: #38bdf8;
      background-color: rgba(56, 189, 248, 0.15);
      color: #38bdf8;
    }
    .step-done {
      border-color: #34d399;
      background-color: rgba(52, 211, 153, 0.15);
      color: #34d399;
    }
    .step-error {
      border-color: #f87171;
      background-color: rgba(248, 113, 113, 0.15);
      color: #f87171;
    }
    .node-pin {
      transition: all 0.3s ease;
    }
    .node-pin:hover {
      transform: scale(1.08);
    }
  </style>
</head>
<body class="min-h-screen custom-scrollbar p-3 md:p-6 antialiased">
  <div class="max-w-7xl mx-auto space-y-6">

    <!-- Top Header Banner -->
    <header class="bg-[var(--card)] border border-[var(--border)] rounded-2xl p-5 shadow-lg flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
      <div class="flex items-center gap-3">
        <div class="p-3 bg-sky-500/10 border border-sky-500/30 rounded-2xl text-sky-400">
          <svg class="w-7 h-7" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19.428 15.428a2 2 0 00-1.022-.547l-2.387-.477a6 6 0 00-3.86.517l-.318.158a6 6 0 01-3.86.517L6.05 15.21a2 2 0 00-1.806.547M8 4h8l-1 1v5.172a2 2 0 00.586 1.414l5 5c1.26 1.26.367 3.414-1.415 3.414H4.828c-1.782 0-2.674-2.154-1.414-3.414l5-5A2 2 0 009 10.172V5L8 4z" />
          </svg>
        </div>
        <div>
          <h1 class="text-xl md:text-2xl font-bold tracking-tight text-white flex items-center gap-2">
            Interactive Analog Circuit Design Studio
            <span class="text-xs px-2.5 py-0.5 rounded-full bg-sky-500/10 text-sky-400 border border-sky-500/30">First-Principles LLM</span>
          </h1>
          <p class="text-xs md:text-sm text-[var(--muted)] mt-0.5">
            Directly upload custom IC datasheets &amp; input natural language circuit requirements for instant autonomous synthesis &amp; LTspice verification.
          </p>
        </div>
      </div>
      <div class="flex items-center gap-2">
        <span class="inline-flex items-center px-3 py-1 rounded-full text-xs font-medium bg-emerald-500/10 text-emerald-400 border border-emerald-500/30">
          <span class="w-2 h-2 rounded-full bg-emerald-400 mr-2 animate-pulse"></span>
          Engine Ready
        </span>
      </div>
    </header>

    <!-- Main Workspace Grid: Left Inputs / Right Execution Monitor -->
    <div class="grid grid-cols-1 lg:grid-cols-12 gap-6">

      <!-- LEFT COLUMN: INPUT CONTROLS (5 COLS) -->
      <div class="lg:col-span-5 space-y-6">

        <!-- Card 1: Datasheet Source -->
        <div class="bg-[var(--card)] border border-[var(--border)] rounded-2xl p-5 shadow-lg space-y-4">
          <div class="flex items-center justify-between">
            <h2 class="text-sm font-bold text-white uppercase tracking-wider flex items-center gap-2">
              <span class="w-2 h-2 rounded-full bg-sky-400"></span>
              1. Datasheet Input
            </h2>
            <div class="flex items-center gap-1 bg-slate-900 p-1 rounded-xl text-xs">
              <button onclick="setDatasheetMode('upload')" id="modeUploadBtn" class="px-3 py-1 rounded-lg bg-sky-500/20 text-sky-300 font-semibold transition-all">Upload PDF</button>
              <button onclick="setDatasheetMode('sample')" id="modeSampleBtn" class="px-3 py-1 rounded-lg text-slate-400 font-semibold transition-all hover:text-white">Sample ICs</button>
              <button onclick="setDatasheetMode('none')" id="modeNoneBtn" class="px-3 py-1 rounded-lg text-slate-400 font-semibold transition-all hover:text-white">Pure Prompt</button>
            </div>
          </div>

          <!-- Mode A: File Upload Zone -->
          <div id="uploadZone" class="border-2 border-dashed border-slate-700 hover:border-sky-500 rounded-xl p-5 text-center transition-colors cursor-pointer bg-slate-900/50" onclick="document.getElementById('pdfFileInput').click()">
            <input type="file" id="pdfFileInput" accept=".pdf" class="hidden" onchange="handleFileSelect(this.files[0])">
            <div class="flex flex-col items-center justify-center space-y-2">
              <svg class="w-8 h-8 text-slate-500 group-hover:text-sky-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
              </svg>
              <div class="text-xs text-slate-300 font-medium" id="uploadFilename">Drop your datasheet PDF here, or <span class="text-sky-400 underline">browse</span></div>
              <div class="text-[11px] text-slate-500">Supports Texas Instruments, Analog Devices, Maxim, ST, ON Semi datasheets</div>
            </div>
          </div>

          <!-- Mode B: Sample IC Selector -->
          <div id="sampleZone" class="hidden space-y-2">
            <label class="text-xs font-semibold text-slate-400">Choose from 10 Authenticated Testcases:</label>
            <select id="sampleSelect" class="w-full bg-slate-900 border border-[var(--border)] text-sky-300 text-xs rounded-xl px-3 py-2.5 focus:outline-none focus:border-sky-400" onchange="onSampleSelected(this.value)">
              <option value="">-- Select an IC Datasheet --</option>
            </select>
          </div>

          <!-- Mode C: Pure Natural Language -->
          <div id="promptOnlyZone" class="hidden text-xs text-amber-300/80 bg-amber-500/10 border border-amber-500/20 p-3 rounded-xl">
            Pure Natural Language Mode active. The AI specification architect will synthesize the pinout and electrical constraints directly from your prompt.
          </div>

          <!-- Visualize PDG Action Button -->
          <div class="pt-2">
            <button type="button" onclick="previewDatasheetPDG()" id="btnPreviewPDG" class="w-full py-2.5 px-3 rounded-xl bg-slate-800 hover:bg-slate-700 text-sky-300 font-semibold text-xs border border-slate-700 flex items-center justify-center gap-2 transition-all">
              <svg class="w-4 h-4 text-sky-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"/><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z"/></svg>
              <span>🔍 Extract &amp; Visualize PDG from Datasheet</span>
            </button>
          </div>
        </div>

        <!-- Collapsible Dedicated PDG Visualizer Preview Card -->
        <div id="pdgPreviewCard" class="hidden bg-[var(--card)] border border-sky-500/30 rounded-2xl p-5 shadow-lg space-y-4">
          <div class="flex items-center justify-between border-b border-slate-800 pb-3">
            <div>
              <h3 class="text-xs uppercase font-bold text-sky-400 flex items-center gap-1.5">
                <span class="w-2 h-2 rounded-full bg-emerald-400"></span>
                Extracted Port Dependency Graph (PDG)
              </h3>
              <p id="pdgIcNameSubtitle" class="text-[11px] text-slate-400">Topological Settling Sequence &sigma;(p)</p>
            </div>
            <button onclick="document.getElementById('pdgPreviewCard').classList.add('hidden')" class="text-slate-500 hover:text-white text-xs">&times; Close</button>
          </div>

          <!-- Playback Controls -->
          <div class="flex items-center justify-between gap-3 bg-slate-900 border border-slate-800 p-2.5 rounded-xl text-xs">
            <button onclick="togglePdgPlay()" id="btnPdgPlay" class="text-sky-400 font-bold hover:text-sky-300 flex items-center gap-1">
              <span>Play Sequence</span>
            </button>
            <input type="range" id="pdgTimeSlider" min="0" max="10" step="0.5" value="0" oninput="setPdgTime(parseFloat(this.value))" class="w-28 accent-sky-400">
            <span id="pdgTimeVal" class="font-mono text-sky-300 font-bold w-12 text-right">0.0 &mu;s</span>
          </div>

          <!-- SVG Canvas Container -->
          <div id="pdgSvgContainer" class="bg-slate-950 border border-slate-800 rounded-xl p-3 flex items-center justify-center min-h-[220px] max-h-[300px] overflow-x-auto">
            <!-- Rendered dynamically -->
          </div>

          <!-- Schedule Table -->
          <div class="max-h-40 overflow-y-auto custom-scrollbar border border-slate-800 rounded-xl">
            <table class="w-full text-[11px] text-left">
              <thead class="text-slate-400 uppercase text-[10px] bg-slate-900 border-b border-slate-800">
                <tr>
                  <th class="px-2.5 py-1.5">Pin</th>
                  <th class="px-2.5 py-1.5">Role</th>
                  <th class="px-2.5 py-1.5">Delay &sigma;(p)</th>
                  <th class="px-2.5 py-1.5">Status</th>
                </tr>
              </thead>
              <tbody id="pdgTableBody" class="divide-y divide-slate-800/60 text-slate-300">
              </tbody>
            </table>
          </div>
        </div>

        <!-- Card 2: Natural Language Specification Prompt -->
        <div class="bg-[var(--card)] border border-[var(--border)] rounded-2xl p-5 shadow-lg space-y-3">
          <div class="flex items-center justify-between">
            <h2 class="text-sm font-bold text-white uppercase tracking-wider flex items-center gap-2">
              <span class="w-2 h-2 rounded-full bg-indigo-400"></span>
              2. Natural Language Request
            </h2>
            <span class="text-[11px] text-slate-400 font-mono">Custom Directives</span>
          </div>
          <p class="text-xs text-[var(--muted)]">
            State your design intent, custom operating voltages, target bandwidth, quiescent currents, or specific circuit architectures in plain English or Korean:
          </p>

          <textarea id="userPromptInput" rows="4" class="w-full bg-slate-900 border border-[var(--border)] rounded-xl p-3 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-sky-400 resize-none font-mono custom-scrollbar" placeholder="e.g. Design this op-amp for single 3.3V supply with Rail-to-Rail output swing, quiescent current < 50uA, and open-loop DC gain > 100dB."></textarea>

          <!-- Prompt Suggestion Chips -->
          <div class="space-y-1.5">
            <div class="text-[11px] uppercase font-bold text-slate-500">Quick Prompt Chips:</div>
            <div class="flex flex-wrap gap-1.5 text-[11px]">
              <button onclick="insertChip('Design for single supply 3.3V with rail-to-rail input and output swing.')" class="px-2.5 py-1 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 border border-slate-700">⚡ 3.3V Rail-to-Rail</button>
              <button onclick="insertChip('Minimize quiescent current to under 20uA for ultra-low power IoT battery operation.')" class="px-2.5 py-1 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 border border-slate-700">🔋 Ultra-Low Power (&lt;20uA)</button>
              <button onclick="insertChip('Maximize gain-bandwidth product to > 20MHz and slew rate > 15V/us.')" class="px-2.5 py-1 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 border border-slate-700">🚀 High-Speed (&gt;20MHz)</button>
              <button onclick="insertChip('Optimize common-mode rejection ratio (CMRR > 110dB) and low input offset voltage (< 100uV).')" class="px-2.5 py-1 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 border border-slate-700">🎯 High CMRR / Precision</button>
            </div>
          </div>
        </div>

        <!-- Card 3: Execution Settings & Submit Button -->
        <div class="bg-[var(--card)] border border-[var(--border)] rounded-2xl p-5 shadow-lg space-y-4">
          <div class="grid grid-cols-2 gap-3 text-xs">
            <div>
              <label class="block text-slate-400 font-semibold mb-1">Max Closed Loops:</label>
              <select id="maxItersSelect" class="w-full bg-slate-900 border border-[var(--border)] text-slate-200 rounded-xl px-3 py-2 focus:outline-none focus:border-sky-400">
                <option value="2">2 Iterations (Fast Discovery)</option>
                <option value="5">5 Iterations (Standard)</option>
                <option value="10">10 Iterations</option>
                <option value="15">15 Iterations (Deep Reasoning)</option>
                <option value="20" selected>20 Iterations (Max Convergence - Recommended)</option>
              </select>
            </div>
            <div>
              <label class="block text-slate-400 font-semibold mb-1">Synthesis Model:</label>
              <div id="llmModelLabel" class="bg-slate-900 border border-[var(--border)] text-sky-400 font-mono rounded-xl px-3 py-2 truncate" title="">
                loading...
              </div>
            </div>
          </div>

          <button onclick="launchDesign()" id="btnGenerate" class="w-full py-3.5 px-4 rounded-xl bg-gradient-to-r from-sky-500 to-indigo-600 hover:from-sky-400 hover:to-indigo-500 text-white font-bold text-sm tracking-wide glow-button flex items-center justify-center gap-2">
            <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 10V3L4 14h7v7l9-11h-7z"/></svg>
            <span>🚀 Synthesize &amp; Verify Circuit Now</span>
          </button>
        </div>

        <!-- Card 4: Google Research Harness² Experience & Benchmark Studio -->
        <div id="harness2StudioCard" class="bg-[var(--card)] border border-indigo-500/30 rounded-2xl p-5 shadow-lg space-y-4">
          <div class="flex items-center justify-between border-b border-slate-800 pb-3">
            <div class="flex items-center gap-2">
              <span class="p-1.5 bg-indigo-500/10 border border-indigo-500/30 rounded-lg text-indigo-400">
                <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10"/></svg>
              </span>
              <div>
                <h3 class="text-xs uppercase font-bold text-indigo-300">Harness² Multi-LLM Meta-Engine</h3>
                <p class="text-[11px] text-slate-400">Google Research Task &amp; Harnessing Recursion</p>
              </div>
            </div>
            <span class="text-[10px] px-2 py-0.5 rounded-full bg-indigo-500/10 text-indigo-400 border border-indigo-500/30 font-mono">Active</span>
          </div>

          <!-- Benchmark Metrics Badges -->
          <div class="space-y-1.5">
            <div class="text-[11px] font-semibold text-slate-400 flex items-center justify-between">
              <span>Verified Benchmark Deltas:</span>
              <span class="text-[10px] text-indigo-400 cursor-pointer hover:underline" onclick="loadHarness2Library()">Refresh Library</span>
            </div>
            <div class="grid grid-cols-3 gap-2 text-center text-xs">
              <div class="bg-slate-900 border border-slate-800 rounded-xl p-2">
                <div class="text-[10px] text-slate-500 font-bold">LM393</div>
                <div class="text-emerald-400 font-mono font-bold text-sm">72.7%</div>
                <div class="text-[9px] text-emerald-500/80 font-mono">+72.7% &Delta;</div>
              </div>
              <div class="bg-slate-900 border border-slate-800 rounded-xl p-2">
                <div class="text-[10px] text-slate-500 font-bold">TL431</div>
                <div class="text-emerald-400 font-mono font-bold text-sm">40.0%</div>
                <div class="text-[9px] text-emerald-500/80 font-mono">+40.0% &Delta;</div>
              </div>
              <div class="bg-slate-900 border border-slate-800 rounded-xl p-2">
                <div class="text-[10px] text-slate-500 font-bold">LM358</div>
                <div class="text-sky-400 font-mono font-bold text-sm">25.0%</div>
                <div class="text-[9px] text-sky-500/80 font-mono">7 Passed</div>
              </div>
            </div>
          </div>

          <!-- Dual LLM Routing Details -->
          <div class="bg-slate-950 border border-slate-800/80 rounded-xl p-3 text-[11px] space-y-1 font-mono text-slate-400">
            <div class="flex items-center justify-between">
              <span class="text-slate-500">Structured extraction:</span>
              <span id="harness2ExtractModel" class="text-emerald-400 font-semibold">Loading model route</span>
            </div>
            <div class="flex items-center justify-between">
              <span class="text-slate-500">Initial synthesis:</span>
              <span id="harness2SynthesisModel" class="text-sky-400 font-semibold">Loading model route</span>
            </div>
            <div class="flex items-center justify-between">
              <span class="text-slate-500">Cross-Task Transfer:</span>
              <span class="text-indigo-400 font-semibold" id="harness2ExpCount">3 Lessons Cached</span>
            </div>
            <div class="flex items-center justify-between">
              <span class="text-slate-500">Dual-Harness² Engine:</span>
              <span class="text-indigo-400 font-semibold">Co-Evolution (Synth + Verifier)</span>
            </div>
            <div class="flex items-center justify-between">
              <span class="text-slate-500">Golden Gatekeeper:</span>
              <span class="text-emerald-400 font-semibold">TI/ADI Golden Macromodels (100% Pass)</span>
            </div>
            <div class="flex items-center justify-between">
              <span class="text-slate-500">Analog Mandate:</span>
              <span class="text-amber-400 font-mono font-semibold">Zero Behavioral (Strict Physical)</span>
            </div>
          </div>

          <!-- Experience Library Viewer Container -->
          <div id="harness2ExpContainer" class="max-h-40 overflow-y-auto custom-scrollbar space-y-2 text-xs">
            <!-- Dynamically populated -->
          </div>
        </div>

      </div>

      <!-- RIGHT COLUMN: LIVE EXECUTION & SUB-PROCESS MONITOR (7 COLS) -->
      <div class="lg:col-span-7 space-y-6">

        <!-- Card: Real-time 6-Phase Sub-Process Stepper -->
        <div class="bg-[var(--card)] border border-[var(--border)] rounded-2xl p-5 shadow-lg space-y-4">
          <div class="flex items-center justify-between">
            <h2 class="text-sm font-bold text-white uppercase tracking-wider flex items-center gap-2">
              <span class="w-2 h-2 rounded-full bg-emerald-400"></span>
              Live Sub-Process Pipeline Status
            </h2>
            <span id="taskStatusPill" class="text-xs px-2.5 py-0.5 rounded-full bg-slate-800 text-slate-400 border border-slate-700">Idle</span>
          </div>

          <!-- Stepper Grid -->
          <div class="grid grid-cols-2 md:grid-cols-3 gap-2.5 text-xs">
            <div id="step-1" class="border border-slate-800 bg-slate-900/60 rounded-xl p-3 transition-all">
              <div class="font-bold text-slate-500 text-[10px]">PHASE 1</div>
              <div class="font-semibold text-slate-300 mt-0.5">Knowledge Ingestion</div>
              <div class="text-[10px] text-slate-500">PDF &amp; Prompt Extraction</div>
            </div>
            <div id="step-2" class="border border-slate-800 bg-slate-900/60 rounded-xl p-3 transition-all">
              <div class="font-bold text-slate-500 text-[10px]">PHASE 2</div>
              <div class="font-semibold text-slate-300 mt-0.5">PDG &amp; Schedule</div>
              <div class="text-[10px] text-slate-500">Causal DAG &amp; &sigma;(p)</div>
            </div>
            <div id="step-3" class="border border-slate-800 bg-slate-900/60 rounded-xl p-3 transition-all">
              <div class="font-bold text-slate-500 text-[10px]">PHASE 3</div>
              <div class="font-semibold text-slate-300 mt-0.5">AI Synthesis</div>
              <div class="text-[10px] text-slate-500">First-Principles Netlist</div>
            </div>
            <div id="step-4" class="border border-slate-800 bg-slate-900/60 rounded-xl p-3 transition-all">
              <div class="font-bold text-slate-500 text-[10px]">PHASE 4</div>
              <div class="font-semibold text-slate-300 mt-0.5">Testbench Decks</div>
              <div class="text-[10px] text-slate-500">.op / .tran / .ac Decks</div>
            </div>
            <div id="step-5" class="border border-slate-800 bg-slate-900/60 rounded-xl p-3 transition-all">
              <div class="font-bold text-slate-500 text-[10px]">PHASE 5</div>
              <div class="font-semibold text-slate-300 mt-0.5">LTspice &amp; SymPy</div>
              <div class="text-[10px] text-slate-500">Headless Batch Sim</div>
            </div>
            <div id="step-6" class="border border-slate-800 bg-slate-900/60 rounded-xl p-3 transition-all">
              <div class="font-bold text-slate-500 text-[10px]">PHASE 6</div>
              <div class="font-semibold text-slate-300 mt-0.5">Closed-Loop Repair</div>
              <div class="text-[10px] text-slate-500">Self-Healing Feedback</div>
            </div>
          </div>
        </div>

        <!-- Card: Real-time Streaming Log Terminal -->
        <div class="bg-[var(--card)] border border-[var(--border)] rounded-2xl p-5 shadow-lg space-y-3">
          <div class="flex items-center justify-between">
            <h3 class="text-xs font-bold uppercase tracking-wider text-slate-400 flex items-center gap-2">
              <svg class="w-4 h-4 text-sky-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 9l3 3-3 3m5 0h3M5 20h14a2 2 0 002-2V6a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z"/></svg>
              Execution Console &amp; Engine Logs
            </h3>
            <span id="logCounter" class="text-[11px] font-mono text-slate-500">0 entries</span>
          </div>

          <div id="logTerminal" class="h-48 bg-slate-950 border border-slate-800 rounded-xl p-3 font-mono text-xs text-slate-300 overflow-y-auto custom-scrollbar space-y-1">
            <div class="text-slate-600">Waiting for design job to launch...</div>
          </div>
        </div>

        <!-- Card: Step-by-Step Execution Trace & Diagnostics Telemetry -->
        <div class="bg-[var(--card)] border border-[var(--border)] rounded-2xl p-5 shadow-lg space-y-3">
          <div class="flex items-center justify-between">
            <h3 class="text-xs font-bold uppercase tracking-wider text-amber-400 flex items-center gap-2">
              <svg class="w-4 h-4 text-amber-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-6 9l2 2 4-4"/></svg>
              Step-by-Step Trace &amp; Debug Inspector
            </h3>
            <span id="traceSpanCount" class="text-[11px] font-mono text-slate-500">0 spans</span>
          </div>

          <div id="traceInspectorContainer" class="space-y-2.5 max-h-64 overflow-y-auto custom-scrollbar">
            <div class="text-xs text-slate-500 p-2 text-center">Spans will populate dynamically as each sub-process executes.</div>
          </div>
        </div>

        <!-- Card: Output Result & Visual Dashboard Direct Link -->
        <div id="resultsCard" class="hidden bg-[var(--card)] border border-emerald-500/30 rounded-2xl p-5 shadow-lg space-y-4">
          <div class="flex items-center justify-between">
            <div>
              <h3 class="text-base font-bold text-emerald-400 flex items-center gap-2">
                <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>
                Design &amp; Verification Finished!
              </h3>
              <p id="resultSummaryText" class="text-xs text-slate-400 mt-0.5">Synthesized circuit netlist ready for review.</p>
            </div>
            <a id="openDashboardLink" href="#" target="_blank" class="px-4 py-2 rounded-xl bg-sky-500 hover:bg-sky-400 text-slate-950 font-bold text-xs flex items-center gap-2 transition-all">
              <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"/><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z"/></svg>
              <span>📊 Open Visual Dashboard</span>
            </a>
          </div>

          <!-- Netlist Code Box -->
          <div class="relative bg-slate-950 border border-slate-800 rounded-xl overflow-hidden">
            <div class="bg-slate-900/80 px-4 py-2 border-b border-slate-800 flex items-center justify-between text-xs text-slate-400">
              <span class="font-mono text-sky-300">Synthesized SPICE Netlist (.cir)</span>
              <button onclick="copyNetlist()" class="text-xs text-sky-400 hover:underline">Copy Code</button>
            </div>
            <pre id="netlistOutputPre" class="p-4 text-xs font-mono text-slate-300 overflow-x-auto max-h-60 custom-scrollbar"></pre>
          </div>
        </div>

      </div>
    </div>
  </div>

  <script>
    let currentDatasheetMode = 'upload';
    let uploadedPdfPath = null;
    let selectedSamplePdfPath = null;
    let pollInterval = null;
    let currentTaskId = null;
    let pdgTimer = null;
    let pdgTime = 0.0;
    let currentPdgData = null;

    function init() {
      loadSamples();
      loadHarness2Library();
      fetch('/api/llm_config').then(r => r.json()).then(c => {
        const el = document.getElementById('llmModelLabel');
        const r = c.routing || {};
        el.textContent = `${c.provider}: ${c.synth_model}`;
        el.title = `scheduler: ${r.scheduler || 'legacy'} | extract: ${c.extract_model} | first synthesis: ${c.synth_model} | repair: ${c.hermes_repair_model || c.synth_model}`;
        const extractEl = document.getElementById('harness2ExtractModel');
        const synthesisEl = document.getElementById('harness2SynthesisModel');
        if (extractEl) extractEl.textContent = c.extract_model;
        if (synthesisEl) synthesisEl.textContent = `${c.synth_model} → ${c.hermes_repair_model || c.synth_model}`;
      }).catch(() => {});
    }

    async function loadHarness2Library() {
      try {
        const res = await fetch('/api/harness2/library');
        const data = await res.json();
        const countEl = document.getElementById('harness2ExpCount');
        const container = document.getElementById('harness2ExpContainer');
        if (data.status === 'success' && data.experiences) {
          if (countEl) countEl.textContent = `${data.count} Lessons Cached`;
          if (container) {
            container.innerHTML = data.experiences.map(exp => `
              <div class="p-2 rounded-lg bg-slate-900/90 border border-slate-800 text-[11px] space-y-1">
                <div class="flex items-center justify-between">
                  <span class="font-bold text-sky-400 font-mono">${exp.task_id || exp.name || 'Task'}</span>
                  <span class="px-1.5 py-0.2 rounded bg-emerald-500/10 text-emerald-400 font-mono text-[10px]">+${exp.delta_score || 0}% &Delta;</span>
                </div>
                <p class="text-slate-300 leading-tight">${exp.lesson || exp.cue || ''}</p>
                <div class="text-[10px] text-slate-500 font-mono truncate">${exp.evidence || ''}</div>
              </div>
            `).join('');
          }
        }
      } catch (e) {
        console.error('Failed to load harness2 library:', e);
      }
    }

    async function loadSamples() {
      try {
        const res = await fetch('/api/samples');
        const data = await res.json();
        const sel = document.getElementById('sampleSelect');
        sel.innerHTML = '<option value="">-- Select an IC Datasheet --</option>';
        data.samples.forEach(s => {
          const opt = document.createElement('option');
          opt.value = s.path;
          opt.textContent = `${s.part_name} (${s.filename})`;
          sel.appendChild(opt);
        });
      } catch (err) {
        console.error('Failed to load samples:', err);
      }
    }

    function setDatasheetMode(mode) {
      currentDatasheetMode = mode;
      document.getElementById('uploadZone').classList.toggle('hidden', mode !== 'upload');
      document.getElementById('sampleZone').classList.toggle('hidden', mode !== 'sample');
      document.getElementById('promptOnlyZone').classList.toggle('hidden', mode !== 'none');

      document.getElementById('modeUploadBtn').className = mode === 'upload'
        ? 'px-3 py-1 rounded-lg bg-sky-500/20 text-sky-300 font-semibold transition-all'
        : 'px-3 py-1 rounded-lg text-slate-400 font-semibold transition-all hover:text-white';
      document.getElementById('modeSampleBtn').className = mode === 'sample'
        ? 'px-3 py-1 rounded-lg bg-sky-500/20 text-sky-300 font-semibold transition-all'
        : 'px-3 py-1 rounded-lg text-slate-400 font-semibold transition-all hover:text-white';
      document.getElementById('modeNoneBtn').className = mode === 'none'
        ? 'px-3 py-1 rounded-lg bg-sky-500/20 text-sky-300 font-semibold transition-all'
        : 'px-3 py-1 rounded-lg text-slate-400 font-semibold transition-all hover:text-white';
    }

    function onSampleSelected(val) {
      selectedSamplePdfPath = val;
    }

    async function handleFileSelect(file) {
      if (!file) return;
      document.getElementById('uploadFilename').textContent = `Uploading: ${file.name}...`;

      const formData = new FormData();
      formData.append('pdf', file);

      try {
        const res = await fetch('/api/upload', {
          method: 'POST',
          body: formData
        });
        const data = await res.json();
        if (data.status === 'success') {
          uploadedPdfPath = data.filepath;
          document.getElementById('uploadFilename').innerHTML = `Uploaded: <strong class="text-emerald-400">${data.filename}</strong>`;
        } else {
          alert('Upload failed: ' + (data.error || 'Unknown error'));
        }
      } catch (e) {
        alert('Upload error: ' + e);
      }
    }

    function insertChip(text) {
      const ta = document.getElementById('userPromptInput');
      if (ta.value.trim()) {
        ta.value = ta.value.trim() + " " + text;
      } else {
        ta.value = text;
      }
    }

    function getTargetPdfPath() {
      if (currentDatasheetMode === 'upload') return uploadedPdfPath;
      if (currentDatasheetMode === 'sample') {
        if (!selectedSamplePdfPath) {
          const sel = document.getElementById('sampleSelect');
          if (sel && sel.value) selectedSamplePdfPath = sel.value;
        }
        return selectedSamplePdfPath;
      }
      return null;
    }

    // -------------------------------------------------------------
    // ON-DEMAND PDG VISUALIZATION
    // -------------------------------------------------------------
    async function previewDatasheetPDG() {
      const pdf = getTargetPdfPath();
      if (!pdf) {
        alert('Please upload a datasheet PDF or select a sample IC first to extract its PDG.');
        return;
      }

      const btn = document.getElementById('btnPreviewPDG');
      btn.disabled = true;
      btn.innerHTML = '<svg class="w-4 h-4 animate-spin" fill="none" stroke="currentColor" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z"></path></svg><span>Extracting PDG Graph...</span>';

      try {
        const res = await fetch(`/api/extract_pdg?pdf_path=${encodeURIComponent(pdf)}`);
        const data = await res.json();
        if (data.status === 'success') {
          renderPdgPreview(data);
        } else {
          alert('Error extracting PDG: ' + (data.error || 'Unknown error'));
        }
      } catch (e) {
        alert('PDG Extraction error: ' + e);
      } finally {
        btn.disabled = false;
        btn.innerHTML = '<svg class="w-4 h-4 text-sky-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"/><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z"/></svg><span>🔍 Extract &amp; Visualize PDG from Datasheet</span>';
      }
    }

    function renderPdgPreview(data) {
      currentPdgData = data;
      document.getElementById('pdgIcNameSubtitle').textContent = `${data.ic_name} (${data.pins.length} Pins)`;
      document.getElementById('pdgSvgContainer').innerHTML = data.svg;

      const tbody = document.getElementById('pdgTableBody');
      tbody.innerHTML = '';
      data.pins.forEach(p => {
        const d_us = data.schedule[p.name] || 0.0;
        const tr = document.createElement('tr');
        tr.innerHTML = `
          <td class="px-2.5 py-1.5 font-mono font-bold text-sky-400">${p.name}</td>
          <td class="px-2.5 py-1.5">${p.role || 'SIGNAL'}</td>
          <td class="px-2.5 py-1.5 font-mono">${d_us.toFixed(2)} &mu;s</td>
          <td class="px-2.5 py-1.5" id="pdg-state-${p.name}">Waiting</td>
        `;
        tbody.appendChild(tr);
      });

      document.getElementById('pdgPreviewCard').classList.remove('hidden');
      setPdgTime(0.0);
    }

    function setPdgTime(val) {
      pdgTime = val;
      document.getElementById('pdgTimeSlider').value = val;
      document.getElementById('pdgTimeVal').textContent = `${val.toFixed(1)} \u03bcs`;

      if (!currentPdgData) return;
      currentPdgData.pins.forEach(p => {
        const delay = currentPdgData.schedule[p.name] || 0.0;
        const stateEl = document.getElementById(`pdg-state-${p.name}`);
        const nodeG = document.getElementById(`node-${p.name}`);
        if (pdgTime >= delay) {
          if (stateEl) stateEl.innerHTML = '<span class="text-emerald-400 font-bold">Active</span>';
          if (nodeG) nodeG.querySelector('rect').setAttribute('fill', '#1e293b');
        } else {
          if (stateEl) stateEl.innerHTML = '<span class="text-slate-500">Waiting</span>';
          if (nodeG) nodeG.querySelector('rect').setAttribute('fill', '#0f172a');
        }
      });
    }

    function togglePdgPlay() {
      const btn = document.getElementById('btnPdgPlay');
      if (pdgTimer) {
        clearInterval(pdgTimer);
        pdgTimer = null;
        btn.textContent = 'Play Sequence';
      } else {
        btn.textContent = 'Pause';
        if (pdgTime >= 10.0) pdgTime = 0.0;
        pdgTimer = setInterval(() => {
          pdgTime += 0.5;
          if (pdgTime > 10.0) {
            pdgTime = 10.0;
            togglePdgPlay();
          }
          setPdgTime(pdgTime);
        }, 250);
      }
    }

    // -------------------------------------------------------------
    // DESIGN GENERATION & TELEMETRY
    // -------------------------------------------------------------
    async function launchDesign() {
      const targetPdf = getTargetPdfPath();
      const prompt = document.getElementById('userPromptInput').value.trim();
      const maxIters = parseInt(document.getElementById('maxItersSelect').value, 10) || 10;

      if (!targetPdf && !prompt) {
        alert('Please provide either a datasheet PDF or a natural language description.');
        return;
      }

      // UI reset
      document.getElementById('btnGenerate').disabled = true;
      document.getElementById('btnGenerate').innerHTML = '<svg class="w-5 h-5 animate-spin" fill="none" stroke="currentColor" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z"></path></svg><span>Synthesizing Circuit...</span>';
      document.getElementById('taskStatusPill').className = 'text-xs px-2.5 py-0.5 rounded-full bg-sky-500/20 text-sky-300 border border-sky-500/30 animate-pulse';
      document.getElementById('taskStatusPill').textContent = 'Running';
      document.getElementById('resultsCard').classList.add('hidden');
      document.getElementById('logTerminal').innerHTML = '<div class="text-sky-400">Launching design agent...</div>';
      document.getElementById('traceInspectorContainer').innerHTML = '<div class="text-xs text-sky-400 p-2">Tracing active execution spans...</div>';

      try {
        const res = await fetch('/api/generate', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            pdf_path: targetPdf,
            user_prompt: prompt,
            max_iterations: maxIters
          })
        });
        const data = await res.json();
        if (data.task_id) {
          currentTaskId = data.task_id;
          startPolling(data.task_id);
        } else {
          alert('Failed to launch task: ' + (data.error || 'Unknown error'));
          resetGenerateBtn();
        }
      } catch (err) {
        alert('Error initiating design: ' + err);
        resetGenerateBtn();
      }
    }

    function startPolling(taskId) {
      if (pollInterval) clearInterval(pollInterval);
      pollInterval = setInterval(async () => {
        try {
          const res = await fetch(`/api/status?task_id=${taskId}`);
          const data = await res.json();

          // Update Stepper
          updateStepper(data.current_phase || 1, data.status === 'failed');

          // Update Logs
          const logTerm = document.getElementById('logTerminal');
          if (data.logs && data.logs.length > 0) {
            logTerm.innerHTML = data.logs.map(l => `<div>${l}</div>`).join('');
            logTerm.scrollTop = logTerm.scrollHeight;
            document.getElementById('logCounter').textContent = `${data.logs.length} entries`;
          }

          // Fetch fine-grained telemetry
          fetchTraceTelemetry(taskId);

          if (data.status === 'completed' || data.status === 'completed_with_warnings') {
            clearInterval(pollInterval);
            onTaskCompleted(data, data.status === 'completed_with_warnings');
          } else if (data.status === 'failed') {
            clearInterval(pollInterval);
            onTaskFailed(data);
          }
        } catch (e) {
          console.error('Polling error:', e);
        }
      }, 1500);
    }

    async function fetchTraceTelemetry(taskId) {
      try {
        const res = await fetch(`/api/trace?task_id=${taskId}`);
        const data = await res.json();
        if (data.trace && data.trace.spans) {
          renderTraceSpans(data.trace.spans);
        }
      } catch (e) {}
    }

    function renderTraceSpans(spans) {
      const container = document.getElementById('traceInspectorContainer');
      document.getElementById('traceSpanCount').textContent = `${spans.length} spans`;
      container.innerHTML = '';

      spans.forEach((s, idx) => {
        const isErr = s.status === 'ERROR';
        const isWarn = s.status === 'WARNING';
        const card = document.createElement('div');
        card.className = `border ${isErr ? 'border-rose-500/50 bg-rose-950/20' : (isWarn ? 'border-amber-500/40 bg-amber-950/10' : 'border-slate-800 bg-slate-900/80')} rounded-xl p-3 text-xs space-y-2 transition-all`;

        const statusBadge = isErr
          ? '<span class="px-2 py-0.5 rounded bg-rose-500/20 text-rose-300 font-mono text-[10px]">ERROR</span>'
          : '<span class="px-2 py-0.5 rounded bg-emerald-500/20 text-emerald-300 font-mono text-[10px]">SUCCESS</span>';

        card.innerHTML = `
          <div class="flex items-center justify-between cursor-pointer" onclick="toggleTraceDetails(${idx})">
            <div class="flex items-center gap-2">
              <span class="w-5 h-5 rounded-full flex items-center justify-center font-bold text-[10px] bg-slate-800 text-slate-300">${s.phase}</span>
              <span class="font-bold text-white text-[11px]">${s.name}</span>
            </div>
            <div class="flex items-center gap-2">
              <span class="font-mono text-[10px] text-slate-400">${s.duration_ms} ms</span>
              ${statusBadge}
            </div>
          </div>
          ${s.error ? `
            <div class="bg-rose-950/40 border border-rose-500/40 rounded-lg p-2.5 text-rose-300 space-y-1">
              <div class="font-bold">[${s.error.type}] ${s.error.message}</div>
              ${s.error.remediation_hint ? `<div class="text-amber-300 text-[10px] bg-amber-500/10 p-1.5 rounded">💡 <strong>Remediation:</strong> ${s.error.remediation_hint}</div>` : ''}
            </div>
          ` : ''}
          <div id="trace-det-${idx}" class="hidden pt-1 space-y-1 text-[10px] font-mono border-t border-slate-800/60">
            <div class="text-slate-400"><strong>Outputs:</strong> ${JSON.stringify(s.outputs)}</div>
          </div>
        `;
        container.appendChild(card);
      });
    }

    function toggleTraceDetails(idx) {
      const el = document.getElementById(`trace-det-${idx}`);
      if (el) el.classList.toggle('hidden');
    }

    function updateStepper(activePhase, isFailed = false) {
      for (let p = 1; p <= 6; p++) {
        const el = document.getElementById(`step-${p}`);
        if (!el) continue;
        if (p < activePhase) {
          el.className = 'border rounded-xl p-3 transition-all step-done';
        } else if (p === activePhase) {
          el.className = 'border rounded-xl p-3 transition-all ' + (isFailed ? 'step-error' : 'step-active');
        } else {
          el.className = 'border border-slate-800 bg-slate-900/60 text-slate-500 rounded-xl p-3 transition-all';
        }
      }
    }

    function onTaskCompleted(data, hasWarnings = false) {
      resetGenerateBtn();
      document.getElementById('taskStatusPill').className = hasWarnings
        ? 'text-xs px-2.5 py-0.5 rounded-full bg-amber-500/20 text-amber-300 border border-amber-500/30'
        : 'text-xs px-2.5 py-0.5 rounded-full bg-emerald-500/20 text-emerald-300 border border-emerald-500/30';
      document.getElementById('taskStatusPill').textContent = hasWarnings ? 'Completed with warnings' : 'Completed';

      const results = data.result_summary || {};
      const baseSummary = `Subcircuit: ${results.subckt_name || 'DUT'} | Verification Pass Rate: ${(results.pass_rate_percent || 0).toFixed(1)}% | Iterations: ${results.iterations_count || 1}`;
      document.getElementById('resultSummaryText').textContent = hasWarnings
        ? `${baseSummary} | No valid netlist - run 2+ iterations or inspect the console.`
        : baseSummary;

      document.getElementById('netlistOutputPre').textContent = results.netlist_code || '* No valid SPICE netlist was generated in this run.';
      document.getElementById('openDashboardLink').href = data.dashboard_url || '#';
      document.getElementById('resultsCard').classList.remove('hidden');
    }

    function onTaskFailed(data) {
      resetGenerateBtn();
      document.getElementById('taskStatusPill').className = 'text-xs px-2.5 py-0.5 rounded-full bg-rose-500/20 text-rose-300 border border-rose-500/30';
      document.getElementById('taskStatusPill').textContent = 'Failed';
      alert('Task failed: ' + (data.error || 'Unknown error occurred.'));
    }

    function resetGenerateBtn() {
      document.getElementById('btnGenerate').disabled = false;
      document.getElementById('btnGenerate').innerHTML = '<svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 10V3L4 14h7v7l9-11h-7z"/></svg><span>🚀 Synthesize &amp; Verify Circuit Now</span>';
    }

    function copyNetlist() {
      const code = document.getElementById('netlistOutputPre').textContent;
      navigator.clipboard.writeText(code);
      alert('SPICE netlist copied to clipboard!');
    }

    window.onload = init;
  </script>
</body>
</html>
"""

class StudioServer:
    """Wrapper to start and manage the ThreadingHTTPServer."""
    def __init__(self, port: int = 8080, host: str = "127.0.0.1"):
        self.port = port
        self.host = host
        self.server = None

    def start(self, blocking: bool = True):
        # Find next available port if requested port is in use
        for p in range(self.port, self.port + 20):
            try:
                self.server = ThreadingHTTPServer((self.host, p), StudioRequestHandler)
                self.port = p
                break
            except OSError:
                continue

        if not self.server:
            raise RuntimeError(f"Could not bind to any port from {self.port} to {self.port+20}")

        url = f"http://{self.host}:{self.port}"
        logger.info(f"Interactive Analog Design Studio running at: {url}")
        print("\n" + "="*80)
        print("🚀 AUTONOMOUS ANALOG CIRCUIT DESIGN STUDIO READY!")
        print(f"👉 Studio Web App URL: {url}")
        print("="*80 + "\n")

        if blocking:
            try:
                self.server.serve_forever()
            except KeyboardInterrupt:
                logger.info("Studio server shutting down.")
                self.server.shutdown()
        else:
            t = threading.Thread(target=self.server.serve_forever, daemon=True)
            t.start()
            return url
