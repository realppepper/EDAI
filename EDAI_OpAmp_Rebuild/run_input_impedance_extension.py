"""Qualified impedance measurement extension; existing55 passes and original80-case ledger stay intact."""
import argparse,json,math,copy
from pathlib import Path
from opamp_pipeline.verify_04_input_impedance import REFERENCE,impedance_deck,measure_pair
from opamp_pipeline.tb_02_ltspice import run_bench
from opamp_pipeline.diag_02_startup_seed import seeded_deck
from opamp_pipeline.loop_02_handoff import write_json
from opamp_pipeline.support.execution_state import file_hash


def main():
    root=Path(__file__).resolve().parent
    p=argparse.ArgumentParser();p.add_argument('--ltspice',required=True);p.add_argument('--output-dir',type=Path,required=True)
    p.add_argument('--baseline',type=Path,default=root/'runs/extended_verification/20261114_stabilized_compact/RESULT.json')
    p.add_argument('--plan',type=Path,default=root/'runs/lm358b_overview_20261112/measurement_plan/plan_02_measurements.json');a=p.parse_args()
    out=a.output_dir.resolve();out.mkdir(parents=True,exist_ok=False)
    baseline_path=a.baseline.resolve()
    read=lambda p:json.loads(p.read_text(encoding='utf-8'))
    baseline=read(baseline_path);source_model=baseline_path.parent/'candidate.inc';model=out/'candidate.inc';model.write_bytes(source_model.read_bytes())
    if file_hash(source_model) not in baseline['input_signatures'].values():raise ValueError('Stored DUT no longer matches baseline input signature')
    planpath=a.plan.resolve();plan=read(planpath)
    if baseline['input_signatures'].get(str(planpath))!=file_hash(planpath):raise ValueError('Plan differs from baseline')
    items={i['method']['kind']:i for i in plan['measurements'] if i['method']['kind'] in {'zid','zic'}}
    if set(items)!={'zid','zic'}:raise ValueError('Both input modes must be present in this extension plan')
    if len(items['zid']['cases'])!=len(items['zic']['cases']) or any(d['fixture']!=c['fixture'] for d,c in zip(items['zid']['cases'],items['zic']['cases'])):
        raise ValueError('Different mode fixtures need separate measurement pairs; refusing to share mismatched bias/load conditions')
    result={'status':'running','source_plan_sha256':file_hash(planpath),'baseline_result':str(baseline_path),'baseline_sha256':file_hash(baseline_path),
            'candidate_sha256':file_hash(model),'measurement_code_sha256':file_hash(root/'opamp_pipeline/verify_04_input_impedance.py'),
            'calibration':[],'measurements':[],'default_candidate_changed':False,'external_llm_calls':0,'full_datasheet_success':False}
    save=lambda:write_json(out/'RESULT.json',result);save()
    def run_pair(label,model,fixture,subckt,seed=None):
        paths=[]
        for mode in ('differential','common'):
            path=out/f'{label}_{mode}.cir';deck=impedance_deck(model,fixture,mode,subckt)
            if seed:deck=seeded_deck(deck,seed)
            path.write_text(deck,encoding='ascii');run_bench(a.ltspice,path,[],ascii_raw=True,timeout=45);paths.append(path)
        measured=measure_pair(*paths);measured['job_paths']=[str(p) for p in paths]
        return measured
    reference=out/'reference.inc';reference.write_text(REFERENCE,encoding='ascii')
    try:
        for case in (items['zid']['cases'][0],items['zid']['cases'][-1]):
            vs=case['fixture']['supply_voltage_V'];m=run_pair(f'cal_{vs:g}',reference,case['fixture'],'ZREF')
            good=not m['gate_issues'] and not m['differential_interpretation_issues']
            for mode,r,c in [('differential',1e7,.1e-12),('common',4e9,1.5e-12)]:
                fit=m[mode];good=good and not fit['fit_issues'] and fit['resistance_Ohm'] is not None and abs(fit['resistance_Ohm']/r-1)<1e-4 and abs(fit['capacitance_F']/c-1)<1e-4
            result['calibration'].append({'supply_V':vs,'passed':good,'measured':m});save()
            if not good:raise ValueError('Known parallel-R/C network failed; DUT verdict withheld')
        print('Reference differential10M/0.1p and common-per-pin4G/1.5p checks passed.',flush=True)
        for index,dcase in enumerate(items['zid']['cases']):
            vs=dcase['fixture']['supply_voltage_V'];seed=baseline['startup_seeds'][f'{vs:.10g}']['seeds']
            m=run_pair(f'dut_{vs:g}',model,dcase['fixture'],'FIRSTAMP',seed)
            result['measurements'].append({'supply_V':vs,'measured':m});save();print(vs,'measurement completed',flush=True)
        combined=copy.deepcopy(baseline)
        for kind,item in items.items():
            row=combined['rows'][item['row_id']];row['cases']=[]
            for c,m in zip(item['cases'],result['measurements']):
                assert math.isclose(c['fixture']['supply_voltage_V'],m['supply_V'],rel_tol=1e-12)
                mode='differential' if kind=='zid' else 'common';fit=m['measured'][mode]
                eligible=not fit['capacitance_fit_issues'] and not m['measured']['gate_issues']
                cap_value=fit['capacitance_F']
                if kind=='zid':eligible=eligible and not m['measured']['differential_interpretation_issues']
                else:
                    pins=[m['measured']['common_pin_p'],m['measured']['common_pin_n']]
                    eligible=not m['measured']['gate_issues'] and all(not f['capacitance_fit_issues'] for f in pins)
                    cap_value=max(f['capacitance_F'] for f in pins)
                limit=item['target']['rules'][1]['value']
                row['cases'].append({'case_id':c['case_id'],'supply_V':c['fixture']['supply_voltage_V'],'fixture':c['fixture'],
                    'status':'unverified_model','measurement_executed':True,'tests':[],
                    'component_checks':[
                        {'metric':'fitted_parallel_resistance','value_Ohm':fit['resistance_Ohm'],'passed':None,'reason':'Frozen MOS model omits calibrated gate leakage; resistance cannot be certified.'},
                        {'metric':'fitted_parallel_capacitance','value_F':cap_value,'limit_F':limit,'passed':cap_value<=limit if eligible else None,'interpretation_qualified':eligible,'common_mode_uses_worst_pin':kind=='zic'}],
                    'measurement':m['measured'],'model_limitations':['Uncalibrated gate-leakage conductance; full source parallel-R/C specification not established.'],
                    'full_continuous_range_verified':False})
        allcases=[c for r in combined['rows'].values() for c in r['cases']]
        assert len(allcases)==baseline['source_cases_required']
        combined['case_status_counts']={s:sum(c['status']==s for c in allcases) for s in sorted({c['status'] for c in allcases})}
        combined['impedance_extension']={'result':str(out/'RESULT.json'),'baseline_readonly':str(baseline_path),'reference_network_qualified':True,'new_passes_claimed':0}
        combined['input_signatures'][str(root/'opamp_pipeline/verify_04_input_impedance.py')]=result['measurement_code_sha256']
        write_json(out/'COMBINED_LEDGER.json',combined)
        result.update(status='extension_completed_with_explicit_model_limitations',combined_case_status_counts=combined['case_status_counts']);save()
    except Exception as e:
        result.update(status='error',error=str(e));save();raise
    print(json.dumps({'output':str(out),'status':result['status'],'counts':combined['case_status_counts']}),flush=True)
    code=out/'code_snapshot';code.mkdir()
    for source in (root/'opamp_pipeline/verify_04_input_impedance.py',Path(__file__)):
        (code/source.name).write_bytes(source.read_bytes())
    write_json(out/'ARTIFACTS.json',{'files':{str(p.relative_to(out)):file_hash(p) for p in out.rglob('*') if p.is_file() and p.name!='ARTIFACTS.json'}})


if __name__=='__main__':main()
