"""Search IEEE via MCP and prepare source-linked input for the design LLM."""
import argparse,json
from datetime import datetime
from pathlib import Path
from opamp_pipeline.ref_02_retrieve import retrieve
from opamp_pipeline.ref_03_design_context import make_context,make_prompt
from opamp_pipeline.support.execution_state import require_current_hkg,require_current_pdg,file_hash
from opamp_pipeline.support.source_checks import fingerprint
from opamp_pipeline.plan_01_select_targets import select_targets
from opamp_pipeline.plan_04_validate import validate_plan


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--run-dir',type=Path,required=True)
    parser.add_argument('--ieee-env-file',type=Path,required=True);parser.add_argument('--mcp-deps',type=Path,required=True)
    parser.add_argument('--previous-result',type=Path);parser.add_argument('--refresh',action='store_true')
    parser.add_argument('--trigger',choices=['initial','manual','failure'],default='manual')
    args=parser.parse_args();root=Path(__file__).resolve().parent;folder=args.run_dir/'measurement_plan'
    def read(path):return json.loads(path.read_text(encoding='utf-8'))
    hkg=require_current_hkg(args.run_dir);pdg=require_current_pdg(args.run_dir)
    status=read(folder/'STATUS.json');manifest=read(folder/'MEASUREMENT_PLAN.json')
    if not status.get('completed') or fingerprint(manifest)!=status.get('final_document_fingerprint'):
        raise ValueError('Measurement plan is incomplete or changed')
    for item in status['inputs']:
        if file_hash(item['path'])!=item['sha256']:raise ValueError('Measurement plan input changed')
    policy=read(Path(status['inputs'][0]['path']))
    selection=read(folder/'plan_01_target_selection.json');measurements=read(folder/'plan_02_measurements.json')
    if selection!=select_targets(hkg,pdg,policy):raise ValueError('Target selection changed')
    validate_plan(selection,measurements,read(folder/'plan_03_execution_policies.json'),hkg,pdg,policy['engineering_defaults'])
    feedback=None;candidate_text=None
    if args.previous_result:
        previous=read(args.previous_result)
        feedback={k:previous.get(k) for k in ('status','parameters','scope','case_judgments','pm_diagnostic','pm_validation','coverage','limitations','model_warnings')}
        feedback['benchmarks']=[{k:b.get(k) for k in ('name','status','metrics','error')} for b in previous['benchmarks']]
        netlist=args.previous_result.parent/'candidate.inc'
        if file_hash(netlist)!=previous.get('netlist_sha256'):raise ValueError('Candidate netlist changed')
        candidate_text=netlist.read_text(encoding='utf-8')
    if args.trigger=='failure' and not (feedback and (any(not j['passed'] for j in feedback['case_judgments']) or any(b['status']!='executed' for b in feedback['benchmarks']))):
        raise ValueError('Failure search requires an actual failed judgment or execution error')
    out=root/'runs/design_context'/datetime.now().strftime('%Y%m%d_%H%M%S_%f');out.mkdir(parents=True)
    state={'status':'running','trigger':args.trigger,'searches':[],'design_llm_invoked':False,'circuit_changed':False}
    def save():
        temp=out/'RESULT.tmp';temp.write_text(json.dumps(state,indent=2,ensure_ascii=False),encoding='utf-8');temp.replace(out/'RESULT.json')
    save()
    try:
        queries=['"two-stage" AND "operational amplifier" AND "compensation"',
                 '"CMOS" AND "operational amplifier" AND "slew rate" AND "settling"']
        for query in queries:
            state['searches'].append(retrieve(query,3,root/'runs/ieee_reference_cache',args.mcp_deps,args.ieee_env_file,args.refresh));save()
        packet=make_context(measurements,state['searches'],feedback,candidate_text)
        packet['provenance']={'measurement_plan_sha256':file_hash(folder/'MEASUREMENT_PLAN.json'),
            'measurements_sha256':file_hash(folder/'plan_02_measurements.json'),
            'previous_result_sha256':file_hash(args.previous_result) if args.previous_result else None,
            'search_result_fingerprints':[s['content_fingerprint'] for s in state['searches']],
            'search_trigger':args.trigger,'retrieval_after_existing_candidate':bool(candidate_text)}
        (out/'DESIGN_INPUT.json').write_text(json.dumps(packet,ensure_ascii=False,indent=2),encoding='utf-8')
        prompt=make_prompt(packet)
        (out/'DESIGN_PROMPT.json').write_text(json.dumps(prompt,ensure_ascii=False,indent=2),encoding='utf-8')
        state['status']='design_input_prepared' if all(s['ok'] for s in state['searches']) else 'design_input_prepared_with_reference_errors'
        state['unique_papers']=len(packet['reference_papers']);state['external_search_calls']=sum(s['external_search_calls'] for s in state['searches'])
        state['full_packet_characters']=len(json.dumps(packet,ensure_ascii=False,indent=2))
        state['prompt_characters']=len(json.dumps(prompt,ensure_ascii=False,indent=2))
        save()
        lines=['# IEEE MCP 설계 참고자료 연결','',f"상태: {state['status']}",f"검색 계기: {args.trigger}",
               '', '원문 사양·시험 조건·기존 회로·측정 피드백과 IEEE 제목/초록을 DESIGN_INPUT.json으로 묶었습니다. LLM API 호출·회로 수정·SPICE 재실행은 하지 않았습니다.',
               '', '현재 회로를 만든 뒤 검색했습니다. 기존 설계가 이 문헌을 사용해 생성됐다고 소급해서 주장하지 않습니다.',
               '', '## 검색 결과','']
        for paper in packet['reference_papers']:
            lines+=['- ['+paper['title']+']('+paper['url']+') — '+str(paper['year'])+', '+paper['venue']+'; '+paper['id']]
        for search in state['searches']:
            if not search['ok']:lines+=['- 검색 오류: '+str(search['error'])]
        lines+=['','## 적용 범위','',
                '논문 초록은 설계 후보·보상 방식 탐색의 참고 자료입니다. 본문 회로도·수식·소자값은 가져오지 않았고 검증된 지침으로 자동 승격하지 않습니다. 원문 사양·프로젝트 정책·실제 측정 결과가 우선합니다.',
                '', '동일 검색은 저장된 결과를 재사용하고 --refresh로 갱신합니다. 자동 반복 실패 감지·탐색 질의 선택·LLM 모델 호출은 아직 연결하지 않았습니다. failure 트리거는 실제 실패가 있을 때만 허용합니다. 검색 실패도 결과에 남기고 참고자료가 있는 것처럼 처리하지 않습니다.',
                '', 'MCP 실행 라이브러리는 기존 설치의 .integration_deps를 재사용합니다. IEEE 키만 기존 설정 파일에서 읽으며 키나 API 요청 URL은 산출물에 저장하지 않습니다.']
        (out/'REPORT.md').write_text('\n'.join(lines),encoding='utf-8')
        (out.parent/'LATEST.json').write_text(json.dumps({'latest_run':str(out),'packet':str(out/'DESIGN_INPUT.json'),'report':str(out/'REPORT.md')},indent=2),encoding='utf-8')
        print(json.dumps({'status':state['status'],'papers':state['unique_papers'],'external_calls':state['external_search_calls'],'output':str(out)},ensure_ascii=False))
    except Exception as error:
        state.update(status='error',error_type=type(error).__name__);save();raise

if __name__=='__main__':main()
