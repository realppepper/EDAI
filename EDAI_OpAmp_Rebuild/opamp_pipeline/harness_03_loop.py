"""Fixed-harness current-chat handoff loop. API transport and Harness² are disabled."""
import json,time
from pathlib import Path
from .pipeline_01_verification import run_pipeline,read
from .harness_01_fixed import DEFAULT_POLICY,validate_candidate,load_harness
from .harness_02_request import make_request,validate_response
from .loop_02_handoff import write_json
from .loop_04_extended_policy import ledger
from .support.execution_state import file_hash
from .support.source_checks import fingerprint
from .support.atomic_files import atomic_write_text,atomic_write_bytes
from .harness_04_feedback import implemented_scope_case_ids
from .harness_05_history import build_iteration_history
from .ref_05_research import record_usage
from .verify_07_startup_gate import gate_assessment
from . import schematic_01_export as schematic
from . import ref_07_datasheet as datasheet_refs


def assessment(baseline,current,scope):
    a,b=ledger(baseline),ledger(current)
    if set(a)!=set(b):raise ValueError('Case coverage changed')
    for k,v in a.items():
        w=b[k]
        if v['target']!=w['target'] or v['case']['fixture']!=w['case']['fixture']:raise ValueError('Targets/fixtures changed')
        if k not in scope and w['case']['status']=='passed_sampled_model_case':raise ValueError('Unknown case promoted without a new qualification study')
    failed=[k for k in scope if b[k]['case']['status']!='passed_sampled_model_case']
    counts={s:sum(v['case']['status']==s for v in b.values()) for s in sorted({v['case']['status'] for v in b.values()})}
    gates=gate_assessment(baseline,current)
    unresolved=failed+gates['failed_operational_gate_ids']
    return {'scope_passed':not unresolved,'failed_case_ids':failed,'failed_requirement_ids':unresolved,
            **gates,'counts':counts,'score':[0,len(unresolved)],'full_datasheet_success':False}


def save(session,state):
    if state['status']=='implemented_scope_passed' and state['candidates']:
        successful=next((c for c in reversed(state['candidates']) if c['assessment']['scope_passed']),None)
        if successful:schematic.complete(session,state,successful)
    write_json(session/'STATE.json',state)
    best=state['candidates'][state['best_index']] if state['candidates'] else None
    write_json(session/'BEST.json',best)
    lines=['# 고정 하네스 + 현재 채팅 설계자 루프','',f"상태: {state['status']}",
           '검사·판정·이력은 코드, 수정 제안은 현재 채팅이 담당합니다. 설계용 API/Harness² 호출은 없습니다.','',
           '| 후보 | 통과 조건 | 실패/오류 조건 | 전체 목표 통과 |','|---|---:|---:|---|']
    for c in state['candidates']:
        a=c['assessment'];lines.append(f"| {c['index']} | {a.get('counts',{}).get('passed_sampled_model_case',0)} | {len(a['failed_case_ids'])} | {a['scope_passed']} |")
    if state.get('pending_candidate'):
        lines+=['',f"검증 대기/중단 후보: {state['pending_candidate']['candidate_path']}",
                '검증 중단은 설계 미달 판정이나 추가 수정 제안으로 계산하지 않습니다.']
    lines+=['',f"최선 후보: {best['candidate_path'] if best else '최초 검증 완료 전'}",f"하네스 SHA256: {state['harness_sha256']}",
            '실제 채팅 토큰/비용은 미측정(null)이며0으로 추정하지 않습니다. 전체 제조사 사양 성공은 false입니다.']
    lines+=schematic.report_lines(state)
    atomic_write_text(session/'REPORT.md','\n'.join(lines))


def prepare(session,state):
    current=state['candidates'][-1];source=current if current.get('ledger_path') else state['candidates'][state['best_index']]
    request=make_request(read(state['plan_path']),read(source['ledger_path']),Path(current['candidate_path']).read_text(encoding='ascii'),state['harness_path'])
    if current.get('execution_error'):
        request['current_execution_failure']=current['execution_error']
        request['feedback_notice']='Measurements belong to the last fully measured candidate, not this failed execution. Use current_execution_failure for the current candidate.'
    history=request.get('iteration_history_configuration',{})
    if history.get('enabled'):
        request['iteration_history']=build_iteration_history(state['candidates'],
            request['evaluation_scope']['implemented_scope_case_ids'],history['max_transitions'])
    request['iteration_index']=len(state['candidates'])
    if state.get('optuna'):
        from .optuna_03_loop_bridge import feedback
        request['numeric_sizing_feedback']=feedback(state)
        if state['optuna'].get('mode')=='designer_proposal':
            from .optuna_04_designer import proposal_contract
            from .optuna_03_loop_bridge import routing_reason
            request['numeric_sizing_proposal']=proposal_contract(state,routing_reason(state,current,read(source['ledger_path'])))
            request['response_schema']={'one_of':{'circuit_revision':request['response_schema'],
                'numeric_sizing_proposal':request['numeric_sizing_proposal']['response_schema']}}
    datasheet_refs.add_catalog(request,state.get('run_dir'))
    request['request_id']=fingerprint({k:v for k,v in request.items() if k!='request_id'})
    suffix=f"_sizing_{len(state.get('sizing_proposals',[])):03d}" if state.get('optuna',{}).get('mode')=='designer_proposal' else ''
    path=session/f"REQUEST_{len(state['candidates']):03d}{suffix}.json";write_json(path,request)
    state['pending_request']={'path':str(path),'sha256':file_hash(path),'request_id':request['request_id']};state['status']='awaiting_chat_designer'


def advance(session,state,ltspice=None,allow_sizing=True):
    current=state['candidates'][-1];best=state['candidates'][state['best_index']]
    if current.get('eligible_for_best',True) and current['assessment']['score']<best['assessment']['score']:state['best_index']=current['index']
    if current['assessment']['scope_passed']:state['status']='implemented_scope_passed';state['pending_request']=None
    elif len(state['candidates'])>=state['max_candidates']:state['status']='candidate_budget_exhausted';state['pending_request']=None
    else:
        if state.get('optuna') and allow_sizing:
            from . import optuna_03_loop_bridge as sizing
            reason=sizing.routing_reason(state,current,read(current['ledger_path']) if current.get('ledger_path') else {})
            state['optuna_routing_reason']=reason
            if reason in {'numeric_repair_eligible','startup_repair_eligible'}:
                if state['optuna'].get('mode')=='designer_proposal':
                    prepare(session,state);save(session,state);return state
                state.update(status='awaiting_optuna_execution',pending_request=None);save(session,state)
                if ltspice:return sizing.execute(session,state,ltspice)
                return state
        prepare(session,state)
    save(session,state)


def load(session):
    session=Path(session).resolve();state=read(session/'STATE.json')
    if file_hash(state['harness_path'])!=state['harness_sha256'] or file_hash(state['plan_path'])!=state['plan_sha256']:raise ValueError('Frozen harness/plan changed')
    if state.get('optuna',{}).get('config_path') and file_hash(state['optuna']['config_path'])!=state['optuna']['config_sha256']:raise ValueError('Frozen sizing configuration changed')
    for proposal in state.get('sizing_proposals',[]):
        for key in ('request','response','config'):
            if file_hash(proposal[key+'_path'])!=proposal[key+'_sha256']:raise ValueError('Accepted sizing proposal changed')
    for event in state.get('optuna_attempts',[]):
        if event.get('status')=='completed' and file_hash(event['result_path'])!=event['result_sha256']:raise ValueError('Recorded sizing result changed')
    for p,sha in state['code_signatures'].items():
        if file_hash(p)!=sha:raise ValueError('Loop/verification code changed during fixed session')
    for p,sha in state.get('literature_artifacts',{}).items():
        if file_hash(p)!=sha:raise ValueError('Attached literature evidence changed')
    for p,sha in state.get('datasheet_reference_artifacts',{}).items():
        if file_hash(p)!=sha:raise ValueError('Attached datasheet reference evidence changed')
    for c in state['candidates']:
        if file_hash(c['candidate_path'])!=c['candidate_sha256']:raise ValueError('Recorded candidate changed')
        if c.get('ledger_path') and file_hash(c['ledger_path'])!=c['ledger_sha256']:raise ValueError('Recorded result changed')
        if c.get('response_path') and file_hash(c['response_path'])!=c['response_sha256']:raise ValueError('Recorded response changed')
    pending=state.get('pending_candidate')
    if pending:
        if file_hash(pending['candidate_path'])!=pending['candidate_sha256']:raise ValueError('Pending design changed')
        if pending.get('response_path') and file_hash(pending['response_path'])!=pending['response_sha256']:raise ValueError('Pending response changed')
    return state


def start(session,model,run_dir,ltspice=None,imports=None,harness=DEFAULT_POLICY,max_candidates=3,defer_validation=False,optuna_config=None,optuna_trials=4,optuna_rounds=1,optuna_from_designer=False):
    session=Path(session).resolve()
    if (session/'STATE.json').exists():raise ValueError('Session already exists')
    if max_candidates<2:raise ValueError('At least one revision slot required')
    model=Path(model).resolve();run_dir=Path(run_dir).resolve();folder=session/'candidate_000';folder.mkdir(parents=True)
    copy=folder/'candidate.inc';data=model.read_bytes()
    if copy.exists() and copy.read_bytes()!=data:raise ValueError('Unrecorded initial candidate differs; preserved for review')
    if not copy.exists():atomic_write_bytes(copy,data)
    validate_candidate(copy.read_text(encoding='ascii'))
    load_harness(harness)
    plan=run_dir/'measurement_plan/plan_02_measurements.json'
    code=list((Path(__file__).parent).rglob('*.py'))+[Path(__file__).parents[1]/p for p in ('run_extended_verification.py','run_input_impedance_extension.py','run_overload_extension.py','run_fixed_harness_loop.py','run_verification_pipeline.py')]
    state={'status':'validating_initial','code_signatures':{str(p):file_hash(p) for p in code},'harness_path':str(Path(harness).resolve()),'harness_sha256':file_hash(harness),'plan_path':str(plan),'plan_sha256':file_hash(plan),
           'run_dir':str(run_dir),'max_candidates':max_candidates,'scope_case_ids':[],'best_index':0,'invalid_submissions':0,
           'external_llm_api_calls':0,'chat_token_usage':None,'api_cost_USD':None,'harness2_enabled':False,
           'initial_imports':[str(Path(p).resolve()) for p in imports] if imports else None,
           'pending_request':None,'automatic_validation_retries':1,
           'pending_candidate':{'index':0,'candidate_path':str(copy),'candidate_sha256':file_hash(copy),'origin':'declared_initial_candidate'},'candidates':[]}
    if optuna_config is not None and optuna_from_designer:raise ValueError('Choose fixed config or designer-selected sizing, not both')
    if optuna_config is not None or optuna_from_designer:
        from .optuna_03_loop_bridge import configure
        from .optuna_04_designer import designer_policy
        state['optuna']=designer_policy(optuna_trials,optuna_rounds) if optuna_from_designer else configure(optuna_config,optuna_trials,optuna_rounds)
        for path in (Path(__file__).parents[1]/'run_optuna_sizing.py',Path(__file__).parents[1]/'requirements-optuna.txt'):
            state['code_signatures'][str(path)]=file_hash(path)
    save(session,state)
    if defer_validation:return state
    return execute_pending(session,state,ltspice)


def execute_pending(session,state,ltspice,automatic_retries=None):
    session=Path(session).resolve()
    pending=state['pending_candidate'];folder=Path(pending['candidate_path']).parent
    if file_hash(pending['candidate_path'])!=pending['candidate_sha256']:raise ValueError('Pending design changed')
    if pending.get('response_path') and file_hash(pending['response_path'])!=pending['response_sha256']:raise ValueError('Pending response changed')
    initial=not state['candidates']
    retries=state.get('automatic_validation_retries',1) if automatic_retries is None else automatic_retries
    if retries<0:raise ValueError('Negative retry budget')
    history=pending.setdefault('validation_attempts',[])
    if history and history[-1]['status']=='started':
        history[-1].update(status='uncommitted_before_resume',finished_unix=time.time())
    for attempt in range(retries+1):
        event={'attempt':len(pending.setdefault('validation_attempts',[]))+1,'status':'started','started_unix':time.time()}
        pending['validation_attempts'].append(event)
        state['status']='validating_initial' if initial else 'validating_candidate'
        state['pending_request']=None;save(session,state)
        try:
            pipe=run_pipeline(pending['candidate_path'],state['run_dir'],folder/'validation',ltspice,
                imports=state.get('initial_imports') if initial else None,
                resume=(folder/'validation/STATE.json').exists(),harness=state['harness_path'])
            path=folder/'validation/LEDGER.json';current=read(path)
            if initial:
                policy,_=load_harness(state['harness_path'])
                scope=implemented_scope_case_ids(ledger(current),policy)
                if not scope:raise ValueError('No independently qualified measurement families in this plan')
                base=current
            else:
                scope=state['scope_case_ids'];base=read(state['candidates'][0]['ledger_path'])
            evaluated=assessment(base,current,scope)
        except Exception as error:
            event.update(status='interrupted',finished_unix=time.time(),error_type=type(error).__name__,error=str(error))
            state['status']='validation_interrupted';save(session,state)
            # Changed/missing inputs and invalid results need explicit attention,
            # not repeated execution. Worker/I/O interruption gets one retry.
            if isinstance(error,(ValueError,FileNotFoundError)) or attempt==retries:return state
            continue
        event.update(status='completed',finished_unix=time.time())
        record={**pending,'ledger_path':str(path),'ledger_sha256':file_hash(path),'assessment':evaluated,
                'pipeline_seconds':pipe['execution_seconds']}
        if initial:state['scope_case_ids']=scope
        state['candidates'].append(record);state['pending_candidate']=None
        advance(session,state,ltspice);return state


def resume(session,ltspice=None):
    session=Path(session).resolve();state=load(session)
    if state['status']=='optuna_ready_to_advance':
        advance(session,state,ltspice,allow_sizing=False);return state
    if state['status'] in {'awaiting_optuna_execution','optimizing_parameters','optuna_interrupted'}:
        if not ltspice:raise ValueError('LTspice required to resume numeric sizing')
        from .optuna_03_loop_bridge import execute
        return execute(session,state,ltspice)
    if state['status'] in {'validating_initial','validating_candidate','validation_interrupted'}:
        if not ltspice and not (not state['candidates'] and state.get('initial_imports')):
            raise ValueError('LTspice required to resume validation')
        return execute_pending(session,state,ltspice)
    # STATE is authoritative; recreate views if their publication was interrupted.
    save(session,state)
    return state


def submit(session,response_path,ltspice,defer_validation=False):
    session=Path(session).resolve();state=load(session);response_path=Path(response_path).resolve();response_sha=file_hash(response_path)
    if any(p.get('submitted_response_sha256')==response_sha for p in state.get('sizing_proposals',[])):return state
    if any(c.get('submitted_response_sha256')==response_sha for c in state['candidates']):return state
    if state.get('pending_candidate',{} ) and state['pending_candidate'].get('submitted_response_sha256')==response_sha:return state
    if state['status']!='awaiting_chat_designer':raise ValueError('No pending design request')
    pending=state['pending_request']
    if file_hash(pending['path'])!=pending['sha256']:raise ValueError('Prepared request changed')
    response=read(response_path)
    approved=None
    try:
        if response.get('action')=='propose_sizing':
            if state.get('optuna',{}).get('mode')!='designer_proposal':raise ValueError('Designer-selected sizing is not enabled')
            from .optuna_04_designer import validate_proposal
            current=state['candidates'][-1]
            approved=validate_proposal(read(pending['path']),response,Path(current['candidate_path']).read_text(encoding='ascii'),state['optuna'],pending['sha256'])
        else:validate_response(read(pending['path']),response)
    except Exception as error:
        state['invalid_submissions']+=1;write_json(session/f"REJECTED_{state['invalid_submissions']:03d}.json",{'response_sha256':response_sha,'error':str(error)})
        if state['invalid_submissions']>=3:state['status']='invalid_response_budget_exhausted'
        save(session,state);raise
    if approved is not None:
        from .optuna_04_designer import accept
        from .optuna_03_loop_bridge import execute
        state=accept(session,state,response_path,response,*approved)
        if defer_validation:return state
        return execute(session,state,ltspice)
    index=len(state['candidates']);folder=session/f'candidate_{index:03d}';folder.mkdir(exist_ok=True)
    model=folder/'candidate.inc';receipt=folder/'RESPONSE.json';payload=response['netlist'].encode('ascii')
    if model.exists() and model.read_bytes()!=payload:raise ValueError('Unrecorded candidate differs; preserved for review')
    if receipt.exists() and read(receipt)!=response:raise ValueError('Unrecorded response differs; preserved for review')
    if (folder/'validation').exists():raise ValueError('Unrecorded validation exists; preserved for review')
    if not model.exists():atomic_write_bytes(model,payload)
    if not receipt.exists():write_json(receipt,response)
    record_usage(state,read(pending['path']),response)
    datasheet_refs.record_usage(state,read(pending['path']),response)
    state['pending_candidate']={'index':index,'candidate_path':str(model),'candidate_sha256':file_hash(model),'response_path':str(receipt),
                                'response_sha256':file_hash(receipt),'submitted_response_sha256':response_sha,'origin':'current_chat_designer','based_on_request_sha256':pending['sha256']}
    state['status']='validating_candidate';save(session,state)
    # An explicit safe pause: a fresh process can validate the persisted candidate.
    if defer_validation:return state
    return execute_pending(session,state,ltspice)
