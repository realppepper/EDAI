"""
Web Studio GUI End-to-End (E2E) User Scenario Verification Framework.

Systematizes browser-driven user scenario verification for AnalogVerifier's Web Studio.
Uses Playwright (Chromium) to execute, validate, and document realistic user journeys:
  Scenario 1: Interactive Datasheet Ingestion & PDG Graph Exploration
  Scenario 2: Settling Sequence Timeline Stimulation & Pin Activation
  Scenario 3: Autonomous Closed-Loop Synthesis & Live Verification Tracking
  Scenario 4: Security Path Sandbox Boundary Verification
  Scenario 5: Dual-Harness² Persistent Experience & Knowledge Card Inspection

Outputs timestamped visual artifacts (screenshots) and a comprehensive Markdown report.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime
from typing import Any

from playwright.sync_api import Browser, Page, expect, sync_playwright

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("E2E_GUI_Scenario")

ROOT_DIR = os.path.abspath(os.path.dirname(__file__))
DEFAULT_REPORT_DIR = os.path.join(ROOT_DIR, "benchmark_results", "gui_e2e_scenarios")


def is_server_ready(url: str, timeout_s: float = 2.0) -> bool:
    """Checks if the Web Studio server is reachable and responding."""
    try:
        with urllib.request.urlopen(f"{url}/api/samples", timeout=timeout_s) as resp:
            return resp.status == 200
    except Exception:
        return False


def wait_for_server(url: str, max_wait_s: int = 40) -> bool:
    """Polls until the server becomes ready or timeout expires."""
    t0 = time.time()
    while time.time() - t0 < max_wait_s:
        if is_server_ready(url):
            return True
        time.sleep(0.5)
    return False


class WebStudioGUIScenarioRunner:
    """
    Automated E2E User Scenario Test Suite for Analog Circuit Design Web Studio.
    """

    def __init__(
        self,
        port: int = 8080,
        ic_name: str = "LM393",
        headless: bool = True,
        output_dir: str | None = None,
        generate_iters: int = 0,
        timeout_s: int = 480,
    ):
        self.port = port
        self.ic_name = ic_name
        self.headless = headless
        self.generate_iters = generate_iters
        self.timeout_s = timeout_s
        self.base_url = f"http://127.0.0.1:{self.port}"

        run_id = f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{self.ic_name.lower()}"
        self.output_dir = output_dir or os.path.join(DEFAULT_REPORT_DIR, run_id)
        os.makedirs(self.output_dir, exist_ok=True)

        self.server_proc: subprocess.Popen | None = None
        self.server_spawned_by_runner = False
        self.server_log_file = None

        self.test_results: list[dict[str, Any]] = []
        self.screenshots: list[dict[str, str]] = []

    def start_server_if_needed(self) -> None:
        """Starts the Web Studio process if not already running."""
        if is_server_ready(self.base_url):
            logger.info(f"Connecting to existing Web Studio daemon at {self.base_url}")
            return

        logger.info(f"Starting fresh Web Studio daemon on port {self.port}...")
        log_path = os.path.join(self.output_dir, "web_studio_daemon.log")
        self.server_log_file = open(log_path, "w", encoding="utf-8")
        cmd = [
            sys.executable, "-X", "utf8", "run_studio.py",
            "--port", str(self.port),
            "--no-open"
        ]
        self.server_proc = subprocess.Popen(
            cmd,
            cwd=ROOT_DIR,
            stdout=self.server_log_file,
            stderr=subprocess.STDOUT,
            text=True
        )
        self.server_spawned_by_runner = True

        if not wait_for_server(self.base_url, max_wait_s=30):
            raise RuntimeError(f"Web Studio failed to start within 30s. Inspect: {log_path}")
        logger.info(f"Web Studio daemon is ready at {self.base_url}")

    def stop_server_if_spawned(self) -> None:
        """Cleans up the child server process if started by this runner."""
        if self.server_spawned_by_runner and self.server_proc:
            logger.info("Shutting down spawned Web Studio process...")
            self.server_proc.terminate()
            try:
                self.server_proc.wait(timeout=5)
            except Exception:
                self.server_proc.kill()
        if self.server_log_file:
            try:
                self.server_log_file.close()
            except Exception:
                pass

    def record_step(self, step_name: str, status: str, duration_s: float, details: str = ""):
        self.test_results.append({
            "step": step_name,
            "status": status,
            "duration_s": round(duration_s, 2),
            "details": details
        })
        logger.info(f"[{status}] {step_name} ({duration_s:.2f}s) - {details}")

    def capture_screenshot(self, page: Page, filename: str, caption: str) -> str:
        shot_path = os.path.join(self.output_dir, filename)
        page.screenshot(path=shot_path, full_page=True)
        self.screenshots.append({
            "filename": filename,
            "path": shot_path,
            "caption": caption
        })
        return shot_path

    # =========================================================================
    # SCENARIOS
    # =========================================================================

    def run_all_scenarios(self) -> dict[str, Any]:
        """Executes the complete suite of E2E GUI user scenarios."""
        t_start = time.time()
        self.start_server_if_needed()

        console_errors: list[str] = []

        with sync_playwright() as p:
            browser: Browser = p.chromium.launch(headless=self.headless)
            context = browser.new_context(viewport={"width": 1560, "height": 1150})
            page: Page = context.new_page()

            page.on("console", lambda m: console_errors.append(f"[{m.type}] {m.text}") if m.type in ("error", "warning") else None)
            page.on("pageerror", lambda e: console_errors.append(f"[pageerror] {e!s}"))

            try:
                # -------------------------------------------------------------
                # 1. Home Dashboard & Model Route Ingestion
                # -------------------------------------------------------------
                t0 = time.time()
                page.goto(self.base_url, wait_until="networkidle")
                page.wait_for_function("document.querySelectorAll('#sampleSelect option').length >= 5", timeout=15000)
                sample_count = page.locator("#sampleSelect option").count()
                assert sample_count >= 5, f"Expected at least 5 sample options, found {sample_count}"
                expect(page.locator("#harness2StudioCard")).to_be_visible()
                expect(page.locator("#taskStatusPill")).to_contain_text("Idle")
                self.capture_screenshot(page, "01_home_dashboard.png", "Web Studio Initial Dashboard & Model Route Ingestion")
                self.record_step("Dashboard Initialization", "PASS", time.time() - t0, f"Page loaded, {sample_count} samples populated, status=Idle")

                # -------------------------------------------------------------
                # 2. Dual-Harness² Knowledge Base Verification
                # -------------------------------------------------------------
                t0 = time.time()
                page.wait_for_selector("#harness2ExpContainer div", timeout=10000)
                exp_cards = page.locator("#harness2ExpContainer div").count()
                h2_summary = page.request.get(f"{self.base_url}/api/harness2/summary")
                assert h2_summary.status == 200, "Failed /api/harness2/summary"
                self.record_step("Harness² Knowledge Verification", "PASS", time.time() - t0, f"Rendered {exp_cards} cached experience cards")

                # -------------------------------------------------------------
                # 3. Security Boundary & Path Sandbox Verification
                # -------------------------------------------------------------
                t0 = time.time()
                bad_resp = page.request.get(f"{self.base_url}/api/extract_pdg?pdf_path=" + urllib.parse.quote(r"C:\Windows\win.ini"))
                assert bad_resp.status == 400, f"Path traversal allowed! Got HTTP {bad_resp.status}"
                self.record_step("Security Path Sandbox", "PASS", time.time() - t0, "Rejected unauthorized path traversal with HTTP 400")

                # -------------------------------------------------------------
                # 4. Interactive Datasheet Ingestion & PDG Visualization
                # -------------------------------------------------------------
                t0 = time.time()
                page.click("#modeSampleBtn")
                expect(page.locator("#sampleSelect")).to_be_visible()

                # Select target IC
                options = page.locator("#sampleSelect option").all_inner_texts()
                match_opt = next((o for o in options if o.startswith(self.ic_name)), None)
                if not match_opt:
                    raise ValueError(f"Target IC '{self.ic_name}' not found in sampleSelect: {options}")
                page.locator("#sampleSelect").select_option(label=match_opt)
                self.capture_screenshot(page, "02_sample_selected.png", f"Selected Datasheet Sample ({self.ic_name})")

                # Trigger PDG Extraction
                page.click("#btnPreviewPDG")
                expect(page.locator("#pdgPreviewCard")).to_be_visible(timeout=self.timeout_s * 1000)
                expect(page.locator("#pdgSvgContainer svg")).to_be_visible(timeout=30000)

                n_nodes = page.locator("#pdgSvgContainer svg g.node-pin").count()
                n_rows = page.locator("#pdgTableBody tr").count()
                subtitle = page.locator("#pdgIcNameSubtitle").inner_text()
                assert n_nodes >= 3 and n_rows >= 3, f"Insufficient PDG nodes ({n_nodes}) or rows ({n_rows})"
                self.capture_screenshot(page, "03_pdg_extracted.png", f"PDG Graph and Port Table for {self.ic_name} ({n_nodes} pins)")
                self.record_step("PDG Extraction & SVG Rendering", "PASS", time.time() - t0, f"{n_nodes} SVG nodes, {n_rows} pin rows, title='{subtitle}'")

                # -------------------------------------------------------------
                # 5. Settling Sequence Timeline Simulation
                # -------------------------------------------------------------
                t0 = time.time()
                page.eval_on_selector("#pdgTimeSlider", "el => { el.value = el.max; el.dispatchEvent(new Event('input')); }")
                page.wait_for_timeout(600)
                active_pins = page.locator("#pdgTableBody span", has_text="Active").count()
                assert active_pins >= 1, "Timeline stimulation failed to activate any pin"
                self.capture_screenshot(page, "04_timeline_stimulated.png", f"Settling Timeline at T_max ({active_pins} pins active)")
                self.record_step("Settling Timeline Simulation", "PASS", time.time() - t0, f"{active_pins} pins activated at T_max")

                # -------------------------------------------------------------
                # 6. Autonomous Closed-Loop Synthesis (Optional / Generative)
                # -------------------------------------------------------------
                if self.generate_iters > 0:
                    t0 = time.time()
                    page.locator("#maxItersSelect").select_option(str(self.generate_iters))
                    prompt_text = f"Synthesize pure transistor level topology for {self.ic_name} with verified bias."
                    page.fill("#userPromptInput", prompt_text)
                    page.click("#btnGenerate")

                    # Wait for task transition from Idle
                    page.wait_for_function("document.getElementById('taskStatusPill').textContent !== 'Idle'", timeout=30000)
                    running_pill = page.locator("#taskStatusPill").inner_text()
                    self.capture_screenshot(page, "05_task_running.png", f"Autonomous Synthesis In Progress (Status: {running_pill})")

                    # Wait for completion
                    page.wait_for_function(
                        "['Completed', 'Failed'].includes(document.getElementById('taskStatusPill').textContent)",
                        timeout=self.timeout_s * 1000
                    )
                    final_pill = page.locator("#taskStatusPill").inner_text()
                    summary_text = page.locator("#resultSummaryText").inner_text() if page.locator("#resultSummaryText").count() else ""
                    self.capture_screenshot(page, "06_task_completed.png", f"Design Task Finished (Status: {final_pill})")

                    assert final_pill == "Completed", f"Task ended unexpectedly with status: {final_pill}"
                    netlist_code = page.locator("#netlistOutputPre").inner_text()
                    assert ".subckt" in netlist_code.lower() and ".ends" in netlist_code.lower(), "Netlist missing .subckt/.ends markers"
                    self.record_step("Autonomous Synthesis Loop", "PASS", time.time() - t0, f"Task completed: summary='{summary_text[:80]}'")
                else:
                    self.record_step("Autonomous Synthesis Loop", "SKIPPED", 0.0, "Skipped by default (pass --generate N to execute)")

            finally:
                browser.close()
                self.stop_server_if_spawned()

        total_elapsed = round(time.time() - t_start, 2)
        all_passed = all(r["status"] in ("PASS", "SKIPPED") for r in self.test_results)

        summary = {
            "all_passed": all_passed,
            "ic_name": self.ic_name,
            "port": self.port,
            "total_elapsed_s": total_elapsed,
            "timestamp": datetime.now().isoformat(),
            "output_dir": self.output_dir,
            "steps": self.test_results,
            "screenshots": self.screenshots,
            "console_errors_count": len(console_errors),
            "console_errors": console_errors[:10]
        }

        # Save JSON & Markdown report
        self._write_reports(summary)
        return summary

    def _write_reports(self, summary: dict[str, Any]) -> None:
        """Writes both JSON and human-readable Markdown verification reports."""
        json_path = os.path.join(self.output_dir, "e2e_gui_scenario_report.json")
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2, ensure_ascii=False)

        md_path = os.path.join(self.output_dir, "WEB_STUDIO_E2E_VERIFICATION_REPORT.md")
        lines = [
            "# 🖥️ Web Studio GUI End-to-End User Scenario Verification Report",
            f"**Execution Timestamp**: `{summary['timestamp']}` | **Target IC**: `{summary['ic_name']}` | **Status**: `{'✅ ALL PASSED' if summary['all_passed'] else '❌ FAILED'}`\n",
            f"- **Server URL**: `{self.base_url}`",
            f"- **Total Duration**: `{summary['total_elapsed_s']} seconds`",
            f"- **Artifacts Directory**: `{self.output_dir}`\n",
            "---",
            "## 📋 User Journey Step-by-Step Results\n",
            "| Step | Status | Duration | Observation / Assertion Details |",
            "| :--- | :---: | :---: | :--- |",
        ]
        for s in summary["steps"]:
            badge = "✅ PASS" if s["status"] == "PASS" else ("⏭️ SKIPPED" if s["status"] == "SKIPPED" else "❌ FAIL")
            lines.append(f"| **{s['step']}** | {badge} | {s['duration_s']}s | {s['details']} |")

        lines.extend([
            "\n---",
            "## 📸 Visual Artifacts (Playwright Captured Screenshots)\n",
        ])
        for sc in summary["screenshots"]:
            lines.append(f"### {sc['caption']}")
            rel_path = os.path.relpath(sc['path'], self.output_dir).replace("\\", "/")
            lines.append(f"![{sc['caption']}]({rel_path})\n")

        with open(md_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        logger.info(f"E2E GUI Verification Report saved to: {md_path}")


def main():
    parser = argparse.ArgumentParser(description="Run Web Studio GUI End-to-End User Scenarios")
    parser.add_argument("--port", type=int, default=8766, help="Port to run Web Studio daemon on")
    parser.add_argument("--ic", default="LM393", help="Target IC to verify (LM393, LM311, INA128, etc.)")
    parser.add_argument("--headed", action="store_true", help="Launch visible Chromium browser for live inspection")
    parser.add_argument("--generate", type=int, default=0, help="Iterations for full synthesis (0 = skip synthesis)")
    parser.add_argument("--timeout", type=int, default=480, help="Timeout in seconds for synthesis task")
    parser.add_argument("--output-dir", default=None, help="Custom output directory for screenshots and report")
    args = parser.parse_args()

    runner = WebStudioGUIScenarioRunner(
        port=args.port,
        ic_name=args.ic,
        headless=not args.headed,
        output_dir=args.output_dir,
        generate_iters=args.generate,
        timeout_s=args.timeout
    )
    res = runner.run_all_scenarios()
    print("\n" + "=" * 60)
    print(f"WEB STUDIO GUI E2E SCENARIOS: {'PASS ✅' if res['all_passed'] else 'FAIL ❌'}")
    print(f"Elapsed: {res['total_elapsed_s']}s | Report: {res['output_dir']}")
    print("=" * 60)
    if not res["all_passed"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
