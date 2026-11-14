"""Code rows -> semantic enrichment -> integrated-document verification."""
import argparse
import json
from pathlib import Path
from opamp_pipeline.pdf_03_render_pages import save_json
from opamp_pipeline.pdf_05_check_layout import check_layout
from opamp_pipeline.spec_01_build_rows import build_rows,build_enrichment_packet
from opamp_pipeline.spec_02_enrich_rows import ManualAnnotations,apply_enrichment
from opamp_pipeline.spec_03_verify_sources import verify_integrated
from opamp_pipeline.support.source_checks import fingerprint
from opamp_pipeline.support.semantic_review import build_review_packet, ManualSemanticReview
from opamp_pipeline.support.execution_state import PipelineExecution


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--run-dir',type=Path,required=True)
    ap.add_argument('--annotations',type=Path)
    ap.add_argument('--semantic-review',type=Path,help='Chat/API reviewer output for the spec03 review packet')
    args=ap.parse_args()
    inputs=[args.run_dir/n for n in ('01_pdf_inventory.json','02_page_plan.json','03_render_manifest.json')]
    inputs+=sorted((args.run_dir/'pages').glob('page_*.json'))
    inputs += [args.annotations,args.semantic_review]
    with PipelineExecution(args.run_dir/'spec_pipeline',inputs) as job:
        run(args,job)


def run(args,job):
    run=args.run_dir;out=run/'spec_pipeline'
    check_layout(str(run))
    base=build_rows(str(run));save_json(out/'spec_01_rows.json',base)
    packet=build_enrichment_packet(base,str(run));save_json(out/'spec_02_input_packet.json',packet)
    job.update(stage='awaiting_semantic_annotations',base_fingerprint=fingerprint(base))
    if not args.annotations:
        print(json.dumps({'status':'awaiting_semantic_annotations','rows':len(base['electrical_specs']),
                          'packet':str(out/'spec_02_input_packet.json'),'external_llm_calls':0},ensure_ascii=False))
        return
    annotations=ManualAnnotations(str(args.annotations)).annotate(packet)
    enriched=apply_enrichment(base,annotations);save_json(out/'spec_02_enriched_rows.json',enriched)
    job.update(stage='awaiting_integrated_verification',enriched_document_fingerprint=fingerprint(enriched))
    inventory=json.loads((run/'01_pdf_inventory.json').read_text(encoding='utf-8'))
    review_packet=build_review_packet(enriched,inventory['source_pdf'])
    save_json(out/'spec_03_llm_input_packet.json',review_packet)
    review=ManualSemanticReview(args.semantic_review).review(review_packet) if args.semantic_review else None
    final,report=verify_integrated(base,enriched,inventory['source_pdf'],review)
    final['_execution']=job.provenance()
    save_json(out/'spec_03_verification.json',report);save_json(out/'spec_03_result.json',final)
    lines=['# 순차 사양 처리 결과','',
           '코드가 생성한 동일 행에 AI 의미 정보를 보완하고, 통합 결과를 원문과 대조했습니다. 두 개의 독립 사양 목록을 합치는 주 실행 경로는 사용하지 않습니다.','',
           '| 항목 | 결과 |','|---|---:|']
    for k,v in report['summary'].items():lines.append(f'| {k} | {v} |')
    lines+=['','행 ID는 원본 PDF 해시·페이지·행 영역에서 생성합니다. 세 단계에서 ID와 원본 셀 근거는 바뀌지 않습니다.',
            '조건 의미 검토는 아래 LLM 보고서에 별도 표시합니다. 미해결 제안과 전체 문서 누락 검토 등이 남아 ready_for_design=false입니다.',
            '현재 AI 보완은 기존에 채팅 AI가 검토한 의미 정보를 행별 주석으로 옮긴 것입니다. 외부 API 호출은 없습니다.']
    (out/'REPORT.md').write_text('\n'.join(lines),encoding='utf-8')
    condition_lines=['# 조건·각주 및 원문 행 대조', '',
        '이 보고서는 코드 규칙 검사 결과입니다. 추가 LLM 의미 검토는 LLM_SEMANTIC_REVIEW.md에 별도 기록합니다. 검토 필요는 오류 확정이 아닙니다.', '',
        '원본 표 재탐색 범위: '+str(report['source_row_coverage']['scope_pages']),
        '결과에 없는 원본 행: '+str(report['source_row_coverage']['missing_from_document']),
        '같은 표 탐지기를 재사용하므로 문서 전체 누락 없음의 독립 증명은 아닙니다.', '']
    for checked in report['rows']:
        audit=checked['condition_audit']
        condition_lines += [f"## {checked['candidate_id']}", '',
            '원문 행: '+audit['row_condition_evidence'], '',
            '| 구분 | 조건 | JSON 값 | 원문 해석값 | 상태 | 원문 근거 |', '|---|---|---|---|---|---|']
        for field in audit['fields']:
            values=[field['scope'],field['field'],field['claimed'],field['source_value'],field['status'],field['source_excerpt']]
            condition_lines.append('| '+' | '.join(str(v).replace('|','∣') for v in values)+' |')
        condition_lines += ['', '각주 참조: '+str(audit['footnote_references']),
            '각주 관련 원문: '+' / '.join(audit['footnote_context']), '']
    (out/'CONDITIONS_REVIEW.md').write_text('\n'.join(condition_lines),encoding='utf-8')
    semantic_lines=['# LLM 의미 검토', '', '범위: 전기적 특성 후보 행의 조건·상속·각주·수식. 원문 인용의 존재는 코드로 검사하지만 LLM 판단의 정확성을 보증하지는 않습니다.',
        '검토자: '+json.dumps(report['semantic_review']['reviewer'],ensure_ascii=False), '']
    for checked in report['rows']:
        review_row=checked['llm_semantic_review']
        semantic_lines += [f"## {checked['candidate_id']} — {review_row['status']}", '']
        for dimension,check in review_row.get('checks',{}).items():
            semantic_lines.append(f"- {dimension}: {check['verdict']} — {check['explanation']}")
            for cite in check.get('evidence',[]):semantic_lines.append(f"  - 원문 {cite['pdf_page']}쪽: {cite['quote']}")
        if review_row.get('suggested_changes'):semantic_lines += ['수정 제안: '+json.dumps(review_row['suggested_changes'],ensure_ascii=False)]
        semantic_lines.append('')
    (out/'LLM_SEMANTIC_REVIEW.md').write_text('\n'.join(semantic_lines),encoding='utf-8')
    table=['# 순차 처리된 사양 후보','',
           '같은 행 ID가 코드 생성 → AI 보완 → 최종 대조 단계에서 유지됩니다. 수치 지지 여부와 전체 설계 사용 가능 여부는 다릅니다. 조건·수식·문서 전체 누락 검토가 남아 있습니다.','',
           '| 행 ID | 사양 | MIN | TYP | MAX | 단위 | 원문 쪽 | 수치 대조 |','|---|---|---|---|---|---|---|---|']
    for row in final['electrical_specs']:
        def show(slot):
            value=row['limits'][slot]
            if value is None:return '—'
            if slot in row.get('printed_notation',{}):return row['printed_notation'][slot]
            return json.dumps(value,ensure_ascii=False) if isinstance(value,dict) else str(value)
        values=[row['id'],row['symbol'],show('min'),show('typ'),show('max'),row['unit'],row['source']['pdf_page'],row['verification'].get('numeric_status','conflict')]
        table.append('| '+' | '.join(str(v).replace('|','∣') for v in values)+' |')
    (out/'SPECIFICATIONS.md').write_text('\n'.join(table),encoding='utf-8')
    job.complete(out/'spec_03_result.json',stage='integrated_document_checked')
    print(json.dumps({'status':'integrated_document_checked','summary':report['summary'],'external_llm_calls':0},ensure_ascii=False))


if __name__=='__main__':main()
