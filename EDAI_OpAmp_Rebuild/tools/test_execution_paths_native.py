"""Native retry/cache/special-adapter qualification with deliberate controller faults."""
from copy import deepcopy
from pathlib import Path
import argparse
import hashlib
import json
import time
from unittest.mock import patch
from opamp_pipeline.validation_01_results import save_report
from opamp_pipeline.validation_03_execution_contract import validate_execution,ExecutionContractError
from opamp_pipeline.validation_04_execution_paths import execution_signature,reusable_job
from opamp_pipeline.validation_05_special_fixtures import impedance_meta,overload_meta
from opamp_pipeline.verify_01_fixtures import build_fixture
from opamp_pipeline.verify_02_metrics import measure
from opamp_pipeline.verify_04_input_impedance import REFERENCE,impedance_deck,measure_pair
from opamp_pipeline.verify_05_overload_recovery import recovery_deck,recovery_metrics,reference_model,analytic_recovery
from opamp_pipeline.diag_03_solver_attempts import run_with_fallback
from opamp_pipeline.tb_02_ltspice import run_bench
from opamp_pipeline.tb_05_waveform_metrics import read_real_raw


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def run(executable,out):
    out=Path(out).resolve();out.mkdir(parents=True,exist_ok=False)
    result={'status':'running','native_jobs':0,'checks':[],'negative_controls':[]}
    start=time.monotonic()
    save=lambda:save_report(out/'RESULT.json',result)
    def check(name,passed,**evidence):
        result['checks'].append({'name':name,'passed':bool(passed),**evidence});save()
        if not passed:raise AssertionError(name)
    def execute(label,deck,meta):
        path=out/label/'bench.cir';path.parent.mkdir(parents=True)
        path.write_text(deck,encoding='ascii');meta['execution_contract_receipt_dir']=str(out/'execution_contracts')
        validate_execution(deck,meta,phase='special_preflight')
        native=run_bench(executable,path,meta['names'],ascii_raw=meta['analysis']!='noise',timeout=45)
        result['native_jobs']+=1;save()
        return path,native
    try:
        f={'supply_voltage_V':5,'rails_V':{'V_plus':5,'V_minus':0},'temperature_C':25,
           'load':{'kind':'resistance','value_Ohm':10000,'connection':'rail_midpoint'},'load_capacitance_pF':None}
        model=out/'settling.inc';model.write_text('.subckt SETREF P N VP VM OUT\nEDRIVE drive 0 P 0 1\nRPOLE drive pole 1k\nCPOLE pole VM 40p\nEOUT OUT 0 pole 0 1\n.ends SETREF\n')
        item={'method':{'kind':'settling','definition':{'input_step_V':2,'error_percent':20}}};case={'fixture':deepcopy(f)}
        deck,meta=build_fixture(model,item,case,'rising','SETREF')
        meta['execution_contract_receipt_dir']=str(out/'execution_contracts')
        primary=out/'retry/bench.cir';primary.parent.mkdir();primary.write_text(deck)
        fallback=deck.replace('.end','.options solver=norm\n.end')
        calls=[]
        def inject_once(*args,**kwargs):
            calls.append(str(args[1]))
            if len(calls)==1:raise TimeoutError('Deliberate controller-level timeout injection; LTspice not called on this attempt')
            result['native_jobs']+=1;save()
            return run_bench(*args,**kwargs)
        with patch('opamp_pipeline.diag_03_solver_attempts.run_bench',side_effect=inject_once):
            retry=run_with_fallback(executable,primary,[],True,45,fallback,meta)
        measured=measure(retry['path'],'settling',f,meta,{})
        check('forced_retry_reaches_native_and_measures',len(calls)==2 and len(retry['attempts'])==2 and not measured['gate_issues'] and measured['value'] is not None,
              attempts=retry['attempts'],measured=measured,first_failure_origin='controlled_timeout_injection')
        cache_deck=retry['path'].read_text(encoding='ascii');sig=execution_signature(cache_deck,meta)
        entry={'completed':True,'path':str(retry['path']),'measurements':{},'execution_signature':sig,
               'artifacts':{str(p):sha(p) for p in (retry['path'],retry['path'].with_suffix('.raw'),retry['path'].with_suffix('.log'))}}
        count=result['native_jobs'];hit=reusable_job(entry,cache_deck,meta,sig)
        cached_measure=measure(hit['path'],'settling',f,meta,hit['measurements'])
        check('cache_reuse_without_native_call',result['native_jobs']==count and cached_measure==measured)
        changed=deepcopy(item);changed['method']['definition']['error_percent']=.1
        same_deck,newmeta=build_fixture(model,changed,case,'rising','SETREF')
        newmeta['execution_contract_receipt_dir']=str(out/'execution_contracts')
        check('changed_measurement_definition_is_cache_miss',reusable_job(entry,same_deck,newmeta,execution_signature(same_deck,newmeta)) is None)
        corrupt=deepcopy(entry);corrupt['artifacts'][str(retry['path'].with_suffix('.raw'))]='0'*64
        check('bad_artifact_receipt_is_cache_miss',reusable_job(corrupt,cache_deck,meta,sig) is None)
        bad=fallback.replace('RL out mid 10000','RL out mid 1000')
        with patch('opamp_pipeline.diag_03_solver_attempts.run_bench') as native:
            try:run_with_fallback(executable,primary,[],True,45,bad,meta)
            except ExecutionContractError:blocked=True
            else:blocked=False
            check('bad_retry_blocked_before_any_execution',blocked and native.call_count==0)
        ref=out/'impedance.inc';ref.write_text(REFERENCE,encoding='ascii');paths=[];metas=[]
        for mode in ('differential','common'):
            m=impedance_meta(ref,f,mode,'ZREF');path,_=execute('impedance_'+mode,impedance_deck(ref,f,mode,'ZREF'),m)
            paths.append(path);metas.append(m)
        z=measure_pair(*paths,metas=metas)
        good=not z['gate_issues'] and not z['differential_interpretation_issues']
        for mode,r,c in [('differential',1e7,.1e-12),('common',4e9,1.5e-12)]:
            fit=z[mode];good=good and not fit['fit_issues'] and fit['resistance_Ohm'] is not None and abs(fit['resistance_Ohm']/r-1)<1e-4 and abs(fit['capacitance_F']/c-1)<1e-4
        check('impedance_reference_and_both_contracts',good,measured=z)
        overloaded=deepcopy(case);overloaded['fixture']['closed_loop_gain']=-10
        over_item={'method':{'kind':'overload_recovery','definition':{'gain':-10,'initial_input_offset_fraction_of_supply':.12,'output_error_band_fraction_of_supply':.001}}}
        for label,cap in [('fast',1e-9),('slow',5e-9)]:
            ref=out/(label+'_overload.inc');ref.write_text(reference_model(cap),encoding='ascii')
            for direction in ('high','low'):
                deck,profile=recovery_deck(ref,over_item,overloaded,direction,'ORREF',True)
                m=overload_meta(ref,over_item,overloaded,direction,profile,'ORREF',True)
                path,_=execute('overload_'+label+'_'+direction,deck,m)
                value=recovery_metrics(read_real_raw(path.with_suffix('.raw')),profile,m,path)
                expected=analytic_recovery(profile,cap,10000)
                good=not value['gate_issues'] and value['value'] is not None and abs(value['value']-expected)<max(5e-9,expected*.01)
                check('overload_'+label+'_'+direction,good,expected_s=expected,measured=value)
                tamper=deepcopy(m);bad_profile=deepcopy(profile);bad_profile['error_band_V']*=10
                try:recovery_metrics(read_real_raw(path.with_suffix('.raw')),bad_profile,tamper,path)
                except ExecutionContractError:blocked=True
                else:blocked=False
                check('overload_band_tamper_'+label+'_'+direction,blocked)
        result.update(status='passed',seconds=time.monotonic()-start,api_calls=0,dut_changed=False)
        save();return result
    except Exception as error:
        result.update(status='error',error_type=type(error).__name__,error=str(error),seconds=time.monotonic()-start)
        save();raise


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--ltspice',required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();value=run(args.ltspice,args.output);print(value['status'],value['native_jobs'])
