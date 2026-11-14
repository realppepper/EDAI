"""Fixed partial-scope goals; challenge overrides never change datasheet sources."""
import math

REQUIRED_BENCHES={'opamp_op','opamp_dc','opamp_ac','opamp_tran_rising','opamp_tran_falling','opamp_loop','opamp_gbw'}


def serializable_diagnostics(value):
    if isinstance(value,float) and not math.isfinite(value):return {'invalid_numeric':repr(value)}
    if isinstance(value,dict):return {k:serializable_diagnostics(v) for k,v in value.items()}
    if isinstance(value,list):return [serializable_diagnostics(v) for v in value]
    return value


def make_policy(context,challenge_gbw=None,include_pm=False):
    selected={}
    for symbol in ('IQ','VOS','GBW','ts')+(('PM',) if include_pm else ()):
        matches=[r for r in context['required_rows'] if r['symbol']==symbol and any(c['fixture']['supply_voltage_V']==5 for c in r['cases'])]
        if len(matches)!=1:raise ValueError('Ambiguous 5V source target: '+symbol)
        row=matches[0];rule=row['target']['rules'][0]
        for direction in (['rising','falling'] if symbol=='ts' else [None]):
            key=symbol+('_'+direction if direction else '')
            selected[key]={'row_id':row['row_id'],'symbol':symbol,'source_target':rule['value'],
                'limit':rule['value'],'operator':rule['operator'],'unit':rule['unit'],
                'target_origin':row['target']['origin'],'direction':direction}
    if challenge_gbw is not None:
        if not math.isfinite(challenge_gbw) or challenge_gbw<=selected['GBW']['limit']:
            raise ValueError('Challenge GBW must be finite and stricter than baseline')
        selected['GBW'].update(limit=challenge_gbw,override_reason='Separate project stress test of revision path, not a datasheet edit')
    return {'name':('strengthened_GBW_trial' if challenge_gbw is not None else 'baseline_partial_5V')+('_with_PM' if include_pm else ''),
        'targets':selected,'temperature_C':25,'supply_V':5,'channel_count':1,
        'full_datasheet_success_is_not_claimed':True,'pm_diagnostic_not_a_formal_target':not include_pm,
        'max_candidates_including_seed':3,'max_simulation_seconds':180,'max_execution_retries_per_candidate':3,
        'llm_mode':'current_chat_manual_handoff','external_llm_api_calls':0,
        'chat_token_usage_and_cost':'unavailable; do not report as zero'}


def evaluate(result,policy):
    benches=result.get('benchmarks',[]);byname={b['name']:b for b in benches}
    issues=[]
    if len(byname)!=len(benches) or set(byname)!=REQUIRED_BENCHES:issues.append('Missing/duplicate/unexpected analysis coverage')
    if result.get('status')!='partial_experiment_completed':issues.append('Experiment not completed normally')
    if result.get('error'):issues.append('Experiment error: '+str(result['error']))
    for b in benches:
        if b.get('status')!='executed':issues.append(b['name']+': '+b.get('error','execution error'))
    def metric(bench,name):return byname.get(bench,{}).get('metrics',{}).get(name)
    values={'IQ':metric('opamp_op','iq_A'),'VOS':metric('opamp_op','vos_V'),
        'GBW':metric('opamp_gbw','unity_Hz'),'ts_rising':metric('opamp_tran_rising','settling_s'),
        'ts_falling':metric('opamp_tran_falling','settling_s')}
    if 'PM' in policy['targets']:
        values['PM']=metric('opamp_loop','phase_margin_deg')
        if result.get('pm_validation',{}).get('qualified') is not True:
            issues.append('PM measurement method/crossover not qualified for this fixture')
    if isinstance(values['VOS'],(int,float)):values['VOS']=abs(values['VOS'])
    iq=values['IQ']
    if not isinstance(iq,(int,float)) or not math.isfinite(iq) or iq<=0:issues.append('Invalid supply current')
    error=metric('opamp_op','servo_error_V')
    if not isinstance(error,(int,float)) or not math.isfinite(error) or abs(error)>1e-6:issues.append('DC servo gate failed')
    dc=byname.get('opamp_dc',{}).get('measurements',{}).get('tracking_error')
    if not isinstance(dc,(int,float)) or not math.isfinite(dc) or dc<0 or dc>.01:issues.append('Project 2..3V follower health gate failed (10mV)')
    checks=[]
    for key,t in policy['targets'].items():
        value=values[key];valid=isinstance(value,(int,float)) and not isinstance(value,bool) and math.isfinite(value) and (key=='PM' or value>=0)
        if key=='GBW' and value==0:valid=False
        passed=valid and (value<=t['limit'] if t['operator']=='<=' else value>=t['limit'])
        violation=(max(0,value/t['limit']-1) if t['operator']=='<=' else max(0,1-value/t['limit'])) if valid else 1e6
        checks.append({'key':key,**t,'measured':value if valid else None,'passed':bool(passed),'normalized_violation':violation,
            'missing_or_invalid':not valid,'invalid_value_repr':repr(value) if not valid else None})
    failed=[c for c in checks if not c['passed']]
    score=[len(issues),len(failed),max([c['normalized_violation'] for c in checks],default=0),sum(c['normalized_violation'] for c in checks)]
    return {'scope_passed':not issues and not failed,'full_datasheet_success':False,'gate_issues':issues,
        'checks':checks,'failed_keys':[c['key'] for c in failed],'score':score,
        'diagnostics':serializable_diagnostics({'pm':result.get('pm_diagnostic'),'pm_validation':result.get('pm_validation'),'model_warnings':result.get('model_warnings',[]),
                       'transients':{n:byname.get(n,{}).get('metrics') for n in ('opamp_tran_rising','opamp_tran_falling')}}),
        'unmeasured_requirements_remain':True}
