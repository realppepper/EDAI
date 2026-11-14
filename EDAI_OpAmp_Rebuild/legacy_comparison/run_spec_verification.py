"""Fresh source-cell checks, then provenance-preserving merge; no API calls."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pymupdf
from opamp_pipeline.pdf_03_render_pages import save_json
from opamp_pipeline.support.source_checks import verify_sources
from opamp_pipeline.legacy_comparison.spec_03_merge_evidence import merge_evidence


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--run-dir',type=Path,required=True)
    args=parser.parse_args();root=args.run_dir
    read=lambda name: json.loads((root/name).read_text(encoding='utf-8'))
    inventory=read('01_pdf_inventory.json')
    candidate=read('06_spec_candidates.json');native=read('06_code_table_evidence.json')
    source=Path(inventory['source_pdf'])
    digest=hashlib.sha256(source.read_bytes()).hexdigest()
    pages={r['source']['pdf_page'] for r in native['rows']}
    with pymupdf.open(source) as doc:
        words={n:doc[n-1].get_text('words') for n in pages}
    checked=verify_sources(candidate,native,words,digest)
    save_json(root/'07_source_verification.json',checked)
    merged=merge_evidence(candidate,native,checked)
    save_json(root/'08_merged_specs.json',merged)
    lines=['# 사양 원문 대조와 통합 결과','',
           '수치·열 위치는 원본 PDF 단어와 다시 대조했습니다. 조건 의미·수식·전체 문서 누락은 아직 검증 완료가 아닙니다.','',
           '| 항목 | 결과 |','|---|---:|']
    for k,v in checked['summary'].items():lines.append(f'| {k} | {v} |')
    lines+=['','## 행별 상태','','| 사양 | 코드 근거 행 | 수치 검사 | 단위 검사 | 최종 상태 |','|---|---|---|---|---|']
    for r in checked['rows']:
        lines.append(f"| {r['candidate_id']} | {r['native_row_id']} | {r.get('numeric_status','mapping conflict')} | {r.get('unit_check',{}).get('status','not checked')} | {r['status']} |")
    lines+=['','통합 JSON은 원본 두 JSON을 덮어쓰지 않습니다. 일치한 수치에는 코드 근거를 연결하고, 이름·조건·복합값은 AI 후보 출처와 미검증 상태를 유지합니다. 충돌 값은 통합 limits에서 비우고 양쪽 원값을 보존합니다.',
            '서로 일치한다는 이유만으로 전체 사양 정확성을 확정하지 않습니다. ready_for_design=false 상태입니다.']
    (root/'07_source_verification.md').write_text('\n'.join(lines),encoding='utf-8')
    print(json.dumps(checked['summary'],ensure_ascii=False))


if __name__=='__main__':main()
