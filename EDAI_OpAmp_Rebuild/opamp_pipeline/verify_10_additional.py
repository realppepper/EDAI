"""Versioned additional checks; never rewrite a completed circuit's source ledger."""
import json
from pathlib import Path
from .verify_01_fixtures import build_fixture
from .verify_02_metrics import measure
from .verify_03_calibrate import calibrate
from .tb_02_ltspice import run_bench
from .support.execution_state import file_hash
from .support.measurement_capabilities import measurement_capability
from .verify_11_settling import calibrate_settling
from .loop_02_handoff import write_json
from .validation_03_execution_contract import validate_execution,ExecutionContractError


def run_additional(model,request_path,out,ltspice):
    model,request_path,out=map(lambda p:Path(p).resolve(),(model,request_path,out))
    out.mkdir(parents=True,exist_ok=False)
    request=json.loads(request_path.read_text(encoding='utf-8'))
    if request['candidate_sha256']!=file_hash(model):raise ValueError('Additional check DUT changed')
    pdf=Path(request['source_pdf'])
    if request['source_sha256']!=file_hash(pdf):raise ValueError('Additional check PDF changed')
    signatures={str(p):file_hash(p) for p in [model,request_path,*Path(__file__).parent.rglob('*.py')]}
    result={'status':'running','input_signatures':signatures,'historical_ledger_rewritten':False,
        'circuit_revisions_used':0,'full_datasheet_success':False,'additional_cases':[],'capability_inventory':[]}
    save=lambda:write_json(out/'RESULT.json',result)
    save()
    def execute(label,deck,meta):
        meta['execution_contract_receipt_dir']=str(out/'execution_contracts')
        validate_execution(deck,meta,phase='execution_preflight')
        p=out/'jobs'/(label+'.cir');p.parent.mkdir(exist_ok=True)
        p.write_text(deck,encoding='ascii')
        r=run_bench(ltspice,p,meta.get('names',[]),ascii_raw=meta['analysis']!='noise',timeout=60)
        print(label+' completed',flush=True)
        return {'path':p,'measurements':r['measurements']}
    try:
        validation=calibrate(out,{'measurements':[]},execute)
        write_json(out/'ADAPTER_VALIDATION.json',validation)
        if validation['status']!='passed':raise ValueError('Reference calibration failed; no DUT verdicts')
        item=request['settling_measurement'];case=item['cases'][0]
        # Independent first-order controls: both a passing and failing timing target.
        controls=calibrate_settling(out,item,case,execute)
        write_json(out/'SETTLING_REFERENCE_VALIDATION.json',controls)
        if len(controls)!=4 or not all(c['passed'] for c in controls):raise ValueError('Settling reference controls failed')
        for inventory in request['capability_items']:
            result['capability_inventory'].append({**inventory,**measurement_capability(inventory['symbol'],request['model_capabilities'],request['physical_channels'])})
        save()
        for direction in ('rising','falling'):
            deck,meta=build_fixture(model,item,case,direction)
            job=execute('dut_settling_'+direction,deck,meta)
            measured=measure(job['path'],'settling',case['fixture'],meta,job['measurements'])
            passed=not measured['gate_issues'] and measured['value'] is not None and measured['value']<=item['target_s']
            result['additional_cases'].append({'kind':'settling','direction':direction,
                'status':'passed_sampled_model_case' if passed else 'failed_in_model',
                'target_s':item['target_s'],'definition':meta['step'],'measured':measured,
                'source_interpretation':request['settling_source_interpretation'],
                'manufacturer_protocol_equivalence_confirmed':False,'job_path':str(job['path'])})
            save()
        result['status']='completed_with_explicit_limits'
        result['all_additional_checks_passed']=all(c['status']=='passed_sampled_model_case' for c in result['additional_cases'])
        result['artifacts']={str(p):file_hash(p) for p in out.rglob('*') if p.is_file() and p.name!='RESULT.json'}
        save();return result
    except Exception as error:
        result.update(status='error',error_type=type(error).__name__,error=str(error))
        if isinstance(error,ExecutionContractError):
            result.update(error_category='execution_contract_error',validation=error.validation,
                          physical_spec_failure_established=False)
        save();raise
