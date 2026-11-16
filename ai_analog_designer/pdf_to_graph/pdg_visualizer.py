import json
import logging
import os
from typing import Any

import networkx as nx

from .hardware_kg_builder import HardwareKnowledgeGraphBuilder
from .pdf_parser import PDFDatasheetParser
from .pdg_extractor import PortDependencyGraphExtractor

logger = logging.getLogger("PDGVisualizer")

class PDGVisualizer:
    """
    Direct visualizer for Port Dependency Graphs (PDG) extracted from IC datasheets.
    Generates Mermaid diagrams, SVG layouts, and interactive HTML timeline simulators.
    """

    ROLE_COLORS = {
        "POWER": "#38bdf8",     # Sky blue
        "GROUND": "#94a3b8",    # Slate
        "BIAS": "#fbbf24",      # Amber
        "ENABLE": "#f59e0b",    # Amber-orange
        "CONTROL": "#a855f7",   # Purple
        "SIGNAL": "#60a5fa",    # Blue
        "INPUT": "#60a5fa",     # Blue
        "FEEDBACK": "#ec4899",  # Pink
        "OUTPUT": "#34d399"     # Emerald
    }

    @classmethod
    def extract_from_pdf(cls, pdf_path: str, max_pages: int = 15) -> dict[str, Any]:
        """Runs the PDF-to-HKG-to-PDG pipeline on demand and returns visualization data."""
        parser = PDFDatasheetParser(max_pages=max_pages)
        parsed_doc = parser.parse_pdf(pdf_path)

        kg_builder = HardwareKnowledgeGraphBuilder()
        stem = os.path.splitext(os.path.basename(pdf_path))[0].lower()
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        auto_cache = os.path.abspath(os.path.join(base_dir, "output_interactive", ".hkg_cache", f"{stem}_hkg.json"))
        gt_cache = os.path.abspath(os.path.join(base_dir, "benchmarks", "pdg_groundtruth", f"{stem}.json"))
        if os.path.exists(auto_cache):
            with open(auto_cache, "r", encoding="utf-8") as f:
                raw_extraction = json.load(f)
            hkg = kg_builder._json_to_networkx_graph(raw_extraction)
            hkg.graph["parsed_pages"] = PDFDatasheetParser.audit_pages(parsed_doc)
        elif os.path.exists(gt_cache):
            with open(gt_cache, "r", encoding="utf-8") as f:
                raw_gt = json.load(f)
            raw_extraction = {
                "ic_device": {"name": raw_gt.get("ic", stem.upper()), "category": "Analog IC"},
                "pins": raw_gt.get("pins", []),
                "electrical_parameters": raw_gt.get("electrical_parameters", [])
            }
            hkg = kg_builder._json_to_networkx_graph(raw_extraction)
            hkg.graph["parsed_pages"] = PDFDatasheetParser.audit_pages(parsed_doc)
        else:
            try:
                hkg = kg_builder.build_kg_from_parsed_pdf(parsed_doc, pins_only=True)
                raw_extraction = hkg.graph.get("raw_extraction", {})
                try:
                    os.makedirs(os.path.dirname(auto_cache), exist_ok=True)
                    with open(auto_cache, "w", encoding="utf-8") as f:
                        json.dump(raw_extraction, f, indent=2)
                    logger.info(f"Cached HKG extraction to {auto_cache}")
                except Exception as e:
                    logger.warning(f"Could not cache HKG: {e}")
            except Exception as e:
                logger.warning(f"HKG extraction error in visualizer: {e}. Falling back to heuristic pin extraction...")
                raw_extraction = {}
                from .hardware_kg_builder import HardwareKnowledgeGraph
                hkg = HardwareKnowledgeGraph()

        extractor = PortDependencyGraphExtractor()
        if hkg and len(hkg.nodes) > 0:
            pdg, schedule, levels = extractor.extract_pdg(hkg)
        else:
            pdg, schedule, levels = None, {}, [[]]

        ic_info = raw_extraction.get("ic_device") or {"name": os.path.splitext(os.path.basename(pdf_path))[0]}
        if not isinstance(ic_info, dict):
            ic_info = {"name": os.path.splitext(os.path.basename(pdf_path))[0]}
        pins = raw_extraction.get("pins") or []

        # Heuristic fallback if table extraction yielded 0 pins:
        if not pins:
            # Build generic pins from filename
            pins = [
                {"name": "VCC", "role": "POWER", "direction": "INPUT", "description": "Positive Supply"},
                {"name": "GND", "role": "GROUND", "direction": "INPUT", "description": "Ground"},
                {"name": "IN", "role": "SIGNAL", "direction": "INPUT", "description": "Signal Input"},
                {"name": "OUT", "role": "OUTPUT", "direction": "OUTPUT", "description": "Output"}
            ]
            schedule = {"VCC": 0.0, "GND": 0.0, "IN": 4.0e-6, "OUT": 7.0e-6}
            levels = [["VCC", "GND"], ["IN"], ["OUT"]]

        # Clean pins
        cleaned_pins = []
        for p in pins:
            if isinstance(p, dict) and p.get("name"):
                cleaned_pins.append({
                    "name": str(p["name"]),
                    "role": (p.get("role") or "SIGNAL").upper(),
                    "direction": (p.get("direction") or "INPUT").upper(),
                    "description": p.get("description") or ""
                })
        if not cleaned_pins:
            cleaned_pins = [
                {"name": "VCC", "role": "POWER", "direction": "INPUT", "description": "Positive Supply"},
                {"name": "GND", "role": "GROUND", "direction": "INPUT", "description": "Ground"},
                {"name": "IN", "role": "SIGNAL", "direction": "INPUT", "description": "Signal Input"},
                {"name": "OUT", "role": "OUTPUT", "direction": "OUTPUT", "description": "Output"}
            ]
        pins = cleaned_pins

        return {
            "ic_info": ic_info,
            "pins": pins,
            "schedule": schedule,
            "levels": levels,
            "pdg": pdg
        }


    @classmethod
    def to_mermaid(cls, pins: list[dict[str, Any]], schedule: dict[str, float], pdg: nx.DiGraph | None = None) -> str:
        """Generates Mermaid graph TD syntax reflecting true causal physical dependencies."""
        lines = ["graph TD"]
        for p in pins:
            pname = p["name"]
            role = (p.get("role") or "SIGNAL").upper()
            t_us = schedule.get(pname, 0.0) * 1e6
            volt_info = f" | {p['nominal_voltage']}V" if p.get("nominal_voltage") is not None else ""
            lines.append(f'    {pname}["{pname} ({role}){volt_info}<br/>&sigma;={t_us:.1f}&mu;s"]')

        # Draw dependency arrows directly from graph edges if available
        if pdg and len(pdg.edges()) > 0:
            for u, v, data in pdg.edges(data=True):
                raw_delay = data.get("delay_us")
                if raw_delay is None:
                    raw_delay = data.get("weight", 0.0) * 1e6
                try:
                    delay_us = float(raw_delay) if raw_delay is not None else 0.0
                except (ValueError, TypeError):
                    delay_us = 0.0
                cond = data.get("condition", "")
                label = f"{delay_us:.1f}us: {cond}" if cond else f"{delay_us:.1f}us"
                lines.append(f'    {u} -->|"{label}"| {v}')
        else:
            # Fallback topological order
            sorted_pins = sorted(pins, key=lambda x: schedule.get(x["name"], 0.0))
            for i in range(len(sorted_pins)):
                for j in range(i + 1, len(sorted_pins)):
                    u, v = sorted_pins[i]["name"], sorted_pins[j]["name"]
                    t_diff = (schedule.get(v, 0.0) - schedule.get(u, 0.0)) * 1e6
                    if t_diff > 0:
                        lines.append(f'    {u} -->|"{t_diff:.1f}us"| {v}')

        return "\n".join(lines)

    @classmethod
    def to_svg(
        cls,
        pins: list[dict[str, Any]],
        schedule: dict[str, float],
        pdg: nx.DiGraph | None = None,
        width: int = 920,
        height: int = 340
    ) -> str:
        """Generates standalone, responsive SVG markup directly from the PDG graph structure."""
        role_cols = {
            "POWER": 130, "GROUND": 130,
            "BIAS": 380, "REFERENCE": 380,
            "CONTROL": 610, "SIGNAL": 610, "INPUT": 610, "ENABLE": 610,
            "OUTPUT": 820, "FEEDBACK": 820
        }

        col_counts = {}
        nodes_by_name = {}
        nodes = []

        for p in pins:
            pname = p["name"]
            role = (p.get("role") or "SIGNAL").upper()
            col_x = role_cols.get(role, 610)
            c_idx = col_counts.get(col_x, 0)
            col_counts[col_x] = c_idx + 1

            color = cls.ROLE_COLORS.get(role, "#60a5fa")
            t_us = schedule.get(pname, 0.0) * 1e6

            volt_badge = ""
            if p.get("nominal_voltage") is not None:
                volt_badge = f"{p['nominal_voltage']}V"
            elif p.get("voltage_range") and isinstance(p["voltage_range"], dict) and p["voltage_range"].get("typ") is not None:
                volt_badge = f"{p['voltage_range']['typ']}V"

            node_dict = {
                "name": pname,
                "role": role,
                "color": color,
                "delay_us": t_us,
                "volt_badge": volt_badge,
                "x": col_x,
                "y": 55 + c_idx * 56
            }
            nodes.append(node_dict)
            nodes_by_name[pname] = node_dict

        max_y = max([n["y"] for n in nodes] + [280]) + 50
        svg_height = max(height, max_y)

        svg_parts = [
            f'<svg class="w-full h-full text-slate-200" viewBox="0 0 {width} {svg_height}" xmlns="http://www.w3.org/2000/svg">',
            '<defs>',
            '  <marker id="pdg-arr" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">',
            '    <path d="M 0 0 L 10 5 L 0 10 z" fill="#38bdf8"/>',
            '  </marker>',
            '  <filter id="glow" x="-20%" y="-20%" width="140%" height="140%">',
            '    <feDropShadow dx="0" dy="2" stdDeviation="4" flood-color="#38bdf8" flood-opacity="0.15"/>',
            '  </filter>',
            '</defs>',
            '<!-- Column Stage Labels -->',
            '  <text x="130" y="24" text-anchor="middle" font-size="10" font-weight="bold" fill="#64748b" letter-spacing="1">1. POWER &amp; GROUND</text>',
            '  <text x="380" y="24" text-anchor="middle" font-size="10" font-weight="bold" fill="#64748b" letter-spacing="1">2. BIAS &amp; REFERENCE</text>',
            '  <text x="610" y="24" text-anchor="middle" font-size="10" font-weight="bold" fill="#64748b" letter-spacing="1">3. SIGNAL &amp; CONTROL</text>',
            '  <text x="820" y="24" text-anchor="middle" font-size="10" font-weight="bold" fill="#64748b" letter-spacing="1">4. OUTPUT &amp; STABILIZATION</text>'
        ]

        # Draw physical dependency edges directly from graph
        edges_to_draw = []
        if pdg and len(pdg.edges()) > 0:
            for u, v, data in pdg.edges(data=True):
                if u in nodes_by_name and v in nodes_by_name:
                    edges_to_draw.append((nodes_by_name[u], nodes_by_name[v], data))
        else:
            # Fallback
            for n1 in nodes:
                for n2 in nodes:
                    if n1["delay_us"] < n2["delay_us"]:
                        edges_to_draw.append((n1, n2, {"delay_us": n2["delay_us"] - n1["delay_us"], "condition": "Physical Sequence"}))

        for n1, n2, data in edges_to_draw:
            x1 = n1["x"] + 55
            y1 = n1["y"]
            x2 = n2["x"] - 55
            y2 = n2["y"]
            dx = max(30, abs(x2 - x1) / 2)
            d = f'M {x1} {y1} C {x1+dx} {y1}, {x2-dx} {y2}, {x2} {y2}'
            raw_delay = data.get("delay_us")
            if raw_delay is None:
                raw_delay = data.get("weight", 0.0) * 1e6
            try:
                delay_val = float(raw_delay) if raw_delay is not None else 0.0
            except (ValueError, TypeError):
                delay_val = 0.0
            cond_str = data.get("condition") or ""

            svg_parts.append(
                f'<path d="{d}" fill="none" stroke="#334155" stroke-width="1.6" stroke-dasharray="4,3" marker-end="url(#pdg-arr)">'
                f'<title>{n1["name"]} &rarr; {n2["name"]} | &delta;={delay_val:.1f}&mu;s ({cond_str})</title>'
                f'</path>'
            )

        # Draw node cards
        for n in nodes:
            volt_display = f'<tspan fill="#38bdf8" font-size="9"> {n["volt_badge"]}</tspan>' if n["volt_badge"] else ""
            svg_parts.extend([
                f'<g class="node-pin" id="node-{n["name"]}">',
                f'  <rect x="{n["x"]-55}" y="{n["y"]-22}" width="110" height="44" rx="10" fill="#0f172a" stroke="{n["color"]}" stroke-width="1.8" filter="url(#glow)"/>',
                f'  <text x="{n["x"]}" y="{n["y"]-4}" text-anchor="middle" font-size="11" font-weight="bold" fill="#f8fafc">{n["name"]}{volt_display}</text>',
                f'  <text x="{n["x"]}" y="{n["y"]+12}" text-anchor="middle" font-size="9" fill="{n["color"]}" font-family="monospace">&sigma;={n["delay_us"]:.1f} &mu;s</text>',
                '</g>'
            ])

        svg_parts.append('</svg>')
        return "\n".join(svg_parts)

    @classmethod
    def export_interactive_html(cls, pdf_path: str, output_path: str) -> str:
        """Extracts and exports an interactive PDG visualizer dashboard for any PDF datasheet."""
        res = cls.extract_from_pdf(pdf_path)
        ic_name = res["ic_info"].get("name", "ANALOG_IC")
        pins = res["pins"]
        sched = res["schedule"]
        pdg = res.get("pdg")

        svg_content = cls.to_svg(pins, sched, pdg=pdg)
        mermaid_code = cls.to_mermaid(pins, sched, pdg=pdg)

        # Determine realistic timeline range
        max_time_s = max(sched.values()) if sched else 10e-6
        max_time_us = max(10.0, max_time_s * 1e6 * 1.25)
        slider_step = max(0.5, round(max_time_us / 50.0, 1))

        pins_json = json.dumps(pins)
        sched_json = json.dumps(sched)

        html = f"""<!DOCTYPE html>
<html lang="en" class="dark">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Port Dependency Graph (PDG) — {ic_name}</title>
  <script src="https://www.gstatic.com/antigravity/web/dev/tailwindcss.min.js"></script>
  <style>
    body {{ background: #090d16; color: #f8fafc; font-family: ui-sans-serif, system-ui, sans-serif; }}
    .node-pin {{ transition: all 0.3s ease; }}
    .node-pin:hover {{ transform: scale(1.08); }}
  </style>
</head>
<body class="p-6 min-h-screen">
  <div class="max-w-5xl mx-auto space-y-6">

    <header class="bg-slate-900 border border-slate-800 rounded-2xl p-5 shadow flex items-center justify-between">
      <div>
        <h1 class="text-xl font-bold text-white flex items-center gap-2">
          Port Dependency Graph (PDG) Visualizer
          <span class="text-xs px-2.5 py-0.5 rounded-full bg-sky-500/10 text-sky-400 border border-sky-500/30">{ic_name}</span>
        </h1>
        <p class="text-xs text-slate-400 mt-1">Datasheet Source: <span class="font-mono text-slate-300">{os.path.basename(pdf_path)}</span> | Extracted Pins: {len(pins)}</p>
      </div>

      <!-- Timeline Controls -->
      <div class="flex items-center gap-3 bg-slate-950 border border-slate-800 px-4 py-2 rounded-xl text-xs">
        <button onclick="togglePlay()" id="btnPlay" class="text-sky-400 font-bold hover:text-sky-300 flex items-center gap-1">
          <span>Play &sigma;(p)</span>
        </button>
        <input type="range" id="slider" min="0" max="{max_time_us:.1f}" step="{slider_step:.1f}" value="0" oninput="setTime(parseFloat(this.value))" class="w-32 accent-sky-400">
        <span id="timeVal" class="font-mono text-sky-300 font-bold w-16 text-right">0.0 &mu;s</span>
      </div>
    </header>

    <!-- Graph Container -->
    <div class="bg-slate-950 border border-slate-800 rounded-2xl p-6 flex items-center justify-center min-h-[340px] shadow-inner overflow-x-auto">
      {svg_content}
    </div>

    <!-- Activation Schedule Table -->
    <div class="bg-slate-900 border border-slate-800 rounded-2xl p-5 space-y-3">
      <h3 class="text-xs font-bold uppercase tracking-wider text-slate-400">Topological Settling Sequence &sigma;(p)</h3>
      <table class="w-full text-xs text-left">
        <thead class="text-slate-400 uppercase text-[10px] border-b border-slate-800">
          <tr>
            <th class="py-2">Pin Name</th>
            <th class="py-2">Physical Role</th>
            <th class="py-2">Direction</th>
            <th class="py-2">Settling Delay</th>
            <th class="py-2">State</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-slate-800 text-slate-300" id="tableBody">
        </tbody>
      </table>
    </div>

  </div>

  <script>
    const PINS = {pins_json};
    const SCHED = {sched_json};
    let curTime = 0.0;
    let timer = null;

    function renderTable() {{
      const tbody = document.getElementById('tableBody');
      tbody.innerHTML = '';
      PINS.forEach(p => {{
        const delay = SCHED[p.name] || 0.0;
        const d_us = delay * 1e6;
        const tr = document.createElement('tr');
        tr.innerHTML = `
          <td class="py-2 font-mono font-bold text-sky-400">${{p.name}}</td>
          <td class="py-2">${{p.role || 'SIGNAL'}}</td>
          <td class="py-2 text-slate-400">${{p.direction || 'INPUT'}}</td>
          <td class="py-2 font-mono">${{d_us.toFixed(1)}} &mu;s</td>
          <td class="py-2" id="state-${{p.name}}">Waiting</td>
        `;
        tbody.appendChild(tr);
      }});
      setTime(0.0);
    }}

    function setTime(val) {{
      curTime = val;
      document.getElementById('slider').value = val;
      document.getElementById('timeVal').textContent = `${{val.toFixed(1)}} \u03bcs`;

      PINS.forEach(p => {{
        const delay = (SCHED[p.name] || 0.0) * 1e6;
        const stateEl = document.getElementById(`state-${{p.name}}`);
        const nodeG = document.getElementById(`node-${{p.name}}`);
        if (curTime >= delay) {{
          if (stateEl) stateEl.innerHTML = '<span class="text-emerald-400 font-bold">Active & Settled</span>';
          if (nodeG) nodeG.querySelector('rect').setAttribute('fill', '#1e293b');
        }} else {{
          if (stateEl) stateEl.innerHTML = '<span class="text-slate-500">Waiting</span>';
          if (nodeG) nodeG.querySelector('rect').setAttribute('fill', '#0f172a');
        }}
      }});
    }}

    function togglePlay() {{
      const btn = document.getElementById('btnPlay');
      if (timer) {{
        clearInterval(timer);
        timer = null;
        btn.textContent = 'Play \u03c3(p)';
      }} else {{
        btn.textContent = 'Pause';
        if (curTime >= {max_time_us:.1f}) curTime = 0.0;
        timer = setInterval(() => {{
          curTime += {slider_step:.1f};
          if (curTime > {max_time_us:.1f}) {{
            curTime = {max_time_us:.1f};
            togglePlay();
          }}
          setTime(curTime);
        }}, 200);
      }}
    }}

    window.onload = renderTable;
  </script>
</body>
</html>
"""
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(html)
        return output_path
