"""Build source-grounded PDG using current-chat annotations; no API invocation."""
import argparse
import json
from pathlib import Path
from opamp_pipeline.pdg_01_build import build_pdg_packet,build_pdg
from opamp_pipeline.pdg_02_validate import validate_pdg
from opamp_pipeline.pdg_03_audit import audit_pdg
from opamp_pipeline.pdg_04_schedule import generate_schedule,policy_templates
from opamp_pipeline.pdg_05_visualize import render_pdg_inspector,diagram_svg
from opamp_pipeline.pdf_03_render_pages import save_json
from opamp_pipeline.support.execution_state import PipelineExecution,require_current_hkg


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--run-dir',type=Path,required=True);ap.add_argument('--annotations',type=Path)
    ap.add_argument('--policy',type=Path,help='Explicit engineering execution policy; never a hidden default timing rule')
    args=ap.parse_args();run=args.run_dir;out=run/'pdg_pipeline'
    inputs=[run/'01_pdf_inventory.json',run/'02_page_plan.json',run/'hkg_pipeline/STATUS.json',run/'hkg_pipeline/hkg_01_graph.json',args.annotations,args.policy]
    with PipelineExecution(out,inputs) as job:
        inventory=json.loads((run/'01_pdf_inventory.json').read_text(encoding='utf-8'))
        job.track_input(inventory['source_pdf'])
        hkg=require_current_hkg(run);plan=json.loads((run/'02_page_plan.json').read_text(encoding='utf-8'))
        packet=build_pdg_packet(hkg,inventory['source_pdf'],plan);save_json(out/'pdg_01_input_packet.json',packet)
        if not args.annotations:
            job.update(stage='awaiting_source_reviewed_port_annotations')
            print(json.dumps({'status':'awaiting_source_reviewed_port_annotations','external_api_calls':0}));return
        annotations=json.loads(args.annotations.read_text(encoding='utf-8'))
        pdg=build_pdg(hkg,packet,annotations);validation=validate_pdg(pdg,hkg,packet,annotations)
        pdg['_execution']=job.provenance();save_json(out/'pdg_01_graph.json',pdg);save_json(out/'pdg_02_validation.json',validation)
        audit=audit_pdg(pdg);save_json(out/'pdg_03_audit.json',audit)
        if audit['status']!='functional_checks_passed':raise ValueError('Channel/coverage audit failed; inspect pdg_03_audit.json')
        policy=json.loads(args.policy.read_text(encoding='utf-8')) if args.policy else None
        templates=policy_templates(pdg);schedule=generate_schedule(pdg,policy)
        save_json(out/'pdg_04_policy_templates.json',templates);save_json(out/'pdg_04_schedule.json',schedule)
        (out/'pdg_05_inspector.html').write_text(render_pdg_inspector(pdg,audit,schedule,templates),encoding='utf-8')
        (out/'pdg_05_graph.svg').write_text(diagram_svg(pdg),encoding='utf-8')
        lines=['# PDG 생성 결과','',
            '원본의 핀·동작 설명을 바탕으로 신호 및 유효 동작 의존관계를 연결했습니다. 전원 인가 순서를 강제하거나 시작 대기 시간을 생성하지 않았습니다.', '',
            f"대상 {pdg['target_product']} / 포트 {pdg['summary']['ports']}개 / 채널 {pdg['summary']['channels']}개 / 노드 {pdg['summary']['nodes']}개 / 관계 {pdg['summary']['dependencies']}개", '',
            '| 포트 | 역할 | 데이터시트 핀 표의 번호 |','|---|---|---|']
        for node in pdg['nodes']:
            if node['type']=='Port':lines.append('| '+node['label']+' | '+node['data']['role']+' | '+json.dumps(node['data'].get('reference_pin_numbers',{}),ensure_ascii=False)+' |')
        lines+=['', '핀 번호는 원본 표의 패키지별 열을 구분한 참고 정보이며 새 IC의 핀 배치나 패키지를 결정한 것이 아닙니다.', '',
            '| 관계 | 종류 | 시간 순서 강제 | 근거 |','|---|---|---|---|']
        lookup={n['id']:n for n in pdg['nodes']}
        for edge in pdg['edges']:
            cites=' / '.join(f"{e['pdf_page']}쪽: {e['quote']}" for e in edge['evidence'])
            lines.append('| '+lookup[edge['source']]['label']+' → '+lookup[edge['target']]['label']+' | '+edge['relation']+' | 아니오 | '+cites.replace('|','∣').replace('\n',' ')+' |')
        lines+=['', '## 순서와 대기 시간', '']
        for item in pdg['ordering_exceptions']:lines.append('- '+item['statement'])
        for item in pdg['open_timing_questions']:lines.append('- 미정: '+item)
        lines+=['', '이 데이터시트의 응용 설명은 입력이 전원보다 먼저 인가될 수 있다고 말합니다. 따라서 반드시 전원 다음 입력이라는 관계를 만들지 않았습니다. 이는 전원 없는 상태에서 임의의 입력을 허용하는 안전 판정이 아니며, 절대 최대 정격 등은 별도로 확인해야 합니다.', '',
            '실제 검사 항목·수치 대기 시간·측정 종료 조건은 검사 정책에서 회로에 맞춰 명시해야 합니다. PDG 원문 관계와 실행 정책은 별도로 저장합니다. 테스트벤치·회로 설계는 생성하지 않았습니다.', '',
            '## 연결·출처 검사', '',
            f"채널 {audit['summary']['channels']}개 / 입력-출력 경로 {audit['summary']['present_signal_paths']}/{audit['summary']['expected_signal_paths']}개 / 교차 채널 오류 {audit['summary']['cross_channel_errors']}개 / 전원 도달 오류 {audit['summary']['unreachable_supply_errors']}개", '',
            '관계 출처: '+json.dumps(audit['summary']['origin_counts'],ensure_ascii=False),
            '누락/오류: '+json.dumps(audit['errors'],ensure_ascii=False),
            '자동 정확도 점수는 계산하지 않았습니다. 이 검사는 관계 누락과 출처 구조를 확인합니다.', '',
            '## 실행 정책과 시각화', '',
            '정책 상태: '+schedule['status'],
            'DC/AC는 분석 작업의 순서이며 과도응답 핀 시간표와 구분합니다. 입력 정책이 없으면 기본 지연을 채우지 않습니다. 정책을 넣어 시간표를 생성해도 회로 바인딩과 동작 조건 게이트가 평가되기 전에는 실행 준비 완료로 표시하지 않습니다.', '',
            '[PDG 검토 화면]('+(out/'pdg_05_inspector.html').resolve().as_posix()+')',
            '[채널·출처 감사 결과]('+(out/'pdg_03_audit.json').resolve().as_posix()+')',
            '[정책 입력 양식]('+(out/'pdg_04_policy_templates.json').resolve().as_posix()+')']
        (out/'PDG_REPORT.md').write_text('\n'.join(lines),encoding='utf-8')
        require_current_hkg(run)
        job.complete(out/'pdg_01_graph.json',stage='pdg_built_audited_and_policy_checked',summary=pdg['summary'],
                     audit_summary=audit['summary'],execution_policy_status=schedule['status'])
        print(json.dumps({'summary':pdg['summary'],'audit':audit['summary'],'policy_status':schedule['status'],'external_api_calls':0},ensure_ascii=False))


if __name__=='__main__':main()
