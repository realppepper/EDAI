"""
EDAI 설계 UI 서버 (파이썬 기본 웹 서버만 씀, 추가 설치 없음).

    새 설계: 데이터시트 PDF 를 올리면 runs/<날짜_시각_이름>/ 을 만들고 pipeline.py 를 따로 돌린다
    지난 결과 불러오기: runs/ 아래 실행 폴더 목록. 팀원에게 받은 실행 폴더도 runs/ 에 넣으면 목록에 나온다
    결과 보기: 실행 폴더의 report.html 을 그대로 보여 준다 (폴더만 있으면 더블클릭으로도 열림)

사용법 (WSL 가상환경, 프로젝트 폴더에서):
    ~/.venvs/edai/bin/python ui_server.py          그 뒤 브라우저에서 http://localhost:8765
"""

import json
import os
import re
import shutil
import signal
import subprocess
import sys
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

# 기록 시간은 한국 시간으로. 팀원 서버(Daytona)는 UTC 라 9시간 이르게 찍혔다 (2026-11-27). 하위 과정(하네스 등)도 물려받는다
os.environ["TZ"] = os.environ.get("EDAI_TZ", "Asia/Seoul")
if hasattr(time, "tzset"):
    time.tzset()

HERE = Path(__file__).resolve().parent
RUNS_DIR = HERE / "runs"
UI_FILE = HERE / "ui" / "index.html"
HOST, PORT = "127.0.0.1", 8765
MAX_PDF_BYTES = 50 * 1024 * 1024
DATASHEET_DIR = HERE / "datasheets"              # 준비된 데이터시트 (catalog.json 이 목록과 설명)
import make_run_report                           # noqa: E402  실행 이름 형식 (run_info)
from pipeline import STEPS                       # noqa: E402  단계 이름표
STEP_KEYS = tuple(k for k, _ in STEPS)
CONTENT_TYPES = {".html": "text/html; charset=utf-8", ".json": "application/json; charset=utf-8",
                 ".svg": "image/svg+xml", ".png": "image/png", ".pdf": "application/pdf",
                 ".txt": "text/plain; charset=utf-8", ".cir": "text/plain; charset=utf-8"}


def suggest_from(steps: list) -> str:
    """다시 돌릴 때 기본으로 고를 단계: 실패한 단계. 단, 구조 고르기가 '동작한 후보 없음'으로 실패했으면
    그 앞의 실패한 구조 고치기(LLM)부터 (고르기만 다시 하면 같은 이유로 바로 다시 실패한다)."""
    failed = next((x for x in steps if x["state"] == "fail"), None)
    if failed is None:
        return next((x["key"] for x in steps if x["state"] != "done"), STEP_KEYS[0])
    if failed["key"] == "rank" and "동작한 후보" in (failed.get("error") or ""):
        return "fix"
    return failed["key"]


WAITING_REFRESH_S = 3


def waiting_page(run_dir: Path) -> str:
    """결과 화면 파일(report.html)이 아직 없을 때 보여 줄 화면. 단계 목록이 있으면 그대로 그리고, 3초마다 다시 읽는다.
    실행을 시작한 직후 화면이 파일보다 먼저 열려 'not found' 가 1단계 내내(약 6분) 남던 문제 (2026-11-27)."""
    try:
        if not (run_dir / "status.json").exists():
            raise FileNotFoundError("단계 기록이 아직 없음")
        return make_run_report.render(run_dir).replace(
            "<head>", f"<head><meta http-equiv='refresh' content='{WAITING_REFRESH_S}'>", 1)
    except Exception:
        pass
    return f"""<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta http-equiv="refresh" content="{WAITING_REFRESH_S}"><meta name="viewport" content="width=device-width, initial-scale=1">
<style>
:root {{ --bg:#fff; --fg:#1d2330; --muted:#6b7280; --accent:#2856c7; }}
@media (prefers-color-scheme: dark) {{ :root {{ --bg:#15181e; --fg:#e7e9ee; --muted:#9aa3b2; --accent:#7aa2ff; }} }}
body {{ margin:0; background:var(--bg); color:var(--fg); font:15px/1.6 "Malgun Gothic","Apple SD Gothic Neo",sans-serif;
  display:grid; place-items:center; min-height:100vh; }}
.box {{ text-align:center; }} .sub {{ color:var(--muted); font-size:13px; }}
.spin {{ width:28px; height:28px; border:3px solid var(--muted); border-top-color:var(--accent); border-radius:50%;
  margin:0 auto 12px; animation:r 1s linear infinite; }}
@keyframes r {{ to {{ transform:rotate(360deg); }} }}
@media (prefers-reduced-motion: reduce) {{ .spin {{ animation:none; }} }}
</style></head><body><div class="box"><div class="spin" aria-hidden="true"></div>
<div>설계를 시작하는 중이에요</div><div class="sub">데이터시트를 읽기 시작하면 단계별 진행이 여기에 나와요</div></div></body></html>"""


def datasheet_catalog() -> list:
    """datasheets/catalog.json 의 묶음 목록. 파일이 없는 항목은 뺀다."""
    catalog = DATASHEET_DIR / "catalog.json"
    if not catalog.exists():
        return []
    groups = json.loads(catalog.read_text(encoding="utf-8")).get("groups", [])
    return [{"title": g["title"], "items": [x for x in g["items"] if (DATASHEET_DIR / x["file"]).is_file()]}
            for g in groups]


def run_list() -> list:
    """runs/ 아래 실행 폴더 (최근 것 먼저)."""
    out = []
    for d in sorted(RUNS_DIR.glob("*"), reverse=True):
        status_file = d / "status.json"
        if not d.is_dir() or not status_file.exists():
            continue
        try:
            s = json.loads(status_file.read_text(encoding="utf-8"))
        except ValueError:
            continue
        steps = s.get("steps", [])
        titles = dict(STEPS)
        for x in steps:
            x["title"] = titles.get(x["key"], x["title"])
        harness = next((x for x in steps if x["key"] == "harness"), {})
        current = next((x["title"] for x in steps if x["state"] in ("run", "fail")), None)
        info = make_run_report.run_info(d)
        out.append({"id": d.name, "title": info["title"], "memo": info["memo"], "when": info["when"],
                    "state": s.get("state"), "started": s.get("started"),
                    "done": sum(x["state"] == "done" for x in steps), "total": len(steps), "current": current,
                    "pass_rate": (harness.get("summary") or {}).get("pass_rate"),
                    "steps": [{"key": x["key"], "title": x["title"], "state": x["state"]} for x in steps],
                    "suggest_from": suggest_from(steps)})
    return out


from extract_datasheet import AV_DIR             # noqa: E402  박준석 시스템 폴더 (저장소 루트)
SEED_DIR = AV_DIR / "harness2_library" / "operational_amplifier"   # run_harness.py 가 잠깐 넣는 씨앗
STOP_WAIT_S = 15


def pipeline_pids(run_dir: Path) -> list:
    """이 실행 폴더를 돌리고 있는 pipeline.py 프로세스 (WSL /proc 에서 찾음)."""
    out = []
    for proc in Path("/proc").glob("[0-9]*"):
        try:
            args = (proc / "cmdline").read_bytes().split(b"\0")
        except OSError:
            continue
        text = [a.decode("utf-8", "replace") for a in args]
        if any(a.endswith("pipeline.py") for a in text) and any(Path(a).name == run_dir.name for a in text if a):
            out.append(int(proc.name))
    return out


def stop_pipeline(run_dir: Path) -> bool:
    """돌고 있는 과정을 멈춘다 (하네스·ngspice 같은 자식 프로세스까지). 멈춘 단계는 '실패: 사용자가 멈춤'으로 적고,
    하네스 씨앗 폴더를 지운다 (강제로 끊으면 run_harness.py 가 못 지움). 멈춘 것이 있었으면 True."""
    pids = pipeline_pids(run_dir)
    for pid in pids:
        try:
            os.killpg(os.getpgid(pid), signal.SIGTERM)
        except OSError:
            pass
    deadline = time.time() + STOP_WAIT_S
    while pids and time.time() < deadline and pipeline_pids(run_dir):
        time.sleep(0.5)
    for pid in pipeline_pids(run_dir):
        try:
            os.killpg(os.getpgid(pid), signal.SIGKILL)
        except OSError:
            pass
    status_file = run_dir / "status.json"
    if status_file.exists():
        status = json.loads(status_file.read_text(encoding="utf-8"))
        if status.get("state") == "running":
            for step in status["steps"]:
                if step["state"] == "run":
                    step.update(state="fail", error="사용자가 멈춤")
            status["state"] = "failed"
            status_file.write_text(json.dumps(status, ensure_ascii=False, indent=1), encoding="utf-8")
    try:
        part = json.loads((run_dir / "hkg.json").read_text(encoding="utf-8"))["ic_device"]["name"]
        shutil.rmtree(SEED_DIR / ("EDAI_" + re.sub(r"\W", "_", str(part)).upper()), ignore_errors=True)
    except (OSError, ValueError, KeyError):
        pass
    if pids:
        with open(run_dir / "log.txt", "a", encoding="utf-8") as f:
            f.write(f"[{time.strftime('%H:%M:%S')}] 사용자가 멈춤\n")
        make_run_report.write(run_dir)
    return bool(pids)


def start_pipeline(run_dir: Path, start: str = None, reparse: bool = False) -> None:
    """reparse: 저장된 PDF 읽기 결과를 쓰지 않고 PDF 를 새로 읽는다 (1단계부터 다시 돌릴 때만 뜻이 있음)."""
    cmd = [sys.executable, str(HERE / "pipeline.py"), str(run_dir)] + (["--from", start] if start else [])         + (["--reparse"] if reparse else [])
    log = open(run_dir / "pipeline_stdout.txt", "a", encoding="utf-8")
    subprocess.Popen(cmd, cwd=HERE, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)


class Handler(BaseHTTPRequestHandler):
    def send(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def send_json(self, data, code: int = 200) -> None:
        self.send(code, json.dumps(data, ensure_ascii=False).encode("utf-8"), CONTENT_TYPES[".json"])

    def do_GET(self) -> None:
        url = urllib.parse.urlparse(self.path)
        path = urllib.parse.unquote(url.path)
        if path in ("/", "/index.html"):
            return self.send(200, UI_FILE.read_bytes(), CONTENT_TYPES[".html"])
        if path == "/api/runs":
            return self.send_json(run_list())
        if path == "/api/zip":                     # 최종 회로 ZIP (넷리스트 + 회로도 PNG + 설명.txt), final_zip.py
            query = dict(urllib.parse.parse_qsl(url.query))
            run_dir = (RUNS_DIR / query.get("id", "")).resolve()
            if run_dir.parent != RUNS_DIR.resolve() or not run_dir.is_dir():
                return self.send_json({"error": "실행을 찾지 못했어요"}, 404)
            import final_zip
            try:
                name, data = final_zip.build(run_dir)
            except ValueError as error:
                return self.send_json({"error": str(error)}, 409)
            self.send_response(200)
            self.send_header("Content-Type", "application/zip")
            self.send_header("Content-Disposition", "attachment; filename=\"final.zip\"; "
                             f"filename*=UTF-8''{urllib.parse.quote(name)}")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        if path == "/api/datasheets":              # 준비된 데이터시트 목록 (파일이 있는 것만)
            return self.send_json(datasheet_catalog())
        if path.startswith("/datasheets/"):         # 고른 데이터시트 PDF (화면이 받아서 /api/run 으로 다시 올림)
            target = (DATASHEET_DIR / path[len("/datasheets/"):]).resolve()
            if target.parent == DATASHEET_DIR.resolve() and target.suffix.lower() == ".pdf" and target.is_file():
                return self.send(200, target.read_bytes(), CONTENT_TYPES[".pdf"])
        if path.startswith("/runs/"):
            target = (RUNS_DIR / path[len("/runs/"):]).resolve()
            if RUNS_DIR.resolve() in target.parents and target.is_file():
                return self.send(200, target.read_bytes(), CONTENT_TYPES.get(target.suffix.lower(), "application/octet-stream"))
            # 실행을 막 시작해 결과 화면 파일이 아직 없으면 'not found' 대신 진행 중 화면 (몇 초 뒤 다시 읽음)
            if target.name == "report.html" and target.parent.parent == RUNS_DIR.resolve() and target.parent.is_dir():
                return self.send(200, waiting_page(target.parent).encode("utf-8"), CONTENT_TYPES[".html"])
        self.send(404, b"not found", "text/plain")

    def do_POST(self) -> None:
        url = urllib.parse.urlparse(self.path)
        query = dict(urllib.parse.parse_qsl(url.query))
        if url.path == "/api/run":                  # 본문 = PDF 파일 그대로
            size = int(self.headers.get("Content-Length") or 0)
            if not 0 < size <= MAX_PDF_BYTES:
                return self.send_json({"error": "PDF 크기가 0 이거나 너무 큽니다"}, 400)
            data = self.rfile.read(size)
            if not data.startswith(b"%PDF"):
                return self.send_json({"error": "PDF 파일이 아닙니다"}, 400)
            title = (query.get("title") or "datasheet").strip()[:60].upper()   # 분석이 끝나면 부품 이름으로 바뀜
            slug = re.sub(r"[^a-z0-9]+", "_", title.lower()).strip("_") or "chip"
            run_id = f"{time.strftime('%Y%m%d_%H%M%S')}_{slug}"
            run_dir = RUNS_DIR / run_id
            run_dir.mkdir(parents=True)
            (run_dir / "datasheet.pdf").write_bytes(data)
            (run_dir / "input.json").write_text(json.dumps(
                {"title": title, "name": f"ui_{run_id}", "pdf_name": query.get("filename")}, ensure_ascii=False, indent=1),
                encoding="utf-8")
            start_pipeline(run_dir)
            return self.send_json({"id": run_id})
        if url.path == "/api/memo":                 # 본문 = 메모 글 (input.json 에 저장, 실행 중이어도 덮어써지지 않음)
            run_dir = RUNS_DIR / query.get("id", "")
            inp_file = run_dir / "input.json"
            if not inp_file.exists() or run_dir.resolve().parent != RUNS_DIR.resolve():
                return self.send_json({"error": "실행 폴더가 없습니다"}, 400)
            raw = self.rfile.read(int(self.headers.get("Content-Length") or 0))
            try:
                memo = raw.decode("utf-8")
            except UnicodeDecodeError:                # 브라우저는 UTF-8. 윈도우 도구가 보낸 글자도 받아 줌
                memo = raw.decode("cp949", errors="replace")
            memo = memo.strip()[:80]
            inp = json.loads(inp_file.read_text(encoding="utf-8"))
            inp["memo"] = memo
            inp_file.write_text(json.dumps(inp, ensure_ascii=False, indent=1), encoding="utf-8")
            make_run_report.write(run_dir)
            return self.send_json({"id": run_dir.name, "memo": memo})
        if url.path == "/api/rerun":                # 고른 단계부터 다시 (돌고 있으면 멈춘 뒤)
            run_dir = RUNS_DIR / query.get("id", "")
            start = query.get("from")
            if not (run_dir / "input.json").exists() or start not in STEP_KEYS:
                return self.send_json({"error": "실행 폴더나 단계 이름이 잘못됐습니다"}, 400)
            stop_pipeline(run_dir)                  # 돌고 있으면 멈추고 다시
            start_pipeline(run_dir, start, reparse=query.get("reparse") == "1" and start == "extract")
            return self.send_json({"id": run_dir.name})
        if url.path == "/api/stop":                 # 돌고 있는 과정 멈추기
            run_dir = RUNS_DIR / query.get("id", "")
            if not (run_dir / "input.json").exists() or run_dir.resolve().parent != RUNS_DIR.resolve():
                return self.send_json({"error": "실행 폴더가 없습니다"}, 400)
            return self.send_json({"id": run_dir.name, "stopped": stop_pipeline(run_dir)})
        self.send(404, b"not found", "text/plain")

    def log_message(self, fmt, *args) -> None:      # 목록 새로 읽기 요청이 많아 화면 기록은 끔
        pass


def main() -> None:
    RUNS_DIR.mkdir(exist_ok=True)
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"EDAI UI: http://localhost:{PORT}  (끄려면 Ctrl+C)", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
