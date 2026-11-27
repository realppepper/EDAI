"""
보기 전용 웹페이지: 실행 폴더(runs/)의 끝난 결과 화면을 모아 목록 한 장 + 실행별 결과 화면으로 만든다.
새 설계는 할 수 없고 지난 결과만 본다. 서버 없이 올려 두고 링크로 공유하는 용도.

    index.html                     목록 (칩 이름 (번호), 월/일 시:분 · 메모 · 상태 · 하네스 결과) + 고른 결과 화면
    runs/<실행 폴더>/report.html    결과 화면 (그림이 파일 안에 들어 있음)
데이터시트 PDF 와 회로도 SVG/PNG 원본 파일은 넣지 않는다 (제조사 자료, 그림은 결과 화면 안에 이미 있음).

사용법: python make_view_site.py [결과 폴더 (기본 sim_out/view_site)]
"""

import html
import json
import re
import shutil
import sys
from pathlib import Path

import make_run_report

HERE = Path(__file__).resolve().parent
SOURCES = [HERE / "runs", HERE / "samples" / "runs"]
STATE_TEXT = {"running": "진행 중", "done": "완료", "failed": "실패"}


def strip_links(report: str) -> str:
    """보기 전용에서는 열리지 않는 파일 링크(데이터시트 PDF, 회로도 SVG/PNG 원본)와 자동 새로고침을 뺀다."""
    report = re.sub(r" · <a href='datasheet\.pdf'[^>]*>[^<]*</a>", "", report)
    report = re.sub(r" · <a href='schematic/[^']*'>(SVG|PNG)</a>", "", report)
    return re.sub(r"<meta http-equiv='refresh'[^>]*>", "", report)


def collect() -> list:
    runs = []
    for source in SOURCES:
        if not source.is_dir():
            continue
        for d in sorted(source.iterdir()):
            if not (d / "report.html").exists() or not (d / "status.json").exists():
                continue
            status = json.loads((d / "status.json").read_text(encoding="utf-8"))
            if status.get("state") != "done":         # 끝까지 완료된 실행만 (진행 중·실패한 실행은 빼기)
                continue
            info = make_run_report.run_info(d)
            steps = status.get("steps", [])
            harness = next((s for s in steps if s["key"] == "harness"), {})
            runs.append({"id": d.name, "dir": d, "title": info["title"], "chip": info["chip"], "when": info["when"],
                         "memo": info["memo"], "state": status.get("state"), "started": status.get("started") or "",
                         "done": sum(s["state"] == "done" for s in steps), "total": len(steps),
                         "pass_rate": (harness.get("summary") or {}).get("pass_rate"),
                         "harness_line": make_run_report.harness_line(d)})
    return sorted(runs, key=lambda r: r["started"], reverse=True)


def build(out: Path) -> Path:
    shutil.rmtree(out, ignore_errors=True)
    runs = collect()
    for r in runs:
        target = out / "runs" / r["id"]
        target.mkdir(parents=True)
        report = (r["dir"] / "report.html").read_text(encoding="utf-8")
        (target / "report.html").write_text(strip_links(report), encoding="utf-8")
    data = [{k: v for k, v in r.items() if k != "dir"} for r in runs]
    page = (HERE / "ui" / "view.html").read_text(encoding="utf-8")
    page = page.replace("/*RUNS*/[]", json.dumps(data, ensure_ascii=False).replace("</", "<\\/"))
    (out / "index.html").write_text(page, encoding="utf-8")
    print(f"{len(runs)}개 실행 -> {out}")
    return out


if __name__ == "__main__":
    build(Path(sys.argv[1]) if len(sys.argv) > 1 else HERE / "sim_out" / "view_site")
