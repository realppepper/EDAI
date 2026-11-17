"""Qualify the source-resistance noise fixture and rerun the unchanged TL071C case."""
import argparse
from copy import deepcopy
from pathlib import Path
import hashlib
import json
import math
from opamp_pipeline.validation_01_results import save_report
from opamp_pipeline.validation_03_execution_contract import validate_execution,ExecutionContractError
from opamp_pipeline.verify_01_fixtures import build_fixture
from opamp_pipeline.verify_02_metrics import measure
from opamp_pipeline.tb_02_ltspice import run_bench
from run_extended_verification import case_verdict


def run(root,out,executable):
    out=Path(out).resolve();out.mkdir(parents=True,exist_ok=False)
    source=root/'runs/cold_start/20261117_tl071'
    dut=source/'final/TL071C_PS_generic_FINAL.inc';plan=source/'document/measurement_plan/plan_02_measurements.json'
    sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
    originals={str(p):sha(p) for p in [dut,plan]}
    result={'status':'running','reference_checks':[],'negative_controls':[],'native_jobs':0,'inputs_sha256':originals}
    save=lambda:save_report(out/'RESULT.json',result)
    save()
    def execute(label,model,item,case,subckt):
        deck,meta=build_fixture(model,item,case,subckt=subckt)
        meta['execution_contract_receipt_dir']=str(out/'execution_contracts')
        path=out/label/'bench.cir';path.parent.mkdir();path.write_text(deck,encoding='ascii')
        validate_execution(deck,meta,phase='noise_preflight')
        native=run_bench(executable,path,meta['names'],ascii_raw=False,timeout=45)
        result['native_jobs']+=1;save()
        value=measure(path,'noise_density',case['fixture'],meta,native['measurements'])
        return value,deck,meta,path
    try:
        reference=out/'noise_reference.inc'
        reference.write_text('* Noiseless controlled-source amplifier; series Rs is the only dissipative noise source\n.subckt NOISEREF P N VP VM OUT\nEAMP OUT VM P N 100\n.ends NOISEREF\n',encoding='ascii')
        for resistance,temperature in [(20,25),(200,25),(20,50)]:
            f={'supply_voltage_V':5,'rails_V':{'V_plus':5,'V_minus':0},'temperature_C':temperature,
               'load':{'kind':'resistance','value_Ohm':None,'connection':'rail_midpoint'},'load_capacitance_pF':None,
               'source_case_conditions':{'source_resistance_Ohm':resistance,'frequency_Hz':1000}}
            item={'method':{'kind':'noise_density'}};case={'fixture':f}
            measured,deck,meta,path=execute(f'ref_{resistance}Ohm_{temperature}C',reference,item,case,'NOISEREF')
            expected=math.sqrt(4*1.380649e-23*(temperature+273.15)*resistance)
            passed=not measured['gate_issues'] and math.isclose(measured['value'],expected,rel_tol=2e-4)
            result['reference_checks'].append({'resistance_Ohm':resistance,'temperature_C':temperature,'expected_V_per_sqrt_Hz':expected,
                                               'measured':measured,'passed':passed,'path':str(path)})
            save()
            if not passed:raise AssertionError('Source resistor thermal-noise analytical control failed')
            bad=deck.replace(f'RSOURCE noise_src inp {resistance}\n','')
            try:validate_execution(bad,meta,phase='injected_missing_source_resistance')
            except ExecutionContractError:blocked=True
            else:blocked=False
            result['negative_controls'].append({'missing_resistor_blocked':blocked,'resistance_Ohm':resistance,'temperature_C':temperature});save()
            if not blocked:raise AssertionError('Missing source resistance was accepted')
        rows=json.loads(plan.read_text(encoding='utf-8'))['measurements']
        item=next(i for i in rows if i['method']['kind']=='noise_density');case=item['cases'][0]
        measured,deck,meta,path=execute('tl071_noise',dut,item,case,'FIRSTAMP')
        verdict=case_verdict(item,case,[measured])
        result.update(dut_measurement=measured,dut_verdict=verdict,dut_job_path=str(path),
                      inputs_unchanged=all(sha(p)==value for p,value in originals.items()),
                      expected_model_limitation_preserved=verdict['status']=='unverified_model')
        if measured['gate_issues'] or measured['value'] is None:raise AssertionError('DUT noise measurement did not complete')
        if not result['inputs_unchanged'] or not result['expected_model_limitation_preserved']:raise AssertionError('Unexpected evidence/model-status change')
        result.update(status='passed_fixture_qualification',api_calls=0,dut_changed=False,full_datasheet_success=False)
        save();return result
    except Exception as error:
        result.update(status='error',error_type=type(error).__name__,error=str(error));save();raise


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--ltspice',required=True);p.add_argument('--output',type=Path,required=True)
    args=p.parse_args();r=run(Path(__file__).resolve().parents[1],args.output,args.ltspice)
    print(r['status'],r['dut_verdict']['status'],r['dut_measurement']['value'])
