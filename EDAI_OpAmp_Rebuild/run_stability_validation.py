"""Analytic PM references, phase-wrap/impedance stress, and existing CMOS crosscheck."""
import argparse,json,math
from pathlib import Path
from datetime import datetime
from opamp_pipeline.tb_06_loop_gain import dual_probe_deck,measure_dual_probe,reference_model,analytical_margin,METHOD,SOURCE
from opamp_pipeline.tb_02_ltspice import run_bench
from opamp_pipeline.tb_05_waveform_metrics import read_real_raw
from opamp_pipeline.loop_02_handoff import write_json
from opamp_pipeline.support.execution_state import file_hash


def main():
    p=argparse.ArgumentParser();p.add_argument('--ltspice',required=True);p.add_argument('--mos-netlist',type=Path,required=True)
    a=p.parse_args();root=Path(__file__).resolve().parent
    out=root/'runs/stability_validation'/datetime.now().strftime('%Y%m%d_%H%M%S_%f');out.mkdir(parents=True)
    result={'status':'running','method':METHOD,'source':SOURCE,'checks':[],'cases':[],
        'scope':'Numerical validation of this single-external-loop fixture, not all circuit stability problems.'}
    def save():write_json(out/'RESULT.json',result)
    def check(name,passed,**details):result['checks'].append({'name':name,'passed':bool(passed),**details})
    save()
    try:
        refs=[('high_pm',[10],100,None),('low_pm',[10,100000],100,None),
              ('negative_pm',[10,100000,100000],100,None),('loading_stress',[10],1000,1000)]
        for name,poles,ro,ri in refs:
            model=out/(name+'.inc');model.write_text(reference_model(poles,ro,ri),encoding='ascii')
            deck=out/(name+'.cir');deck.write_text(dual_probe_deck(model,'PMREF',load_C=0),encoding='ascii')
            run_bench(a.ltspice,deck,[],ascii_raw=True,timeout=25)
            measured=measure_dual_probe(deck.with_suffix('.raw'));expected=analytical_margin(poles,ro,ri)
            op=read_real_raw(deck.with_suffix('.op.raw'))
            delta=max(abs(op['v(xv)'][0]-op['v(xi)'][0]),abs(op['v(yv)'][0]-op['v(yi)'][0]))
            check(name+'_dc_identical',delta<1e-8,voltage_difference_V=delta)
            check(name+'_pm_matches_analytic',measured['single_crossover_applicable'] and abs(measured['phase_margin_deg']-expected['phase_margin_deg'])<.08,
                  measured_deg=measured['phase_margin_deg'],expected_deg=expected['phase_margin_deg'])
            check(name+'_unity_matches_analytic',measured['single_crossover_applicable'] and abs(measured['unity_Hz']/expected['unity_Hz']-1)<.001)
            if name=='negative_pm':check('negative_margin_not_wrapped_to_positive',measured['phase_margin_deg']<0)
            if name=='loading_stress':
                simple=measured['voltage_only_comparison']
                check('impedance_stress_distinguishes_single_injection',not simple['single_crossover_applicable'] or abs(simple['phase_margin_deg']-measured['phase_margin_deg'])>10,
                      voltage_only_deg=simple['phase_margin_deg'],dual_deg=measured['phase_margin_deg'])
            item={'name':name,'poles_Hz':poles,'output_R_Ohm':ro,'input_R_Ohm':ri,'expected':expected,'measured':measured}
            if name!='loading_stress':
                tran=out/(name+'_closed.cir')
                tran.write_text(f'''* Closed-loop small-signal transient validation; analytic model only
.include "{model.resolve()}"
.temp 25
.options plotwinsize=0
VDD vp 0 5
VMID mid 0 2.5
VIN inp 0 PWL(0 2.5 5u 2.5 5.01u 2.501 60u 2.501)
XD inp out vp 0 out PMREF
RL out mid 10k
.save V(out) V(inp)
.tran 0 60u 0 10n
.end
''',encoding='ascii')
                run_bench(a.ltspice,tran,[],ascii_raw=True,timeout=25)
                raw=read_real_raw(tran.with_suffix('.raw'));time=raw['time'];values=raw['v(out)']
                final=2.5+.001*expected['effective_dc_loop_gain']/(1+expected['effective_dc_loop_gain'])
                early=max(abs(v-final) for t,v in zip(time,values) if 10e-6<=t<=20e-6)
                late=max(abs(v-final) for t,v in zip(time,values) if t>=50e-6)
                item['transient']={'early_error_peak_V':early,'late_error_peak_V':late,'observed_until_s':time[-1]}
                if name=='negative_pm':check('negative_pm_growing_closed_loop_response',late>5*early)
                else:check(name+'_closed_loop_settles',late<1e-7)
            result['cases'].append(item);save()
        model=out/'actual_candidate.inc';model.write_bytes(a.mos_netlist.read_bytes())
        for capacitance in (20e-12,100e-12):
            name=f'actual_cmos_{capacitance*1e12:.0f}pF';path=out/(name+'.cir')
            path.write_text(dual_probe_deck(model,'FIRSTAMP',load_C=capacitance),encoding='ascii')
            run_bench(a.ltspice,path,[],ascii_raw=True,timeout=25)
            measured=measure_dual_probe(path.with_suffix('.raw'));op=read_real_raw(path.with_suffix('.op.raw'))
            delta=max(abs(op['v(xv)'][0]-op['v(xi)'][0]),abs(op['v(yv)'][0]-op['v(yi)'][0]))
            check(name+'_dc_identical',delta<1e-8,voltage_difference_V=delta)
            check(name+'_single_downward_crossing',measured['single_crossover_applicable'])
            result['cases'].append({'name':name,'load_C_F':capacitance,'measured':measured});save()
        result['status']='passed' if all(c['passed'] for c in result['checks']) else 'failed';save()
    except Exception as error:
        result.update(status='error',error=str(error));save();raise
    lines=['# 위상여유 측정법 검증','',f"상태: {result['status']}",'',
        'LTspice 설치본 Educational/LoopGain2.asc의 Tian 전압·전류 이중 주입 수식을 사용했습니다. 원래 회로의 부하·DC연결을 유지하고 두 회로의 동작점 동일성을 검사합니다. 위상 전체를 연속으로 풀어 모든 단위이득 교차를 찾으며, 교차가 없거나 여러 개면 단일 PM 판정을 허용하지 않습니다.',
        '', '| 기준 회로 | 이론 PM(°) | 측정 PM(°) |','|---|---:|---:|']
    for c in result['cases']:
        lines.append(f"| {c['name']} | {c.get('expected',{}).get('phase_margin_deg','—')} | {c['measured']['phase_margin_deg']} |")
    lines+=['','## 검증 체크','',*['- '+c['name']+': '+str(c['passed']) for c in result['checks']],
        '', '음의 PM 기준 회로는 작은 신호의 폐루프 응답이 증가하는지 확인했습니다. 높은/낮은 양의 PM 회로는 같은 관측 구간에서 수렴하는지 확인했습니다. 극단적 입출력 임피던스 조건에서 단순 전압 주입이 잘못된 값을 낼 수 있는 반례도 대조합니다.',
        '', '## 적용 범위와 근거','',
        '이번 검증은5V·25°C 단일 외부 단위이득 피드백 테스트벤치와 지정 부하/수치 설정의 검증입니다. 다중 피드백·내부 불안정 루프·모든 토폴로지에 대한 보편 인증이 아닙니다. 모델의 실제 제조 공정 정확성을 검증한 것도 아닙니다.',
        '', '[ADI: 전압 단독 주입의 한계와 이중 주입](https://ez.analog.com/ez-blogs/b/engineerzone-spotlight/posts/so-many-middlebrooks-which-stability-method-wins-part-5-of-7)',
        '', '설치본 참고: <LTspice install>/examples/Educational/LoopGain2.asc']
    (out/'REPORT.md').write_text('\n'.join(lines),encoding='utf-8')
    if result['status']=='passed':
        module=root/'opamp_pipeline/tb_06_loop_gain.py'
        receipt={'status':'passed','method':METHOD,'module_sha256':file_hash(module),
            'result_path':str(out/'RESULT.json'),'result_sha256':file_hash(out/'RESULT.json'),
            'report':str(out/'REPORT.md'),'scope':'5V single external unity follower; load to midrail; single crossover required',
            'tested_actual_candidate_sha256':file_hash(model),'tested_actual_loads_pF':[20,100]}
        write_json(root/'runs/stability_validation/QUALIFICATION.json',receipt)
    print(json.dumps({'status':result['status'],'checks':len(result['checks']),'output':str(out),
        'phase_margins':[(c['name'],c['measured']['phase_margin_deg']) for c in result['cases']]},ensure_ascii=False))
    if result['status']!='passed':raise SystemExit(1)

if __name__=='__main__':main()
