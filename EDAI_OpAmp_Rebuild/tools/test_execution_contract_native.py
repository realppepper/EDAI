"""Native known-answer checks of the contract/measurement boundary, without APIs.

Uses a fresh directory and preserves the TL071C DUT and every historical result.
This is a verification diagnostic, not a design loop or full datasheet sign-off.
"""
import argparse
from copy import deepcopy
from pathlib import Path
import hashlib
import json
import time
from opamp_pipeline.validation_01_results import save_report
from opamp_pipeline.validation_03_execution_contract import validate_execution,ExecutionContractError
from opamp_pipeline.verify_01_fixtures import build_fixture
from opamp_pipeline.verify_02_metrics import measure
from opamp_pipeline.verify_03_calibrate import calibrate
from opamp_pipeline.verify_11_settling import calibrate_settling
from opamp_pipeline.tb_02_ltspice import run_bench


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def run(executable,root,out):
    out=Path(out).resolve();out.mkdir(parents=True,exist_ok=False)
    experiment=root/'runs/cold_start/20261117_tl071'
    dut=experiment/'final/TL071C_PS_generic_FINAL.inc'
    request_path=experiment/'followup_20261117/ADDITIONAL_REQUEST.json'
    plan_path=experiment/'document/measurement_plan/plan_02_measurements.json'
    request=json.loads(request_path.read_text(encoding='utf-8'))
    plan=json.loads(plan_path.read_text(encoding='utf-8'))
    originals={str(p):sha(p) for p in (dut,request_path,plan_path)}
    result={'status':'running','mode':'native_verification_diagnostic_no_api_no_design_changes',
            'inputs_sha256':originals,'native_jobs':[],'negative_controls':[],'dut_cases':[]}
    started=time.monotonic()
    def save():save_report(out/'RESULT.json',result)
    save()
    def execute(label,deck,meta):
        meta['execution_contract_receipt_dir']=str(out/'execution_contracts')
        folder=out/'jobs'/label;folder.mkdir(parents=True,exist_ok=False)
        path=folder/'bench.cir';path.write_text(deck,encoding='ascii')
        preflight=validate_execution(path.read_text(encoding='ascii'),meta,phase='execution_preflight')
        record={'label':label,'path':str(path),'contract_status':preflight['status'],'status':'started'}
        result['native_jobs'].append(record);save()
        try:
            native=run_bench(executable,path,meta['names'],ascii_raw=meta['analysis']!='noise',timeout=45)
        except Exception as error:
            record.update(status='error',error=str(error));save();raise
        record.update(status='completed',deck_sha256=sha(path),raw_sha256=sha(path.with_suffix('.raw')),
                      log_sha256=sha(path.with_suffix('.log')));save()
        print(label+' completed; contract='+preflight['status'],flush=True)
        return {'path':path,'measurements':native['measurements']}
    try:
        calibration=calibrate(out,{'measurements':[]},execute)
        save_report(out/'ADAPTER_VALIDATION.json',calibration)
        if calibration['status']!='passed':raise AssertionError('Existing native known-answer controls failed')
        result['adapter_calibration_status']=calibration['status'];save()
        item=request['settling_measurement'];case=item['cases'][0]
        controls=calibrate_settling(out,item,case,execute)
        save_report(out/'SETTLING_20V_20PERCENT_CONTROLS.json',controls)
        if len(controls)!=4 or not all(c['passed'] for c in controls):raise AssertionError('20V/20% analytical controls failed')
        result['settling_controls_status']='passed';save()
        deck,meta=build_fixture(dut,item,case,'rising')
        mutations=[('20V_became_2V',deck.replace('5.01u 26','5.01u 8').replace('40u 26','40u 8'),deepcopy(meta)),
                   ('20percent_became_point1percent',deck,deepcopy(meta)),
                   ('load_became_20k',deck.replace('RL out mid 2000','RL out mid 20000'),deepcopy(meta))]
        mutations[1][2]['step']['error_fraction']=.001
        for label,bad,badmeta in mutations:
            calls=len(result['native_jobs'])
            try:execute('negative_'+label,bad,badmeta)
            except ExecutionContractError as error:
                result['negative_controls'].append({'label':label,'blocked_before_native_run':len(result['native_jobs'])==calls,
                   'physical_spec_failure_established':error.physical_spec_failure_established,'validation':error.validation})
            else:raise AssertionError('Mutation was not blocked: '+label)
            save()
        # Representative native OP/AC checks, using the unchanged TL071C design.
        for kind in ('iq','gbw','pm'):
            row=next(i for i in plan['measurements'] if i['method']['kind']==kind)
            c=row['cases'][0];d,m=build_fixture(dut,row,c)
            job=execute('dut_'+kind,d,m)
            measured=measure(job['path'],kind,c['fixture'],m,job['measurements'])
            result['dut_cases'].append({'kind':kind,'measured':measured,
                'passed_metric_gates':not measured['gate_issues']})
            if measured['gate_issues']:raise AssertionError('Representative measurement gate failed: '+kind)
            save()
        expected=request.get('settling_source_interpretation',{})
        for direction in ('rising','falling'):
            d,m=build_fixture(dut,item,case,direction)
            job=execute('dut_settling_'+direction,d,m)
            measured=measure(job['path'],'settling',case['fixture'],m,job['measurements'])
            if measured['gate_issues'] or measured['value'] is None:raise AssertionError('Actual settling measurement invalid')
            physical_pass=measured['value']<=item['target_s']
            result['dut_cases'].append({'kind':'settling','direction':direction,'measured':measured,
                'target_s':item['target_s'],'physical_pass':physical_pass,'contract_passed':True})
            # Regression must continue to distinguish a valid measurement from a spec pass.
            if physical_pass:raise AssertionError('Unexpected change to known TL071C settling failure')
            tampered=deepcopy(m);tampered['step']['error_fraction']=.001
            try:measure(job['path'],'settling',case['fixture'],tampered,job['measurements'])
            except ExecutionContractError:
                result['negative_controls'].append({'label':'post_run_metric_tamper_'+direction,
                                                    'blocked_before_verdict':True})
            else:raise AssertionError('Metric tampering after native run was not blocked')
            save()
        result['inputs_unchanged']=all(sha(p)==value for p,value in originals.items())
        if not result['inputs_unchanged']:raise AssertionError('Input evidence changed')
        result.update(status='passed_verification_diagnostic',seconds=time.monotonic()-started,
                      full_datasheet_success=False,
                      limits=['Some directly authored analytical decks remain not_checked by contract; their numerical controls are still evaluated.',
                              'No fallback/cache/startup/specialized-extension qualification in this diagnostic.'])
        save();return result
    except Exception as error:
        result.update(status='error',error_type=type(error).__name__,error=str(error),seconds=time.monotonic()-started)
        save();raise


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--ltspice',required=True)
    p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    r=run(a.ltspice,Path(__file__).resolve().parents[1],a.output)
    print(r['status']+'; native_jobs='+str(len(r['native_jobs'])),flush=True)
