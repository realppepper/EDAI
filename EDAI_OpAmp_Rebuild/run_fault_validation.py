"""Real LTspice negative controls. Faults live in isolated copies, never best DUT."""
import argparse,json,subprocess,sys,time
from pathlib import Path
from datetime import datetime
from opamp_pipeline.loop_01_policy import make_policy,evaluate
from opamp_pipeline.loop_02_handoff import write_json
from opamp_pipeline.support.execution_state import file_hash


def main():
    p=argparse.ArgumentParser();p.add_argument('--ltspice',required=True);p.add_argument('--netlist',type=Path,required=True)
    p.add_argument('--context',type=Path,required=True);a=p.parse_args();root=Path(__file__).resolve().parent
    context=json.loads(a.context.read_text(encoding='utf-8'));policy=make_policy(context)
    out=root/'runs/fault_validation'/datetime.now().strftime('%Y%m%d_%H%M%S_%f');out.mkdir(parents=True)
    original=file_hash(a.netlist)
    result={'status':'running','original_candidate_sha256':original,'cases':[],
        'scope':'Fault detector validation: faults are expected to fail; does not measure design success rate.'}
    def save():write_json(out/'RESULT.json',result)
    save()
    for fault in [None,'open_feedback','weak_bias','syntax_error','missing_measurement']:
        name=fault or 'normal_control';folder=out/name
        command=[sys.executable,str(root/'run_first_opamp.py'),'--ltspice',a.ltspice,'--netlist',str(a.netlist.resolve()),
                 '--output-dir',str(folder),'--bench-timeout','15','--wall-budget','55']
        if fault:command+=['--fault-injection',fault]
        start=time.monotonic()
        proc=subprocess.run(command,cwd=root,capture_output=True,timeout=85)
        (out/(name+'_stdout.txt')).write_bytes(proc.stdout);(out/(name+'_stderr.txt')).write_bytes(proc.stderr)
        data=json.loads((folder/'RESULT.json').read_text(encoding='utf-8'))
        assessment=evaluate(data,policy)
        expected=assessment['scope_passed'] if fault is None else not assessment['scope_passed']
        details=[]
        if fault=='syntax_error':
            details=assessment['gate_issues'];expected=expected and any('unknown' in s.lower() for s in details)
        elif fault=='missing_measurement':
            details=assessment['gate_issues'];expected=expected and 'GBW' in assessment['failed_keys'] and any('unity_hz' in s and 'Missing' in s for s in details)
        elif fault in ('open_feedback','weak_bias'):
            details=assessment['gate_issues']+assessment['failed_keys'];expected=expected and bool(details)
        if fault is None:expected=expected and data.get('pm_validation',{}).get('qualified') is True
        write_json(folder/'LLM_FEEDBACK.json',{'assessment':assessment,'full_result':str((folder/'RESULT.json').resolve()),
            'fault_test':fault,'source_targets_unchanged':True,'physical_cause_is_not_automatically_proven':True})
        result['cases'].append({'name':name,'passed_validation':bool(expected),'circuit_scope_passed':assessment['scope_passed'],
            'failed_keys':assessment['failed_keys'],'gate_issues':assessment['gate_issues'],
            'experiment_status':data['status'],'returncode':proc.returncode,'seconds':time.monotonic()-start,
            'feedback':str((folder/'LLM_FEEDBACK.json').resolve()),'pm_validation':data.get('pm_validation')})
        save()
    result['original_candidate_unchanged']=file_hash(a.netlist)==original
    result['status']='passed' if result['original_candidate_unchanged'] and all(c['passed_validation'] for c in result['cases']) else 'failed'
    save()
    lines=['# 意図的エラー検出'.replace('意図的エラー検出','오류 주입 검증'),'',f"상태: {result['status']}",'',
        '정상 대조군이 통과하고 의도적 결함 네 가지는 실패해야 검출 시험이 통과합니다. 결함 회로를 성공한 설계로 집계하지 않습니다.',
        '', '| 시험 | 검출 시험 통과 | 회로 판정 | 미달 항목 |','|---|---|---|---|']
    for c in result['cases']:lines.append(f"| {c['name']} | {c['passed_validation']} | {c['circuit_scope_passed']} | {', '.join(c['failed_keys'])} |")
    lines+=['','## 주입 내용','',
        '- open_feedback: DC·과도응답 fixture의 출력→반전 입력 연결을 끊고 반전 입력을2.5V에 고정했습니다. 독립 AC 측정 fixture는 유지하므로 모든 개별 측정이 실패해야 하는 것은 아닙니다.',
        '- weak_bias: 복사본의 바이어스 저항을200kΩ→20MΩ로 바꿔 전류를 크게 줄였습니다.',
        '- syntax_error: 존재하지 않는 서브회로 호출을 넣어 실제 LTspice 오류가 발생하도록 했습니다.',
        '- missing_measurement: GBW 분석에서 unity_hz 측정 명령만 제거했습니다. 시뮬레이터 종료 코드0만으로 성공이라 판정하면 안 됩니다.',
        '', '각 LLМ_FEEDBACK.json(실제 파일명 LLM_FEEDBACK.json)에 목표·측정값·미달·누락·실행 오류·전체 로그 경로를 남겼습니다. 원인 확정은 검출기 역할이 아니며, 이 피드백으로 현재 채팅/향후 API 설계자가 진단합니다.',
        '', f"정상 원본 회로 보존: {result['original_candidate_unchanged']}"]
    (out/'REPORT.md').write_text('\n'.join(lines),encoding='utf-8')
    write_json(root/'runs/fault_validation/LATEST.json',{'output':str(out),'report':str(out/'REPORT.md'),'status':result['status']})
    print(json.dumps({'status':result['status'],'output':str(out),'cases':[(c['name'],c['passed_validation'],c['failed_keys']) for c in result['cases']]},ensure_ascii=False))
    if result['status']!='passed':raise SystemExit(1)

if __name__=='__main__':main()
