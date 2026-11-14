"""Run layout checks and import assistant-authored spec JSON, without AI API calls."""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from opamp_pipeline.pdf_05_check_layout import check_layout
from opamp_pipeline.legacy_comparison.spec_01_extract_rows import ManualJSONExtractor, extract_rows, extract_native_tables


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--run-dir', type=Path, required=True)
    ap.add_argument('--manual-json', type=Path)
    ap.add_argument('--code-tables', action='store_true', help='Read original PDF table cells; no LLM API calls')
    ap.add_argument('--pages', type=int, nargs='+', help='Source pages for this extraction task; otherwise use input_pages in manual JSON')
    args = ap.parse_args()
    checks = check_layout(str(args.run_dir))
    print(json.dumps({'blocked_pages': checks['blocked_pages'], 'review_pages': checks['review_pages']}, ensure_ascii=False))
    if args.code_tables:
        result = extract_native_tables(str(args.run_dir), args.pages)
        print(json.dumps({'native_rows': len(result['rows']), 'review_rows': sum(r['requires_review'] for r in result['rows']),
                          'excluded_rows': len(result['excluded_rows']), 'table_issues': result['table_issues'], 'external_llm_calls': 0}, ensure_ascii=False))
    if args.manual_json:
        manual = json.loads(args.manual_json.read_text(encoding='utf-8'))
        pages = args.pages or manual.get('input_pages')
        if not isinstance(pages, list) or not pages or any(not isinstance(p, int) for p in pages):
            raise ValueError('Specify --pages or a nonempty input_pages list in the manual JSON')
        result = extract_rows(str(args.run_dir), ManualJSONExtractor(str(args.manual_json)), pages)
        print(json.dumps({'electrical_specs': len(result['electrical_specs']), 'format_passed': True,
                          'source_accuracy_verified': False, 'external_llm_calls': 0}, ensure_ascii=False))


if __name__ == '__main__':
    main()
