"""Build 25 C measurement definitions and per-test execution policies only."""
import argparse
import json
from pathlib import Path
from opamp_pipeline.plan_01_select_targets import select_targets
from opamp_pipeline.plan_02_measurements import build_measurements
from opamp_pipeline.plan_03_execution_policies import build_policies
from opamp_pipeline.plan_04_validate import validate_plan
from opamp_pipeline.pdf_03_render_pages import save_json
from opamp_pipeline.support.execution_state import PipelineExecution,require_current_hkg,require_current_pdg
from opamp_pipeline.support.source_checks import fingerprint


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--run-dir',type=Path,required=True);ap.add_argument('--project-policy',type=Path,required=True)
    args=ap.parse_args();run=args.run_dir;out=run/'measurement_plan'
    inputs=[args.project_policy,run/'hkg_pipeline/hkg_01_graph.json',run/'hkg_pipeline/STATUS.json',
        run/'pdg_pipeline/pdg_01_graph.json',run/'pdg_pipeline/STATUS.json']
    with PipelineExecution(out,inputs) as job:
        hkg=require_current_hkg(run);pdg=require_current_pdg(run)
        policy=json.loads(args.project_policy.read_text(encoding='utf-8'))
        selection=select_targets(hkg,pdg,policy)
        measurements=build_measurements(selection,hkg,policy['engineering_defaults'])
        policies=build_policies(measurements,pdg,policy['engineering_defaults'])
        validation=validate_plan(selection,measurements,policies,hkg,pdg,policy['engineering_defaults'])
        save_json(out/'plan_01_target_selection.json',selection)
        save_json(out/'plan_02_measurements.json',measurements)
        save_json(out/'plan_03_execution_policies.json',policies)
        save_json(out/'plan_04_validation.json',validation)
        manifest={'stage':'measurement_plan_and_policies_created','target_product':hkg['target_product'],
            'project_policy_fingerprint':fingerprint(policy),'input_hkg_fingerprint':fingerprint(hkg),
            'selection_summary':selection['summary'],'measurement_summary':measurements['summary'],'policy_summary':policies['summary'],
            'plan_files':['plan_01_target_selection.json','plan_02_measurements.json','plan_03_execution_policies.json','plan_04_validation.json'],
            'test_plan_generated':True,'testbench_generated':False,'simulations_executed':0,'ready_for_test_execution':False,
            'unimplemented_measurement_adapters_remain_required':True,'_execution':job.provenance()}
        save_json(out/'MEASUREMENT_PLAN.json',manifest)
        lines=['# 25°C 사양별 검사 계획·실행 정책','',
            '이번 산출물은 계획이며 실제 회로/테스트벤치/시뮬레이션 결과가 아닙니다. 원본 42행을 모두 추적하며 제외 이유도 보존합니다. 원문 MIN/MAX와 TYP 채택 프로젝트 목표를 구분합니다.', '',
            '| 항목 | 개수 |','|---|---:|']
        for key,value in selection['summary'].items():lines.append(f'| {key} | {value} |')
        lines+=['', '## 현재 프로젝트에서 검사할 항목','', '| 사양 | 원문 행 | 분석 | 목표 출처 | 목표 | 전원 표본(V) |', '|---|---|---|---|---|---|']
        for item in measurements['measurements']:
            values=[item['symbol'],item['row_id'],','.join(item['method']['analyses']),item['target']['origin'],
                json.dumps(item['target']['rules'],ensure_ascii=False),','.join(str(c['fixture']['supply_voltage_V']) for c in item['cases'])]
            lines.append('| '+' | '.join(str(v).replace('|','∣') for v in values)+' |')
        lines+=['', '## 이번에 별도 검사하지 않는 원문 행','']
        for item in selection['items']:
            if not item['required_in_project']:lines.append('- '+item['source']['symbol']+' / '+item['row_id']+': '+item['decision']['reason'])
        lines+=['', '## 실행 정책','',
            '분석별 정책 수: '+json.dumps(policies['summary'],ensure_ascii=False),
            'DC 동작점·DC 스윕·AC·noise는 시뮬레이터의 분석 작업 순서입니다. 과도응답만 명시적 자극/관찰/종료 시각을 사용합니다. 기본 프로필의 대기/스텝 전이/FFT 관찰 기간은 공학적 설정이며 데이터시트 시작 지연이 아닙니다.', '',
            '## 명시한 가정과 판정 범위','',
            '- 전원 범위는 명시된 값 또는 경계와 선택된 표본(프로젝트 설정)을 검사합니다. 연속 범위 전체를 검증했다고 주장하지 않습니다.',
            '- 온도는25°C만 검사합니다. 전체 온도 범위 한계를 사용할 때도 원문 범위 출처를 남깁니다. TYP는 제조사 보장이 아닌 프로젝트 목표입니다.',
            '- 입력 바이어스/출력 전류의 부호를 단순 signed 비교로 판정하지 않습니다. 방향 확인 후 크기 기준을 사용합니다.',
            '- 정착시간은 입력 전이 종료부터 측정하며, 정착시간 목표값을 시작 대기 시간으로 사용하지 않습니다.',
            '- THD+N은 FFT와 잡음 기여를 모두 요구합니다. 결정론적 FFT만으로 통과시키지 않습니다.',
            '- 저주파 잡음 pp는 대역 필터·관찰 시간·시드 수의 프로젝트 정의가 있습니다. 시간 영역 잡음 지원이 필요하며 RMS를 임의 상수로 pp 변환하지 않습니다.',
            '- 임피던스는 원문의 병렬 R/C 모델을 보존합니다. 적합 주파수 범위와 용량성 부하 안정성 판정은 프로젝트 정의입니다.',
            '- 모든 필요한 검사 어댑터와 모델·단자 바인딩이 구현/검증되기 전에는 미실행입니다. 미구현 항목을 통과율 분모에서 조용히 빼지 않습니다.', '',
            '## 중단 범위','', '설계 목표와 검사 계획·정책까지 작성했습니다. 회로 설계, 실제 단자 바인딩, 테스트벤치 생성, SPICE 실행은 진행하지 않았습니다.']
        (out/'MEASUREMENT_PLAN_REPORT.md').write_text('\n'.join(lines),encoding='utf-8')
        require_current_hkg(run);require_current_pdg(run)
        job.complete(out/'MEASUREMENT_PLAN.json',stage='measurement_plan_and_policies_created',summary=validation)
        print(json.dumps({'selection':selection['summary'],'measurements':measurements['summary'],'policies':policies['summary'],'validation':validation},ensure_ascii=False))


if __name__=='__main__':main()
