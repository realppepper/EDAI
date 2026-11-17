"""Optional fixed-topology Optuna sizing; source targets and original DUT are immutable."""
import argparse
from pathlib import Path
import sys
import json
import math
import subprocess
import time
from importlib.metadata import version

ROOT=Path(__file__).resolve().parent
LOCAL_DEPS=ROOT/'.optuna_deps'
if LOCAL_DEPS.is_dir():sys.path.insert(0,str(LOCAL_DEPS))

from opamp_pipeline.optuna_01_parameters import validate_space,apply_parameters,normalized_constraints
from opamp_pipeline.optuna_02_screening import load_plan,NativeExecutor,screen_candidate
from opamp_pipeline.verify_03_calibrate import calibrate
from opamp_pipeline.validation_01_results import save_report
from opamp_pipeline.support.execution_state import file_hash
from opamp_pipeline.loop_02_handoff import validate_dut
from opamp_pipeline.validation_03_execution_contract import ExecutionContractError
from opamp_pipeline.harness_01_fixed import DEFAULT_POLICY,load_harness
from opamp_pipeline.optuna_05_acceptance import ranked_candidates,full_assessment,validate_shortlist,POWER_ABS_TOL_MW,POWER_REL_TOL
from opamp_pipeline.harness_06_evolution import _pipeline_evidence


def mark_interrupted_trial(records,number):
    """Update a trial in place; interruption must not inflate the trial budget."""
    matches=[r for r in records if r.get('number')==number]
    if matches:
        record=matches[0]
        # A legacy duplicate can be consolidated without discarding its metadata.
        for duplicate in matches[1:]:
            for key,value in duplicate.items():record.setdefault(key,value)
        records[:]=[r for r in records if r.get('number')!=number or r is record]
    else:
        record={'number':number};records.append(record)
    record.update(status='interrupted_execution',artifacts_preserved=True)
    return record


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('netlist','run-dir','config','output-dir'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--ltspice',required=True);p.add_argument('--trials',type=int,default=4,help='Maximum total trials including the baseline and failures')
    p.add_argument('--harness',type=Path,default=DEFAULT_POLICY)
    p.add_argument('--time-budget',type=float,default=300,help='Search time budget in seconds, checked between trials; excludes calibration/final validation')
    p.add_argument('--bench-timeout',type=float,default=30)
    p.add_argument('--resume',action='store_true');p.add_argument('--validate-best',action='store_true')
    p.add_argument('--validation-candidates',type=int,default=3,help='Bounded full-validation shortlist, including screening-infeasible numeric progress if needed')
    a=p.parse_args()
    if not 1<=a.trials<=20 or not 1<=a.validation_candidates<=20 or not math.isfinite(a.time_budget) or a.time_budget<=0 or not math.isfinite(a.bench_timeout) or a.bench_timeout<=0:p.error('Positive bounded budgets required (trials/validation candidates1..20)')
    try:import optuna
    except ImportError:raise SystemExit('Install requirements-optuna.txt, or install it into .optuna_deps. See docs/OPTUNA_SIZING.md.')
    if optuna.__version__!='5.1.0':raise SystemExit('This adapter was qualified with optuna==5.1.0; use the pinned optional requirements.')
    model=a.netlist.resolve();run_dir=a.run_dir.resolve();config_path=a.config.resolve();out=a.output_dir.resolve()
    read=lambda path:json.loads(Path(path).read_text(encoding='utf-8'))
    text=model.read_text(encoding='ascii');validate_dut(text)
    config=read(config_path);baseline=validate_space(text,config);plan=load_plan(run_dir)
    harness,_=load_harness(a.harness)
    if not isinstance(config.get('seed'),int) or isinstance(config.get('seed'),bool):raise ValueError('Explicit integer random seed required')
    sources=[model,config_path,a.harness.resolve(),run_dir/'measurement_plan/plan_02_measurements.json',Path(__file__),ROOT/'requirements-optuna.txt',*(ROOT/'opamp_pipeline').glob('*.py')]
    inputs={'files':{str(path):file_hash(path) for path in sources},'optuna_version':optuna.__version__,
            'executable':str(Path(a.ltspice).resolve()),'bench_timeout_s':a.bench_timeout,
            'policy':'startup_constraints_partial_screen_bounded_full_scope_v2',
            'constraint_policy':'signed_normalized_per_test_v1',
            'full_validation_candidate_cap':a.validation_candidates,
            'power_tie_tolerance_mW':POWER_ABS_TOL_MW,'power_tie_relative_tolerance':POWER_REL_TOL}
    if out.exists():
        if not a.resume or not (out/'INPUTS.json').exists():raise ValueError('Existing output requires --resume and an intact experiment')
        if read(out/'INPUTS.json')!=inputs:raise ValueError('Inputs/code/environment changed; preserve this study and start a new one')
        result=read(out/'RESULT.json')
    else:
        if a.resume:raise ValueError('No study to resume')
        out.mkdir(parents=True);save_report(out/'INPUTS.json',inputs)
        (out/'original.inc').write_bytes(model.read_bytes());save_report(out/'SEARCH_CONFIG.json',config)
        result={'status':'created','trials':[],'original_model':str(model),'original_sha256':file_hash(model),
                'no_external_llm_calls':True,'original_replaced':False,'full_datasheet_success':False,
                'limits':['Generic FIRSTAMP/bias-node startup adapter only; not a PDK optimization claim.',
                          'SQLite persists trials; sampler RNG is recreated from seed on resume, so interrupted runs need not match uninterrupted suggestions.']}
        save_report(out/'RESULT.json',result)
    save=lambda:save_report(out/'RESULT.json',result)
    # Calibrate the same adapters before any optimization verdict. Avoid rereading
    # old calibration values under changed code (INPUTS above binds all code).
    if not result.get('calibration_passed'):
        folder=out/('calibration_attempt_'+str(len(list(out.glob('calibration_attempt_*')))+1));folder.mkdir()
        calibration=calibrate(folder,plan,NativeExecutor(folder,a.ltspice,a.bench_timeout))
        save_report(folder/'ADAPTER_VALIDATION.json',calibration)
        if calibration['status']!='passed':raise ValueError('Adapter qualification failed; no sizing trials')
        result.update(calibration_passed=True,calibration_result=str(folder/'ADAPTER_VALIDATION.json'));save()
    storage='sqlite:///'+(out/'study.sqlite3').as_posix()
    sampler=optuna.samplers.TPESampler(seed=config['seed'],n_startup_trials=2)
    study=optuna.create_study(study_name='fixed-topology-sizing',storage=storage,direction='minimize',sampler=sampler,load_if_exists=True)
    for old in study.get_trials(deepcopy=False,states=(optuna.trial.TrialState.RUNNING,)):
        study.tell(old.number,state=optuna.trial.TrialState.FAIL)
        mark_interrupted_trial(result['trials'],old.number)
    save()
    if not study.trials:study.enqueue_trial(baseline)
    result.update(status='searching',requested_total_trial_budget=a.trials);save()
    start=time.monotonic()
    while sum(t.state!=optuna.trial.TrialState.WAITING for t in study.trials)<a.trials and time.monotonic()-start<a.time_budget:
        trial=study.ask();values={s['name']:trial.suggest_float(s['name'],s['low'],s['high'],log=s.get('log',False)) for s in config['parameters']}
        folder=out/'trials'/f'trial_{trial.number:04d}';folder.mkdir(parents=True,exist_ok=False)
        candidate=folder/'candidate.inc';candidate.write_text(apply_parameters(text,config,values),encoding='ascii')
        record={'number':trial.number,'params':values,'candidate':str(candidate),'status':'running'}
        result['trials'].append(record);save()
        try:
            screened=screen_candidate(candidate,plan,config['screening_kinds'],folder,a.ltspice,a.bench_timeout)
            startup=screened['startup_constraint_feedback']
            if screened['status']=='startup_failed':
                severity=startup
                objective=severity['total_normalized_violation']
                objective_role='startup_constraint_violation_not_power'
            else:
                severity=normalized_constraints(screened['cases'])
                severity['constraints'].update(startup['constraints'])
                severity['total_normalized_violation']+=startup['total_normalized_violation']
                severity['worst_normalized_violation']=max(severity['worst_normalized_violation'],startup['worst_normalized_violation'])
                objective=screened['objective_power_mW'];objective_role='measured_quiescent_power_mW'
            save_report(folder/'CONSTRAINT_FEEDBACK.json',severity)
            for key,distance in severity['constraints'].items():trial.set_constraint(key,distance)
            trial.set_user_attr('screening',str(folder/'SCREENING.json'))
            trial.set_user_attr('feasible_for_screening',screened['feasible_for_screening'])
            trial.set_user_attr('constraint_policy',severity['policy'])
            trial.set_user_attr('total_normalized_violation',severity['total_normalized_violation'])
            trial.set_user_attr('objective_role',objective_role)
            study.tell(trial,objective)
            # Select case IDs using their family, not an assumed ID prefix.
            performance_ids={c['case_id'] for c in screened['cases'] if c['kind']!='iq'}
            performance=[d['signed_normalized_distance'] for d in severity.get('details',[]) if d['case_id'] in performance_ids]
            record.update(status='startup_failed' if screened['status']=='startup_failed' else 'screened',feasible_for_screening=screened['feasible_for_screening'],
                          objective_power_mW=screened['objective_power_mW'],failed_case_ids=screened['failed_screening_case_ids'],candidate_sha256=file_hash(candidate),
                          optimizer_value=objective,objective_role=objective_role,screening_margin=-max(performance) if performance else 0,
                          total_normalized_violation=severity['total_normalized_violation'],
                          worst_normalized_violation=severity['worst_normalized_violation'],
                          constraint_feedback=str(folder/'CONSTRAINT_FEEDBACK.json'))
        except ExecutionContractError as error:
            study.tell(trial,state=optuna.trial.TrialState.FAIL)
            record.update(status='execution_contract_error',error=str(error),physical_spec_failure_established=False)
            result['status']='blocked_verification_error';save();raise
        except Exception as error:
            study.tell(trial,state=optuna.trial.TrialState.FAIL)
            record.update(status='execution_error',error_type=type(error).__name__,error=str(error),physical_spec_failure_established=False)
        save();print('trial',trial.number,record['status'],record.get('objective_power_mW'),record.get('feasible_for_screening'),flush=True)
    ranked=ranked_candidates(result['trials'])
    result['study_states']={state.name:sum(t.state==state for t in study.trials) for state in optuna.trial.TrialState}
    result['search_seconds_this_invocation']=time.monotonic()-start
    if ranked:
        best=ranked[0]
        if file_hash(best['candidate'])!=best['candidate_sha256']:raise ValueError('Stored candidate changed')
        result.update(best_screened_trial=best,status='completed_partial_screening',
                      selection_policy={'power_abs_tolerance_mW':POWER_ABS_TOL_MW,'power_relative_tolerance':POWER_REL_TOL,
                                        'tie_break':'weakest_screened_performance_headroom_then_trial_number',
                                        'full_validation_candidate_cap':a.validation_candidates})
        save()
        if a.validate_best:
            progress=[]
            def validate(record,rank):
                if file_hash(record['candidate'])!=record['candidate_sha256']:raise ValueError('Stored candidate changed')
                folder=out/('full_validation_trial_'+str(record['number']))
                command=[sys.executable,str(ROOT/'run_verification_pipeline.py'),'--netlist',record['candidate'],'--run-dir',str(run_dir),
                     '--output-dir',str(folder),'--ltspice',a.ltspice,'--harness',str(a.harness.resolve())]
                completed_before=(folder/'STATE.json').exists() and read(folder/'STATE.json').get('status')=='completed'
                if not completed_before:
                    if (folder/'STATE.json').exists():command.append('--resume')
                    result.update(status='validating_best',validating_trial=record['number']);save()
                    with (out/f"full_validation_{record['number']}_stdout.txt").open('w',encoding='utf-8') as stdout,(out/f"full_validation_{record['number']}_stderr.txt").open('w',encoding='utf-8') as stderr:
                        completed=subprocess.run(command,cwd=ROOT,stdout=stdout,stderr=stderr,timeout=1200)
                    if completed.returncode:raise RuntimeError('Candidate verification failed to complete; see saved logs')
                _,document=_pipeline_evidence(folder,record['candidate'],run_dir/'measurement_plan/plan_02_measurements.json')
                evaluated=full_assessment(document,harness)
                item={'number':record['number'],'rank':rank,'assessment':evaluated,
                                 'state_path':str(folder/'STATE.json'),'ledger_sha256':file_hash(folder/'LEDGER.json')}
                progress.append(item);result['full_validation_attempts']=progress;save()
                return item
            chosen,attempts=validate_shortlist(ranked,a.validation_candidates,validate)
            if chosen is None:
                if file_hash(model)!=result['original_sha256']:raise ValueError('Original DUT changed during sizing')
                result.update(status='completed_no_qualified_full_candidate',candidate_passes_implemented_scope=False,original_unchanged=True)
                save();print(result['status'],flush=True);return
            best=next(r for r in ranked if r['number']==chosen['number'])
            full=read(chosen['state_path'])
            result.update(status='completed_with_final_validation',
                          selected_trial=best,final_validation=chosen['state_path'],
                          final_case_counts=full['case_status_counts'],startup_passed=chosen['assessment']['startup_passed'],
                          candidate_passes_implemented_scope=chosen['assessment']['scope_passed'],
                          shortlist_budget_exhausted=not chosen['assessment']['scope_passed'] and len(ranked)>len(attempts))
        exported=out/'best_screened.inc';exported.write_bytes(Path(best['candidate']).read_bytes())
        result['best_screened_path']=str(exported)
        result['exported_trial_number']=best['number']
        result['best_screened_trial']=best
    else:result.update(status='completed_no_screening_feasible_candidate')
    if file_hash(model)!=result['original_sha256']:raise ValueError('Original DUT changed during sizing')
    result['original_unchanged']=True;save()
    print(json.dumps({'status':result['status'],'trials':len(study.trials),'best':result.get('best_screened_trial'),'full_datasheet_success':False},ensure_ascii=False),flush=True)


if __name__=='__main__':main()
