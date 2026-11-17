"""
Interactive and CLI Interface for On-Demand Autonomous Analog Circuit Synthesis.
Allows users to directly supply any IC datasheet PDF and specify custom natural language
circuit requirements, triggering first-principles AI netlist synthesis and LTspice verification.
"""

import argparse
import logging
import os
import sys
import time

from ai_analog_designer import AutonomousAnalogDesignAgent
from ai_analog_designer.visualization import ProcessVisualizer

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("InteractiveDesigner")

def run_cli_design(pdf_path=None, prompt=None, output_dir=None, iterations=12, open_dashboard=True, reuse_hkg=None):
    if not output_dir:
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        output_dir = os.path.abspath(f"output_design/custom_run_{timestamp}")
    os.makedirs(output_dir, exist_ok=True)

    print("\n" + "="*80)
    print("🚀 STARTING ON-DEMAND AUTONOMOUS ANALOG CIRCUIT SYNTHESIS")
    print(f"📄 Datasheet PDF: {pdf_path or '(None - Pure Natural Language Mode)'}")
    print(f"💬 Natural Language Request: {prompt or '(Standard Datasheet Extraction)'}")
    print(f"🔄 Closed-Loop Iterations: {iterations}")
    print(f"📂 Output Directory: {output_dir}")
    print("="*80 + "\n")

    def progress_callback(phase_num, phase_title, msg):
        print(f"[{time.strftime('%H:%M:%S')}] [Phase {phase_num}: {phase_title}] {msg}")

    agent = AutonomousAnalogDesignAgent(
        output_dir=output_dir,
        max_iterations=iterations,
        reuse_hkg_path=reuse_hkg
    )

    result = agent.run(
        datasheet_pdf_path=pdf_path,
        user_prompt=prompt,
        progress_callback=progress_callback
    )

    summary = result.get("summary", {})
    pass_rate = summary.get("pass_rate_percent", 0.0)
    subckt_name = summary.get("subckt_name", "DUT")

    print("\n" + "="*80)
    print("🎉 CIRCUIT DESIGN & VERIFICATION FINISHED!")
    print(f"🔹 Subcircuit Name: {subckt_name}")
    print(f"🔹 Verification Pass Rate: {pass_rate:.1f}%")
    print(f"🔹 Synthesized Netlist: {summary.get('final_netlist_path', 'N/A')}")

    # Generate visual dashboard
    ic_data = ProcessVisualizer.load_ic_data_from_directory(output_dir)
    if ic_data:
        dash_path = os.path.join(output_dir, f"{ic_data['id']}_VISUAL_DASHBOARD.html")
        ProcessVisualizer.export_dashboard([ic_data], dash_path)
        print(f"🔹 Interactive Visual Dashboard: file:///{dash_path.replace(os.sep, '/')}")
        if open_dashboard:
            try:
                import webbrowser
                webbrowser.open(f"file:///{dash_path}")
            except Exception:
                pass
    print("="*80 + "\n")
    return result

def interactive_terminal_wizard():
    print("\n" + "="*80)
    print("🎯 AUTONOMOUS ANALOG CIRCUIT DESIGN — INTERACTIVE TERMINAL WIZARD")
    print("="*80)

    pdf_in = input("Enter path to IC Datasheet PDF (press Enter to skip if pure prompt): ").strip()
    pdf_path = None
    if pdf_in:
        pdf_path = os.path.abspath(pdf_in.strip("'\""))
        if not os.path.exists(pdf_path):
            print(f"Warning: File not found at {pdf_path}. Proceeding in prompt-only mode.")
            pdf_path = None

    prompt_in = input("\nEnter your natural language circuit requirements / target specs:\n> ").strip()
    if not pdf_path and not prompt_in:
        print("Error: You must provide either a PDF datasheet path or a natural language prompt.")
        sys.exit(1)

    iters_in = input("\nEnter number of closed-loop iterations (default: 10): ").strip()
    iterations = int(iters_in) if iters_in.isdigit() else 10

    run_cli_design(pdf_path=pdf_path, prompt=prompt_in, iterations=iterations, open_dashboard=True)

def main():
    parser = argparse.ArgumentParser(description="On-Demand Autonomous Analog Circuit Synthesis & Verification.")
    parser.add_argument("--pdf", help="Path to custom analog IC datasheet PDF.")
    parser.add_argument("--prompt", help="Natural language circuit specification / custom design requirements.")
    parser.add_argument("--iterations", type=int, default=12, help="Number of closed-loop iterations (default: 12).")
    parser.add_argument("--output-dir", help="Output directory for synthesized netlists & reports.")
    parser.add_argument("--web", action="store_true", help="Launch the Web Studio browser interface.")
    parser.add_argument("--port", type=int, default=8080, help="Port for Web Studio (default: 8080).")
    parser.add_argument("--interactive", action="store_true", help="Launch interactive step-by-step CLI wizard.")
    parser.add_argument("--no-open", action="store_true", help="Do not automatically open browser.")
    parser.add_argument("--reuse-hkg", help="Reuse a cached *_knowledge_graph.json (skips all Phase-1 LLM calls).")

    args = parser.parse_args()

    if args.web:
        from ai_analog_designer.web_studio import StudioServer
        server = StudioServer(port=args.port)
        url = server.start(blocking=False)
        if not args.no_open:
            import webbrowser
            webbrowser.open(url)
        print(f"Web Studio listening at {url}. Press Ctrl+C to terminate.")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\nStopped.")
        return

    if args.interactive or (not args.pdf and not args.prompt):
        interactive_terminal_wizard()
        return

    run_cli_design(
        pdf_path=args.pdf,
        prompt=args.prompt,
        output_dir=args.output_dir,
        iterations=args.iterations,
        open_dashboard=not args.no_open,
        reuse_hkg=args.reuse_hkg
    )

if __name__ == "__main__":
    main()
