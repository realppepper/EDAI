"""Step 5: structural checks, not certification of extracted spec values."""
import hashlib
import json
from pathlib import Path
import re
from .pdf_03_render_pages import save_json
from .support.content_audit import compare_content
from .support.parse_identity import parse_image_issues


def table_warnings(text: str) -> list[str]:
    issues = []
    begins, ends = text.count(r"\begin{tabular}"), text.count(r"\end{tabular}")
    if begins != ends:
        issues.append("Unbalanced LaTeX table boundaries")
    for table in re.finditer(r"\\begin\{tabular\}\{([clr| ]+)\}(.*?)\\end\{tabular\}", text, re.S):
        declared = sum(c in "clr" for c in table.group(1))
        header = table.group(2).split(r"\\", 1)[0]
        if re.search(r"\bMIN\b|\bMAX\b|\bTYP\b", header):
            cells = re.split(r"(?<!\\)&", header)
            expanded = sum(int(m.group(1)) if (m := re.search(r"\\multicolumn\{(\d+)\}", c)) else 1 for c in cells)
            if declared != expanded:
                issues.append(f"Table declares {declared} columns but header expands to {expanded}; do not trust column indices")
    return issues


def check_layout(run_dir: str) -> dict:
    root = Path(run_dir)
    manifest = json.loads((root / "03_render_manifest.json").read_text(encoding="utf-8"))
    inventory = json.loads((root / "01_pdf_inventory.json").read_text(encoding="utf-8"))
    actual_hash = hashlib.sha256(Path(inventory["source_pdf"]).read_bytes()).hexdigest()
    if actual_hash != manifest["source_sha256"] or actual_hash != inventory["sha256"]:
        raise ValueError("Original PDF hash mismatch")
    rows = []
    native_pages = {p['pdf_page']: p for p in inventory['pages']}
    images={p['pdf_page']:p for p in manifest['images']}
    for number in manifest["requested_pages"]:
        fatal, warnings = [], []
        path = root / "pages" / f"page_{number:04d}.json"
        if not path.exists():
            rows.append({"pdf_page": number, "status": "blocked", "fatal": ["Missing page result"], "warnings": []})
            continue
        page = json.loads(path.read_text(encoding="utf-8"))
        response = page.get("raw_response", {})
        text = page.get("document_text", "")
        if page.get("status") != "ok": fatal.append("Page API call did not succeed")
        if response.get("finish_reason") in ("length", "max_tokens"): fatal.append("Truncated response")
        if not text.strip(): fatal.append("Empty document text")
        if page.get("source_sha256") != actual_hash or page.get("pdf_page") != number: fatal.append("Source/page identity mismatch")
        if number not in images:fatal.append('Requested image missing from manifest')
        else:fatal.extend(parse_image_issues(page,images[number],actual_hash))
        warnings.extend(table_warnings(text))
        coverage = compare_content(native_pages[number].get('text', ''), text)
        if coverage['possible_omissions']:
            warnings.append(f"Content comparison needs review: {len(coverage['possible_omissions'])} source lines contain unmatched tokens")
        if not native_pages[number].get('text', '').strip():
            warnings.append('No native text reference; image-based content review required')
        if page.get("requires_finish_reason_review"): warnings.append("Unknown completion reason")
        roles = page.get("roles", [])
        if "target_specs" in roles and not all(t in text.upper() for t in ("MIN", "TYP", "MAX")):
            warnings.append("Expected MIN/TYP/MAX labels not all present")
        rows.append({"pdf_page": number, "status": "blocked" if fatal else "review_required" if warnings else "structure_checks_passed",
                     "fatal": fatal, "warnings": warnings, "content_coverage": coverage,
                     "table_blocks": sum(b["type"] == "table" for b in page.get("blocks", []))})
    result = {"stage": "pdf_05_check_layout", "source_sha256": actual_hash,
              "blocked_pages": [r["pdf_page"] for r in rows if r["fatal"]],
              "review_pages": [r["pdf_page"] for r in rows if r["warnings"]], "pages": rows,
              "verified_spec_accuracy": False,
              "content_coverage_verified": False,
              "scope": "Structural checks and native-text token coverage on requested pages. Unmatched content requires review; charts, scanned text and semantic completeness are not certified."}
    save_json(root / "05_layout_checks.json", result)
    lines = ["# 파싱 구조 검사", "", "원문 사양값의 정확성을 확정하는 검사가 아닙니다.", "",
             "| 페이지 | 상태 | 발견 사항 |", "|---:|---|---|"]
    for row in rows:
        lines.append(f"| {row['pdf_page']} | {row['status']} | {'; '.join(row['fatal'] + row['warnings']) or '구조 검사상 이상 미검출'} |")
    (root / "05_layout_checks.md").write_text("\n".join(lines), encoding="utf-8")
    detail = ['# 파싱 내용 대조', '', '원문 텍스트에 있지만 파싱 결과에서 같은 토큰을 찾지 못한 후보입니다. 표기 변환도 포함되므로 실제 누락 확정이 아닙니다. 그래프·이미지·의미의 완전성은 별도 검토가 필요합니다.', '']
    for row in rows:
        detail += [f"## {row['pdf_page']}쪽", '']
        for issue in row.get('content_coverage', {}).get('possible_omissions', []):
            detail.append(f"- 원문: {issue['source_text']} / 미대응 토큰: {', '.join(issue['missing_tokens'])}")
    (root / '05_content_review.md').write_text('\n'.join(detail), encoding='utf-8')
    return result
