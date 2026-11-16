"""
Dedicated CLI tool to extract and visualize the Port Dependency Graph (PDG) from any IC datasheet PDF.
Outputs Mermaid DAG, terminal activation schedule, and generates interactive HTML simulator.
"""

import argparse
import logging
import os
import re
import sys
import webbrowser

from ai_analog_designer.pdf_to_graph import PDGVisualizer

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("PDGVisualizerCLI")

def main():
    parser = argparse.ArgumentParser(description="Extract and visualize the Port Dependency Graph (PDG) from an analog IC datasheet.")
    parser.add_argument("--pdf", help="Path to datasheet PDF.")
    parser.add_argument("--sample", help="Name of sample IC (e.g. LM358, NE555, TL431, LM393, LM317, LM386, INA128, OPA2134, TLC2932A).")
    parser.add_argument("--output-html", help="Path to export interactive HTML visualizer.")
    parser.add_argument("--open", action="store_true", help="Automatically open generated HTML in web browser.")
    args = parser.parse_args()

    pdf_path = None
    if args.pdf:
        pdf_path = os.path.abspath(args.pdf)
    elif args.sample:
        candidate = os.path.join("testcases", f"{args.sample.lower()}.pdf")
        if os.path.exists(candidate):
            pdf_path = os.path.abspath(candidate)
        else:
            print(f"Error: Sample IC '{args.sample}' not found in testcases/.")
            sys.exit(1)
    else:
        print("Error: Please provide --pdf <path> or --sample <name>.")
        sys.exit(1)

    if not os.path.exists(pdf_path):
        print(f"Error: Datasheet file not found at: {pdf_path}")
        sys.exit(1)

    print("\n" + "="*80)
    print(f"🔍 EXTRACTING PORT DEPENDENCY GRAPH (PDG) FROM: {os.path.basename(pdf_path)}")
    print("="*80 + "\n")

    res = PDGVisualizer.extract_from_pdf(pdf_path)
    ic_name = res["ic_info"].get("name", "ANALOG_IC")
    pins = res["pins"]
    schedule = res["schedule"]

    print(f"🔹 Target IC: {ic_name}")
    print(f"🔹 Total Pins Extracted: {len(pins)}")
    print("\n📅 Pin Activation Schedule \u03c3(p):")
    print(f"{'Pin Name':<12} | {'Role':<12} | {'Direction':<12} | {'Settling Delay':<12}")
    print("-" * 55)
    for p in pins:
        pname = p["name"]
        role = p.get("role", "SIGNAL").upper()
        direction = p.get("direction", "INPUT")
        delay_us = schedule.get(pname, 0.0) * 1e6
        print(f"{pname:<12} | {role:<12} | {direction:<12} | {delay_us:.2f} \u03bcs")

    print("\n📊 Mermaid Diagram Topology:")
    mermaid = PDGVisualizer.to_mermaid(pins, schedule, pdg=res.get("pdg"))
    print(mermaid)

    # Export interactive HTML
    safe_ic_name = re.sub(r'[^a-zA-Z0-9_\-]', '_', ic_name)
    out_html = args.output_html or os.path.abspath(os.path.join("benchmark_results", f"{safe_ic_name}_PDG_VISUALIZER.html"))
    PDGVisualizer.export_interactive_html(pdf_path, out_html)
    print("\n" + "="*80)
    print(f"🎉 Interactive PDG HTML Simulator Exported: file:///{out_html.replace(os.sep, '/')}")
    print("="*80 + "\n")

    if args.open:
        webbrowser.open(f"file:///{out_html}")

if __name__ == "__main__":
    main()
