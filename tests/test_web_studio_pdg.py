"""
Browser end-to-end test for the Web Studio (Playwright, real Chromium).

Covers:
  1. page loads, sample list is populated from /api/samples
  2. selecting a datasheet and clicking "Extract & Visualize PDG" renders the SVG graph + pin table
  3. the PDG timeline slider updates pin states
  4. /api/extract_pdg refuses paths outside testcases/ and uploads/ (path sandbox)
  5. (optional, --generate) launching a design task moves the status pill out of Idle

Usage:
  python tests/test_web_studio_pdg.py                  # PDG flow + sandbox
  python tests/test_web_studio_pdg.py --generate 1     # also start a 1-iteration synthesis
"""
import argparse
import os
import subprocess
import sys
import time
import urllib.parse
import urllib.request

from playwright.sync_api import expect, sync_playwright

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SHOTS = os.path.join(ROOT, "benchmark_results", "web_studio")


def wait_server(url, timeout=40):
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            with urllib.request.urlopen(url, timeout=2) as r:
                if r.status == 200:
                    return True
        except Exception:
            time.sleep(0.5)
    return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8766)
    ap.add_argument("--ic", default="LM393", help="sample IC to visualize")
    ap.add_argument("--generate", type=int, default=0, help="also start a design task with N iterations")
    ap.add_argument("--timeout", type=int, default=480)
    args = ap.parse_args()
    os.makedirs(SHOTS, exist_ok=True)

    log_path = os.path.join(SHOTS, "studio_server.log")
    log_file = open(log_path, "w", encoding="utf-8")
    srv = subprocess.Popen([sys.executable, "-X", "utf8", "run_studio.py", "--port", str(args.port), "--no-open"],
                           cwd=ROOT, stdout=log_file, stderr=subprocess.STDOUT, text=True)
    base = f"http://127.0.0.1:{args.port}"
    try:
        assert wait_server(base + "/api/samples"), "studio server did not start"
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1500, "height": 1100})
            console_errors = []
            page.on("console", lambda m: console_errors.append(m.text) if m.type == "error" else None)
            page.on("pageerror", lambda e: console_errors.append(str(e)))

            page.goto(base, wait_until="networkidle")
            expect(page.locator("#sampleSelect option")).to_have_count(12, timeout=15000)  # placeholder + 11 ICs
            expect(page.locator("#pdgPreviewCard")).to_be_hidden()
            expect(page.locator("#harness2StudioCard")).to_be_visible()
            
            # Verify Harness2 Library loaded experiences
            page.wait_for_selector("#harness2ExpContainer div", timeout=10000)
            exp_count = page.locator("#harness2ExpContainer div").count()
            print(f"[browser] Harness2 library loaded {exp_count} experience cards")
            assert exp_count >= 1, "Harness2 experience cards not rendered"

            page.screenshot(path=os.path.join(SHOTS, "01_home.png"), full_page=True)

            # switch to sample mode first (the select is hidden in upload mode), then pick the IC by label
            page.click("#modeSampleBtn")
            expect(page.locator("#sampleSelect")).to_be_visible()
            page.locator("#sampleSelect").select_option(label=next(
                o for o in page.locator("#sampleSelect option").all_inner_texts() if o.startswith(args.ic)))
            page.click("#btnPreviewPDG")
            expect(page.locator("#pdgPreviewCard")).to_be_visible(timeout=args.timeout * 1000)
            expect(page.locator("#pdgSvgContainer svg")).to_be_visible(timeout=30000)
            n_nodes = page.locator("#pdgSvgContainer svg g.node-pin").count()
            n_rows = page.locator("#pdgTableBody tr").count()
            subtitle = page.locator("#pdgIcNameSubtitle").inner_text()
            print(f"[browser] PDG rendered: {n_nodes} node groups, {n_rows} table rows, subtitle='{subtitle}'")
            assert n_nodes >= 3 and n_rows >= 3, "PDG graph/table not populated"
            page.screenshot(path=os.path.join(SHOTS, "02_pdg_extracted.png"), full_page=True)

            # timeline playback: move slider to the end and confirm at least one pin becomes Active
            page.eval_on_selector("#pdgTimeSlider", "el => { el.value = el.max; el.dispatchEvent(new Event('input')); }")
            page.wait_for_timeout(500)
            active = page.locator("#pdgTableBody span", has_text="Active").count()
            print(f"[browser] timeline: {active} pins active at t=max")
            assert active >= 1, "timeline simulation did not activate any pin"
            page.screenshot(path=os.path.join(SHOTS, "03_timeline_end.png"), full_page=True)

            # path sandbox
            bad = page.request.get(f"{base}/api/extract_pdg?pdf_path=" + urllib.parse.quote(r"C:\Windows\win.ini"))
            print(f"[api] /api/extract_pdg outside root -> HTTP {bad.status}")
            assert bad.status == 400, "path sandbox failed"

            # harness2 API checks
            h2_summary = page.request.get(f"{base}/api/harness2/summary")
            assert h2_summary.status == 200, f"/api/harness2/summary failed: {h2_summary.status}"
            h2_data = h2_summary.json()
            print(f"[api] /api/harness2/summary -> status={h2_data.get('status')}, entries={len(h2_data.get('summary', []))}")

            h2_lib = page.request.get(f"{base}/api/harness2/library")
            assert h2_lib.status == 200, f"/api/harness2/library failed: {h2_lib.status}"
            lib_data = h2_lib.json()
            print(f"[api] /api/harness2/library -> status={lib_data.get('status')}, count={lib_data.get('count')}")
            assert lib_data.get('count', 0) >= 1, "harness2 library should have cached lessons"

            if args.generate:
                page.locator("#maxItersSelect").select_option(str(args.generate))
                page.click("#btnGenerate")
                page.wait_for_function("document.getElementById('taskStatusPill').textContent !== 'Idle'", timeout=30000)
                print(f"[browser] design task started: pill='{page.locator('#taskStatusPill').inner_text()}'")
                page.screenshot(path=os.path.join(SHOTS, "04_task_running.png"), full_page=True)

                page.wait_for_function("['Completed','Failed'].includes(document.getElementById('taskStatusPill').textContent)",
                                       timeout=args.timeout * 1000)
                pill = page.locator("#taskStatusPill").inner_text()
                summary = page.locator("#resultSummaryText").inner_text() if page.locator("#resultSummaryText").count() else ""
                print(f"[browser] task finished: pill='{pill}' summary='{summary[:120]}'")
                page.screenshot(path=os.path.join(SHOTS, "05_task_finished.png"), full_page=True)
                assert pill == "Completed", f"design task ended as {pill}"

            print("[browser] console errors:", console_errors[:5] if console_errors else "none")
            browser.close()
        print("WEB STUDIO E2E: PASS")
    finally:
        srv.terminate()
        try:
            srv.wait(timeout=10)
        except Exception:
            srv.kill()
        try:
            log_file.close()
        except Exception:
            pass


if __name__ == "__main__":
    main()
