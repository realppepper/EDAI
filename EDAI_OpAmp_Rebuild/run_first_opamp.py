"""First all-transistor LEVEL1 op-amp experiment, separately from calibration."""
import argparse,json,math,time
from datetime import datetime
from pathlib import Path
from opamp_pipeline.design_01_cmos_candidate import candidate
from opamp_pipeline.tb_04_opamp_fixtures import generate_fixtures
from opamp_pipeline.tb_02_ltspice import run_bench
from opamp_pipeline.tb_05_waveform_metrics import read_real_raw,settling_metrics
from opamp_pipeline.support.execution_state import file_hash
from opamp_pipeline.design_02_check_bias import check_bias
from opamp_pipeline.tb_02_ltspice import decode_log
from opamp_pipeline.tb_06_loop_gain import dual_probe_deck,measure_dual_probe
from opamp_pipeline.support.stability_receipt import current_qualification


def main():
    p=argparse.ArgumentParser();p.add_argument('--ltspice',required=True)
    p.add_argument('--cc-pf',type=float,default=60);p.add_argument('--rz-ohm',type=float,default=680)
    p.add_argument('--netlist',type=Path);p.add_argument('--output-dir',type=Path)
    p.add_argument('--measurement-plan',type=Path)
    p.add_argument('--bench-timeout',type=float,default=45);p.add_argument('--wall-budget',type=float,default=180)
    p.add_argument('--fault-injection',choices=['open_feedback','weak_bias','syntax_error','missing_measurement'])
    a=p.parse_args();root=Path(__file__).resolve().parent
    out=a.output_dir or root/'runs/first_cmos_opamp'/datetime.now().strftime('%Y%m%d_%H%M%S_%f')
    if out.exists() and any(out.iterdir()):raise ValueError('Refusing nonempty experiment directory')
    if a.bench_timeout<=0 or a.wall_budget<=0:raise ValueError('Positive execution budgets required')
    out.mkdir(parents=True,exist_ok=True)
    planpath=a.measurement_plan or root/'runs/lm358b_overview_20261112/measurement_plan/plan_02_measurements.json'
    plan=json.loads(planpath.read_text(encoding='utf-8'))
    result={'status':'running','parameters':({'source':'provided_netlist'} if a.netlist else {'cc_pF':a.cc_pf,'rz_Ohm':a.rz_ohm}),
            'scope':'Single-channel generic MOS experiment at5V/25C; not full LM358B compliance.',
            'dut_pin_order':['P','N','VP','VM','OUT'],'actual_channel_count':1,
            'design_author':'current chat assistant; no external model API',
            'model_type':'generic LEVEL1; not TI/PDK, not manufacturing validation',
            'measurement_plan':str(planpath),'measurement_plan_sha256':file_hash(planpath),
            'fault_injection':a.fault_injection,'is_fault_test':a.fault_injection is not None,
            'benchmarks':[],'case_judgments':[], 'all_required_specs_passed':False,
            'limitations':['Only a subset of5V cases executed; remaining source rows remain unevaluated.',
                           'No mismatch, physical noise calibration, corners or layout.',
                           'PM voltage-injection estimate is crosschecked, not a qualified general return-ratio adapter.']}
    started=time.monotonic()
    def save():
        result['execution_seconds']=time.monotonic()-started
        temporary=out/'RESULT.json.tmp'
        temporary.write_text(json.dumps(result,indent=2,ensure_ascii=False),encoding='utf-8')
        temporary.replace(out/'RESULT.json')
    def judgment(symbol,value,operator=None,case_note='5V case only; other cases remain unevaluated'):
        row=next(m for m in plan['measurements'] if m['symbol']==symbol)
        rule=row['target']['rules'][0];limit=rule['value'];op=operator or rule['operator']
        valid=value is not None and math.isfinite(value)
        passed=valid and (value<=limit if op=='<=' else value>=limit)
        result['case_judgments'].append({'symbol':symbol,'row_id':row['row_id'],'measured':value,
            'operator':op,'limit':limit,'unit':rule['unit'],'passed':bool(passed),'scope':case_note,
            'target_origin':row['target'].get('origin',row['target'].get('target_origin','see source plan'))})
    save()
    try:
        text=a.netlist.read_text(encoding='utf-8') if a.netlist else candidate(a.cc_pf*1e-12,a.rz_ohm)
        if a.fault_injection=='weak_bias':text=text.replace('Rbias VP BIAS 200k','Rbias VP BIAS 20Meg')
        if a.fault_injection=='syntax_error':text=text.replace('.ends FIRSTAMP','Xfault 0 0 UNKNOWN_FAULT\n.ends FIRSTAMP')
        model=out/'candidate.inc';model.write_text(text,encoding='ascii')
        result['netlist_sha256']=file_hash(model)
        benches=generate_fixtures(model,'FIRSTAMP')
        for b in benches:
            b['deck']=b['deck'].replace('Calibration fixture, single channel; NOT the full LM358B test plan',
                                    'Actual transistor DUT, selected 5V cases only').replace('RL out mid 1Meg','RL out mid 10k')
            b['deck']=b['deck'].replace('.options plotwinsize=0 meascplxfmt=cartesian',
                                      '.options plotwinsize=0 meascplxfmt=cartesian\n.save V(*) I(*)')
            if b['analysis']=='op':
                # IQ requires zero external output current, not a loaded offset follower.
                b['deck']=b['deck'].replace('RL out mid 10k\n','').replace('VIN inp 0 2.5',
                        'Bservo inp 0 V=2.5+1e6*(2.5-V(out))')
                b['deck']=b['deck'].replace('.op\n',
                    '.save V(xdut:tail) V(xdut:diode) V(xdut:x) V(xdut:bias) V(xdut:comp)\n.op\n')
            if b['analysis']=='tran':b['deck']=b['deck'].replace('CL out mid 20p','CL out mid 100p')
        ac=next(b for b in benches if b['analysis']=='ac')
        loop={'name':'opamp_loop','analysis':'ac','names':[],
              'deck':dual_probe_deck(model,'FIRSTAMP',load_R=10000,load_C=20e-12)}
        gbw=dict(ac);gbw['name']='opamp_gbw';gbw['deck']=ac['deck'].replace('CL out mid 20p\n','')
        benches.extend([loop,gbw])
        if a.fault_injection=='open_feedback':
            for bench in benches:bench['deck']=bench['deck'].replace('VFB out inn 0','VFIX inn 0 2.5')
        if a.fault_injection=='missing_measurement':
            gbw['deck']=gbw['deck'].replace('.meas ac unity_hz WHEN mag(V(out))=1 FALL=1','* Deliberately omit required unity_hz measurement')
        for bench in benches:
            path=out/(bench['name']+'.cir');path.write_text(bench['deck'],encoding='ascii')
            try:
                remaining=a.wall_budget-(time.monotonic()-started)
                if remaining<=0:raise TimeoutError('Experiment wall budget exhausted')
                run=run_bench(a.ltspice,path,bench['names'],ascii_raw=True,timeout=min(a.bench_timeout,remaining))
            except Exception as error:
                result['benchmarks'].append({'name':bench['name'],'status':'execution_or_measurement_error','error':str(error)})
                save();continue
            item={'name':bench['name'],'analysis':bench['analysis'],'status':'executed',**run,'netlist':str(path)}
            v=run['measurements']
            if bench['analysis']=='op':
                raw=read_real_raw(path.with_suffix('.raw'))
                item['op_snapshot']={key:values[0] for key,values in raw.items()}
                item['bias_diagnostic']=check_bias(item['op_snapshot'])
                iq=-raw['i(vdd)'][0];vos=raw['v(out)'][0]-raw['v(inp)'][0]
                item['metrics']={'iq_A':iq,'vos_V':vos,'output_V':raw['v(out)'][0],
                                 'servo_error_V':raw['v(out)'][0]-2.5}
                if abs(raw['v(out)'][0]-2.5)>1e-6:raise ValueError('DC servo did not enforce target output')
                judgment('IQ',iq);judgment('VOS',abs(vos))
            elif bench['analysis']=='ac':
                if bench['name']=='opamp_loop':
                    measured=measure_dual_probe(path.with_suffix('.raw'))
                    qualified=current_qualification(model,root/'runs/stability_validation/QUALIFICATION.json')
                    pm=measured['phase_margin_deg']
                    item['metrics']={'unity_Hz':measured['unity_Hz'],'phase_margin_deg':pm,
                        'phase_margin_estimate_deg':pm,'measurement':measured,'qualification':qualified}
                    result['pm_validation']={'qualified':qualified['qualified'] and measured['single_crossover_applicable'],
                        'status':qualified['status'] if measured['single_crossover_applicable'] else 'ambiguous_or_missing_unity_crossing',
                        'value_deg':pm,'qualification':qualified,'measurement':measured}
                    if result['pm_validation']['qualified']:judgment('PM',pm)
                else:
                    item['metrics']={'gain_V_per_V':v['gain_low'],'gain_dB':20*math.log10(v['gain_low']),
                                     'unity_Hz':v['unity_hz'],'phase_margin_estimate_deg':180+v['unity_phase']}
                    if bench['name']=='opamp_gbw':judgment('GBW',v['unity_hz'])
            elif bench['analysis']=='tran':
                raw=read_real_raw(path.with_suffix('.raw'))
                item['step']=bench['step'];item['metrics']=settling_metrics(raw['time'],raw['v(out)'],bench['step'])
                judgment('ts',item['metrics']['settling_s'],case_note=bench['direction']+' 5V/10kOhm/100pF/2Vstep/0.1%; finite observation')
            result['benchmarks'].append(item);save()
        result['model_warnings']=sorted({line.strip() for b in result['benchmarks'] if b.get('log')
            for line in decode_log(b['log']).splitlines() if 'recommended for a level 1' in line.lower()})
        byname={b['name']:b for b in result['benchmarks'] if b['status']=='executed'}
        if 'opamp_loop' in byname and 'opamp_ac' in byname and byname['opamp_loop']['metrics']['unity_Hz'] is not None:
            l=byname['opamp_loop']['metrics'];o=byname['opamp_ac']['metrics']
            result['loop_crosscheck']={'unity_relative_error':abs(l['unity_Hz']/o['unity_Hz']-1),
                                     'phase_difference_deg':abs(l['phase_margin_estimate_deg']-o['phase_margin_estimate_deg']),
                                     'not_general_return_ratio_certification':True}
            result['pm_diagnostic']={'estimate_deg':l['phase_margin_estimate_deg'],'target_deg':56,
                                     'provisional_meets_target':l['phase_margin_estimate_deg']>=56,
                                     'status':result.get('pm_validation',{}).get('status','not_qualified')}
        attempted={x['row_id'] for x in result['case_judgments']}
        result['coverage']={'source_rows_required':len(plan['measurements']),
            'rows_with_selected_case_judgments':len(attempted),
            'required_rows_without_case_judgments':[{'row_id':m['row_id'],'symbol':m['symbol']} for m in plan['measurements'] if m['row_id'] not in attempted],
            'full_row_conditions_verified':False,'total_success_rate_not_computed':True}
        result['status']='partial_experiment_completed' if all(b['status']=='executed' for b in result['benchmarks']) else 'partial_with_execution_errors'
        if result.get('pm_validation',{}).get('qualified'):
            result['limitations'][-1]='PM numerically validated for this same-model single external unity-feedback fixture only; not arbitrary topologies/internal unstable loops.'
        result['execution_seconds']=time.monotonic()-started
        save()
    except Exception as error:
        result.update(status='error',error=str(error));save();raise
    lines=['# 첫 일반 MOS op amp 실험','',result['scope'],'',f"상태: {result['status']}",'',
           '회로: NMOS 차동 입력·PMOS 미러 부하 → PMOS 공통소스2단·NMOS 전류 싱크, RC Miller 보상. 바이어스는 저항과 MOS로 구성하며 DUT 내부에 이상적 전류원·제어원은 없습니다. 일반 LEVEL1 모델 가정은 모든 사이징 실험에서 고정합니다.',
           '', '| 항목 | 측정 | 목표 | 판정 |','|---|---:|---:|---|']
    for c in result['case_judgments']:lines.append(f"| {c['symbol']} ({c['scope']}) | {c['measured']} {c['unit']} | {c['operator']} {c['limit']} | {c['passed']} |")
    lines+=['','## 분석별 측정','']
    for b in result['benchmarks']:lines.append(f"- {b['name']}: {json.dumps(b.get('metrics',b.get('measurements',b.get('error'))),ensure_ascii=False)}")
    lines+=['','## 한계','',*['- '+x for x in result['limitations']],
            '', '5V 대표 조건 일부만 평가했습니다. PM은 Tian 이중 주입·위상 연속화·전체 교차 검사를 사용하며, 기준 검증 영수증과 같은 모델/연결/시험 조건일 때만 해당 사례를 판정합니다. 미검증 사양은 그대로 남기며 전체 성공률을 계산하지 않습니다. 36V 전류, 전출력 범위 이득, 출력 구동, 잡음 등은 이 결과로 판정할 수 없습니다.']
    op=next((b for b in result['benchmarks'] if b.get('bias_diagnostic')),None)
    if op:
        lines+=['','## 내부 바이어스 명목 진단','',op['bias_diagnostic']['method'],
                '', '| MOS | VGS 크기(V) | VDS 크기(V) | 명목 포화 여유(V) | 영역 |','|---|---:|---:|---:|---|']
        for d in op['bias_diagnostic']['devices']:
            lines.append(f"| {d['device']} | {d['vgs_magnitude_V']:.6g} | {d['vds_magnitude_V']:.6g} | {d['saturation_margin_V']:.6g} | {d['region_nominal']} |")
    lines+=['','## 모델 경고','',
            'LEVEL1은 교육용 모델 가정이며 실제 공정 정확성을 보장하지 않습니다. 권장 채널 길이·산화막 범위 경고를 보존합니다. 성능에 맞춰 모델 계수를 수정하지 않았습니다.',
            *['- '+w for w in result.get('model_warnings',[])]]
    (out/'REPORT.md').write_text('\n'.join(lines),encoding='utf-8')
    (out.parent/'LATEST.json').write_text(json.dumps({'latest_run':str(out),'report':str(out/'REPORT.md')},indent=2),encoding='utf-8')
    print(json.dumps({'output':str(out),'status':result['status'],'judgments':result['case_judgments'],'pm':result.get('pm_diagnostic')},ensure_ascii=False))

if __name__=='__main__':main()
