"""Project operating gate, separate from the datasheet's case count."""
import math
from .support.execution_state import file_hash

GATE_ID='OPERATIONAL-STARTUP'
POLICY={'stop_time_s':100e-6,'tail_window_s':20e-6,
        'max_internal_tail_span_V':.005,'max_output_midpoint_error_V':.01,
        'min_bias_V':.65,'origin':'project_operational_requirement_not_datasheet_spec'}


def startup_gate(core,plan):
    supplies=sorted({float(c['fixture']['supply_voltage_V'])
                     for r in plan['measurements'] for c in r['cases']})
    if not supplies:raise ValueError('No startup supply coverage')
    records=[]
    for supply in supplies:
        key=f'{supply:.10g}';receipt=core.get('startup_seeds',{}).get(key)
        failure=core.get('startup_seed_failures',{}).get(key)
        passed=False;details={};reason='Startup diagnostic missing'
        if receipt is not None:
            artifacts=receipt.get('artifacts',{})
            if len(artifacts)<3 or any(file_hash(p)!=h for p,h in artifacts.items()):
                raise ValueError('Startup waveform artifacts missing or changed')
            details=receipt['details']
            span,out,bias=(details[k] for k in ('max_internal_tail_span_V','output_final_V','bias_final_V'))
            passed=(all(math.isfinite(v) for v in (span,out,bias)) and 0<=span<=.005
                    and abs(out-supply/2)<=.01 and bias>.65 and failure is None)
            reason='Qualified physical-ramp settling' if passed else 'Startup settling bounds not met'
        elif failure:reason=failure['error']
        records.append({'supply_V':supply,'passed':passed,'details':details,'reason':reason,
                        'artifact_paths':list(receipt.get('artifacts',{})) if receipt else [failure['path']] if failure else []})
    return {'id':GATE_ID,'required':True,'policy':dict(POLICY),'supplies_V':supplies,
            'passed':all(r['passed'] for r in records),'cases':records,
            'datasheet_case_count_increment':0}


def gate_assessment(baseline,current):
    """Legacy records stay historical; new required gates cannot disappear."""
    a=baseline.get('operational_startup');b=current.get('operational_startup')
    if a and not b:raise ValueError('Required startup evidence disappeared')
    if a and b and (a['policy']!=b['policy'] or a['supplies_V']!=b['supplies_V']):
        raise ValueError('Startup policy/coverage changed during comparison')
    if b:
        passed=(b.get('required') is True and b.get('passed') is True
                and len(b.get('cases',[]))==len(b['supplies_V'])
                and sorted(c['supply_V'] for c in b['cases'])==b['supplies_V']
                and all(c.get('passed') is True for c in b['cases']))
        return {'startup_gate_required':True,'startup_passed':passed,
                'failed_operational_gate_ids':[] if passed else [GATE_ID]}
    return {'startup_gate_required':False,'startup_passed':None,'failed_operational_gate_ids':[]}
