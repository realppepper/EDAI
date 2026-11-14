"""Validate op-amp fixture methods using a fully disclosed analytical calibration DUT."""
import argparse,json,math,uuid
from pathlib import Path
from datetime import datetime,timezone
from opamp_pipeline.tb_02_ltspice import run_bench
from opamp_pipeline.tb_03_validate_reference import judge
from opamp_pipeline.tb_04_opamp_fixtures import REFERENCE_MODEL,generate_fixtures,reference_transfer
from opamp_pipeline.tb_05_waveform_metrics import read_real_raw,settling_metrics


def expected_step(step):
    """Analytic two-pole closed-loop response to the finite-ramp input."""
    h=reference_transfer();k=h['gain'];t1=h['tau1'];t2=h['tau2']
    b=t1+t2;disc=math.sqrt(b*b-4*t1*t2*(1+k))
    slow=-2*(1+k)/(b+disc);fast=-(b+disc)/(2*t1*t2)
    initial=2.5+k/(1+k)*(step['initial_V']-2.5+.0005)
    final=2.5+k/(1+k)*(step['final_V']-2.5+.0005)
    tr=step['transition_s'];target=step['final_V']
    def integral(t):
        if t<=0:return 0
        return t-(fast/slow*math.expm1(slow*t)-slow/fast*math.expm1(fast*t))/(fast-slow)
    def output(t):return initial+(final-initial)*(integral(t)-integral(t-tr))/tr
    band=abs(step['final_V']-step['initial_V'])*step['error_fraction']
    lo=tr;hi=step['stop_s']-step['start_s']
    if abs(output(hi)-target)>band:raise ValueError('Analytic calibration reference does not settle')
    for _ in range(70):
        mid=(lo+hi)/2
        if abs(output(mid)-target)>band:lo=mid
        else:hi=mid
    return {'settling_s':(lo+hi)/2-tr,'final_output_V':final}


def main():
    p=argparse.ArgumentParser();p.add_argument('--ltspice',required=True);a=p.parse_args()
    root=Path(__file__).resolve().parent
    out=root/'runs/opamp_testbench_validation'/datetime.now().strftime('%Y%m%d_%H%M%S_%f');out.mkdir(parents=True)
    result={'run_id':str(uuid.uuid4()),'status':'running','scope':'Testbench calibration only; no physical op-amp designed; no LM358B compliance claim.',
            'temperature_C':25,'supply_V':5,'load_R_Ohm':1e6,'load_C_F':20e-12,
            'dut_type':'linear_analytical_calibration_model','actual_dut_channel_count':1,
            'limitations':['No supply/rail saturation, slew limiting, device noise or physical power accounting in reference model.',
                          'Open-loop AC phase margin estimate is valid here for the declared unity-feedback model only.',
                          'Settling is checked through the finite observation window, not guaranteed forever.',
                          '32 required source rows/169 execution policies are not all implemented or executed.'],
            'reference_model_notes':'Artificial 200uA source tests current extraction; it does not predict real IC power.',
            'benches':[],'checks':[],'external_api_calls':0,'simulator':a.ltspice}
    def save(): (out/'RESULT.json').write_text(json.dumps(result,indent=2,ensure_ascii=False),encoding='utf-8')
    def check(name,value,expected,tolerance):
        result['checks'].append({'name':name,'measured':value,'expected':expected,'absolute_tolerance':tolerance,'passed':judge(value,expected,tolerance)})
    save()
    try:
        model=out/'calibration_amp.inc';model.write_text(REFERENCE_MODEL,encoding='ascii')
        transfer=reference_transfer();k=transfer['gain']
        for bench in generate_fixtures(model):
            path=out/(bench['name']+'.cir');path.write_text(bench['deck'],encoding='ascii')
            run=run_bench(a.ltspice,path,bench['names'],ascii_raw=True)
            item={'name':bench['name'],'analysis':bench['analysis'],**run,'netlist':str(path)}
            values=run['measurements']
            if bench['analysis']=='op':
                raw=read_real_raw(path.with_suffix('.raw'))
                if len(next(iter(raw.values())))!=1:raise ValueError('Expected one OP solution')
                item['metrics']={'output_V':raw['v(out)'][0],'iq_A':-raw['i(vdd)'][0],
                                 'input_differential_V':raw['v(inp)'][0]-raw['v(inn)'][0]}
                check('op_output_V',item['metrics']['output_V'],2.5+k/(1+k)*.0005,1e-7)
                check('op_supply_current_A',item['metrics']['iq_A'],200e-6,1e-9)
            elif bench['analysis']=='dc':
                raw=read_real_raw(path.with_suffix('.raw'))
                errors=[out_v-in_v for out_v,in_v in zip(raw['v(out)'],raw['v(inp)'])]
                check('dc_sweep_span_V',max(raw['v(inp)'])-min(raw['v(inp)']),1,1e-8)
                check('dc_max_tracking_error_V',max(abs(x) for x in errors),values['tracking_error'],1e-7)
                check('dc_mid_output_V',values['output_mid'],2.5+k/(1+k)*.0005,1e-7)
                check('dc_tracking_error_analytic_V',values['tracking_error'],(k*.0005+.5)/(1+k),1e-7)
                item['metrics']={'tracking_error_V':values['tracking_error'],
                                 'scope':'Only sampled 2..3 V follower tracking; NOT a certified VCM or output-swing range.'}
            elif bench['analysis']=='ac':
                check('ac_low_gain_V_per_V',values['gain_low'],k,2)
                check('ac_unity_frequency_Hz',values['unity_hz'],transfer['unity_hz'],transfer['unity_hz']*.001)
                check('ac_unity_phase_deg',values['unity_phase'],transfer['phase_deg'],.02)
                item['metrics']={'low_gain_dB':20*math.log10(values['gain_low']),
                                 'unity_Hz':values['unity_hz'],'unity_feedback_phase_margin_estimate_deg':180+values['unity_phase']}
                result['negative_control']={'name':'1.2MHz target deliberately fails on ~1MHz reference',
                                            'target_Hz':1.2e6,'measured_Hz':values['unity_hz'],
                                            'correctly_rejected':values['unity_hz']<1.2e6,
                                            'not_a_full_datasheet_judgment':True}
            else:
                raw=read_real_raw(path.with_suffix('.raw'));step=bench['step']
                metrics=settling_metrics(raw['time'],raw['v(out)'],step);expected=expected_step(step)
                item.update({'step':step,'metrics':metrics,'analytic_expected':expected})
                if metrics['settling_s'] is None:raise ValueError('Calibration step unexpectedly failed to settle')
                check(bench['name']+'_settling_s',metrics['settling_s'],expected['settling_s'],10e-9)
                check(bench['name']+'_final_V',raw['v(out)'][-1],expected['final_output_V'],2e-6)
            result['benches'].append(item);save()
        result['status']='passed' if all(x['passed'] for x in result['checks']) and result['negative_control']['correctly_rejected'] else 'failed'
        save()
    except Exception as error:
        result.update(status='error',error=str(error));save();raise
    lines=['# op amp 기본 테스트벤치 검증','',result['scope'],'',f"상태: {result['status']}",
           '', '| 검사 | 측정값 | 이론/비교값 | 허용 절대 오차 | 통과 |','|---|---:|---:|---:|---|']
    for c in result['checks']:lines.append(f"| {c['name']} | {c['measured']:.10g} | {c['expected']:.10g} | {c['absolute_tolerance']:.3g} | {c['passed']} |")
    lines+=['','## 범위와 한계','',
            '`.op`: 단위이득 피드백의 동작점·공급전류. `.dc`: 2~3V 입력 스윕의 출력 추종. `.ac`: DC 서보를 둔 개방루프 이득·단위이득 주파수·위상. `.tran`: 1↔3V 양방향 스텝의0.1% 정착·오버슈트.',
            '', '일반 트랜지스터 모델을 사용한 실제 회로 생성 전, 측정법 검증을 위해 내부식이 공개된 선형 기준 증폭기를 사용했습니다. 이는 회로 설계 결과가 아니며 전원 전류200µA도 인위적으로 설정한 검증값입니다. PDK·실제 잡음·레일 제한·슬루 제한은 없습니다.',
            '', 'RC2극 모델과 피드백 방정식으로 이론값을 별도 계산했습니다. 실제 파형 전체에서 마지막 오차 범위 이탈 후 복귀를 찾아 정착시간을 계산하고, 입력 전이 종료 시점을 기준으로 삼습니다. 종료 시점까지 이탈하면 미정착입니다.',
            '', '조원 deterministic_testbench.py의 follower·DC 서보·양방향 응답 구성을 참고했습니다. 하드코딩된 채널 수 나눗셈·기본 지연은 가져오지 않았습니다. 현재는 단일 채널·5V·25°C의 별도 검증 설정이며 기존 계획32행/169정책을 실행한 결과가 아닙니다.',
            '', '다음 단계는 실제 트랜지스터 op amp 넷리스트를 명시적 단자 매핑으로 연결하고, HKG 사양별 시험 조건/정책을 바인딩하는 것입니다. 나머지 사양은 미구현 상태로 유지합니다.']
    (out/'REPORT.md').write_text('\n'.join(lines),encoding='utf-8')
    if result['status']=='passed':
        (out.parent/'LATEST.json').write_text(json.dumps({'latest_successful_run':str(out),'report':str(out/'REPORT.md')},indent=2),encoding='utf-8')
    print(json.dumps({'status':result['status'],'checks':len(result['checks']),'output':str(out)},ensure_ascii=False))
    if result['status']!='passed':raise SystemExit(1)

if __name__=='__main__':main()
