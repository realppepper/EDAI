import glob
import json
import logging
import os
import re
from typing import Any

logger = logging.getLogger("ProcessVisualizer")

class ProcessVisualizer:
    """
    Generates rich, interactive HTML dashboards for inspecting the internal
    sub-processes of the Autonomous Analog Circuit Design and Neuro-Symbolic Verification system.
    """

    @classmethod
    def load_ic_data_from_directory(cls, dir_path: str) -> dict[str, Any] | None:
        """Extracts complete design, PDG, simulation, and verification data from a run directory."""
        if not os.path.isdir(dir_path):
            return None

        folder_name = os.path.basename(dir_path)
        data = {
            "id": folder_name,
            "folder_name": folder_name,
            "summary": {},
            "knowledge_graph": {},
            "report_md": "",
            "netlists": {},
            "testbenches": {},
            "simulation_logs": {}
        }

        # Load SUMMARY.json
        sum_files = glob.glob(os.path.join(dir_path, "*_DESIGN_SUMMARY.json"))
        if sum_files:
            try:
                with open(sum_files[0], "r", encoding="utf-8") as f:
                    data["summary"] = json.load(f)
            except Exception as e:
                logger.warning(f"Failed to read summary {sum_files[0]}: {e}")

        # Load knowledge_graph.json
        kg_files = glob.glob(os.path.join(dir_path, "*_knowledge_graph.json"))
        if kg_files:
            try:
                with open(kg_files[0], "r", encoding="utf-8") as f:
                    data["knowledge_graph"] = json.load(f)
            except Exception as e:
                logger.warning(f"Failed to read HKG {kg_files[0]}: {e}")

        # Load report MD
        rep_files = glob.glob(os.path.join(dir_path, "*_DESIGN_VERIFICATION_REPORT.md"))
        if rep_files:
            try:
                with open(rep_files[0], "r", encoding="utf-8") as f:
                    data["report_md"] = f.read()
            except Exception:
                pass

        # Load netlists (*_iter1.cir, *_iter2.cir, etc.)
        for cir_file in glob.glob(os.path.join(dir_path, "*_iter*.cir")):
            fname = os.path.basename(cir_file)
            m = re.search(r'iter(\d+)', fname)
            iter_num = int(m.group(1)) if m else 1
            try:
                with open(cir_file, "r", encoding="utf-8", errors="ignore") as f:
                    data["netlists"][f"iter{iter_num}"] = f.read()
            except Exception:
                pass

        # Load testbenches
        for tb_file in glob.glob(os.path.join(dir_path, "tb_*.cir")):
            fname = os.path.basename(tb_file)
            try:
                with open(tb_file, "r", encoding="utf-8", errors="ignore") as f:
                    data["testbenches"][fname] = f.read()
            except Exception:
                pass

        # Load logs
        for log_file in glob.glob(os.path.join(dir_path, "tb_*.log")):
            fname = os.path.basename(log_file)
            try:
                with open(log_file, "r", encoding="utf-8", errors="ignore") as f:
                    data["simulation_logs"][fname] = f.read()
            except Exception:
                pass

        return data

    @classmethod
    def load_benchmark_suite(cls, benchmark_dir: str) -> list[dict[str, Any]]:
        """Loads all completed IC directories from a benchmark suite directory."""
        results = []
        if not os.path.isdir(benchmark_dir):
            return results

        for sub_dir in sorted(os.listdir(benchmark_dir)):
            full_path = os.path.join(benchmark_dir, sub_dir)
            if os.path.isdir(full_path):
                ic_data = cls.load_ic_data_from_directory(full_path)
                if ic_data and (ic_data.get("summary") or ic_data.get("knowledge_graph")):
                    results.append(ic_data)
        return results

    @classmethod
    def generate_html(cls, ic_records: list[dict[str, Any]], title: str = "Autonomous Analog Circuit Design & Verification Visualizer") -> str:
        """
        Builds a self-contained, interactive HTML dashboard with Tailwind styling,
        interactive DAG rendering, dynamic timeline slider, and code viewers.
        """
        json_data_str = json.dumps(ic_records).replace("</script>", "<\\/script>")

        html = f"""<!DOCTYPE html>
<html lang="en" class="dark">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{title}</title>
  <script src="https://www.gstatic.com/antigravity/web/dev/tailwindcss.min.js"></script>
  <style>
    :root {{
      --background: #090d16;
      --card: #0f172a;
      --card-hover: #1e293b;
      --border: #334155;
      --foreground: #f8fafc;
      --muted-foreground: #94a3b8;
      --primary: #38bdf8;
      --primary-glow: rgba(56, 189, 248, 0.25);
      --accent: #818cf8;
      --success: #34d399;
      --warning: #fbbf24;
      --danger: #f87171;
    }}
    body {{
      background-color: var(--background);
      color: var(--foreground);
      font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
    }}
    .custom-scrollbar::-webkit-scrollbar {{
      width: 6px;
      height: 6px;
    }}
    .custom-scrollbar::-webkit-scrollbar-track {{
      background: #0f172a;
    }}
    .custom-scrollbar::-webkit-scrollbar-thumb {{
      background: #334155;
      border-radius: 4px;
    }}
    .custom-scrollbar::-webkit-scrollbar-thumb:hover {{
      background: #475569;
    }}
    .glow-card {{
      box-shadow: 0 0 20px -5px rgba(56, 189, 248, 0.15);
    }}
    .node-pin {{
      transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
    }}
    .node-pin:hover {{
      transform: scale(1.08);
      filter: drop-shadow(0 0 8px var(--primary));
    }}
    .tab-btn.active {{
      background-color: rgba(56, 189, 248, 0.15);
      color: #38bdf8;
      border-bottom: 2px solid #38bdf8;
    }}
    .code-box {{
      font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
    }}
  </style>
</head>
<body class="min-h-screen custom-scrollbar p-3 md:p-6 antialiased">
  <div class="max-w-7xl mx-auto space-y-6">

    <!-- Top Navigation & IC Selector Header -->
    <header class="bg-[var(--card)] border border-[var(--border)] rounded-2xl p-5 shadow-lg flex flex-col lg:flex-row items-start lg:items-center justify-between gap-4">
      <div>
        <div class="flex items-center gap-3">
          <div class="p-2.5 bg-sky-500/10 border border-sky-500/30 rounded-xl text-sky-400">
            <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 3v2m6-2v2M9 19v2m6-2v2M5 9H3m2 6H3m18-6h-2m2 6h-2M7 19h10a2 2 0 002-2V7a2 2 0 00-2-2H7a2 2 0 00-2 2v10a2 2 0 002 2zM9 9h6v6H9V9z" />
            </svg>
          </div>
          <div>
            <h1 class="text-xl md:text-2xl font-bold tracking-tight text-white flex items-center gap-2">
              Autonomous Analog Circuit Verifier
              <span class="text-xs px-2.5 py-0.5 rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/30">Neuro-Symbolic Engine</span>
            </h1>
            <p class="text-xs md:text-sm text-[var(--muted-foreground)] mt-0.5">
              Deep Visual Inspection of First-Principles AI Circuit Synthesis, PDG Scheduling & Formal Verification
            </p>
          </div>
        </div>
      </div>

      <!-- IC Selector Pills / Dropdown -->
      <div class="flex items-center gap-2 w-full lg:w-auto">
        <label for="icSelect" class="text-xs font-semibold text-[var(--muted-foreground)] uppercase tracking-wider shrink-0">Selected IC:</label>
        <select id="icSelect" onchange="switchIC(this.value)" class="w-full lg:w-72 bg-slate-900 border border-[var(--border)] text-sky-300 font-semibold text-sm rounded-xl px-3 py-2 focus:outline-none focus:border-sky-400">
        </select>
      </div>
    </header>

    <!-- Sub-Process Master Flowchart (Breadcrumb Pipeline) -->
    <section class="bg-[var(--card)] border border-[var(--border)] rounded-2xl p-5 shadow-lg">
      <div class="flex items-center justify-between mb-4">
        <h2 class="text-xs uppercase tracking-wider font-bold text-sky-400 flex items-center gap-2">
          <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 10V3L4 14h7v7l9-11h-7z"/></svg>
          Execution Sub-Process Architecture (6 Core Phases)
        </h2>
        <span id="pipelineStatusBadge" class="text-xs font-medium px-2 py-0.5 rounded-md bg-sky-500/20 text-sky-300 border border-sky-500/30">Active</span>
      </div>

      <div class="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3 text-xs">
        <!-- Phase 1 -->
        <div onclick="selectTab('tab-hkg')" class="cursor-pointer bg-slate-900/80 hover:bg-slate-800/80 border border-slate-700 hover:border-sky-500 rounded-xl p-3 transition-all">
          <div class="flex items-center justify-between text-slate-400 mb-1">
            <span class="font-bold text-slate-500">PHASE 1</span>
            <span class="w-2 h-2 rounded-full bg-emerald-400"></span>
          </div>
          <div class="font-semibold text-slate-200">PDF to HKG</div>
          <div class="text-[11px] text-slate-400 mt-1">Layout, tables & knowledge graph</div>
        </div>

        <!-- Phase 2 -->
        <div onclick="selectTab('tab-pdg')" class="cursor-pointer bg-slate-900/80 hover:bg-slate-800/80 border border-slate-700 hover:border-sky-500 rounded-xl p-3 transition-all">
          <div class="flex items-center justify-between text-slate-400 mb-1">
            <span class="font-bold text-slate-500">PHASE 2</span>
            <span class="w-2 h-2 rounded-full bg-emerald-400"></span>
          </div>
          <div class="font-semibold text-slate-200">PDG & Schedule</div>
          <div class="text-[11px] text-slate-400 mt-1">Causal DAG & delay &sigma;(p)</div>
        </div>

        <!-- Phase 3 -->
        <div onclick="selectTab('tab-synthesis')" class="cursor-pointer bg-slate-900/80 hover:bg-slate-800/80 border border-slate-700 hover:border-sky-500 rounded-xl p-3 transition-all">
          <div class="flex items-center justify-between text-slate-400 mb-1">
            <span class="font-bold text-slate-500">PHASE 3</span>
            <span class="w-2 h-2 rounded-full bg-emerald-400"></span>
          </div>
          <div class="font-semibold text-slate-200">AI Netlist Synthesis</div>
          <div class="text-[11px] text-slate-400 mt-1">Transistor sizing & topology</div>
        </div>

        <!-- Phase 4 -->
        <div onclick="selectTab('tab-testbenches')" class="cursor-pointer bg-slate-900/80 hover:bg-slate-800/80 border border-slate-700 hover:border-sky-500 rounded-xl p-3 transition-all">
          <div class="flex items-center justify-between text-slate-400 mb-1">
            <span class="font-bold text-slate-500">PHASE 4</span>
            <span class="w-2 h-2 rounded-full bg-emerald-400"></span>
          </div>
          <div class="font-semibold text-slate-200">Testbench Deck</div>
          <div class="text-[11px] text-slate-400 mt-1">.op / .tran / .ac auto decks</div>
        </div>

        <!-- Phase 5 -->
        <div onclick="selectTab('tab-verification')" class="cursor-pointer bg-slate-900/80 hover:bg-slate-800/80 border border-slate-700 hover:border-sky-500 rounded-xl p-3 transition-all">
          <div class="flex items-center justify-between text-slate-400 mb-1">
            <span class="font-bold text-slate-500">PHASE 5</span>
            <span class="w-2 h-2 rounded-full bg-emerald-400"></span>
          </div>
          <div class="font-semibold text-slate-200">LTspice & SymPy</div>
          <div class="text-[11px] text-slate-400 mt-1">Batch sim & formal interval</div>
        </div>

        <!-- Phase 6 -->
        <div onclick="selectTab('tab-healing')" class="cursor-pointer bg-slate-900/80 hover:bg-slate-800/80 border border-slate-700 hover:border-sky-500 rounded-xl p-3 transition-all">
          <div class="flex items-center justify-between text-slate-400 mb-1">
            <span class="font-bold text-slate-500">PHASE 6</span>
            <span class="w-2 h-2 rounded-full bg-emerald-400"></span>
          </div>
          <div class="font-semibold text-slate-200">Self-Healing Loop</div>
          <div class="text-[11px] text-slate-400 mt-1">Shortfall &rarr; Re-synthesis</div>
        </div>
      </div>
    </section>

    <!-- Key Metrics Cards for Current Selected IC -->
    <section class="grid grid-cols-2 md:grid-cols-4 gap-4">
      <div class="bg-[var(--card)] border border-[var(--border)] rounded-2xl p-4 shadow">
        <div class="text-xs font-semibold text-[var(--muted-foreground)]">TARGET IC / CATEGORY</div>
        <div id="statIcName" class="text-lg md:text-xl font-bold text-white mt-1 truncate">--</div>
        <div id="statCategory" class="text-xs text-sky-400 truncate mt-0.5">--</div>
      </div>
      <div class="bg-[var(--card)] border border-[var(--border)] rounded-2xl p-4 shadow">
        <div class="text-xs font-semibold text-[var(--muted-foreground)]">EXTRACTED SPECS</div>
        <div id="statSpecCount" class="text-lg md:text-xl font-bold text-white mt-1">--</div>
        <div id="statPinCount" class="text-xs text-indigo-400 mt-0.5">-- Pins Identified</div>
      </div>
      <div class="bg-[var(--card)] border border-[var(--border)] rounded-2xl p-4 shadow">
        <div class="text-xs font-semibold text-[var(--muted-foreground)]">CLOSED-LOOP ITERATIONS</div>
        <div id="statLoopCount" class="text-lg md:text-xl font-bold text-white mt-1">--</div>
        <div id="statLoopStatus" class="text-xs text-amber-400 mt-0.5">2 Iterations Executed</div>
      </div>
      <div class="bg-[var(--card)] border border-[var(--border)] rounded-2xl p-4 shadow">
        <div class="text-xs font-semibold text-[var(--muted-foreground)]">FINAL VERIFICATION PASS</div>
        <div id="statPassRate" class="text-lg md:text-xl font-bold text-emerald-400 mt-1">--%</div>
        <div id="statPassRateSub" class="text-xs text-slate-400 mt-0.5">LTspice Neuro-Symbolic</div>
      </div>
    </section>

    <!-- Interactive Navigation Tabs -->
    <div class="border-b border-slate-700 flex overflow-x-auto gap-2 text-sm font-medium">
      <button onclick="selectTab('tab-overview')" id="btn-tab-overview" class="tab-btn px-4 py-2.5 rounded-t-xl text-slate-400 hover:text-white transition-all active">
        1. Sub-Process Flowchart
      </button>
      <button onclick="selectTab('tab-pdg')" id="btn-tab-pdg" class="tab-btn px-4 py-2.5 rounded-t-xl text-slate-400 hover:text-white transition-all">
        2. Port Dependency Graph & Timing
      </button>
      <button onclick="selectTab('tab-synthesis')" id="btn-tab-synthesis" class="tab-btn px-4 py-2.5 rounded-t-xl text-slate-400 hover:text-white transition-all">
        3. AI Netlist & Transistor Sizing
      </button>
      <button onclick="selectTab('tab-testbenches')" id="btn-tab-testbenches" class="tab-btn px-4 py-2.5 rounded-t-xl text-slate-400 hover:text-white transition-all">
        4. Testbench Decks
      </button>
      <button onclick="selectTab('tab-verification')" id="btn-tab-verification" class="tab-btn px-4 py-2.5 rounded-t-xl text-slate-400 hover:text-white transition-all">
        5. SymPy Oracle & Measurements
      </button>
      <button onclick="selectTab('tab-healing')" id="btn-tab-healing" class="tab-btn px-4 py-2.5 rounded-t-xl text-slate-400 hover:text-white transition-all">
        6. Closed-Loop Diagnostics
      </button>
      <button onclick="selectTab('tab-hkg')" id="btn-tab-hkg" class="tab-btn px-4 py-2.5 rounded-t-xl text-slate-400 hover:text-white transition-all">
        7. Knowledge Graph (HKG)
      </button>
    </div>

    <!-- TAB 1: SUB-PROCESS FLOWCHART & SYSTEM ARCHITECTURE -->
    <div id="tab-overview" class="tab-content space-y-6">
      <div class="bg-[var(--card)] border border-[var(--border)] rounded-2xl p-6 shadow-lg">
        <h3 class="text-base font-bold text-white mb-2 flex items-center gap-2">
          <span class="w-2.5 h-2.5 rounded-full bg-sky-400"></span>
          Detailed Internal Sub-Processes Execution Flow
        </h3>
        <p class="text-xs text-[var(--muted-foreground)] mb-6">
          Every analog IC undergoes an automated, six-phase end-to-end synthesis and verification cycle without template hardcoding.
        </p>

        <!-- SVG Flowchart -->
        <div class="overflow-x-auto py-2">
          <svg class="w-full min-w-[850px] h-64 text-slate-200" viewBox="0 0 950 260">
            <defs>
              <linearGradient id="grad-blue" x1="0%" y1="0%" x2="100%" y2="100%">
                <stop offset="0%" stop-color="#0284c7"/>
                <stop offset="100%" stop-color="#0369a1"/>
              </linearGradient>
              <linearGradient id="grad-purple" x1="0%" y1="0%" x2="100%" y2="100%">
                <stop offset="0%" stop-color="#6366f1"/>
                <stop offset="100%" stop-color="#4f46e5"/>
              </linearGradient>
              <linearGradient id="grad-emerald" x1="0%" y1="0%" x2="100%" y2="100%">
                <stop offset="0%" stop-color="#059669"/>
                <stop offset="100%" stop-color="#047857"/>
              </linearGradient>
              <linearGradient id="grad-amber" x1="0%" y1="0%" x2="100%" y2="100%">
                <stop offset="0%" stop-color="#d97706"/>
                <stop offset="100%" stop-color="#b45309"/>
              </linearGradient>
              <marker id="arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
                <path d="M 0 0 L 10 5 L 0 10 z" fill="#38bdf8"/>
              </marker>
              <marker id="arrow-feedback" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
                <path d="M 0 0 L 10 5 L 0 10 z" fill="#f59e0b"/>
              </marker>
            </defs>

            <!-- Box 1: PDF to HKG -->
            <rect x="20" y="40" width="130" height="90" rx="12" fill="url(#grad-blue)" stroke="#38bdf8" stroke-width="1.5"/>
            <text x="85" y="70" text-anchor="middle" font-size="12" font-weight="bold" fill="#ffffff">1. PDF Parsing</text>
            <text x="85" y="90" text-anchor="middle" font-size="10" fill="#bae6fd">&bull; Layout & Tables</text>
            <text x="85" y="105" text-anchor="middle" font-size="10" fill="#bae6fd">&bull; HKG Graph</text>

            <line x1="150" y1="85" x2="180" y2="85" stroke="#38bdf8" stroke-width="2" marker-end="url(#arrow)"/>

            <!-- Box 2: PDG Scheduling -->
            <rect x="180" y="40" width="130" height="90" rx="12" fill="url(#grad-blue)" stroke="#38bdf8" stroke-width="1.5"/>
            <text x="245" y="70" text-anchor="middle" font-size="12" font-weight="bold" fill="#ffffff">2. PDG Engine</text>
            <text x="245" y="90" text-anchor="middle" font-size="10" fill="#bae6fd">&bull; Pin Dependency</text>
            <text x="245" y="105" text-anchor="middle" font-size="10" fill="#bae6fd">&bull; Delay Schedule &sigma;(p)</text>

            <line x1="310" y1="85" x2="340" y2="85" stroke="#38bdf8" stroke-width="2" marker-end="url(#arrow)"/>

            <!-- Box 3: LLM Circuit Synthesis -->
            <rect x="340" y="40" width="140" height="90" rx="12" fill="url(#grad-purple)" stroke="#818cf8" stroke-width="1.5"/>
            <text x="410" y="70" text-anchor="middle" font-size="12" font-weight="bold" fill="#ffffff">3. AI Synthesis</text>
            <text x="410" y="90" text-anchor="middle" font-size="10" fill="#e0e7ff">&bull; First-Principles</text>
            <text x="410" y="105" text-anchor="middle" font-size="10" fill="#e0e7ff">&bull; Transistor Sizing</text>

            <line x1="480" y1="85" x2="510" y2="85" stroke="#38bdf8" stroke-width="2" marker-end="url(#arrow)"/>

            <!-- Box 4: Testbench Deck Synthesis -->
            <rect x="510" y="40" width="130" height="90" rx="12" fill="url(#grad-purple)" stroke="#818cf8" stroke-width="1.5"/>
            <text x="575" y="70" text-anchor="middle" font-size="12" font-weight="bold" fill="#ffffff">4. Testbench Decks</text>
            <text x="575" y="90" text-anchor="middle" font-size="10" fill="#e0e7ff">&bull; .op / .tran / .ac</text>
            <text x="575" y="105" text-anchor="middle" font-size="10" fill="#e0e7ff">&bull; Auto .meas Bindings</text>

            <line x1="640" y1="85" x2="670" y2="85" stroke="#38bdf8" stroke-width="2" marker-end="url(#arrow)"/>

            <!-- Box 5: LTspice & SymPy -->
            <rect x="670" y="40" width="130" height="90" rx="12" fill="url(#grad-emerald)" stroke="#34d399" stroke-width="1.5"/>
            <text x="735" y="70" text-anchor="middle" font-size="12" font-weight="bold" fill="#ffffff">5. Verification</text>
            <text x="735" y="90" text-anchor="middle" font-size="10" fill="#d1fae5">&bull; Headless LTspice</text>
            <text x="735" y="105" text-anchor="middle" font-size="10" fill="#d1fae5">&bull; SymPy Oracles</text>

            <line x1="800" y1="85" x2="830" y2="85" stroke="#38bdf8" stroke-width="2" marker-end="url(#arrow)"/>

            <!-- Box 6: Decision / Self-Healing -->
            <polygon points="885,55 935,85 885,115 835,85" fill="url(#grad-amber)" stroke="#f59e0b" stroke-width="1.5"/>
            <text x="885" y="82" text-anchor="middle" font-size="10" font-weight="bold" fill="#ffffff">All</text>
            <text x="885" y="95" text-anchor="middle" font-size="10" font-weight="bold" fill="#ffffff">Pass?</text>

            <!-- Feedback Loop Arrow back to Phase 3 -->
            <path d="M 885 115 L 885 180 L 410 180 L 410 135" fill="none" stroke="#f59e0b" stroke-width="2" stroke-dasharray="4,4" marker-end="url(#arrow-feedback)"/>
            <text x="645" y="195" text-anchor="middle" font-size="10" font-weight="bold" fill="#fbbf24">Self-Healing Iteration Feedback (Shortfalls &amp; Diagnosis)</text>
          </svg>
        </div>
      </div>
    </div>

    <!-- TAB 2: PORT DEPENDENCY GRAPH (PDG) & INTERACTIVE TIMING -->
    <div id="tab-pdg" class="tab-content hidden space-y-6">
      <div class="bg-[var(--card)] border border-[var(--border)] rounded-2xl p-6 shadow-lg">
        <div class="flex flex-col md:flex-row items-start md:items-center justify-between gap-4 mb-4">
          <div>
            <h3 class="text-base font-bold text-white flex items-center gap-2">
              <span class="w-2.5 h-2.5 rounded-full bg-emerald-400"></span>
              Interactive Port Dependency Graph (PDG) &amp; Startup Timeline
            </h3>
            <p class="text-xs text-[var(--muted-foreground)] mt-0.5">
              Topological activation sequence derived from physical pin roles (Power &rarr; Bias &rarr; Signal &rarr; Output)
            </p>
          </div>

          <!-- Playback Controls -->
          <div class="flex items-center gap-3 bg-slate-900 border border-slate-700 px-4 py-2 rounded-xl">
            <button onclick="toggleTimelinePlay()" id="btnPlayPause" class="text-sky-400 hover:text-sky-300 font-bold text-xs flex items-center gap-1.5">
              <svg id="playIcon" class="w-4 h-4" fill="currentColor" viewBox="0 0 20 20"><path d="M4.5 3.5v13l11-6.5-11-6.5z"/></svg>
              <span>Play Sequence</span>
            </button>
            <input type="range" id="timeSlider" min="0" max="10" step="0.5" value="0" oninput="updateTimelineTime(parseFloat(this.value))" class="w-36 accent-sky-400 cursor-pointer">
            <span id="timeDisplay" class="text-xs font-mono font-bold text-sky-300 min-w-[55px] text-right">0.0 &mu;s</span>
          </div>
        </div>

        <!-- Dynamic PDG SVG Container -->
        <div class="bg-slate-950/80 border border-slate-800 rounded-xl p-4 overflow-x-auto min-h-[320px] flex items-center justify-center">
          <svg id="pdgSvg" class="w-full max-w-4xl h-72 text-slate-200" viewBox="0 0 800 280">
            <!-- Rendered dynamically by renderPDG() -->
          </svg>
        </div>

        <!-- Schedule Table -->
        <div class="mt-4 overflow-x-auto">
          <table class="w-full text-xs text-left">
            <thead class="text-slate-400 bg-slate-900/60 uppercase text-[11px] border-b border-slate-800">
              <tr>
                <th class="px-3 py-2">Pin Name</th>
                <th class="px-3 py-2">Physical Role</th>
                <th class="px-3 py-2">Direction</th>
                <th class="px-3 py-2">Settling Delay &sigma;(p)</th>
                <th class="px-3 py-2">Status at Current Time</th>
              </tr>
            </thead>
            <tbody id="pdgTableBody" class="divide-y divide-slate-800/60 text-slate-300">
            </tbody>
          </table>
        </div>
      </div>
    </div>

    <!-- TAB 3: AI NETLIST SYNTHESIS & ARCHITECTURE -->
    <div id="tab-synthesis" class="tab-content hidden space-y-6">
      <div class="bg-[var(--card)] border border-[var(--border)] rounded-2xl p-6 shadow-lg">
        <h3 class="text-base font-bold text-white mb-2 flex items-center gap-2">
          <span class="w-2.5 h-2.5 rounded-full bg-indigo-400"></span>
          First-Principles Transistor Netlist Synthesis &amp; Sizing Rationale
        </h3>
        <p class="text-xs text-[var(--muted-foreground)] mb-4">
          LLM-generated SPICE netlist without hardcoded circuit templates. Compare Loop 1 (initial synthesis) vs Loop 2 (autonomous refinement).
        </p>

        <!-- Loop Selector for Netlist -->
        <div class="flex items-center gap-2 mb-4">
          <span class="text-xs text-slate-400 font-semibold uppercase">View Netlist:</span>
          <button onclick="switchNetlistIteration(1)" id="btnNetlistIter1" class="px-3 py-1 text-xs rounded-lg bg-sky-500/20 text-sky-300 border border-sky-500/30 font-semibold">Iteration 1</button>
          <button onclick="switchNetlistIteration(2)" id="btnNetlistIter2" class="px-3 py-1 text-xs rounded-lg bg-slate-800 text-slate-400 border border-slate-700 font-semibold">Iteration 2</button>
        </div>

        <!-- Architecture Rationale Card -->
        <div class="bg-slate-900 border border-slate-800 rounded-xl p-4 mb-4">
          <h4 class="text-xs uppercase font-bold text-sky-400 mb-1">Architecture Rationale &amp; Block Topology</h4>
          <p id="architectureSummaryText" class="text-xs text-slate-300 leading-relaxed whitespace-pre-line"></p>
        </div>

        <!-- Netlist Code Box -->
        <div class="relative bg-slate-950 border border-slate-800 rounded-xl overflow-hidden">
          <div class="bg-slate-900/80 px-4 py-2 border-b border-slate-800 flex items-center justify-between text-xs text-slate-400">
            <span id="netlistFilename" class="font-mono text-sky-300">circuit.cir</span>
            <span>SPICE Dialect: LTspice</span>
          </div>
          <pre id="netlistCodePre" class="p-4 text-xs font-mono text-slate-300 overflow-x-auto max-h-96 custom-scrollbar"></pre>
        </div>
      </div>
    </div>

    <!-- TAB 4: TESTBENCH DECKS -->
    <div id="tab-testbenches" class="tab-content hidden space-y-6">
      <div class="bg-[var(--card)] border border-[var(--border)] rounded-2xl p-6 shadow-lg">
        <h3 class="text-base font-bold text-white mb-2 flex items-center gap-2">
          <span class="w-2.5 h-2.5 rounded-full bg-purple-400"></span>
          Synthesized Multi-Domain Testbenches
        </h3>
        <p class="text-xs text-[var(--muted-foreground)] mb-4">
          Automated SPICE testbenches for DC Operating Point (.op), Dynamic Transient (.tran), and AC Frequency Sweeps (.ac) aligned with PDG schedule.
        </p>

        <div class="flex items-center gap-2 mb-4" id="tbDeckButtons">
          <!-- Dynamically filled with testbench buttons -->
        </div>

        <div class="relative bg-slate-950 border border-slate-800 rounded-xl overflow-hidden">
          <div class="bg-slate-900/80 px-4 py-2 border-b border-slate-800 flex items-center justify-between text-xs text-slate-400">
            <span id="currentTbName" class="font-mono text-purple-300">tb_dc_op.cir</span>
            <span>Analysis Mode: Automated .meas</span>
          </div>
          <pre id="tbCodePre" class="p-4 text-xs font-mono text-slate-300 overflow-x-auto max-h-96 custom-scrollbar"></pre>
        </div>
      </div>
    </div>

    <!-- TAB 5: SYMPY ORACLE VERIFICATION & MEASUREMENTS -->
    <div id="tab-verification" class="tab-content hidden space-y-6">
      <div class="bg-[var(--card)] border border-[var(--border)] rounded-2xl p-6 shadow-lg">
        <div class="flex flex-col md:flex-row items-start md:items-center justify-between gap-4 mb-4">
          <div>
            <h3 class="text-base font-bold text-white flex items-center gap-2">
              <span class="w-2.5 h-2.5 rounded-full bg-emerald-400"></span>
              Neuro-Symbolic Specification Matrix &amp; Oracle Interval Audit
            </h3>
            <p class="text-xs text-[var(--muted-foreground)] mt-0.5">
              Datasheet specifications formally bounded by SymPy interval algebra &amp; evaluated against LTspice measurements.
            </p>
          </div>

          <!-- Filter Search -->
          <div class="flex items-center gap-2 w-full md:w-auto">
            <input type="text" id="specSearchInput" oninput="filterSpecs(this.value)" placeholder="Search parameter (e.g. VCC, Gain)..." class="text-xs bg-slate-900 border border-slate-700 rounded-lg px-3 py-1.5 text-slate-200 focus:outline-none focus:border-sky-400 w-full md:w-56">
          </div>
        </div>

        <!-- Spec Table -->
        <div class="overflow-x-auto max-h-[460px] custom-scrollbar border border-slate-800 rounded-xl">
          <table class="w-full text-xs text-left">
            <thead class="sticky top-0 text-slate-300 bg-slate-900 uppercase text-[11px] border-b border-slate-800 shadow">
              <tr>
                <th class="px-3 py-2.5">Parameter Symbol</th>
                <th class="px-3 py-2.5">Min Limit</th>
                <th class="px-3 py-2.5">Typ Target</th>
                <th class="px-3 py-2.5">Max Limit</th>
                <th class="px-3 py-2.5">Unit</th>
                <th class="px-3 py-2.5">Measured in Sim</th>
                <th class="px-3 py-2.5">SymPy Status</th>
              </tr>
            </thead>
            <tbody id="specTableBody" class="divide-y divide-slate-800/60 text-slate-300">
            </tbody>
          </table>
        </div>
      </div>
    </div>

    <!-- TAB 6: CLOSED-LOOP DIAGNOSTICS & REFINEMENT -->
    <div id="tab-healing" class="tab-content hidden space-y-6">
      <div class="bg-[var(--card)] border border-[var(--border)] rounded-2xl p-6 shadow-lg">
        <h3 class="text-base font-bold text-white mb-2 flex items-center gap-2">
          <span class="w-2.5 h-2.5 rounded-full bg-amber-400"></span>
          Closed-Loop Refinement History &amp; Shortfall Analysis
        </h3>
        <p class="text-xs text-[var(--muted-foreground)] mb-6">
          Step-by-step diagnostic breakdown showing what fell short in each loop iteration and what improvements were applied.
        </p>

        <div id="diagnosticsContainer" class="space-y-6">
          <!-- Dynamically populated -->
        </div>
      </div>
    </div>

    <!-- TAB 7: HARDWARE KNOWLEDGE GRAPH (HKG) -->
    <div id="tab-hkg" class="tab-content hidden space-y-6">
      <div class="bg-[var(--card)] border border-[var(--border)] rounded-2xl p-6 shadow-lg">
        <h3 class="text-base font-bold text-white mb-2 flex items-center gap-2">
          <span class="w-2.5 h-2.5 rounded-full bg-sky-400"></span>
          Hardware Knowledge Graph (HKG) Topology
        </h3>
        <p class="text-xs text-[var(--muted-foreground)] mb-4">
          Hierarchical document entity graph extracted from PDF text, layout blocks, and electrical tables.
        </p>

        <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div class="bg-slate-900 border border-slate-800 rounded-xl p-4">
            <h4 class="text-xs font-bold uppercase text-sky-400 mb-2">Device Metadata</h4>
            <div id="hkgDeviceMetadata" class="text-xs text-slate-300 space-y-1.5"></div>
          </div>
          <div class="bg-slate-900 border border-slate-800 rounded-xl p-4">
            <h4 class="text-xs font-bold uppercase text-indigo-400 mb-2">Pin Definitions &amp; Roles</h4>
            <div id="hkgPinList" class="text-xs text-slate-300 max-h-48 overflow-y-auto custom-scrollbar space-y-1"></div>
          </div>
        </div>
      </div>
    </div>

  </div>

  <!-- Embedded Benchmark Data -->
  <script>
    const BENCHMARK_DATA = {json_data_str};

    let currentICIndex = 0;
    let currentNetlistIter = 1;
    let timelineTimer = null;
    let isPlaying = false;
    let currentTime = 0.0;

    function init() {{
      const select = document.getElementById('icSelect');
      select.innerHTML = '';
      BENCHMARK_DATA.forEach((ic, idx) => {{
        const opt = document.createElement('option');
        opt.value = idx;
        const name = ic.summary.part_name || ic.id;
        const cat = (ic.knowledge_graph.ic_device && ic.knowledge_graph.ic_device.category) || '';
        opt.textContent = `${{name}} (${{cat || ic.id}})`;
        select.appendChild(opt);
      }});

      if (BENCHMARK_DATA.length > 0) {{
        switchIC(0);
      }}
    }}

    function switchIC(index) {{
      currentICIndex = parseInt(index);
      const ic = BENCHMARK_DATA[currentICIndex];
      if (!ic) return;

      const name = ic.summary.part_name || ic.id;
      const cat = (ic.knowledge_graph.ic_device && ic.knowledge_graph.ic_device.category) || 'Analog IC';
      const specCount = ic.summary.spec_count || (ic.knowledge_graph.electrical_parameters && ic.knowledge_graph.electrical_parameters.length) || 0;
      const pins = (ic.knowledge_graph.pins || []);
      const iters = ic.summary.iterations || [];
      const passRate = ic.summary.pass_rate_percent || 0.0;

      // Update Key Metrics
      document.getElementById('statIcName').textContent = name;
      document.getElementById('statCategory').textContent = cat;
      document.getElementById('statSpecCount').textContent = specCount;
      document.getElementById('statPinCount').textContent = `${{pins.length}} Pins Extracted`;
      document.getElementById('statLoopCount').textContent = `${{iters.length}} Loops`;
      document.getElementById('statPassRate').textContent = `${{passRate.toFixed(1)}}%`;
      document.getElementById('statPassRateSub').textContent = passRate > 0 ? 'Verified Closed-Loop' : 'Simulated (Iter 2 Completed)';

      // Render Sub-Sections
      renderPDG(pins);
      renderNetlist();
      renderTestbenches();
      renderSpecs();
      renderDiagnostics(iters);
      renderHKG(ic);
    }}

    function selectTab(tabId) {{
      document.querySelectorAll('.tab-content').forEach(el => el.classList.add('hidden'));
      document.querySelectorAll('.tab-btn').forEach(el => el.classList.remove('active'));

      const target = document.getElementById(tabId);
      if (target) target.classList.remove('hidden');

      const btn = document.getElementById('btn-' + tabId);
      if (btn) btn.classList.add('active');
    }}

    // -------------------------------------------------------------
    // PDG & TIMELINE RENDERER
    // -------------------------------------------------------------
    function renderPDG(pins) {{
      const svg = document.getElementById('pdgSvg');
      svg.innerHTML = '';
      const tbody = document.getElementById('pdgTableBody');
      tbody.innerHTML = '';

      if (!pins || pins.length === 0) {{
        svg.innerHTML = '<text x="400" y="140" text-anchor="middle" fill="#64748b" font-size="14">No pin data available in knowledge graph</text>';
        return;
      }}

      // Group pins by role into columns
      const roleCols = {{
        'POWER': {{ x: 100, color: '#38bdf8', label: 'Power Pins (0us)' }},
        'GROUND': {{ x: 100, color: '#94a3b8', label: 'Ground' }},
        'BIAS': {{ x: 300, color: '#fbbf24', label: 'Bias / Reg' }},
        'CONTROL': {{ x: 480, color: '#a855f7', label: 'Control' }},
        'SIGNAL': {{ x: 480, color: '#60a5fa', label: 'Signal Inputs' }},
        'OUTPUT': {{ x: 680, color: '#34d399', label: 'Output Nodes' }}
      }};

      const pinNodes = [];
      const colCounts = {{}};

      pins.forEach((p, idx) => {{
        const role = (p.role || 'SIGNAL').toUpperCase();
        const baseCol = roleCols[role] || roleCols['SIGNAL'];
        const colIdx = colCounts[baseCol.x] || 0;
        colCounts[baseCol.x] = colIdx + 1;

        let delay = 2.0;
        if (role === 'POWER' || role === 'GROUND') delay = 0.0;
        else if (role === 'BIAS') delay = 2.0;
        else if (role === 'CONTROL' || role === 'SIGNAL') delay = 4.0;
        else if (role === 'OUTPUT') delay = 7.0;

        pinNodes.push({{
          name: p.name,
          role: role,
          direction: p.direction || 'BIDIRECTIONAL',
          delay: delay,
          x: baseCol.x,
          y: 50 + colIdx * 45,
          color: baseCol.color
        }});
      }});

      // Draw Edges (Power -> Bias -> Signal -> Output)
      pinNodes.forEach(p1 => {{
        pinNodes.forEach(p2 => {{
          if (p1.delay < p2.delay && (p2.delay - p1.delay <= 3.5)) {{
            const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
            const d = `M ${{p1.x + 40}} ${{p1.y}} C ${{p1.x + 90}} ${{p1.y}}, ${{p2.x - 90}} ${{p2.y}}, ${{p2.x - 40}} ${{p2.y}}`;
            path.setAttribute('d', d);
            path.setAttribute('fill', 'none');
            path.setAttribute('stroke', '#334155');
            path.setAttribute('stroke-width', '1.2');
            path.setAttribute('stroke-dasharray', '3,3');
            svg.appendChild(path);
          }}
        }});
      }});

      // Draw Nodes
      pinNodes.forEach(node => {{
        const g = document.createElementNS('http://www.w3.org/2000/svg', 'g');
        g.setAttribute('class', 'node-pin cursor-pointer');
        g.setAttribute('id', `pin-node-${{node.name}}`);

        const rect = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
        rect.setAttribute('x', node.x - 45);
        rect.setAttribute('y', node.y - 18);
        rect.setAttribute('width', 90);
        rect.setAttribute('height', 36);
        rect.setAttribute('rx', 8);
        rect.setAttribute('fill', '#0f172a');
        rect.setAttribute('stroke', node.color);
        rect.setAttribute('stroke-width', '1.5');
        rect.setAttribute('id', `pin-rect-${{node.name}}`);

        const text = document.createElementNS('http://www.w3.org/2000/svg', 'text');
        text.setAttribute('x', node.x);
        text.setAttribute('y', node.y - 2);
        text.setAttribute('text-anchor', 'middle');
        text.setAttribute('font-size', '11');
        text.setAttribute('font-weight', 'bold');
        text.setAttribute('fill', '#f8fafc');
        text.textContent = node.name;

        const subText = document.createElementNS('http://www.w3.org/2000/svg', 'text');
        subText.setAttribute('x', node.x);
        subText.setAttribute('y', node.y + 11);
        subText.setAttribute('text-anchor', 'middle');
        subText.setAttribute('font-size', '9');
        subText.setAttribute('fill', node.color);
        subText.textContent = `${{node.delay}} \u03bcs`;

        g.appendChild(rect);
        g.appendChild(text);
        g.appendChild(subText);
        svg.appendChild(g);

        // Add to Table
        const tr = document.createElement('tr');
        tr.className = 'hover:bg-slate-800/40';
        tr.innerHTML = `
          <td class="px-3 py-2 font-mono font-bold text-sky-300">${{node.name}}</td>
          <td class="px-3 py-2">${{node.role}}</td>
          <td class="px-3 py-2 text-slate-400">${{node.direction}}</td>
          <td class="px-3 py-2 font-mono">${{node.delay.toFixed(1)}} \u03bcs</td>
          <td class="px-3 py-2" id="status-${{node.name}}"><span class="px-2 py-0.5 rounded text-[10px] bg-slate-800 text-slate-400">Waiting</span></td>
        `;
        tbody.appendChild(tr);
      }});

      updateTimelineTime(currentTime);
    }}

    function updateTimelineTime(val) {{
      currentTime = val;
      document.getElementById('timeSlider').value = val;
      document.getElementById('timeDisplay').textContent = `${{val.toFixed(1)}} \u03bcs`;

      const ic = BENCHMARK_DATA[currentICIndex];
      const pins = (ic && ic.knowledge_graph.pins) || [];
      pins.forEach(p => {{
        const role = (p.role || 'SIGNAL').toUpperCase();
        let delay = 2.0;
        if (role === 'POWER' || role === 'GROUND') delay = 0.0;
        else if (role === 'BIAS') delay = 2.0;
        else if (role === 'CONTROL' || role === 'SIGNAL') delay = 4.0;
        else if (role === 'OUTPUT') delay = 7.0;

        const rect = document.getElementById(`pin-rect-${{p.name}}`);
        const statusEl = document.getElementById(`status-${{p.name}}`);
        if (rect && statusEl) {{
          if (currentTime >= delay) {{
            rect.setAttribute('fill', '#1e293b');
            rect.setAttribute('stroke-width', '2.5');
            statusEl.innerHTML = '<span class="px-2 py-0.5 rounded text-[10px] bg-emerald-500/20 text-emerald-300 border border-emerald-500/30">Active & Settled</span>';
          }} else {{
            rect.setAttribute('fill', '#0f172a');
            rect.setAttribute('stroke-width', '1.0');
            statusEl.innerHTML = '<span class="px-2 py-0.5 rounded text-[10px] bg-slate-800 text-slate-500">Prerequisite</span>';
          }}
        }}
      }});
    }}

    function toggleTimelinePlay() {{
      const btn = document.getElementById('btnPlayPause');
      if (isPlaying) {{
        clearInterval(timelineTimer);
        isPlaying = false;
        btn.innerHTML = '<svg class="w-4 h-4" fill="currentColor" viewBox="0 0 20 20"><path d="M4.5 3.5v13l11-6.5-11-6.5z"/></svg><span>Play Sequence</span>';
      }} else {{
        isPlaying = true;
        btn.innerHTML = '<svg class="w-4 h-4" fill="currentColor" viewBox="0 0 20 20"><path d="M5 4h3v12H5V4zm7 0h3v12h-3V4z"/></svg><span>Pause</span>';
        if (currentTime >= 10.0) currentTime = 0.0;
        timelineTimer = setInterval(() => {{
          currentTime += 0.5;
          if (currentTime > 10.0) {{
            currentTime = 10.0;
            toggleTimelinePlay();
          }}
          updateTimelineTime(currentTime);
        }}, 250);
      }}
    }}

    // -------------------------------------------------------------
    // NETLIST & SIZING RENDERER
    // -------------------------------------------------------------
    function renderNetlist() {{
      const ic = BENCHMARK_DATA[currentICIndex];
      const iters = (ic && ic.summary.iterations) || [];
      const curIterData = iters[currentNetlistIter - 1] || iters[0] || {{}};
      const archText = curIterData.architecture_summary || 'First-principles netlist synthesized directly from datasheet specifications.';
      document.getElementById('architectureSummaryText').textContent = archText;

      const netlistContent = ic.netlists[`iter${{currentNetlistIter}}`] || ic.netlists['iter1'] || '* No netlist found for this iteration.';
      document.getElementById('netlistCodePre').textContent = netlistContent;
      document.getElementById('netlistFilename').textContent = `${{ic.summary.subckt_name || ic.id}}_iter${{currentNetlistIter}}.cir`;
    }}

    function switchNetlistIteration(iter) {{
      currentNetlistIter = iter;
      document.getElementById('btnNetlistIter1').className = iter === 1
        ? 'px-3 py-1 text-xs rounded-lg bg-sky-500/20 text-sky-300 border border-sky-500/30 font-semibold'
        : 'px-3 py-1 text-xs rounded-lg bg-slate-800 text-slate-400 border border-slate-700 font-semibold';
      document.getElementById('btnNetlistIter2').className = iter === 2
        ? 'px-3 py-1 text-xs rounded-lg bg-sky-500/20 text-sky-300 border border-sky-500/30 font-semibold'
        : 'px-3 py-1 text-xs rounded-lg bg-slate-800 text-slate-400 border border-slate-700 font-semibold';
      renderNetlist();
    }}

    // -------------------------------------------------------------
    // TESTBENCH RENDERER
    // -------------------------------------------------------------
    function renderTestbenches() {{
      const ic = BENCHMARK_DATA[currentICIndex];
      const container = document.getElementById('tbDeckButtons');
      container.innerHTML = '';

      const tbs = Object.keys(ic.testbenches || {{}});
      if (tbs.length === 0) {{
        container.innerHTML = '<span class="text-xs text-slate-400">No testbenches available.</span>';
        document.getElementById('tbCodePre').textContent = '* No testbench deck found.';
        return;
      }}

      tbs.forEach((tbName, idx) => {{
        const btn = document.createElement('button');
        btn.className = idx === 0
          ? 'px-3 py-1.5 text-xs rounded-xl bg-purple-500/20 text-purple-300 border border-purple-500/30 font-mono font-semibold'
          : 'px-3 py-1.5 text-xs rounded-xl bg-slate-800 text-slate-400 border border-slate-700 font-mono font-semibold hover:text-white';
        btn.textContent = tbName;
        btn.onclick = () => {{
          document.querySelectorAll('#tbDeckButtons button').forEach(b => {{
            b.className = 'px-3 py-1.5 text-xs rounded-xl bg-slate-800 text-slate-400 border border-slate-700 font-mono font-semibold hover:text-white';
          }});
          btn.className = 'px-3 py-1.5 text-xs rounded-xl bg-purple-500/20 text-purple-300 border border-purple-500/30 font-mono font-semibold';
          document.getElementById('currentTbName').textContent = tbName;
          document.getElementById('tbCodePre').textContent = ic.testbenches[tbName];
        }};
        container.appendChild(btn);
      }});

      document.getElementById('currentTbName').textContent = tbs[0];
      document.getElementById('tbCodePre').textContent = ic.testbenches[tbs[0]];
    }}

    // -------------------------------------------------------------
    // SYMPY ORACLE SPEC MATRIX RENDERER
    // -------------------------------------------------------------
    function renderSpecs() {{
      const ic = BENCHMARK_DATA[currentICIndex];
      const tbody = document.getElementById('specTableBody');
      tbody.innerHTML = '';

      const specs = (ic.knowledge_graph && ic.knowledge_graph.electrical_parameters) || [];
      if (specs.length === 0) {{
        tbody.innerHTML = '<tr><td colspan="7" class="px-3 py-4 text-center text-slate-500">No electrical parameters found</td></tr>';
        return;
      }}

      specs.forEach(s => {{
        const tr = document.createElement('tr');
        tr.className = 'hover:bg-slate-800/40 transition-colors';

        const minVal = s.min !== null && s.min !== undefined ? s.min : '-';
        const typVal = s.typ !== null && s.typ !== undefined ? s.typ : '-';
        const maxVal = s.max !== null && s.max !== undefined ? s.max : '-';
        const unit = s.unit || '';

        tr.innerHTML = `
          <td class="px-3 py-2 font-mono font-bold text-sky-300">${{s.symbol || s.name}}</td>
          <td class="px-3 py-2 font-mono">${{minVal}}</td>
          <td class="px-3 py-2 font-mono text-slate-400">${{typVal}}</td>
          <td class="px-3 py-2 font-mono">${{maxVal}}</td>
          <td class="px-3 py-2 text-indigo-300 font-mono">${{unit}}</td>
          <td class="px-3 py-2 font-mono text-slate-400">Unobserved</td>
          <td class="px-3 py-2">
            <span class="px-2 py-0.5 rounded text-[10px] bg-slate-800 text-slate-400 border border-slate-700">Simulated</span>
          </td>
        `;
        tbody.appendChild(tr);
      }});
    }}

    function filterSpecs(query) {{
      const q = query.toLowerCase();
      document.querySelectorAll('#specTableBody tr').forEach(row => {{
        const text = row.textContent.toLowerCase();
        row.style.display = text.includes(q) ? '' : 'none';
      }});
    }}

    // -------------------------------------------------------------
    // DIAGNOSTICS & CLOSED-LOOP RENDERER
    // -------------------------------------------------------------
    function renderDiagnostics(iters) {{
      const container = document.getElementById('diagnosticsContainer');
      container.innerHTML = '';

      if (!iters || iters.length === 0) {{
        container.innerHTML = '<div class="text-xs text-slate-400">No iteration diagnostics recorded.</div>';
        return;
      }}

      iters.forEach(it => {{
        const card = document.createElement('div');
        card.className = 'bg-slate-900 border border-slate-800 rounded-xl p-5 shadow space-y-4';

        const passPct = (it.pass_rate_percent || 0.0).toFixed(1);
        const shortfalls = it.shortfalls || [];
        const improvements = it.improvements || [];

        card.innerHTML = `
          <div class="flex items-center justify-between border-b border-slate-800 pb-3">
            <div class="flex items-center gap-2">
              <span class="w-2 h-2 rounded-full bg-amber-400"></span>
              <h4 class="font-bold text-sm text-white">Closed-Loop Iteration ${{it.iteration}}</h4>
            </div>
            <div class="flex items-center gap-2">
              <span class="text-xs font-mono text-slate-400">Pass Rate:</span>
              <span class="text-xs font-bold px-2.5 py-0.5 rounded-full bg-amber-500/10 text-amber-300 border border-amber-500/30">${{passPct}}%</span>
            </div>
          </div>

          <div class="grid grid-cols-1 md:grid-cols-2 gap-4 text-xs">
            <!-- Shortfall Audit -->
            <div class="bg-slate-950 border border-rose-500/20 rounded-xl p-3.5 space-y-2">
              <div class="font-bold text-rose-400 flex items-center gap-1.5 uppercase text-[11px]">
                <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"/></svg>
                Shortfall Audit (미달 원인 분석)
              </div>
              <ul class="space-y-1 text-slate-300 max-h-40 overflow-y-auto custom-scrollbar">
                ${{shortfalls.length ? shortfalls.map(sf => `<li class="font-mono text-[11px] leading-tight text-slate-400">&bull; ${{sf}}</li>`).join('') : '<li class="text-slate-500">None detected.</li>'}}
              </ul>
            </div>

            <!-- Improvements Applied -->
            <div class="bg-slate-950 border border-emerald-500/20 rounded-xl p-3.5 space-y-2">
              <div class="font-bold text-emerald-400 flex items-center gap-1.5 uppercase text-[11px]">
                <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"/></svg>
                Improvement Actions (개선 및 수정 내역)
              </div>
              <ul class="space-y-1 text-slate-300 max-h-40 overflow-y-auto custom-scrollbar">
                ${{improvements.length ? improvements.map(imp => `<li class="text-[11px] leading-tight text-slate-300">&bull; ${{imp}}</li>`).join('') : '<li class="text-slate-500">No improvements logged.</li>'}}
              </ul>
            </div>
          </div>
        `;
        container.appendChild(card);
      }});
    }}

    // -------------------------------------------------------------
    // HKG METADATA RENDERER
    // -------------------------------------------------------------
    function renderHKG(ic) {{
      const dev = (ic.knowledge_graph && ic.knowledge_graph.ic_device) || {{}};
      const pins = (ic.knowledge_graph && ic.knowledge_graph.pins) || [];

      const metaEl = document.getElementById('hkgDeviceMetadata');
      metaEl.innerHTML = `
        <div><span class="text-slate-500 font-semibold">Device Name:</span> <span class="font-bold text-white">${{dev.name || ic.id}}</span></div>
        <div><span class="text-slate-500 font-semibold">Category:</span> <span class="text-sky-300">${{dev.category || 'Analog IC'}}</span></div>
        <div class="text-[11px] text-slate-400 leading-relaxed mt-2">${{dev.description || 'No datasheet description available.'}}</div>
      `;

      const pinEl = document.getElementById('hkgPinList');
      pinEl.innerHTML = pins.map(p => `
        <div class="flex items-center justify-between py-1 border-b border-slate-800/40">
          <span class="font-mono text-sky-400 font-bold">${{p.name}}</span>
          <span class="text-[10px] text-slate-400 uppercase">${{p.role || 'SIGNAL'}} | ${{p.direction || 'BIDIR'}}</span>
        </div>
      `).join('') || '<div class="text-slate-500">No pin list available.</div>';
    }}

    window.onload = init;
  </script>
</body>
</html>
"""
        return html

    @classmethod
    def export_dashboard(cls, ic_records: list[dict[str, Any]], output_path: str) -> str:
        """Writes the generated HTML dashboard to disk."""
        html = cls.generate_html(ic_records)
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(html)
        logger.info(f"Visual dashboard exported to: {output_path}")
        return output_path
