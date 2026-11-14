"""Calibrate LTspice measurement plumbing; no API or op-amp design."""
import argparse,json,uuid
from datetime import datetime,timezone
from pathlib import Path
from opamp_pipeline.tb_01_reference_benches import reference_benches
from opamp_pipeline.tb_02_ltspice import run_bench
from opamp_pipeline.tb_03_validate_reference import validate_reference,judge

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--ltspice',required=True);args=parser.parse_args()
    root=Path(__file__).resolve().parent/'runs'/'testbench_validation'/datetime.now().strftime('%Y%m%d_%H%M%S_%f')
    root.mkdir(parents=True)
    result={'run_id':str(uuid.uuid4()),'started_utc':datetime.now(timezone.utc).isoformat(),'status':'running',
            'scope':'Analytical calibration only; NOT LM358B specification validation or generated op-amp.',
            'simulator':args.ltspice,'temperature_C':25,'benchmarks':[],'api_calls':0}
    def save(): (root/'RESULT.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    save()
    try:
        for bench in reference_benches():
            path=root/(bench['name']+'.cir');path.write_text(bench['netlist'],encoding='ascii')
            run=run_bench(args.ltspice,path,bench['expected'])
            checks=validate_reference(run['measurements'],bench['expected'])
            result['benchmarks'].append({'name':bench['name'],**run,'checks':checks,'passed':all(x['passed'] for x in checks.values())});save()
        # Real measured divider value must fail against an intentionally incorrect goal.
        actual=result['benchmarks'][0]['measurements']['output_v']
        result['negative_controls']={'wrong_goal_rejected':not judge(actual,3.0,0.01),
                                     'missing_rejected':not judge(None,0,1),
                                     'nonfinite_rejected':not judge(float('nan'),0,1)}
        result['status']='passed' if all(x['passed'] for x in result['benchmarks']) and all(result['negative_controls'].values()) else 'failed'
        save()
    except Exception as error:
        result['status']='error';result['error']=str(error);save();raise
    lines=['# LTspice テストベンチ校正'.replace('テストベンチ校正','테스트벤치 기본 검증'),'',result['scope'],'',f"상태: {result['status']}",'', '| 회로 | 측정 | 실제 값 | 이론 값 | 허용 절대 오차 | 결과 |','|---|---|---:|---:|---:|---|']
    for bench in result['benchmarks']:
        for name,c in bench['checks'].items():lines.append(f"| {bench['name']} | {name} | {c['measured']:.9g} | {c['expected']:.9g} | {c['absolute_tolerance']:.3g} | {c['passed']} |")
    lines+=['',f"실패 판정 검증: {result['negative_controls']}",'','저항 분압: 5V×10k/(10k+10k)=2.5V, 전원 전류250µA. RC: τ=RC=1ms, fc=1/(2πRC), fc에서 이득1/√2·위상−45°, τ에서 출력1−exp(−1). MOS: 25°C=TNOM, LEVEL1·λ=0, Id=KP(W/L)(Vgs−Vto)²/2=125µA, Vd=3.75V, 포화 조건 Vds≥0.5V.', '', '기준 회로는 측정 경로 검증 전용입니다. op amp 이득·위상여유·잡음 등의 측정 정확도와 LM358B 목표 달성은 아직 검증하지 않았습니다.']
    (root/'REPORT.md').write_text('\n'.join(lines),encoding='utf-8')
    print(json.dumps({'status':result['status'],'output':str(root)},ensure_ascii=False))
    if result['status']!='passed':raise SystemExit(1)

if __name__=='__main__':main()
