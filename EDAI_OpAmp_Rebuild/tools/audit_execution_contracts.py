"""Offline plan/deck audit: generates fixtures but never launches LTspice or APIs."""
import argparse
import json
from pathlib import Path
from opamp_pipeline.verify_01_fixtures import build_fixture
from opamp_pipeline.validation_03_execution_contract import validate_execution,ExecutionContractError
from opamp_pipeline.validation_01_results import digest,save_report

SUPPORTED={'vos','iq','gbw','pm','settling','ib','ios','vcm','vswing','aol','iout','isc','sr',
           'cmrr','psrr','noise_density','ro','capacitive_drive','input_resistance'}


def audit(plan,model,out,additional=None):
    out=Path(out);out.mkdir(parents=True,exist_ok=False)
    data=json.loads(Path(plan).read_text(encoding='utf-8'));rows=[]
    measurements=list(data['measurements'])
    if additional:
        measurements.append(json.loads(Path(additional).read_text(encoding='utf-8'))['settling_measurement'])
    for item in measurements:
        kind=item['method']['kind']
        for case in item['cases']:
            case_id=case.get('case_id','ADDITIONAL-'+digest(case)[:16])
            if kind not in SUPPORTED:
                rows.append({'kind':kind,'case_id':case_id,'status':'not_checked_specialized_or_unimplemented_adapter'})
                continue
            variants=['lower','upper'] if kind=='vcm' else ['rising','falling'] if kind in {'sr','settling'} else ['pm','rising','falling'] if kind=='capacitive_drive' else ['source','sink'] if kind=='isc' else ['upper','lower'] if kind=='vswing' and case['fixture'].get('forced_output_rail')=='both' else ['default']
            for variant in variants:
                row={'kind':kind,'case_id':case_id,'variant':variant}
                try:
                    deck,meta=build_fixture(model,item,case,variant)
                    result=validate_execution(deck,meta,receipt_dir=out/'receipts')
                    row['status']=result['status']
                except ExecutionContractError as error:
                    row.update(status='execution_contract_error',failed_checks=[c['check_id'] for c in error.validation['checks'] if c['status']=='failed'])
                except (ValueError,KeyError,NotImplementedError) as error:
                    row.update(status='cannot_bind_contract',error=str(error))
                rows.append(row)
    result={'mode':'offline_generated_fixture_audit_no_simulation','source_plan':str(Path(plan).resolve()),
            'plan_sha256':digest(data),'rows':rows,
            'counts':{status:sum(r['status']==status for r in rows) for status in sorted({r['status'] for r in rows})},
            'not_a_circuit_performance_verdict':True}
    save_report(out/'RESULT.json',result)
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--plan',type=Path,required=True);p.add_argument('--model',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--additional',type=Path)
    a=p.parse_args();print(audit(a.plan,a.model,a.output,a.additional)['counts'])
