"""Collect/review typical graphs and attach separate references to spec JSON."""
import argparse
import json
from pathlib import Path
from opamp_pipeline.chart_01_collect import collect_charts,build_chart_review_packet
from opamp_pipeline.chart_02_verify import apply_chart_review,link_to_specs
from opamp_pipeline.pdf_03_render_pages import save_json
from opamp_pipeline.support.execution_state import PipelineExecution,require_current_spec


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--run-dir',type=Path,required=True)
    ap.add_argument('--review',type=Path);ap.add_argument('--spec-document',type=Path)
    args=ap.parse_args()
    inputs=[args.run_dir/n for n in ('01_pdf_inventory.json','02_page_plan.json','03_render_manifest.json')]
    inputs+=sorted((args.run_dir/'pages').glob('page_*.json'))
    inputs+=[args.review]
    with PipelineExecution(args.run_dir/'chart_pipeline',inputs) as job:
        run(args,job)


def run(args,job):
    out=args.run_dir/'chart_pipeline'
    spec_path=args.spec_document or args.run_dir/'spec_pipeline/spec_03_result.json'
    specs=require_current_spec(args.run_dir,spec_path) if spec_path.exists() else None
    candidates=collect_charts(args.run_dir)
    save_json(out/'chart_01_candidates.json',candidates)
    save_json(out/'chart_02_review_packet.json',build_chart_review_packet(candidates))
    review=json.loads(args.review.read_text(encoding='utf-8')) if args.review else None
    references=apply_chart_review(candidates,review)
    references['_graph_execution']=job.provenance()
    save_json(out/'chart_02_references.json',references)
    if specs is not None:
        combined=link_to_specs(specs,references)
        combined['_graph_execution']=job.provenance()
        save_json(out/'spec_with_chart_references.json',combined)
    lines=['# 특성곡선 참고 정보 및 검토 결과','',
        '평가 온도는 25°C이며 원문의 온도·전원·부하 조건은 변경하지 않습니다. 모든 그래프는 참고 자료이며 합격 기준으로 자동 채택하지 않습니다. 메타데이터의 시각 검토와 곡선 전체 수치 검증은 구분합니다.', '',
        '| 그림 | 쪽 | 원문 제목 | 25°C 활용 | 파싱 제목 대조 | 수치 검토 |','|---|---:|---|---|---|---|']
    for g in references['graphs']:
        m=g.get('reviewed_metadata',{});cap=g['source']['caption_candidate'] or {}
        values=[cap.get('figure_number','?'),g['source']['pdf_page'],m.get('title',cap.get('title','?')),
            g.get('evaluation_applicability',{}).get('status','pending'),g.get('parser_caption_check','pending'),g['numeric_data']['status']]
        lines.append('| '+' | '.join(str(v).replace('|','∣') for v in values)+' |')
    for g in references['graphs']:
        m=g.get('reviewed_metadata',{});v=g.get('visual_review',{})
        lines+=['', '## '+m.get('figure_number',g['id'])+' — '+m.get('title','검토 전'),'',v.get('explanation','검토 전'),
            '', '[원본 페이지 이미지]('+Path(g['source']['page_image_path']).as_posix()+')',
            '', '축·범례: '+json.dumps({'axes':m.get('axes'),'traces':m.get('traces')},ensure_ascii=False),
            '원문 조건: '+json.dumps(m.get('conditions'),ensure_ascii=False),
            '조건 대체·스윕·곡선별 연결: '+json.dumps(g.get('condition_annotations'),ensure_ascii=False),
            '수치 검토: '+json.dumps(g['numeric_data'],ensure_ascii=False)]
    (out/'GRAPH_REPORT.md').write_text('\n'.join(lines),encoding='utf-8')
    if specs is not None:
        require_current_spec(args.run_dir,spec_path)
    final_path=out/('spec_with_chart_references.json' if specs is not None else 'chart_02_references.json')
    job.complete(final_path,stage='references_written',review_provided=review is not None,
                 linked_spec_complete=specs is not None,summary=references['summary'])
    print(json.dumps({'summary':references['summary'],'external_api_calls':0},ensure_ascii=False))


if __name__=='__main__':main()
