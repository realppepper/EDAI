"""Outer instruction-edit controller; each probe uses the unchanged fixed inner loop.

Chat supplies proposals and designs. The host freezes evidence, executes probes,
and selects only a whole tested policy. No provider calls or evaluator edits.
"""
from copy import deepcopy
from pathlib import Path

from . import harness_03_loop as fixed
from .harness_01_fixed import DEFAULT_POLICY, load_harness, validate_candidate
from .harness_02_request import make_request
from .harness_04_feedback import describe_case
from .loop_02_handoff import write_json
from .loop_04_extended_policy import ledger
from .pipeline_01_verification import ROOT, check_chain, read
from .support.atomic_files import atomic_write_bytes
from .support.execution_state import file_hash
from .support.source_checks import fingerprint

EDITABLE = frozenset({'C3', 'C5', 'C6'})
TERMINAL = {'implemented_scope_passed', 'candidate_budget_exhausted'}


def _put(path, data):
    """Idempotent publication without overwriting different prior evidence."""
    path = Path(path)
    if path.exists():
        if path.read_bytes() != data:
            raise ValueError('Existing artifact differs: ' + str(path))
    else:
        atomic_write_bytes(path, data)


def _json(path, value):
    import json
    _put(path, json.dumps(value, ensure_ascii=False, indent=2,
                          allow_nan=False).encode('utf-8'))


def _signatures():
    paths = list((ROOT / 'opamp_pipeline').rglob('*.py'))
    paths += [ROOT / p for p in ('run_fixed_harness_loop.py',
        'run_verification_pipeline.py', 'run_extended_verification.py',
        'run_input_impedance_extension.py', 'run_overload_extension.py',
        'run_harness2_loop.py')]
    return {str(p): file_hash(p) for p in paths}


def _save(session, state):
    write_json(Path(session) / 'STATE.json', state)


def _pipeline_evidence(folder, model, plan):
    folder = Path(folder).resolve()
    state = read(folder / 'STATE.json')
    if state['status'] != 'completed':
        raise ValueError('A completed full verification pipeline is required')
    for p, sha in state['outputs'].items():
        if file_hash(p) != sha:
            raise ValueError('Pipeline output changed: ' + p)
    paths = [state['results'][k] for k in ('core', 'impedance', 'overload')]
    checked = check_chain(*paths, model, plan)
    if checked != read(folder / 'LEDGER.json'):
        raise ValueError('Pipeline ledger differs from its qualified chain')
    return paths, checked


def start(session, baseline_pipeline, model, run_dir, harness=DEFAULT_POLICY):
    session = Path(session).resolve()
    if (session / 'STATE.json').exists():
        raise ValueError('Evolution session already exists')
    model, run_dir = Path(model).resolve(), Path(run_dir).resolve()
    plan = run_dir / 'measurement_plan/plan_02_measurements.json'
    policy, _ = load_harness(harness)
    validate_candidate(model.read_text(encoding='ascii'))
    paths, result = _pipeline_evidence(baseline_pipeline, model, plan)
    base_policy, base_model = session / 'baseline/harness.json', session / 'baseline/candidate.inc'
    _put(base_policy, Path(harness).read_bytes())
    _put(base_model, model.read_bytes())
    _json(session / 'baseline/LEDGER.json', result)
    request = make_request(read(plan), result, base_model.read_text(encoding='ascii'), base_policy)
    scope = request['evaluation_scope']['implemented_scope_case_ids']
    if not scope:
        raise ValueError('No qualified cases to evaluate instruction changes')
    assessment = fixed.assessment(result, result, scope)
    state = {'schema_version': 1, 'status': 'awaiting_harness_proposal',
        'harness2_enabled': True, 'external_llm_api_calls': 0,
        'chat_token_usage': None, 'api_cost_USD': None,
        'instruction_changes_per_round': 2, 'design_revisions_per_branch': 1,
        'code_signatures': _signatures(), 'run_dir': str(run_dir),
        'plan_path': str(plan), 'plan_sha256': file_hash(plan),
        'baseline_pipeline': str(Path(baseline_pipeline).resolve()),
        'baseline_imports': paths, 'baseline_policy': str(base_policy),
        'baseline_candidate': str(base_model), 'baseline_ledger': str(session / 'baseline/LEDGER.json'),
        'baseline_assessment': assessment, 'scope_case_ids': scope,
        'artifacts': {str(p): file_hash(p) for p in (base_policy, base_model, session / 'baseline/LEDGER.json')},
        'branches': {}, 'proposal_response': None, 'decision': None,
        'global_default_modified': False, 'rollback_events': []}
    if assessment['scope_passed']:
        state['status'] = 'no_unmet_cases'
    else:
        packet = {'schema_version': 1, 'mode': 'current_chat_harness_improver',
            'baseline_design_request': request,
            'constraints': [
                'Append conditional rules only to C3/C5/C6; original rules remain unchanged.',
                'Never change targets, measurement code, models, fixtures, coverage, retry policy or success criteria.',
                'Propose at most two separately tested variants; no automatic mixing of memories or rules.',
                'Use diagnostic evidence to state hypotheses, not confirmed physical causes.',
                'No hidden successful netlist/value, universal sizing recipe, or evaluator bypass.',
                'Chat roles remain manual. Token usage is unknown, not zero.'],
            'response_schema': {'request_id': 'echo exactly', 'request_sha256': 'SHA256 of this file',
                'proposals': [{'id': 'short ASCII identifier', 'title': 'brief description',
                    'rules': [{'component_id': 'C3 or C5 or C6',
                        'when': 'applicability and limitations', 'text': 'conditional design instruction',
                        'evidence_case_ids': ['existing required case IDs'],
                        'expected_effect': 'testable hypothesis', 'risks': 'tradeoffs and possible regressions'}]}]}}
        packet['request_id'] = fingerprint(packet)
        path = session / 'PROPOSE_REQUEST.json'; _json(path, packet)
        state['proposal_request'] = {'path': str(path), 'sha256': file_hash(path), 'request_id': packet['request_id']}
        state['artifacts'][str(path)] = file_hash(path)
    _save(session, state)
    return state


def load(session):
    state = read(Path(session) / 'STATE.json')
    signatures = {**state['code_signatures'], **state['artifacts'],
                  state['plan_path']: state['plan_sha256']}
    for p, sha in signatures.items():
        if file_hash(p) != sha:
            raise ValueError('Frozen evolution input/code changed: ' + p)
    return state


def build_variants(base, response, request, request_sha256):
    """Append only; neither proposal text nor JSON may mutate enforced boundaries."""
    if set(response) != {'request_id', 'request_sha256', 'proposals'}:
        raise ValueError('Unexpected proposal response fields')
    if response['request_id'] != request['request_id'] or response['request_sha256'] != request_sha256:
        raise ValueError('Harness proposal belongs to another request')
    proposals = response['proposals']
    if not isinstance(proposals, list) or not 1 <= len(proposals) <= 2:
        raise ValueError('One or two instruction variants required')
    import re
    allowed = set(request['baseline_design_request']['evaluation_scope']['implemented_scope_case_ids'])
    variants = {}; total_length = 0
    for proposal in proposals:
        if not isinstance(proposal, dict) or set(proposal) != {'id', 'title', 'rules'}:
            raise ValueError('Unexpected proposal fields')
        name = proposal['id']
        if not isinstance(name, str) or not re.fullmatch(r'[a-z][a-z0-9_]{0,31}', name) or name == 'control' or name in variants:
            raise ValueError('Invalid/duplicate proposal ID')
        if not isinstance(proposal['title'], str) or not proposal['title'].strip() or len(proposal['title']) > 200:
            raise ValueError('Short proposal title required')
        rules = proposal['rules']
        if not isinstance(rules, list) or not 1 <= len(rules) <= 3:
            raise ValueError('One to three conditional rules per variant required')
        tree = deepcopy(base)
        for index, rule in enumerate(rules):
            fields = {'component_id', 'when', 'text', 'evidence_case_ids', 'expected_effect', 'risks'}
            if not isinstance(rule, dict) or set(rule) != fields or rule['component_id'] not in EDITABLE:
                raise ValueError('Only conditional C3/C5/C6 additions are allowed')
            for key in ('when', 'text', 'expected_effect', 'risks'):
                if not isinstance(rule[key], str) or not rule[key].strip() or len(rule[key]) > 1600:
                    raise ValueError('Bounded nonempty rule content required')
                total_length += len(rule[key])
            evidence = rule['evidence_case_ids']
            if not isinstance(evidence, list) or not evidence or any(not isinstance(k, str) for k in evidence) or not set(evidence) <= allowed:
                raise ValueError('Rule requires known implemented-scope evidence')
            component = next(c for c in tree['components'] if c['id'] == rule['component_id'])
            if not component['enabled']:
                raise ValueError('Cannot enable a disabled component')
            component['rules'].append({'id': f'H2-{name}-{index+1}',
                'text': f"When: {rule['when']}\nInstruction: {rule['text']}\nHypothesis: {rule['expected_effect']}\nRisks: {rule['risks']}"})
        tree['id'] = base['id'] + '__' + name
        tree['parent_harness_id'] = base['id']
        tree['effectiveness'] = 'Proposed conditional instructions; effectiveness not established.'
        tree['harness2_provenance'] = {'proposal_id': name, 'request_id': request['request_id'],
            'instruction_evolution_location': 'outer controller; inner probe policy stays frozen',
            'proposal': deepcopy(proposal)}
        variants[name] = tree
    if total_length > 9000:
        raise ValueError('Instruction edit budget exceeded')
    return variants


def propose(session, response_path):
    session = Path(session).resolve(); state = load(session)
    if state['status'] not in {'awaiting_harness_proposal', 'preparing_probes'}:
        raise ValueError('No pending instruction proposal')
    request = state['proposal_request']; response = read(response_path)
    variants = build_variants(read(state['baseline_policy']), response, read(request['path']), request['sha256'])
    receipt = session / 'PROPOSAL_RESPONSE.json'; _json(receipt, response)
    state['artifacts'][str(receipt)] = file_hash(receipt)
    state['proposal_response'] = str(receipt); state['status'] = 'preparing_probes'; _save(session, state)
    policies = {'control': read(state['baseline_policy']), **variants}
    for name, policy in policies.items():
        folder = session / 'branches' / name; policy_path = folder / 'harness.json'
        _json(policy_path, policy); state['artifacts'][str(policy_path)] = file_hash(policy_path)
        branch = folder / 'loop'
        if (branch / 'STATE.json').exists():
            fixed.load(branch)
        else:
            fixed.start(branch, state['baseline_candidate'], state['run_dir'],
                imports=state['baseline_imports'], harness=policy_path, max_candidates=2)
        state['branches'][name] = {'session': str(branch), 'policy': str(policy_path)}
        _save(session, state)
    state['status'] = 'awaiting_probe_designs'; _save(session, state)
    return state


def submit(session, branch, response_path, ltspice=None, defer_validation=False):
    state = load(session)
    if state['status'] != 'awaiting_probe_designs' or branch not in state['branches']:
        raise ValueError('No open branch')
    return fixed.submit(state['branches'][branch]['session'], response_path, ltspice, defer_validation)


def resume(session, branch, ltspice=None):
    state = load(session)
    if state['status'] != 'awaiting_probe_designs' or branch not in state['branches']:
        raise ValueError('No open branch')
    return fixed.resume(state['branches'][branch]['session'], ltspice)


def outcome(base_result, current_result, scope):
    """Recompute from ledgers; never use LLM-provided scores or pass claims."""
    assessment = fixed.assessment(base_result, current_result, scope)
    cases = ledger(current_result)
    unusable = [k for k in scope if not describe_case(cases[k], True)['case_assessment']['target_verdict_usable']]
    base_cases = ledger(base_result)
    regressions = [k for k in scope if base_cases[k]['case']['status'] == 'passed_sampled_model_case'
                   and cases[k]['case']['status'] != 'passed_sampled_model_case']
    if base_result.get('operational_startup',{}).get('passed') and not assessment.get('startup_passed'):
        regressions.append('OPERATIONAL-STARTUP')
    return {**assessment, 'unusable_case_ids': unusable, 'regressions_from_baseline': regressions,
            'comparison_usable': not unusable,
            'eligible': not unusable and not regressions}


def choose(outcomes):
    """Whole-policy local adoption only if it strictly beats a matched control.

    A tie keeps the baseline policy. No failed/unmeasured variant memory merges.
    """
    control = outcomes['control']
    # A measured regression is a valid negative control. Its instructions cannot
    # be retained, but it must not veto a safe, strictly superior variant.
    # Old saved outcomes predate comparison_usable; retain fail-closed behavior
    # for abbreviated records without explicit measurement-validity evidence.
    control_comparable = control.get('comparison_usable',
        not control['unusable_case_ids'] if 'unusable_case_ids' in control else control['eligible'])
    chosen = 'control' if control['eligible'] else 'baseline'
    if control_comparable:
        failed = set(control.get('failed_requirement_ids',control['failed_case_ids']))
        eligible = [name for name, value in outcomes.items() if name != 'control'
                    and value['eligible'] and set(value.get('failed_requirement_ids',value['failed_case_ids'])) < failed]
        if eligible:
            chosen = min(eligible, key=lambda k: (len(outcomes[k].get('failed_requirement_ids',outcomes[k]['failed_case_ids'])), k))
    return {'selected_branch': chosen, 'adopted': chosen not in {'control', 'baseline'},
            'decision_policy_version': 2,
            'control_comparison_usable': control_comparable,
            'control_retainable': control['eligible'],
            'reason': ('Whole tested variant strictly improves the matched control without baseline regressions.'
                       if chosen not in {'control', 'baseline'} else
                       'No qualified strict improvement over the matched control; baseline instructions retained.'),
            'scope': 'local task evidence only; no general success-rate benefit established',
            'composed_untested_policy': False}


def decide(session):
    session = Path(session).resolve(); state = load(session)
    if state['status'] in {'decided', 'rolled_back'}:
        return state
    if state['status'] != 'awaiting_probe_designs':
        raise ValueError('Instruction probes are not ready')
    base = read(state['baseline_ledger']); outcomes = {}; records = {}
    for name, branch in state['branches'].items():
        inner = fixed.load(branch['session'])
        if inner['status'] not in TERMINAL or len(inner['candidates']) != 2:
            raise ValueError('Complete the single revision in every branch before selection: ' + name)
        # Evaluate the actual probe, not the retained best baseline candidate.
        record = inner['candidates'][-1]
        if not record.get('ledger_path'):
            raise ValueError('Probe has no completed measurement ledger: ' + name)
        _, result = _pipeline_evidence(Path(record['ledger_path']).parent,
                                      record['candidate_path'], state['plan_path'])
        outcomes[name] = outcome(base, result, state['scope_case_ids'])
        records[name] = record
    decision = choose(outcomes); name = decision['selected_branch']
    if name == 'baseline':
        policy, model, result_path = state['baseline_policy'], state['baseline_candidate'], state['baseline_ledger']
    else:
        policy, model, result_path = state['branches'][name]['policy'], records[name]['candidate_path'], records[name]['ledger_path']
    active = {'policy_path': policy, 'policy_sha256': file_hash(policy),
        'candidate_path': model, 'candidate_sha256': file_hash(model),
        'ledger_path': result_path, 'ledger_sha256': file_hash(result_path),
        'decision': decision, 'global_default_modified': False}
    write_json(session / 'DECISION.json', {'decision': decision, 'outcomes': outcomes})
    write_json(session / 'ACTIVE.json', active)
    for p in (session / 'DECISION.json', session / 'ACTIVE.json'):
        state['artifacts'][str(p)] = file_hash(p)
    state.update(status='decided', decision=decision); _save(session, state)
    return state


def rollback(session, reason):
    session = Path(session).resolve(); state = load(session)
    if not isinstance(reason, str) or not reason.strip():
        raise ValueError('Rollback reason required')
    if state['status'] != 'decided':
        raise ValueError('A completed decision is required before rollback')
    previous = read(session / 'ACTIVE.json')
    _json(session / 'ACTIVE_BEFORE_ROLLBACK.json', previous)
    policy, model, result = (state[k] for k in ('baseline_policy', 'baseline_candidate', 'baseline_ledger'))
    write_json(session / 'ACTIVE.json', {'policy_path': policy, 'policy_sha256': file_hash(policy),
        'candidate_path': model, 'candidate_sha256': file_hash(model),
        'ledger_path': result, 'ledger_sha256': file_hash(result), 'rollback_reason': reason,
        'global_default_modified': False})
    state['rollback_events'].append({'reason': reason, 'previous_active_sha256': fingerprint(previous)})
    for p in (session / 'ACTIVE.json', session / 'ACTIVE_BEFORE_ROLLBACK.json'):
        state['artifacts'][str(p)] = file_hash(p)
    state['status'] = 'rolled_back'; _save(session, state)
    return state
