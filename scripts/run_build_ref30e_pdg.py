import json
import os
import sys
import time

repo_root = os.path.abspath(r"C:\Users\Sera\.gemini\antigravity\worktrees\Project2\graph_analyze_codebase")
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

# Ensure ParseBench is in sys.path
pb_src = os.path.join(repo_root, "parsebench_repo", "src")
if os.path.exists(pb_src) and pb_src not in sys.path:
    sys.path.insert(0, pb_src)

from ai_analog_designer.llm_client import LLMClient
from ai_analog_designer.pdf_to_graph.hardware_kg_builder import (
    HardwareKnowledgeGraphBuilder,
)
from ai_analog_designer.pdf_to_graph.pdf_parser import PDFDatasheetParser
from ai_analog_designer.pdf_to_graph.pdg_extractor import PortDependencyGraphExtractor
from ai_analog_designer.pdf_to_graph.pdg_fidelity_verifier import PDGFidelityVerifier

pdf_path = r"D:\Sera\Documents\2026-2\pre-capstone\Project2\testcases\ref30e.pdf"
out_dir = os.path.join(repo_root, "output_ref30e_pipeline")
os.makedirs(out_dir, exist_ok=True)

openrouter_key = os.getenv("OPENROUTER_API_KEY", "")
model_name = "nvidia/nemotron-3.5-lightning:free"

print(f"=== [STEP 1] Parsing PDF with NVIDIA Nemotron-Parse: {pdf_path} ===", flush=True)
cache_file = os.path.join(out_dir, "parsed_full_document.json")
if os.path.exists(cache_file):
    print(f"-> Loading cached parsed document from {cache_file}...", flush=True)
    with open(cache_file, "r", encoding="utf-8") as f:
        parsed_data = json.load(f)
else:
    print(f"-> Parsing {pdf_path} (max 40 pages, concurrency=4)...", flush=True)
    t_parse = time.time()
    parser = PDFDatasheetParser(max_pages=40, concurrency=4)
    parsed_data = parser.parse_pdf(pdf_path)
    print(f"-> Parsed {parsed_data['processed_pages']}/{parsed_data['total_pages']} pages in {time.time()-t_parse:.1f}s!", flush=True)
    with open(cache_file, "w", encoding="utf-8") as f:
        json.dump(parsed_data, f, indent=2, ensure_ascii=False)

print(f"\n=== [STEP 2] Configuring LLM Client (OpenRouter 100% Free: {model_name}) ===", flush=True)
llm_client = LLMClient(
    api_key=openrouter_key,
    default_model=model_name,
    base_url="https://openrouter.ai/api/v1/chat/completions",
    provider="openrouter",
    request_timeout=120
)
llm_client.fallback_models = []

print("\n=== [STEP 3] Extracting Hardware Knowledge Graph (HKG) ===", flush=True)
t0 = time.time()
kg_builder = HardwareKnowledgeGraphBuilder(
    llm_client=llm_client,
    max_spec_pages=15,
    parallel_spec_calls=4
)
hkg = kg_builder.build_kg_from_parsed_pdf(parsed_data)
elapsed_kg = time.time() - t0
print(f"-> HKG Build Complete in {elapsed_kg:.1f}s!", flush=True)

raw_data = hkg.graph.get("raw_extraction", {})
hkg_json_path = os.path.join(out_dir, "ref30e_knowledge_graph.json")
with open(hkg_json_path, "w", encoding="utf-8") as f:
    json.dump(raw_data, f, indent=2, ensure_ascii=False)

print("\n=== [STEP 4] Extracting Port Dependency Graph (PDG) ===", flush=True)
pdg_extractor = PortDependencyGraphExtractor()
pdg, schedule, levels = pdg_extractor.extract_pdg(hkg)
print(f"-> PDG Nodes: {len(pdg.nodes)}, Edges: {len(pdg.edges)}", flush=True)
print(f"-> Test Sequence Schedule (us): {schedule}", flush=True)

# Save PDG structure
pdg_data = {
    "nodes": [{"id": n, **d} for n, d in pdg.nodes(data=True)],
    "edges": [{"source": u, "target": v, **d} for u, v, d in pdg.edges(data=True)],
    "schedule_us": {k: round(v * 1e6, 3) for k, v in schedule.items()}
}
pdg_json_path = os.path.join(out_dir, "ref30e_pdg.json")
with open(pdg_json_path, "w", encoding="utf-8") as f:
    json.dump(pdg_data, f, indent=2, ensure_ascii=False)

print("\n=== [STEP 5] Running ParseBench-Powered Provenance Fidelity Audit ===", flush=True)
audit_res = PDGFidelityVerifier.audit_pdg(hkg, pdg, schedule)
audit_json_path = os.path.join(out_dir, "ref30e_parsebench_audit.json")
with open(audit_json_path, "w", encoding="utf-8") as f:
    json.dump(audit_res, f, indent=2, ensure_ascii=False)

print("\n--- ParseBench Audit Result ---", flush=True)
print(f"Benchmark Engine: {audit_res.get('benchmark_framework')}", flush=True)
print(f"Fidelity Score: {audit_res.get('fidelity_score_pct')}%", flush=True)
print(f"Status: {audit_res.get('status')}", flush=True)
print(f"Pin Provenance: {audit_res.get('pin_provenance', {}).get('grounded_pct')}% ({audit_res.get('pin_provenance', {}).get('grounded')}/{audit_res.get('pin_provenance', {}).get('pins')})", flush=True)
print(f"Spec Provenance: {audit_res.get('spec_provenance', {}).get('grounded_pct')}% ({audit_res.get('spec_provenance', {}).get('grounded')}/{audit_res.get('spec_provenance', {}).get('specs')})", flush=True)
print(f"Topological Validity (DAG): {audit_res.get('topological_validity', {}).get('is_dag')}", flush=True)
print(f"Edge Origin (Datasheet vs Rule): {audit_res.get('edge_origin', {}).get('datasheet_pct')}%", flush=True)

# Generate Visualizer HTML for REF30E PDG
html_content = f"""<!DOCTYPE html>
<html lang="ko">
<head>
  <meta charset="UTF-8">
  <title>REF30E Port Dependency Graph (PDG)</title>
  <script type="text/javascript" src="https://unpkg.com/vis-network/standalone/umd/vis-network.min.js"></script>
  <style>
    body {{ margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #0b0f19; color: #f8fafc; overflow: hidden; }}
    #header {{ position: absolute; top: 0; left: 0; right: 0; height: 56px; background: rgba(15, 23, 42, 0.95); border-bottom: 1px solid #1e293b; display: flex; align-items: center; justify-content: space-between; padding: 0 20px; z-index: 10; }}
    h1 {{ font-size: 1.1rem; margin: 0; font-weight: 600; color: #38bdf8; }}
    .badges {{ display: flex; gap: 10px; }}
    .badge {{ background: #1e293b; border: 1px solid #334155; padding: 4px 10px; border-radius: 9999px; font-size: 0.78rem; }}
    #network {{ width: 100vw; height: 100vh; padding-top: 56px; box-sizing: border-box; }}
    #audit-panel {{ position: absolute; bottom: 20px; left: 20px; background: rgba(15, 23, 42, 0.92); border: 1px solid #334155; border-radius: 8px; padding: 14px 18px; font-size: 0.82rem; z-index: 10; backdrop-filter: blur(8px); min-width: 260px; }}
    .audit-title {{ font-weight: 700; color: #38bdf8; margin-bottom: 8px; font-size: 0.9rem; }}
    .audit-row {{ display: flex; justify-content: space-between; margin-bottom: 5px; }}
  </style>
</head>
<body>
  <div id="header">
    <h1>REF30E Port Dependency Graph (PDG)</h1>
    <div class="badges">
      <div class="badge">Model: <b>{model_name} (100% Free)</b></div>
      <div class="badge">ParseBench Score: <b>{audit_res.get('fidelity_score_pct')}%</b></div>
      <div class="badge">Status: <b>{audit_res.get('status')}</b></div>
      <div class="badge">PDG Edges: <b>{len(pdg.edges)}</b></div>
    </div>
  </div>
  <div id="audit-panel">
    <div class="audit-title">ParseBench Provenance Audit</div>
    <div class="audit-row"><span>Fidelity Score:</span> <b>{audit_res.get('fidelity_score_pct')}%</b></div>
    <div class="audit-row"><span>Status:</span> <b>{audit_res.get('status')}</b></div>
    <div class="audit-row"><span>Pin Grounded:</span> <b>{audit_res.get('pin_provenance', {}).get('grounded_pct')}%</b></div>
    <div class="audit-row"><span>Spec Grounded:</span> <b>{audit_res.get('spec_provenance', {}).get('grounded_pct')}%</b></div>
    <div class="audit-row"><span>Is DAG:</span> <b>{audit_res.get('topological_validity', {}).get('is_dag')}</b></div>
  </div>
  <div id="network"></div>
  <script>
    const rawNodes = {json.dumps(pdg_data['nodes'])};
    const rawEdges = {json.dumps(pdg_data['edges'])};
    const nodes = new vis.DataSet(rawNodes.map(n => ({{
      id: n.id,
      label: n.id + "\\n[" + (n.role || '') + "]",
      shape: 'box',
      margin: 10,
      color: {{ background: n.role === 'POWER' ? '#ef4444' : (n.role === 'GROUND' ? '#64748b' : (n.role === 'OUTPUT' ? '#10b981' : '#3b82f6')), border: '#f8fafc' }},
      font: {{ color: '#ffffff', face: 'system-ui', size: 13 }}
    }})));
    const edges = new vis.DataSet(rawEdges.map(e => ({{
      from: e.source,
      to: e.target,
      label: e.delay_us ? e.delay_us + ' μs' : '',
      arrows: 'to',
      font: {{ size: 11, color: '#38bdf8', align: 'top' }},
      color: {{ color: e.origin === 'datasheet' ? '#38bdf8' : '#64748b', opacity: 0.8 }}
    }})));
    const container = document.getElementById('network');
    const options = {{
      layout: {{ hierarchical: {{ direction: 'UD', sortMethod: 'directed', levelSeparation: 120, nodeSpacing: 160 }} }},
      physics: false
    }};
    new vis.Network(container, {{ nodes: nodes, edges: edges }}, options);
  </script>
</body>
</html>
"""
html_path = os.path.join(out_dir, "ref30e_pdg_interactive.html")
with open(html_path, "w", encoding="utf-8") as f:
    f.write(html_content)

print(f"\n-> Saved Interactive PDG to: {html_path}", flush=True)
print("=== All Steps Completed Successfully! ===", flush=True)

