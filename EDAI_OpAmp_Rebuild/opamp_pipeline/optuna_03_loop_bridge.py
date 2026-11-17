"""Optional bounded numeric-repair stage inside the existing fixed-harness loop."""
from pathlib import Path
from copy import deepcopy
import subprocess
import sys
import time
import math
from .support.execution_state import file_hash
from .loop_04_extended_policy import ledger
from .loop_02_handoff import write_json

ROOT=Path(__file__).resolve().parents[1]


def routing_reason(state,current,document):
    """Only optimize measured numeric misses, not missing/invalid verification."""
    if current['assessment']['scope_passed']:return 'already_satisfied'
    policy=state.get('optuna')
    if not policy:return 'disabled'
    if len(state.get('optuna_attempts',[]))>=policy['max_rounds']:return 'sizing_budget_exhausted'
    if current.get('execution_error'):return 'measurement_execution_error'
    startup=document.get('operational_startup',{})
    if startup.get('passed') is not True:
        from .optuna_06_startup import repair_evidence
        if repair_evidence(startup,current.get('candidate_path'),current.get('candidate_sha256')):
            return 'startup_repair_eligible'
        return 'startup_not_qualified'
    records=ledger(document)
    for case_id in current['assessment']['failed_case_ids']:
        row=records[case_id];case=row['case']
        if case['status']!='failed_in_model':return 'verification_or_model_issue'
        if case.get('gate_issues') or any(p.get('gate_issues') for p in case.get('parts',[])):return 'measurement_prerequisites_not_qualified'
        tests=case.get('tests',[])
        if not tests or any(isinstance(t.get('value'),bool) or not isinstance(t.get('value'),(int,float)) or not math.isfinite(t['value']) for t in tests):return 'missing_numeric_feedback'
    return 'numeric_repair_eligible'


def configure(path,trials=4,max_rounds=1):
    import json
    path=Path(path).resolve();config=json.loads(path.read_text(encoding='utf-8'))
    for value in (trials,max_rounds):
        if isinstance(value,bool) or not isinstance(value,int) or not 1<=value<=20:raise ValueError('Bounded sizing budgets must be integers1..20')
    if not config.get('screening_kinds'):raise ValueError('Sizing screening quantities required')
    return {'config_path':str(path),'config_sha256':file_hash(path),'trials':trials,
            'max_rounds':max_rounds,'screening_kinds':config['screening_kinds']}


def feedback(state):
    return {'mode':'bounded_numeric_repair','routing_reason':state.get('optuna_routing_reason'),
            'attempts':deepcopy(state.get('optuna_attempts',[])),
            'instruction':'Sizing is measured evidence, not a proven physical cause. Preserve source targets, report tradeoffs, and revise structure or justified bounds if needed.',
            'full_datasheet_success':False}


def execute(session,state,ltspice):
    """Called only by advance/resume; pending event is persisted before subprocess."""
    from . import harness_03_loop as fixed
    from .harness_06_evolution import _pipeline_evidence
    session=Path(session);policy=state['optuna'];current=state['candidates'][-1]
    if policy.get('mode')=='designer_proposal' and policy.get('proposal_for_candidate')!=current['candidate_sha256']:
        raise ValueError('No approved sizing proposal for the current candidate')
    if file_hash(policy['config_path'])!=policy['config_sha256']:raise ValueError('Frozen sizing contract changed')
    from .optuna_01_parameters import validate_space
    try:validate_space(Path(current['candidate_path']).read_text(encoding='ascii'),fixed.read(policy['config_path']))
    except ValueError as error:
        state['optuna_routing_reason']='incompatible_sizing_contract: '+str(error)
        fixed.prepare(session,state);fixed.save(session,state);return state
    attempts=state.setdefault('optuna_attempts',[])
    event=attempts[-1] if attempts and attempts[-1]['status'] in {'started','interrupted'} else None
    if event is None:
        if len(attempts)>=policy['max_rounds']:raise ValueError('Sizing round budget exhausted')
        event={'index':len(attempts),'status':'started','base_candidate_index':current['index'],
               'output':str(session/f'optuna_{len(attempts):03d}'),'started_unix':time.time()}
        attempts.append(event)
    if event['base_candidate_index']!=current['index']:raise ValueError('Sizing base changed during interrupted execution')
    state.update(status='optimizing_parameters',pending_request=None);fixed.save(session,state)
    out=Path(event['output'])
    command=[sys.executable,str(ROOT/'run_optuna_sizing.py'),'--netlist',current['candidate_path'],
             '--run-dir',state['run_dir'],'--config',policy['config_path'],'--output-dir',str(out),
             '--ltspice',str(ltspice),'--trials',str(policy['trials']),'--time-budget','180',
             '--bench-timeout','20','--validate-best','--harness',state['harness_path']]
    if (out/'INPUTS.json').exists():command.append('--resume')
    logs=session/f"optuna_{event['index']:03d}_process";logs.mkdir(exist_ok=True)
    try:
        with (logs/'stdout.txt').open('w',encoding='utf-8') as stdout,(logs/'stderr.txt').open('w',encoding='utf-8') as stderr:
            process=subprocess.run(command,cwd=ROOT,stdout=stdout,stderr=stderr,timeout=3600)
        if process.returncode:raise RuntimeError('Sizing worker did not complete; preserve artifacts and resume explicitly')
        result=fixed.read(out/'RESULT.json')
        if not result.get('original_unchanged') or result['original_sha256']!=current['candidate_sha256']:raise ValueError('Sizing evidence belongs to another candidate')
        event.update(status='completed',result_path=str(out/'RESULT.json'),result_sha256=file_hash(out/'RESULT.json'),
                     outcome=result['status'],trial_count=len(result['trials']),
                     trials=[{k:t[k] for k in ('number','params','status','objective_power_mW','feasible_for_screening','failed_case_ids','error') if k in t} for t in result['trials']])
        if result.get('status')=='completed_with_final_validation':
            candidate=Path(result['best_screened_path']);validation=Path(result['final_validation']).parent
            _,document=_pipeline_evidence(validation,candidate,state['plan_path'])
            baseline=fixed.read(state['candidates'][0]['ledger_path'])
            evaluated=fixed.assessment(baseline,document,state['scope_case_ids'])
            old=ledger(fixed.read(current['ledger_path']));new=ledger(document)
            regressions=[key for key,value in old.items() if value['case']['status']=='passed_sampled_model_case' and new[key]['case']['status']!='passed_sampled_model_case']
            record={'index':len(state['candidates']),'origin':'optuna_numeric_repair',
                    'candidate_path':str(candidate),'candidate_sha256':file_hash(candidate),
                    'ledger_path':str(validation/'LEDGER.json'),'ledger_sha256':file_hash(validation/'LEDGER.json'),
                    'assessment':evaluated,'pipeline_seconds':fixed.read(validation/'STATE.json')['execution_seconds'],
                    'eligible_for_best':not regressions,'previous_pass_regressions':regressions,
                    'sizing_result':str(out/'RESULT.json'),'sizing_sha256':event['result_sha256']}
            state['candidates'].append(record);event['registered_candidate_index']=record['index']
        state.update(optuna_routing_reason='sizing_completed_return_to_controller',status='optuna_ready_to_advance')
        fixed.save(session,state)
        fixed.advance(session,state,ltspice,allow_sizing=False)
        return state
    except Exception as error:
        if event.get('status')=='completed':
            state['status']='optuna_ready_to_advance'
        else:
            event.update(status='interrupted',error_type=type(error).__name__,error=str(error))
            state.update(status='optuna_interrupted',pending_request=None)
        fixed.save(session,state)
        return state
