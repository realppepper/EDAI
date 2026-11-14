"""Run the first two local-only steps, saving each stage for debugging."""
import argparse
import json
from pathlib import Path
from collections import defaultdict
from opamp_pipeline.pdf_01_inventory import inspect_pdf
from opamp_pipeline.pdf_02_page_plan import plan_pages


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf", required=True)
    ap.add_argument("--target", required=True)
    ap.add_argument("--output", required=True)
    args = ap.parse_args()
    out = Path(args.output).resolve()
    out.mkdir(parents=True, exist_ok=True)
    inventory = inspect_pdf(args.pdf)
    (out / "01_pdf_inventory.json").write_text(json.dumps(inventory, ensure_ascii=False, indent=2), encoding="utf-8")
    plan = plan_pages(inventory, args.target)
    (out / "02_page_plan.json").write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
    groups = defaultdict(list)
    for page in plan["pages"]:
        for role in page["roles"] or ["unclassified"]:
            groups[role].append(page["pdf_page"])
    lines = [f"# {args.target} 문서 탐색 결과", "", f"전체 {inventory['page_count']}쪽을 이미지 변환·API 호출 없이 확인했습니다.",
             "후보 페이지 지도이며 최종 사양 추출 결과가 아닙니다. 모든 페이지의 원문 텍스트를 01_pdf_inventory.json에 보존했습니다.", "",
             "| 정보 종류 | PDF 페이지 |", "|---|---|"]
    for role, numbers in groups.items():
        lines.append(f"| {role} | {', '.join(map(str, numbers))} |")
    lines += ["", "## 페이지별 근거", "", "| 페이지 | 분류 | 근거 제목 | 재확인 필요 |", "|---:|---|---|---|"]
    for page in plan["pages"]:
        titles = list(dict.fromkeys(e["title"] for e in page["evidence"]))
        lines.append(f"| {page['pdf_page']} | {', '.join(page['roles']) or 'unclassified'} | {' / '.join(titles).replace('|','∣')} | {page['requires_review']} |")
    lines += ["", "주의: 범위는 PDF 책갈피의 상하위 관계로 계산했습니다. 같은 페이지에 다른 내용이 함께 있을 수 있으며, 제외 결정을 자동 확정하지 않습니다."]
    (out / "OVERVIEW.md").write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"pages": inventory["page_count"], "mapped": plan["mapped_pages"], "api_calls": 0, "image_renders": 0,
                      "output": str(out), "groups": groups}, ensure_ascii=False))


if __name__ == "__main__":
    main()
