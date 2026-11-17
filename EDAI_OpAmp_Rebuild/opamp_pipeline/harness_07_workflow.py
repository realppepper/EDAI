"""Bounded operational Harness2 rounds around the existing fixed design loop.

There is no matched control experiment here. A policy/circuit pair may progress
locally after qualified improvement; this does not establish policy efficacy.
Chat supplies instruction/design responses, while the host owns execution/state.
"""
from copy import deepcopy
from pathlib import Path

from . import harness_03_loop as fixed
from . import harness_06_evolution as evolution
from .harness_01_fixed import DEFAULT_POLICY, load_harness, validate_candidate
from .harness_02_request import make_request
from .loop_02_handoff import write_json
from .pipeline_01_verification import ROOT, read
from .support.atomic_files import atomic_write_text
from .support.execution_state import file_hash
from .support.source_checks import fingerprint
from . import schematic_01_export as schematic

DONE = {'implemented_scope_passed', 'round_budget_exhausted',
        'invalid_proposal_budget_exhausted', 'invalid_response_budget_exhausted'}


def _pair(policy, candidate, pipeline, ledger):
    return {**{key: str(Path(value).resolve()) for key, value in
        [('policy_path', policy), ('candidate_path', candidate),
         ('pipeline_path', pipeline), ('ledger_path', ledger)]},
        'policy_sha256': file_hash(policy), 'candidate_sha256': file_hash(candidate),
        'ledger_sha256': file_hash(ledger)}


def _verify_pair(pair):
    for name in ('policy', 'candidate', 'ledger'):
        if file_hash(pair[name + '_path']) != pair[name + '_sha256']:
            raise ValueError('Recorded workflow pair changed: ' + name)


def _save(session, state):
    session = Path(session)
    if state['status']=='implemented_scope_passed':
        schematic.complete(session,state,state['active'])
    write_json(session / 'STATE.json', state)  # authoritative checkpoint first
    write_json(session / 'ACTIVE.json', state['active'])
    write_json(session / 'BEST.json', state['active'])
    write_json(session / 'NEXT_ACTION.json', {'status': state['status'],
        'actor': ('chat_improver' if state['status'] == 'awaiting_harness_proposal'
                  else 'chat_designer' if state['status'] == 'awaiting_chat_designer'
                  else 'host' if state['status'] in {'validating_initial', 'validating_candidate', 'validation_interrupted', 'preparing_round'}
                  else 'none'), 'request': state.get('pending_request')})
    lines = ['# 연속 회로·지침 설계 루프', '', f"상태: {state['status']}",
        f"회차 예산: {len(state['rounds'])}/{state['max_rounds']}; 회차별 수정 한도: {state['revisions_per_round']}",
        f"최선 회로: {state['active']['candidate_path']}",
        f"연결 지침: {state['active']['policy_path']}", '',
        '| 회차 | 완료 | 정책 채택 | 선택 결과 |', '|---|---|---|---|']
    for r in state['rounds']:
        d = r.get('decision', {})
        lines.append(f"| {r['index']} | {r.get('completed', False)} | {d.get('policy_adopted', False)} | {d.get('reason', '진행 중')} |")
    lines += ['', '현재 검증 범위의 성공만 판정한다. 범위 밖 조건은 미검증으로 유지한다.',
        '운영 중의 국소 개선 채택이며 지침 효과 비교 실험이 아니다.',
        '설계/지침 응답은 현재 채팅이 담당한다. API/토큰 비용은 미측정(null).']
    lines += schematic.report_lines(state)
    atomic_write_text(session / 'REPORT.md', '\n'.join(lines) + '\n')


def load(session):
    state = read(Path(session) / 'STATE.json')
    for path, sha in {**state['code_signatures'], **state['artifacts'],
                      state['plan_path']: state['plan_sha256']}.items():
        if file_hash(path) != sha:
            raise ValueError('Frozen workflow code/input changed: ' + path)
    _verify_pair(state['active'])
    for r in state['rounds']:
        _verify_pair(r['base'])
        path = Path(r['inner_session'])
        if (path / 'STATE.json').exists():
            inner = fixed.load(path)
            if (inner['max_candidates'] != state['revisions_per_round'] + 1
                    or inner['harness_sha256'] != file_hash(r['policy_path'])
                    or inner['candidates'] and inner['scope_case_ids'] != state['scope_case_ids']):
                raise ValueError('Inner loop budget, policy or scope changed')
    return state


def _prepare_proposal(session, state):
    active = state['active']; index = len(state['rounds']) + 1
    base_request = make_request(read(state['plan_path']), read(active['ledger_path']),
        Path(active['candidate_path']).read_text(encoding='ascii'), active['policy_path'])
    packet = {'schema_version': 1, 'mode': 'operational_harness_improver',
        'round_index': index, 'baseline_design_request': base_request,
        'execution_capabilities': {'designer': 'current_chat',
            'designer_can_execute_simulations': False,
            'designer_can_request_extra_probe_round': False,
            'host_validates_full_plan_after_each_design': True,
            'design_revisions_this_round': state['revisions_per_round'],
            'remaining_outer_rounds': state['max_rounds'] - index + 1},
        'recent_rounds': [deepcopy(r['decision']) for r in state['rounds'][-3:]],
        'constraints': [
            'Return zero or one instruction variant; zero keeps the active policy.',
            'Only append conditional C3/C5/C6 rules; immutable rules and evaluators remain unchanged.',
            'Fit instructions to the actual tools and design budget above. Do not require unavailable probes as already established facts.',
            'Consider all unresolved requirements. A single-parameter probe is not mandatory when a bounded multi-objective repair is needed.',
            'No known successful recipe or unverified physical cause claims.',
            'Operational progress only: no matched control or policy-effectiveness claim.'],
        'response_schema': {'request_id': 'echo exactly', 'request_sha256': 'SHA256 of this file',
            'reason': 'why retain or change instructions',
            'proposals': '[] to retain, otherwise one proposal in Harness2 format: id,title,rules; each rule has component_id,when,text,evidence_case_ids,expected_effect,risks'}}
    packet['request_id'] = fingerprint(packet)
    path = Path(session) / f'round_{index:03d}/PROPOSE_REQUEST.json'
    evolution._json(path, packet)
    state['artifacts'][str(path)] = file_hash(path)
    state['pending_request'] = {'path': str(path), 'sha256': file_hash(path), 'request_id': packet['request_id']}
    state['status'] = 'awaiting_harness_proposal'


def start(session, baseline_pipeline, model, run_dir, harness=DEFAULT_POLICY,
          max_rounds=3, revisions_per_round=2,optuna_config=None,optuna_trials=4,optuna_rounds=1,optuna_from_designer=False):
    session = Path(session).resolve()
    if (session / 'STATE.json').exists():
        raise ValueError('Workflow already exists')
    for name, n in [('rounds', max_rounds), ('revisions', revisions_per_round)]:
        if isinstance(n, bool) or not isinstance(n, int) or not 1 <= n <= 20:
            raise ValueError('Bounded positive integer required: ' + name)
    run_dir = Path(run_dir).resolve(); plan = run_dir / 'measurement_plan/plan_02_measurements.json'
    model = Path(model).resolve(); load_harness(harness)
    validate_candidate(model.read_text(encoding='ascii'))
    _, result = evolution._pipeline_evidence(baseline_pipeline, model, plan)
    policy_path, model_path, ledger_path = (session / 'baseline' / n for n in ('harness.json', 'candidate.inc', 'LEDGER.json'))
    evolution._put(policy_path, Path(harness).read_bytes()); evolution._put(model_path, model.read_bytes())
    evolution._json(ledger_path, result)
    request = make_request(read(plan), result, model_path.read_text(encoding='ascii'), policy_path)
    scope = request['evaluation_scope']['implemented_scope_case_ids']
    if not scope: raise ValueError('No qualified scope')
    active = _pair(policy_path, model_path, baseline_pipeline, ledger_path)
    code = evolution._signatures()
    code[str(ROOT / 'run_opamp_workflow.py')] = file_hash(ROOT / 'run_opamp_workflow.py')
    state = {'schema_version': 1, 'mode': 'operational_harness_workflow',
        'status': 'initializing', 'code_signatures': code, 'run_dir': str(run_dir),
        'plan_path': str(plan), 'plan_sha256': file_hash(plan), 'scope_case_ids': scope,
        'max_rounds': max_rounds, 'revisions_per_round': revisions_per_round,
        'active': active, 'rounds': [], 'artifacts': {str(p): file_hash(p) for p in (policy_path, model_path, ledger_path)},
        'pending_request': None, 'invalid_proposals': 0,
        'accepted_proposal_sha256': [], 'accepted_design_sha256': [],
        'external_llm_api_calls': 0, 'chat_token_usage': None, 'api_cost_USD': None,
        'harness2_enabled': True, 'matched_control_experiment': False,
        'full_datasheet_success': False, 'global_default_modified': False}
    if optuna_config is not None and optuna_from_designer:raise ValueError('Choose fixed or designer sizing mode')
    if optuna_config is not None or optuna_from_designer:
        from .optuna_03_loop_bridge import configure
        from .optuna_04_designer import designer_policy
        state['optuna']=designer_policy(optuna_trials,optuna_rounds) if optuna_from_designer else configure(optuna_config,optuna_trials,optuna_rounds)
        if state['optuna'].get('config_path'):state['artifacts'][state['optuna']['config_path']]=state['optuna']['config_sha256']
    if fixed.assessment(result, result, scope)['scope_passed']:
        state['status'] = 'implemented_scope_passed'
    else: _prepare_proposal(session, state)
    _save(session, state)
    return state


def _finish_round(session, state, inner):
    r = state['rounds'][-1]; base = read(r['base']['ledger_path'])
    base_a=fixed.assessment(base, base, state['scope_case_ids'])
    base_failed = set(base_a.get('failed_requirement_ids',base_a['failed_case_ids']))
    selected = None; trials = []
    for record in inner['candidates'][1:]:
        _, measured = evolution._pipeline_evidence(Path(record['ledger_path']).parent,
            record['candidate_path'], state['plan_path'])
        a = evolution.outcome(base, measured, state['scope_case_ids'])
        trials.append({'index': record['index'], 'candidate_sha256': record['candidate_sha256'],
                       'assessment': a, 'ledger_path': record['ledger_path']})
        if a['eligible'] and set(a.get('failed_requirement_ids',a['failed_case_ids'])) < base_failed:
            if selected is None or len(a.get('failed_requirement_ids',a['failed_case_ids'])) < len(selected[1].get('failed_requirement_ids',selected[1]['failed_case_ids'])):
                selected = (record, a)
    adopted = bool(selected) and r['proposed_policy']
    if selected:
        record, assessment = selected
        state['active'] = _pair(r['policy_path'], record['candidate_path'],
            Path(record['ledger_path']).parent, record['ledger_path'])
        success = assessment['scope_passed']
    else: success = False
    decision = {'round_index': r['index'], 'policy_adopted': adopted,
        'circuit_improved': bool(selected), 'active': deepcopy(state['active']),
        'reason': 'Qualified circuit progress; tested whole policy/circuit pair retained.' if selected
                  else 'No safe strict progress; prior circuit and policy retained.',
        'proposal_reason': r['proposal_reason'],
        'tested_policy_path': r['policy_path'], 'trials': trials,
        'policy_effectiveness_proved': False}
    r.update(completed=True, decision=decision)
    path = Path(r['inner_session']).parent / 'DECISION.json'; evolution._json(path, decision)
    state['artifacts'][str(path)] = file_hash(path)
    state['pending_request'] = None
    if success: state['status'] = 'implemented_scope_passed'
    elif len(state['rounds']) >= state['max_rounds']: state['status'] = 'round_budget_exhausted'
    else: _prepare_proposal(session, state)


def _sync(session, state, ltspice=None, execute=False):
    if state['status'] in DONE or state['status'] == 'awaiting_harness_proposal':
        _save(session, state); return state
    r = state['rounds'][-1]; inner_path = Path(r['inner_session'])
    if not (inner_path / 'STATE.json').exists():
        imports, _ = evolution._pipeline_evidence(r['base']['pipeline_path'],
            r['base']['candidate_path'], state['plan_path'])
        sizing=state.get('optuna',{})
        fixed.start(inner_path, r['base']['candidate_path'], state['run_dir'],
            imports=imports, harness=r['policy_path'], max_candidates=state['revisions_per_round'] + 1,
              defer_validation=True,optuna_config=sizing.get('config_path'),
              optuna_trials=sizing.get('trials',4),optuna_rounds=sizing.get('max_rounds',1),
              optuna_from_designer=sizing.get('mode')=='designer_proposal')
    inner = fixed.load(inner_path)
    # Initial baseline imports require no new EDA execution. Interrupted candidate
    # validation resumes only on an explicit execute=True call.
    if not inner['candidates'] or execute and inner['status'] in {'validating_initial', 'validating_candidate', 'validation_interrupted','awaiting_optuna_execution','optimizing_parameters','optuna_interrupted','optuna_ready_to_advance'}:
        inner = fixed.resume(inner_path, ltspice)
    for c in [*inner['candidates'], *([inner['pending_candidate']] if inner.get('pending_candidate') else [])]:
        sha = c.get('submitted_response_sha256')
        if sha and sha not in state['accepted_design_sha256']: state['accepted_design_sha256'].append(sha)
    if inner['status'] in evolution.TERMINAL:
        _finish_round(session, state, inner)
    elif inner['status'] == 'invalid_response_budget_exhausted':
        state.update(status=inner['status'], pending_request=None)
    else:
        state.update(status=inner['status'], pending_request=inner.get('pending_request'))
    _save(session, state)
    return state


def propose(session, response_path):
    session = Path(session).resolve(); state = load(session); sha = file_hash(response_path)
    if sha in state['accepted_proposal_sha256']: return _sync(session, state)
    if state['status'] != 'awaiting_harness_proposal': raise ValueError('No pending instruction request')
    pending = state['pending_request']; request = read(pending['path'])
    try:
        response = read(response_path)
        if set(response) != {'request_id', 'request_sha256', 'reason', 'proposals'}:
            raise ValueError('Unexpected instruction response fields')
        if response['request_id'] != pending['request_id'] or response['request_sha256'] != pending['sha256']:
            raise ValueError('Instruction response belongs to another round')
        if not isinstance(response['reason'], str) or not response['reason'].strip() or len(response['reason']) > 3000:
            raise ValueError('Bounded instruction decision reason required')
        proposals = response['proposals']
        if not isinstance(proposals, list) or len(proposals) > 1:
            raise ValueError('Zero or one policy proposal required')
        base = read(state['active']['policy_path'])
        normalized = {k: response[k] for k in ('request_id', 'request_sha256', 'proposals')}
        policy = next(iter(evolution.build_variants(base, normalized, request, pending['sha256']).values())) if proposals else base
    except ValueError as error:
        state['invalid_proposals'] += 1
        write_json(session / f"REJECTED_PROPOSAL_{state['invalid_proposals']:03d}.json", {'response_sha256': sha, 'error': str(error)})
        if state['invalid_proposals'] >= 3: state.update(status='invalid_proposal_budget_exhausted', pending_request=None)
        _save(session, state); raise
    index = len(state['rounds']) + 1; folder = session / f'round_{index:03d}'
    receipt, policy_path = folder / 'PROPOSAL_RESPONSE.json', folder / 'harness.json'
    evolution._json(receipt, response); evolution._json(policy_path, policy)
    for path in (receipt, policy_path): state['artifacts'][str(path)] = file_hash(path)
    state['rounds'].append({'index': index, 'base': deepcopy(state['active']),
        'policy_path': str(policy_path), 'proposed_policy': bool(proposals),
        'proposal_reason': response['reason'], 'inner_session': str(folder / 'loop'), 'completed': False})
    state['accepted_proposal_sha256'].append(sha)
    state.update(status='preparing_round', pending_request=None); _save(session, state)
    return _sync(session, state)


def submit(session, response_path, ltspice=None, defer_validation=False):
    session = Path(session).resolve(); state = load(session)
    state = _sync(session, state)
    if file_hash(response_path) in state['accepted_design_sha256']: return state
    if state['status'] != 'awaiting_chat_designer': raise ValueError('No pending circuit design request')
    try:
        fixed.submit(state['rounds'][-1]['inner_session'], response_path, ltspice,
                     defer_validation=defer_validation)
    except ValueError:
        _sync(session, state); raise
    return _sync(session, state)


def resume(session, ltspice=None):
    session = Path(session).resolve()
    return _sync(session, load(session), ltspice, execute=True)
