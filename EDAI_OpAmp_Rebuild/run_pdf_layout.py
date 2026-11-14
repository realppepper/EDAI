"""Run steps 3–4 on a saved page plan. Never calls a general-purpose LLM."""
import argparse
import os
from pathlib import Path
import json
from opamp_pipeline.pdf_03_render_pages import render_pages
from opamp_pipeline.pdf_04_parse_layout import parse_layout


def read_nvidia_key(env_file: Path | None) -> str:
    if env_file:
        for line in env_file.read_text(encoding="utf-8-sig").splitlines():
            if line.strip().startswith("#") or "=" not in line:
                continue
            name, value = line.split("=", 1)
            if name.strip() == "NVIDIA_API_KEY":
                return value.strip().strip('"\'')
        raise ValueError("NVIDIA_API_KEY not found in the specified env file")
    return os.getenv("NVIDIA_API_KEY", "")


def write_readable_results(run: Path, summary: dict) -> None:
    lines = ["# 후보 페이지 파싱 결과", "",
             f"선정 {len(summary['requested_pages'])}쪽 / 성공 {len(summary['succeeded_pages'])}쪽 / 실패 {len(summary['failed_pages'])}쪽.",
             "표·텍스트·배치를 읽은 원본 결과입니다. 사양 JSON 추출·원문 값 검증·회로 설계는 아직 실행하지 않았습니다.",
             "이미지는 한 번만 읽고 분류별로 재사용합니다. 원문 전체 텍스트와 단어 좌표는 API에 보내지 않았습니다.", "",
             "| PDF 페이지 | 역할 | 텍스트 문자 수 | 배치 블록 수 | 상태 |", "|---:|---|---:|---:|---|"]
    for number in summary["requested_pages"]:
        path = run / "pages" / f"page_{number:04d}.json"
        if not path.exists():
            continue
        page = json.loads(path.read_text(encoding="utf-8"))
        text = page.get("document_text", "")
        (path.with_suffix(".md")).write_text(f"# 원문 PDF {number}쪽 — Nemotron 파싱 텍스트\n\n"
            "정확성 대조 전의 페이지 파싱 결과입니다. 원본 응답과 배치 좌표는 같은 이름의 JSON에 있습니다.\n\n" + text, encoding="utf-8")
        lines.append(f"| {number} | {', '.join(page.get('roles', []))} | {len(text)} | {len(page.get('blocks', []))} | {page['status']} |")
    lines += ["", "그림·차트 블록을 반환해도 곡선의 정확한 수치화나 회로 연결 복원을 완료한 것은 아닙니다.",
              "이번 호출에 포함하지 않은 재확인 후보 페이지: " + (", ".join(map(str, summary.get("pending_review_pages", []))) or "없음") + ". 원래 목록에는 보존됩니다.",
              "후단 LLM을 부르기 전에 필요한 표·설명 블록만 선택하고 원문과 대조하는 다음 단계를 구성해야 합니다."]
    (run / "LAYOUT_REPORT.md").write_text("\n".join(lines), encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-dir", type=Path, required=True)
    ap.add_argument("--env-file", type=Path)
    ap.add_argument("--render-only", action="store_true")
    args = ap.parse_args()
    run = args.run_dir.resolve()
    rendered = render_pages(str(run / "01_pdf_inventory.json"), str(run / "02_page_plan.json"), str(run))
    if args.render_only:
        print(json.dumps({"rendered_pages": rendered["requested_pages"]}, ensure_ascii=False))
        return
    parsed = parse_layout(str(run / "03_render_manifest.json"), str(run), read_nvidia_key(args.env_file))
    write_readable_results(run, parsed)
    print(json.dumps(parsed, ensure_ascii=False), flush=True)
    if not parsed["all_requested_pages_succeeded"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
