"""Build HKG from current, completed source artifacts; no LLM/API call."""
import argparse
import json
from pathlib import Path
from opamp_pipeline.hkg_01_build import build_hkg
from opamp_pipeline.hkg_02_validate import validate_hkg
from opamp_pipeline.hkg_query import specification_contexts
from opamp_pipeline.pdf_03_render_pages import save_json
from opamp_pipeline.support.execution_state import PipelineExecution,require_current_spec,require_current_references,file_hash


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--run-dir',type=Path,required=True)
    ap.add_argument('--spec-only',action='store_true',help='Build without graph references')
    ap.add_argument('--example-symbol',help='Export a linked context example; symbol comparison is case-sensitive')
    args=ap.parse_args();run=args.run_dir
    inventory_path=run/'01_pdf_inventory.json'
    inventory=json.loads(inventory_path.read_text(encoding='utf-8'))
    spec=run/'spec_pipeline/spec_03_result.json'
    input_path=spec if args.spec_only else run/'chart_pipeline/spec_with_chart_references.json'
    inputs=[inventory_path,input_path,run/'spec_pipeline/STATUS.json',Path(inventory['source_pdf'])]
    if not args.spec_only:inputs.append(run/'chart_pipeline/STATUS.json')
    with PipelineExecution(run/'hkg_pipeline',inputs) as job:
        document=require_current_spec(run,spec) if args.spec_only else require_current_references(run)
        if file_hash(inventory['source_pdf'])!=document['source_sha256']:
            raise ValueError('Original HKG source PDF changed')
        checked_images=set()
        for item in document.get('characteristic_graphs',[]):
            source=item['source'];path=source['page_image_path']
            if path not in checked_images:
                if file_hash(path)!=source['page_image_sha256']:raise ValueError('HKG graph source image changed')
                checked_images.add(path)
        graph=build_hkg(document,inventory['page_count'])
        validation=validate_hkg(graph,document)
        graph['_execution']=job.provenance()
        out=run/'hkg_pipeline'
        save_json(out/'hkg_01_graph.json',graph)
        save_json(out/'hkg_02_validation.json',validation)
        symbol=args.example_symbol or (document['electrical_specs'][0]['symbol'] if document['electrical_specs'] else None)
        contexts=specification_contexts(graph,symbol=symbol) if symbol else []
        save_json(out/'HKG_EXAMPLE_CONTEXT.json',{'symbol':symbol,'contexts':contexts,'effective_conditions_generated':False})
        lines=['# HKG 생성 결과','',
            '기존 검토 결과를 사양·조건·출처·검토 상태의 노드와 관계로 연결했습니다. 새로운 의미 검증이나 설계 목표 채택을 수행한 것은 아닙니다. 원문 온도 범위와 미검증 상태를 유지합니다.', '',
            f"대상: {document['target_product']} / 노드 {graph['summary']['nodes']}개 / 관계 {graph['summary']['edges']}개", '',
            '| 노드 종류 | 개수 |','|---|---:|']
        for kind,count in graph['summary']['node_types'].items():lines.append(f'| {kind} | {count} |')
        lines+=['', '## 연결 방식', '',
            '제품 → 사양 → MIN/TYP/MAX 값·단위·원문 표기',
            '사양 → 공통 조건 / 행별 조건 / 조건 대체·역할 해석',
            '사양 → 원본 PDF 페이지 / 코드·LLM 검토 상태',
            '특성곡선 → 관련 사양 (같은 시험 조건이라는 뜻은 아님)', '',
            '## 사양 목록', '', '| 사양 | 원문 행 ID | MIN | TYP | MAX | 단위 | 원문 쪽 |', '|---|---|---|---|---|---|---:|']
        for row in document['electrical_specs']:
            values=[row['symbol'],row['id'],*[json.dumps(row['limits'][k],ensure_ascii=False) for k in ('min','typ','max')],row['unit'],row['source']['pdf_page']]
            lines.append('| '+' | '.join(str(v).replace('|','∣') for v in values)+' |')
        lines+=['', '## 조회 예시: '+str(symbol), '',
            'HKG_EXAMPLE_CONTEXT.json에 사양값과 연결된 공통/행별 조건, 출처, 검토 상태, 관련 그래프를 함께 저장했습니다.', '',
            '조건은 합성하지 않았으며 사양값·온도 범위·검토 상태가 원본 입력과 동일한지 검사했습니다. 그래프 수치는 계속 자동 설계 사용 금지입니다. 미검증 동작 조건과 동작 제약도 미검증 상태 그대로 보존했습니다.', '',
            'PDG, 신호 인가 일정, 검사 계획, 테스트벤치, 회로 설계는 생성하지 않았습니다.']
        (out/'HKG_REPORT.md').write_text('\n'.join(lines),encoding='utf-8')
        require_current_spec(run,spec) if args.spec_only else require_current_references(run)
        job.complete(out/'hkg_01_graph.json',stage='hkg_built_and_structurally_validated',summary=graph['summary'])
        print(json.dumps({'summary':graph['summary'],'validation':validation,'external_api_calls':0},ensure_ascii=False))


if __name__=='__main__':main()
