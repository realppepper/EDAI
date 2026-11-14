"""Register chat-authored revisions and execute the full80-case validation loop."""
import argparse,json,subprocess,sys
from pathlib import Path
from opamp_pipeline.loop_04_extended_policy import compare_extended
from opamp_pipeline.loop_02_handoff import write_json,validate_dut
from opamp_pipeline.support.execution_state import file_hash


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--session',type=Path,required=True)
    parser.add_argument('--response',type=Path,required=True);parser.add_argument('--baseline',type=Path,required=True)
    parser.add_argument('--validation-result',type=Path);parser.add_argument('--ltspice')
    parser.add_argument('--run-dir',type=Path,default=Path('runs/lm358b_overview_20261112'))
    args=parser.parse_args();session=args.session.resolve();session.mkdir(parents=True,exist_ok=True)
    read=lambda p:json.loads(Path(p).read_text(encoding='utf-8'))
    request=read(session/'DESIGN_REQUEST.json');response=read(args.response)
    numerical_policy=request.get('numerical_policy','default')
    if numerical_policy not in {'default','startup_seeded'}:raise ValueError('Unknown numerical policy')
    if response['based_on_request_sha256']!=file_hash(session/'DESIGN_REQUEST.json'):raise ValueError('Response belongs to another request')
    if request['baseline_sha256']!=file_hash(args.baseline):raise ValueError('Baseline changed')
    model=Path(response['candidate_file']);validate_dut(model.read_text(encoding='ascii'))
    if file_hash(model)!=response['candidate_sha256']:raise ValueError('Submitted candidate changed')
    baseline=read(args.baseline);statepath=session/'STATE.json'
    state=read(statepath) if statepath.exists() else {'status':'started','candidates':[],
        'baseline_result':str(args.baseline.resolve()),'baseline_sha256':file_hash(args.baseline),
        'baseline_candidate':str(args.baseline.resolve().parent/'candidate.inc'),
        'default_candidate':str(args.baseline.resolve().parent/'candidate.inc'),
        'priority_best_candidate':None,'candidate_budget_including_baseline':request['candidate_budget_including_baseline'],
        'chat_tokens':None,'external_llm_api_calls':0,'full_datasheet_success':False}
    for saved in state['candidates']:
        receipt=Path(saved['comparison']).parent/'DESIGN_RESPONSE.json'
        if file_hash(saved['candidate_path'])!=saved['candidate_sha256'] or file_hash(saved['validation_result'])!=saved['validation_sha256']:
            raise ValueError('A recorded candidate or validation was modified')
        if file_hash(receipt)!=saved['response_sha256']:raise ValueError('An accepted design response was modified')
    screened=state.get('screened_out_candidates',[])
    for saved in screened:
        for path_key,hash_key in (('candidate_path','candidate_sha256'),('screen_result','screen_sha256'),('response_path','response_sha256')):
            if file_hash(saved[path_key])!=saved[hash_key]:raise ValueError('A recorded screening artifact was modified')
    if any(c['candidate_sha256']==response['candidate_sha256'] for c in screened):
        print(json.dumps({'status':state['status'],'already_screened_out':True},ensure_ascii=False));return
    existing=next((c for c in state['candidates'] if c['candidate_sha256']==response['candidate_sha256']),None)
    if existing:
        if file_hash(args.response)!=existing['response_sha256']:raise ValueError('Registered response was modified')
        if file_hash(existing['validation_result'])!=existing['validation_sha256']:raise ValueError('Recorded validation changed')
        print(json.dumps({'status':state['status'],'already_registered':True},ensure_ascii=False));return
    if response.get('feedback_comparison_sha256'):
        if not state['candidates'] or response['feedback_comparison_sha256']!=file_hash(state['candidates'][-1]['comparison']):
            raise ValueError('Revision not bound to latest regression feedback')
    if len(state['candidates'])+len(screened)+1>=state['candidate_budget_including_baseline']:raise ValueError('Candidate budget exhausted; baseline preserved')
    index=len(state['candidates'])+len(screened)+1;folder=session/f'iteration_{index:03d}';folder.mkdir(exist_ok=True)
    write_json(folder/'DESIGN_RESPONSE.json',response);state['status']='validating_candidate';write_json(statepath,state)
    result_path=args.validation_result
    if result_path is None:
        if not args.ltspice:raise ValueError('LTspice required for execution')
        output=folder/'validation';root=Path(__file__).resolve().parent
        command=[sys.executable,str(root/'run_extended_verification.py'),'--ltspice',args.ltspice,
                 '--netlist',str(model),'--run-dir',str(args.run_dir.resolve()),
                 '--reuse-calibration',str(args.baseline.resolve().parent),'--output-dir',str(output)]
        command+=['--bench-timeout','60','--numerical-policy',numerical_policy]
        if (output/'RESULT.json').exists():command+=['--resume',str(output)]
        proc=subprocess.run(command,cwd=root,capture_output=True,timeout=900)
        (folder/'stdout.txt').write_bytes(proc.stdout);(folder/'stderr.txt').write_bytes(proc.stderr)
        result_path=output/'RESULT.json'
        if proc.returncode!=0:state.update(status='validation_execution_error');write_json(statepath,state);raise RuntimeError('Validation failed; saved logs and partial state retained')
    candidate=read(result_path)
    if candidate.get('numerical_policy','default')!=numerical_policy or baseline.get('numerical_policy','default')!=numerical_policy:
        raise ValueError('Baseline/candidate numerical policies do not match the request')
    if file_hash(result_path.parent/'candidate.inc')!=response['candidate_sha256']:raise ValueError('Validation belongs to another circuit')
    if candidate['status']!='completed_with_explicit_unverified_cases':raise ValueError('Incomplete candidate validation')
    comparison=compare_extended(baseline,candidate,request.get('priority_case_ids'));write_json(folder/'COMPARISON.json',comparison)
    record={'candidate_sha256':response['candidate_sha256'],'candidate_path':str(model),'response_sha256':file_hash(args.response),
        'validation_result':str(result_path.resolve()),'validation_sha256':file_hash(result_path),
        'comparison':str((folder/'COMPARISON.json').resolve()),'summary':comparison['summary'],
        'adoptable':comparison['adoptable_without_losing_previous_passes']}
    state['candidates'].append(record)
    if comparison['priority_goals_passed']:
        state['priority_best_candidate']=str(model)
        write_json(session/'BEST_PRIORITY.json',record)
    if record['adoptable']:
        state.update(status='priority_goals_passed_without_new_failed_cases',default_candidate=str(model))
    else:state['status']='revision_required_regressions' if comparison['priority_goals_passed'] else 'revision_required_priority_failures'
    if not record['adoptable'] and len(state['candidates'])+len(screened)+1>=state['candidate_budget_including_baseline']:
        state['status']='candidate_budget_exhausted_baseline_preserved'
    write_json(statepath,state);write_json(session/'BEST_DEFAULT.json',{'candidate_path':state['default_candidate'],
        'candidate_sha256':file_hash(state['default_candidate']),
        'whole_datasheet_success':False,'note':'Priority-only improvement is not automatically adopted if a previous pass regresses.'})
    print(json.dumps({'status':state['status'],**comparison['summary'],'default_candidate':state['default_candidate']},ensure_ascii=False))

if __name__=='__main__':main()
