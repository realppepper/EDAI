import json
import os
import sys
import time

repo_root = os.path.abspath(r"C:\Users\Sera\.gemini\antigravity\worktrees\Project2\graph_analyze_codebase")
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

import concurrent.futures as cf

from ai_analog_designer.llm_client import LLMClient
from ai_analog_designer.pdf_to_graph.hardware_kg_builder import (
    PINS_PROMPT,
    ROLES,
    SPEC_CATEGORIES,
    SPECS_PROMPT,
    HardwareKnowledgeGraphBuilder,
    _num,
)
from ai_analog_designer.pdf_to_graph.pdf_parser import PDFDatasheetParser

pdf_path = r"D:\Sera\Documents\2026-2\pre-capstone\Project2\testcases\ads7891.pdf"
out_dir = os.path.join(repo_root, "output_ads7891_knowledge_graph")
os.makedirs(out_dir, exist_ok=True)

openrouter_key = os.getenv("OPENROUTER_API_KEY", "")
model_name = "nvidia/nemotron-3.5-lightning:free"

print("=== [STEP 1] Loading Cached 32-page Nemotron-Parse Data ===", flush=True)
cache_file = os.path.join(out_dir, "parsed_full_document.json")
with open(cache_file, "r", encoding="utf-8") as f:
    parsed_data = json.load(f)
print(f"-> Loaded {len(parsed_data['pages'])} pages successfully.", flush=True)

print(f"\n=== [STEP 2] LLM Client (OpenRouter 100% Free: {model_name}) ===", flush=True)
llm_client = LLMClient(
    api_key=openrouter_key,
    default_model=model_name,
    base_url="https://openrouter.ai/api/v1/chat/completions",
    provider="openrouter",
    request_timeout=180
)
llm_client.fallback_models = []

print("\n=== [STEP 3] Extracting Nodes & Edges (Pins + All Spec Pages) ===", flush=True)
P = PDFDatasheetParser
# Pin table in ADS7891 is on Page 6 & 7
pin_pages = [6, 7]
pin_text = P.page_tagged_text(parsed_data, pin_pages, 25000)
spec_pages = P.select_pages(parsed_data, "specs")

sys_p = "You are a meticulous analog IC datasheet analyst. Extract only what the datasheet states. Never invent values."

t0 = time.time()
spec_jobs = []
with cf.ThreadPoolExecutor(max_workers=5) as ex:
    print(f"-> Submitting pin extraction (Pages {pin_pages})...", flush=True)
    f_pins = ex.submit(llm_client.complete_json, PINS_PROMPT.format(text=pin_text, roles="|".join(ROLES)),
                       system_prompt=sys_p, max_tokens=6000, tag="hkg_pins")
    for pn in spec_pages:
        txt = P.page_tagged_text(parsed_data, [pn], 14000, layout=True)
        print(f"-> Submitting spec extraction (Page {pn})...", flush=True)
        spec_jobs.append((pn, ex.submit(llm_client.complete_json, SPECS_PROMPT.format(text=txt, ic="ADS7891"),
                                        system_prompt=sys_p, max_tokens=6000, tag=f"hkg_specs_p{pn}")))

    pins_json = f_pins.result()
    print("-> Pin extraction finished!", flush=True)
    specs_json = {"electrical_parameters": []}
    for pn, f in spec_jobs:
        try:
            res = f.result()
            rows = res.get("electrical_parameters") or []
            for r in rows:
                if isinstance(r, dict) and not r.get("page"):
                    r["page"] = pn
            specs_json["electrical_parameters"].extend(rows)
            print(f"-> Page {pn} spec extracted: {len(rows)} parameters", flush=True)
        except Exception as e:
            print(f"-> Page {pn} error: {e}", flush=True)

# Build graph structure
raw_data = {
    "ic_device": pins_json.get("ic_device") or {"name": "ADS7891", "category": "ADC"},
    "pins": pins_json.get("pins") or [],
    "port_dependencies": pins_json.get("port_dependencies") or [],
    "functional_blocks": pins_json.get("functional_blocks") or [],
    "electrical_parameters": [],
    "provenance": {"pin_pages": pin_pages, "spec_pages": spec_pages}
}

seen = set()
for p in specs_json.get("electrical_parameters") or []:
    if not isinstance(p, dict):
        continue
    for k in ("min", "typ", "max"):
        p[k] = _num(p.get(k))
    cat = str(p.get("category") or "ELECTRICAL").upper()
    p["category"] = cat if cat in SPEC_CATEGORIES else "ELECTRICAL"
    key = (str(p.get("symbol")).upper(), p["category"], p.get("min"), p.get("typ"), p.get("max"),
           str(p.get("test_conditions"))[:40])
    if key in seen:
        continue
    seen.add(key)
    raw_data["electrical_parameters"].append(p)

builder = HardwareKnowledgeGraphBuilder(llm_client=llm_client)
hkg = builder._json_to_networkx_graph(raw_data)
elapsed = time.time() - t0
print(f"\n-> Knowledge Graph extraction finished in {elapsed:.1f}s!", flush=True)

# Save JSON
json_out = os.path.join(out_dir, "ads7891_knowledge_graph.json")
with open(json_out, "w", encoding="utf-8") as f:
    json.dump(raw_data, f, indent=2, ensure_ascii=False)
print(f"-> Saved JSON to: {json_out}", flush=True)

nodes = list(hkg.nodes(data=True))
edges = list(hkg.edges(data=True))
print("\n=== [STEP 4] Knowledge Graph Stats ===", flush=True)
print(f"Total Nodes: {len(nodes)}", flush=True)
print(f"Total Edges: {len(edges)}", flush=True)

node_types = {}
for n, d in nodes:
    nt = d.get("node_type", "UNKNOWN")
    node_types[nt] = node_types.get(nt, 0) + 1
for nt, cnt in sorted(node_types.items()):
    print(f"  - Node '{nt}': {cnt}", flush=True)

edge_relations = {}
for u, v, d in edges:
    rel = d.get("relation", "UNKNOWN")
    edge_relations[rel] = edge_relations.get(rel, 0) + 1
for rel, cnt in sorted(edge_relations.items()):
    print(f"  - Edge '{rel}': {cnt}", flush=True)

# Save Text Summary
summary_out = os.path.join(out_dir, "ads7891_graph_summary.txt")
with open(summary_out, "w", encoding="utf-8") as f:
    f.write(f"ADS7891 Hardware Knowledge Graph Summary\n{'='*50}\n")
    f.write("Parser: nvidia/nemotron-parse (NVIDIA NIM 32 pages)\n")
    f.write(f"LLM Engine: {model_name} (OpenRouter 100% Free)\n")
    f.write(f"Total Nodes: {len(nodes)} | Total Edges: {len(edges)}\n\n")
    f.write("=== NODE TYPES ===\n")
    for nt, cnt in sorted(node_types.items()):
        f.write(f"  {nt}: {cnt}\n")
    f.write("\n=== EDGE RELATIONS ===\n")
    for rel, cnt in sorted(edge_relations.items()):
        f.write(f"  {rel}: {cnt}\n")
    f.write("\n=== EXTRACTED PINS (Sample) ===\n")
    for p in raw_data.get("pins", [])[:20]:
        f.write(f"  Pin {p.get('name')} (Pin {p.get('pin_number')}): Role={p.get('role')}, Dir={p.get('direction')}\n")
    f.write("\n=== ELECTRICAL PARAMETERS (Sample) ===\n")
    f.writelines(f"  [{s.get('category')}] {s.get('symbol')} ({s.get('name')}): min={s.get('min')}, typ={s.get('typ')}, max={s.get('max')} {s.get('unit')} [p.{s.get('page')}]\n" for s in raw_data.get("electrical_parameters", [])[:25])

print(f"-> Saved Summary to: {summary_out}", flush=True)

# Generate HTML Visualizer
print("\n=== [STEP 5] Generating Interactive HTML Visualizer ===", flush=True)
html_nodes = []
html_edges = []
color_map = {
    "IC": "#6366f1",
    "PIN": "#10b981",
    "FUNCTIONAL_BLOCK": "#f59e0b",
    "SPECIFICATION": "#3b82f6",
    "OPERATING_CONDITION": "#ec4899",
    "UNKNOWN": "#94a3b8"
}

for n, d in nodes:
    nt = d.get("node_type", "UNKNOWN")
    color = color_map.get(nt, "#94a3b8")
    label = d.get("name") or str(n)
    title_lines = [f"<b>{n}</b>", f"Type: {nt}"]
    for k, v in d.items():
        if k not in ("name", "node_type") and v:
            title_lines.append(f"{k}: {v}")
    html_nodes.append({
        "id": str(n),
        "label": label[:22],
        "title": "<br>".join(title_lines),
        "color": color,
        "shape": "box" if nt in ("IC", "FUNCTIONAL_BLOCK") else ("ellipse" if nt == "PIN" else "dot"),
        "size": 26 if nt == "IC" else (18 if nt == "PIN" else 12)
    })

for u, v, d in edges:
    rel = d.get("relation", "")
    html_edges.append({
        "from": str(u),
        "to": str(v),
        "label": rel,
        "arrows": "to",
        "font": {"size": 9, "align": "middle", "color": "#94a3b8"},
        "color": {"color": "#475569", "opacity": 0.6}
    })

html_content = f"""<!DOCTYPE html>
<html lang="ko">
<head>
  <meta charset="UTF-8">
  <title>ADS7891 Hardware Knowledge Graph</title>
  <script type="text/javascript" src="https://unpkg.com/vis-network/standalone/umd/vis-network.min.js"></script>
  <style>
    body {{ margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #0b0f19; color: #f8fafc; overflow: hidden; }}
    #header {{ position: absolute; top: 0; left: 0; right: 0; height: 56px; background: rgba(15, 23, 42, 0.95); border-bottom: 1px solid #1e293b; display: flex; align-items: center; justify-content: space-between; padding: 0 20px; z-index: 10; }}
    h1 {{ font-size: 1.1rem; margin: 0; font-weight: 600; color: #38bdf8; }}
    .badges {{ display: flex; gap: 10px; }}
    .badge {{ background: #1e293b; border: 1px solid #334155; padding: 4px 10px; border-radius: 9999px; font-size: 0.78rem; }}
    #network {{ width: 100vw; height: 100vh; padding-top: 56px; box-sizing: border-box; }}
    #legend {{ position: absolute; bottom: 20px; left: 20px; background: rgba(15, 23, 42, 0.92); border: 1px solid #334155; border-radius: 8px; padding: 12px 16px; font-size: 0.8rem; z-index: 10; backdrop-filter: blur(8px); }}
    .legend-item {{ display: flex; align-items: center; gap: 8px; margin-bottom: 6px; }}
    .legend-item:last-child {{ margin-bottom: 0; }}
    .legend-dot {{ width: 12px; height: 12px; border-radius: 50%; }}
  </style>
</head>
<body>
  <div id="header">
    <h1>ADS7891 Hardware Knowledge Graph (HKG)</h1>
    <div class="badges">
      <div class="badge">Model: <b>{model_name} (100% Free)</b></div>
      <div class="badge">Nodes: <b>{len(nodes)}</b></div>
      <div class="badge">Edges: <b>{len(edges)}</b></div>
      <div class="badge">Parser: <b>Nemotron-Parse (32 Pages)</b></div>
    </div>
  </div>
  <div id="legend">
    <div style="font-weight: 600; margin-bottom: 8px; color: #94a3b8;">Graph Legend</div>
    <div class="legend-item"><span class="legend-dot" style="background: #6366f1;"></span>IC Device</div>
    <div class="legend-item"><span class="legend-dot" style="background: #10b981;"></span>Pin Interface</div>
    <div class="legend-item"><span class="legend-dot" style="background: #f59e0b;"></span>Functional Block</div>
    <div class="legend-item"><span class="legend-dot" style="background: #3b82f6;"></span>Specification</div>
    <div class="legend-item"><span class="legend-dot" style="background: #ec4899;"></span>Operating Condition</div>
  </div>
  <div id="network"></div>
  <script>
    const nodes = new vis.DataSet({json.dumps(html_nodes)});
    const edges = new vis.DataSet({json.dumps(html_edges)});
    const container = document.getElementById('network');
    const data = {{ nodes: nodes, edges: edges }};
    const options = {{
      nodes: {{ borderWidth: 1, font: {{ color: '#f8fafc', face: 'system-ui' }} }},
      edges: {{ smooth: {{ type: 'continuous' }} }},
      physics: {{
        solver: 'forceAtlas2Based',
        forceAtlas2Based: {{ gravitationalConstant: -35, centralGravity: 0.008, springLength: 100, springConstant: 0.08 }},
        stabilization: {{ iterations: 100 }}
      }}
    }};
    new vis.Network(container, data, options);
  </script>
</body>
</html>
"""

html_out = os.path.join(out_dir, "ads7891_interactive_graph.html")
with open(html_out, "w", encoding="utf-8") as f:
    f.write(html_content)
print(f"-> Saved Interactive Visualizer to: {html_out}", flush=True)
print("\n=== BUILD COMPLETE! ===", flush=True)
