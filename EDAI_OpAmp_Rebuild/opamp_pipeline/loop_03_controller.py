"""Persisted partial-scope loop: evaluate, stop, hand off, preserve best, resume."""
import json,subprocess,sys,time,uuid
from pathlib import Path
from datetime import datetime,timezone
from .loop_01_policy import make_policy,evaluate
from .loop_02_handoff import write_json,prepare_request,accept_response,validate_dut
from .support.execution_state import file_hash
from .support.source_checks import fingerprint


def read(path):return json.loads(Path(path).read_text(encoding='utf-8'))


def save(session,state):
    session=Path(session);write_json(session/'STATE.json',state)
    best=next((c for c in state['candidates'] if c['id']==state.get('best_candidate_id')),None)
    if best:
        write_json(session/'BEST.json',{'candidate_id':best['id'],'candidate_path':best['candidate_path'],
            'candidate_sha256':best['candidate_sha256'],'result_path':best['result_path'],
            'result_sha256':best['result_sha256'],'score':best['assessment']['score'],
            'scope_passed':best['assessment']['scope_passed'],'full_datasheet_success':False})
    lines=['# 채팅 설계자 + 코드 실행 루프','',f"상태: {state['status']}",f"프로필: {state['policy']['name']}",
        f"보존한 최선 후보: {state.get('best_candidate_id')}",'',
        '현재 채팅이 설계 판단을 담당하고 코드는 실행·판정·피드백·후보 보존을 담당합니다. 자동 API 설계 호출은 없습니다.',
        '', '| 후보 | 출처 | 일부 목표 통과 | 실패 항목 | 실행 오류 |','|---|---|---|---|---|']
    for c in state['candidates']:
        assessment=c['assessment']
        lines.append(f"| {c['id']} | {c['origin']} | {assessment['scope_passed']} | {', '.join(assessment['failed_keys'])} | {len(assessment['gate_issues'])} |")
    lines+=['','## 후보별 판정','', '| 후보 | 항목 | 측정 | 목표 | 통과 |','|---|---|---:|---|---|']
    for c in state['candidates']:
        for check in c['assessment']['checks']:
            lines.append(f"| {c['id']} | {check['key']} | {check['measured']} {check['unit']} | {check['operator']} {check['limit']} | {check['passed']} |")
    lines+=['','## 검증 범위와 기록','',
        '- 5V/25°C의 명시된 targets만 판정합니다. IQ, VOS, GBW, 양방향 정착시간 및 선택적으로 검증된 PM이 포함됩니다. DC2~3V 추종10mV는 별도 공학적 건전성 게이트이며 전체 입력 범위 인증이 아닙니다.',
        '- 원문에서 채택한32개 행은 CONTEXT.json에 보존합니다. 미구현 조건은 미검증이며 전체 사양 성공을 선언하지 않습니다.',
        ('- 이 세션의 PM은 검증된 Tian 이중 주입·단일 교차·동일 시험 범위 조건을 요구하는 정식 사례 판정입니다. 모든 회로의 안정성 인증은 아닙니다.' if 'PM' in state['policy']['targets'] else '- 이 세션에서는 PM을 정식 목표로 선택하지 않았으며 진단 정보로만 보존합니다.'),
        '- 후보 수 한도3개(초기 후보 포함), 새 시뮬레이션 시간 한도180초. 실제 채팅 토큰과 비용은 관측 불가로 null이며0으로 추정하지 않습니다.',
        '- source_target은 원문에서 채택한 목표이며 limit은 현재 실험 기준입니다. 강화 실험은 별도 프로젝트 목표이고 원문 JSON을 바꾸지 않습니다.',
        '- 각 후보와 결과는 개별 폴더/원본 해시로 보존합니다. 재시작 시 STATE.json에서 이어가며 미완료 실행 로그를 성공으로 재사용하지 않습니다.',
        '- 강제 중단으로 시간을 알 수 없으면0으로 처리하지 않고 실행 예산에 보수적으로 예약 차감하며 시도 기록에 표시합니다.',
        '', f"새 실행 시간·중단 예약을 포함한 예산 사용: {state['simulation_seconds']:.3f}초",f"실제 채팅 토큰: {state['chat_token_usage']}"]
    (session/'REPORT.md').write_text('\n'.join(lines),encoding='utf-8')


def advance(session,state):
    candidate=state['candidates'][-1]
    previous=next((c for c in state['candidates'] if c['id']==state.get('best_candidate_id')),None)
    if previous is None or candidate['assessment']['score']<previous['assessment']['score']:
        state['best_candidate_id']=candidate['id']
    if candidate['assessment']['scope_passed']:
        state['status']='partial_scope_passed';state['pending_request']=None
    elif len(state['candidates'])>=state['policy']['max_candidates_including_seed']:
        state['status']='candidate_budget_exhausted'
    elif state['simulation_seconds']>=state['policy']['max_simulation_seconds']:
        state['status']='simulation_budget_exhausted'
    else:prepare_request(session,state)
    save(session,state)


def start(session,context_path,seed_result,challenge_gbw=None,include_pm=False):
    session=Path(session).resolve()
    if session.exists():raise ValueError('Session directory already exists')
    context=read(context_path);seed=read(seed_result);seed_path=Path(seed_result).resolve()
    if file_hash(seed_path)!=context['provenance']['previous_result_sha256']:raise ValueError('Seed does not match source design context')
    plan=Path(seed['measurement_plan']).resolve()
    if file_hash(plan)!=context['provenance']['measurements_sha256'] or file_hash(plan)!=seed['measurement_plan_sha256']:
        raise ValueError('Source measurement plan changed')
    model=seed_path.parent/'candidate.inc'
    if file_hash(model)!=seed['netlist_sha256']:raise ValueError('Seed netlist changed')
    validate_dut(model.read_text(encoding='utf-8'))
    policy=make_policy(context,challenge_gbw,include_pm)
    session.mkdir(parents=True)
    write_json(session/'CONTEXT.json',context)
    folder=session/'candidate_000';folder.mkdir()
    write_json(folder/'RESULT.json',seed)
    (folder/'candidate.inc').write_bytes(model.read_bytes())
    state={'session_id':uuid.uuid4().hex,'created_utc':datetime.now(timezone.utc).isoformat(),'status':'initialized',
        'policy':policy,'policy_fingerprint':fingerprint(policy),'context_sha256':file_hash(session/'CONTEXT.json'),
        'source_context_path':str(Path(context_path).resolve()),'source_context_sha256':file_hash(context_path),
        'measurement_plan_path':str(plan),'measurement_plan_sha256':file_hash(plan),
        'candidates':[],'best_candidate_id':None,'pending_request':None,'pending_candidate':None,
        'simulation_seconds':0,'chat_token_usage':None,'external_llm_api_calls':0,'api_cost_USD':None,
        'seed_import_note':'Previously measured same-model candidate imported; not a new LLM or simulation call.'}
    state['candidates'].append({'id':'candidate_000','origin':'imported_previous_chat_design',
        'candidate_path':str(folder/'candidate.inc'),'candidate_sha256':file_hash(folder/'candidate.inc'),
        'result_path':str(folder/'RESULT.json'),'result_sha256':file_hash(folder/'RESULT.json'),
        'original_result_path':str(seed_path),'original_result_sha256':file_hash(seed_path),
        'assessment':evaluate(seed,policy),'simulation_seconds':0,'token_usage':None})
    advance(session,state)
    return state


def load(session):
    session=Path(session);state=read(session/'STATE.json')
    if fingerprint(state['policy'])!=state['policy_fingerprint']:raise ValueError('Active policy changed')
    if file_hash(session/'CONTEXT.json')!=state['context_sha256']:raise ValueError('Stored design context changed')
    if file_hash(state['measurement_plan_path'])!=state['measurement_plan_sha256']:raise ValueError('Measurement plan changed')
    for candidate in state['candidates']:
        if file_hash(candidate['candidate_path'])!=candidate['candidate_sha256'] or file_hash(candidate['result_path'])!=candidate['result_sha256']:
            raise ValueError('Recorded candidate or result was modified')
    return state


def execute_pending(session,state,ltspice):
    pending=state['pending_candidate'];folder=Path(pending['folder'])
    if file_hash(pending['candidate_path'])!=pending['candidate_sha256']:raise ValueError('Pending netlist changed')
    if file_hash(folder/'DESIGN_RESPONSE.json')!=pending['response_sha256']:raise ValueError('Pending design response changed')
    attempts=pending['execution_attempts']
    if attempts:
        path=Path(attempts[-1]['path']);result_path=path/'RESULT.json'
        if result_path.exists() and read(result_path).get('status') in ('partial_experiment_completed','partial_with_execution_errors'):
            if not attempts[-1].get('charged'):
                elapsed=read(result_path).get('execution_seconds',attempts[-1].get('allocated_seconds',60))
                state['simulation_seconds']+=elapsed
                attempts[-1].update(charged=True,elapsed_seconds=elapsed,time_accounting='recovered_child_checkpoint')
            return finish_pending(session,state,path,read(result_path))
        if not attempts[-1].get('charged'):
            # Unknown time after power loss is reserved against the budget, not called zero.
            reserve=attempts[-1].get('allocated_seconds',60)+30
            state['simulation_seconds']+=reserve
            attempts[-1].update(charged=True,budget_reservation_seconds=reserve,time_accounting='conservative_interruption_reservation')
    remaining=state['policy']['max_simulation_seconds']-state['simulation_seconds']
    if remaining<=0 or len(attempts)>=state['policy']['max_execution_retries_per_candidate']:
        state['status']='execution_budget_exhausted';save(session,state);return state
    experiment=folder/f'execution_{len(attempts)+1:02d}'
    allocated=min(60,remaining)
    attempts.append({'path':str(experiment),'status':'started','started_utc':datetime.now(timezone.utc).isoformat(),
                     'allocated_seconds':allocated,'charged':False})
    save(session,state)
    script=Path(__file__).resolve().parents[1]/'run_first_opamp.py'
    command=[sys.executable,str(script),'--ltspice',str(ltspice),'--netlist',pending['candidate_path'],
        '--output-dir',str(experiment),'--measurement-plan',state['measurement_plan_path'],
        '--bench-timeout','20','--wall-budget',str(allocated)]
    start_time=time.monotonic()
    try:
        proc=subprocess.run(command,cwd=script.parent,capture_output=True,timeout=allocated+30)
        (folder/f'execution_{len(attempts):02d}_stdout.txt').write_bytes(proc.stdout)
        (folder/f'execution_{len(attempts):02d}_stderr.txt').write_bytes(proc.stderr)
        attempts[-1]['returncode']=proc.returncode
    except subprocess.TimeoutExpired:
        attempts[-1].update(status='controller_timeout',charged=True,elapsed_seconds=time.monotonic()-start_time)
        state['simulation_seconds']+=attempts[-1]['elapsed_seconds']
        save(session,state);return state
    elapsed=time.monotonic()-start_time;state['simulation_seconds']+=elapsed
    attempts[-1].update(elapsed_seconds=elapsed,status='finished',charged=True,time_accounting='controller_wall_time')
    result_path=experiment/'RESULT.json'
    result=read(result_path) if result_path.exists() else {'status':'error','benchmarks':[],'error':'No result file generated'}
    if not result_path.exists():write_json(result_path,result)
    save(session,state)
    return finish_pending(session,state,experiment,result)


def finish_pending(session,state,experiment,result):
    pending=state['pending_candidate']
    if result.get('status') in ('partial_experiment_completed','partial_with_execution_errors') and result.get('netlist_sha256')!=pending['candidate_sha256']:
        raise ValueError('Simulator consumed a different netlist')
    if result.get('status') in ('partial_experiment_completed','partial_with_execution_errors') and result.get('measurement_plan_sha256')!=state['measurement_plan_sha256']:
        raise ValueError('Simulator consumed a different measurement plan')
    item={k:pending[k] for k in ('id','candidate_path','candidate_sha256','response_sha256','based_on_request_sha256','execution_attempts','token_usage')}
    item.update(origin='current_chat_revision',result_path=str(experiment/'RESULT.json'),
        result_sha256=file_hash(experiment/'RESULT.json'),assessment=evaluate(result,state['policy']))
    state['candidates'].append(item);state['pending_candidate']=None
    advance(session,state);return state


def submit(session,response,ltspice):
    state=load(session);accept_response(session,state,response);save(session,state)
    return execute_pending(session,state,ltspice)


def resume(session,ltspice):
    state=load(session)
    if state['status']=='testing_candidate':return execute_pending(session,state,ltspice)
    save(session,state)
    return state
