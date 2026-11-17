"""Qualify overload timing then append both saturation directions to the unchanged80-case ledger."""
import argparse,json,copy,math
from pathlib import Path
from opamp_pipeline.verify_05_overload_recovery import recovery_deck,recovery_metrics,reference_model,analytic_recovery
from opamp_pipeline.tb_05_waveform_metrics import read_real_raw
from opamp_pipeline.diag_02_startup_seed import seeded_deck
from opamp_pipeline.diag_03_solver_attempts import run_with_fallback
from opamp_pipeline.tb_02_ltspice import run_bench
from opamp_pipeline.loop_02_handoff import write_json
from opamp_pipeline.support.execution_state import file_hash
from opamp_pipeline.validation_05_special_fixtures import overload_meta
from opamp_pipeline.validation_03_execution_contract import validate_execution,ExecutionContractError


def recovery_job_path(out,index,supply,direction):
    """Keep each stimulus direction's unchanged fallback in its own directory."""
    if direction not in {'high','low'}:raise ValueError('Invalid overload direction')
    folder=Path(out)/f'case_{index:03d}_{direction}'
    folder.mkdir(exist_ok=False)
    return folder/f'dut_{supply:g}.cir'


def main():
    root=Path(__file__).resolve().parent;p=argparse.ArgumentParser();p.add_argument('--ltspice',required=True)
    p.add_argument('--output-dir',type=Path,required=True)
    p.add_argument('--baseline',type=Path,default=root/'runs/impedance_extension/20261114_final/COMBINED_LEDGER.json')
    p.add_argument('--plan',type=Path,default=root/'runs/lm358b_overview_20261112/measurement_plan/plan_02_measurements.json');a=p.parse_args()
    read=lambda p:json.loads(p.read_text(encoding='utf-8'));base=read(a.baseline);plan=read(a.plan)
    if base['input_signatures'].get(str(a.plan.resolve()))!=file_hash(a.plan):raise ValueError('Source plan differs from baseline')
    source=a.baseline.parent/'candidate.inc'
    if file_hash(source) not in base['input_signatures'].values():raise ValueError('Stored model differs from baseline input')
    item=next(i for i in plan['measurements'] if i['method']['kind']=='overload_recovery');limit=item['target']['rules'][0]['value']
    out=a.output_dir.resolve();out.mkdir(parents=True,exist_ok=False);model=out/'candidate.inc';model.write_bytes(source.read_bytes())
    result={'status':'running','baseline_path':str(a.baseline.resolve()),'baseline_sha256':file_hash(a.baseline),
            'plan_sha256':file_hash(a.plan),'model_sha256':file_hash(model),'measurement_code_sha256':file_hash(root/'opamp_pipeline/verify_05_overload_recovery.py'),
            'calibration':[],'cases':[],'model_changed':False,'external_llm_calls':0,'full_datasheet_success':False}
    save=lambda:write_json(out/'RESULT.json',result);save()
    try:
        case=item['cases'][0]
        for name,cap in [('fast',1e-9),('slow',5e-9)]:
            ref=out/f'{name}_reference.inc';ref.write_text(reference_model(cap),encoding='ascii')
            for direction in ('high','low'):
                deck,profile=recovery_deck(ref,item,case,direction,'ORREF',calibration_stimulus_port=True);path=out/f'cal_{name}_{direction}.cir';path.write_text(deck,encoding='ascii')
                meta=overload_meta(ref,item,case,direction,profile,'ORREF',calibration=True)
                meta['execution_contract_receipt_dir']=str(out/'execution_contracts')
                validate_execution(deck,meta,phase='overload_preflight')
                run_bench(a.ltspice,path,[],ascii_raw=True,timeout=60)
                m=recovery_metrics(read_real_raw(path.with_suffix('.raw')),profile,meta,path)
                expected=analytic_recovery(profile,cap,case['fixture']['load']['value_Ohm'])
                expected_pass=expected<=limit;observed_pass=m['value'] is not None and m['value']<=limit
                qualified=not m['gate_issues'] and m['value'] is not None and abs(m['value']-expected)<max(5e-9,expected*.01) and expected_pass==observed_pass
                result['calibration'].append({'name':name,'direction':direction,'qualified':qualified,'expected_s':expected,'expected_spec_pass':expected_pass,'measured':m,'profile':profile});save()
                if not qualified:raise ValueError('Recovery known-answer/slow-failure calibration did not qualify')
        print('Fast/slow analytic recovery controls qualified in both directions.',flush=True)
        combined=copy.deepcopy(base);row=combined['rows'][item['row_id']];row['cases']=[]
        for index,case in enumerate(item['cases']):
            vs=case['fixture']['supply_voltage_V'];record={'case_id':case['case_id'],'supply_V':vs,'fixture':case['fixture'],'parts':[],'tests':[]}
            result['cases'].append(record)
            for direction in ('high','low'):
                deck,profile=recovery_deck(model,item,case,direction);fallback=deck.replace('solver=alt','solver=norm')
                meta=overload_meta(model,item,case,direction,profile)
                meta['execution_contract_receipt_dir']=str(out/'execution_contracts')
                seed=base['startup_seeds'].get(f'{vs:.10g}')
                if seed:deck=seeded_deck(deck,seed['seeds'])
                path=recovery_job_path(out,index,vs,direction);path.write_text(deck,encoding='ascii')
                try:
                    job=run_with_fallback(a.ltspice,path,[],True,60,fallback,meta=meta)
                    m=recovery_metrics(read_real_raw(job['path'].with_suffix('.raw')),profile,meta,job['path'])
                    part={**m,'direction':direction,'profile':profile,'path':str(job['path']),'solver_attempts':job['attempts']}
                    passed=not m['gate_issues'] and m['value'] is not None and m['value']<=limit
                    record['tests'].append({'metric':'overload_recovery','variant':direction,'value':m['value'],'operator':'<=','limit':limit,'unit':'s','passed':passed})
                except Exception as e:
                    part={'direction':direction,'execution_error':str(e)}
                    if isinstance(e,ExecutionContractError):
                        part.update(error_type=type(e).__name__,validation=e.validation,physical_spec_failure_established=False)
                    record['tests'].append({'metric':'overload_recovery','variant':direction,'value':None,'operator':'<=','limit':limit,'unit':'s','passed':False})
                record['parts'].append(part);save();print(vs,direction,part.get('value',part.get('execution_error')),flush=True)
            if any(p.get('error_type')=='ExecutionContractError' for p in record['parts']):record['status']='execution_contract_error'
            elif any('execution_error' in p for p in record['parts']):record['status']='execution_error'
            elif any(p['gate_issues'] for p in record['parts']):record['status']='unverified_adapter';record['reason']='Declared saturation/release protocol not established'
            else:record['status']='passed_sampled_model_case' if all(t['passed'] for t in record['tests']) else 'failed_in_model'
            record['full_continuous_range_verified']=False;record['manufacturer_protocol_equivalence_claimed']=False
            row['cases'].append(copy.deepcopy(record));save()
        before={c['case_id']:c for r in base['rows'].values() for c in r['cases']};after={c['case_id']:c for r in combined['rows'].values() for c in r['cases']}
        assert set(before)==set(after) and len(after)==base['source_cases_required']
        assert all(c==after[k] for k,c in before.items() if c['status']=='passed_sampled_model_case')
        counts={s:sum(c['status']==s for c in after.values()) for s in sorted({c['status'] for c in after.values()})}
        combined['case_status_counts']=counts;combined['overload_extension']={'result':str(out/'RESULT.json'),'calibration_qualified':True,'source_conditions_unchanged':True}
        combined['input_signatures'][str(root/'opamp_pipeline/verify_05_overload_recovery.py')]=result['measurement_code_sha256']
        write_json(out/'COMBINED_LEDGER.json',combined)
        result.update(status='extension_completed',case_status_counts=counts);save()
    except Exception as e:result.update(status='error',error=str(e));save();raise
    snapshots=out/'code_snapshot';snapshots.mkdir()
    for source in (root/'opamp_pipeline/verify_05_overload_recovery.py',Path(__file__)):(snapshots/source.name).write_bytes(source.read_bytes())
    write_json(out/'ARTIFACTS.json',{'files':{str(p.relative_to(out)):file_hash(p) for p in out.rglob('*') if p.is_file() and p.name!='ARTIFACTS.json'}})
    print(json.dumps({'status':result['status'],'counts':counts,'output':str(out)}),flush=True)


if __name__=='__main__':main()
