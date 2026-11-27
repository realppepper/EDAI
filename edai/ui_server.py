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

HERE = Path(__file__).resolve().parent
RUNS_DIR = HERE / "runs"
UI_FILE = HERE / "ui" / "index.html"
HOST, PORT = "127.0.0.1", 8765
MAX_PDF_BYTES = 50 * 1024 * 1024
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
                    "harness_line": make_run_report.harness_line(d),
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


def start_pipeline(run_dir: Path, start: str = None) -> None:
    cmd = [sys.executable, str(HERE / "pipeline.py"), str(run_dir)] + (["--from", start] if start else [])
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
        if path.startswith("/runs/"):
            target = (RUNS_DIR / path[len("/runs/"):]).resolve()
            if RUNS_DIR.resolve() in target.parents and target.is_file():
                return self.send(200, target.read_bytes(), CONTENT_TYPES.get(target.suffix.lower(), "application/octet-stream"))
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
            start_pipeline(run_dir, start)
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
