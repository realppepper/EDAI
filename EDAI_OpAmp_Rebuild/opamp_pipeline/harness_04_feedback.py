"""Describe existing verification evidence without changing verdicts or targets."""
from copy import deepcopy


PASS = 'passed_sampled_model_case'


def implemented_scope_case_ids(records, policy):
    """Same capability registry as the host, independent of current pass counts."""
    kinds = set(policy['qualified_measurement_families'])
    return [key for key, record in records.items() if record['kind'] in kinds]


def unique_messages(values):
    return list(dict.fromkeys(values))


def describe_case(record, required):
    case = record['case']
    parts = case.get('parts', [])
    gates = unique_messages([*case.get('gate_issues', []),
                             *(g for part in parts for g in part.get('gate_issues', []))])
    limitations = unique_messages([*case.get('model_limitations', []),
                                   *(v for part in parts for v in part.get('model_limitations', []))])
    status = case['status']
    if not required:
        if status == PASS:
            raise ValueError('A case outside the qualified registry cannot be promoted to a pass')
        category = 'verification_extension_needed'
        action = 'Retain in the full plan. Extend/qualify the model or adapter separately; do not claim circuit compliance.'
    elif status == 'execution_error':
        category = 'measurement_execution_error'
        action = 'Diagnose execution/data completeness with the host. This is not an established physical specification miss.'
    elif limitations or status == 'unverified_model':
        category = 'model_scope_review_needed'
        action = 'Ask the host to resolve the model/registry limitation. Do not turn a lower bound or unsupported result into a pass.'
    elif gates:
        category = 'measurement_prerequisite_not_met'
        action = 'This required case remains unresolved. Diagnose the recorded gate and recheck under the same immutable fixture; do not waive the case or relax the protocol.'
    elif status == PASS:
        category = 'passed'
        action = 'Preserve this result when revising and revalidate the candidate.'
    elif status == 'failed_in_model':
        category = 'measured_specification_miss'
        action = 'Propose a circuit revision as a hypothesis and revalidate all required cases.'
    elif status == 'unverified_adapter':
        category = 'required_case_qualification_needed'
        action = 'The registry includes this case but its current result is unqualified. Resolve the recorded reason with the host; it is not waived.'
    else:
        category = 'host_review_needed'
        action = 'Unknown result status: keep the required case unresolved and request host review.'
    if status == PASS and (gates or limitations):
        raise ValueError('Passing status conflicts with unresolved measurement gates/model limitations')
    usable = category in {'passed', 'measured_specification_miss'}
    diagnostics = []
    for part in parts:
        detail = {key: deepcopy(part[key]) for key in (
            'value', 'metrics', 'overload_evidence', 'qualification_checks',
            'model_scope', 'component_checks', 'gate_issues', 'model_limitations') if key in part}
        detail['variant'] = part.get('direction', part.get('variant', 'default'))
        # Keep the evidence link without copying raw waveform arrays into a prompt.
        if part.get('job_path') or part.get('path'):
            detail['source_artifact'] = part.get('job_path') or part['path']
        diagnostics.append(detail)
    interpretation = {
        'required_for_implemented_scope': required,
        'retained_in_full_plan': True,
        'category': category,
        'target_verdict_usable': usable,
        'test_values_usage': 'acceptance_evidence' if usable else 'diagnostic_only_not_a_compliance_verdict',
        'next_action': action,
        'physical_failure_cause_confirmed': False,
    }
    return {'case_assessment': interpretation, 'gate_issues': gates,
            'model_limitations': limitations, 'part_diagnostics': diagnostics,
            'measurement_coverage': deepcopy(case.get('measurement_coverage')),
            'numerical_attempts': deepcopy(case.get('numerical_attempts', []))}


def scope_and_task_summary(records, policy, feedback):
    required = implemented_scope_case_ids(records, policy)
    required_set = set(required)
    outside = [key for key in records if key not in required_set]
    scope = {
        'meaning': 'Current verified capability boundary, not chronological urgency or a waiver of full-plan requirements.',
        'total_plan_cases': len(records),
        'implemented_scope_case_ids': required,
        'verification_extension_case_ids': outside,
        'implemented_scope_case_count': len(required),
        'verification_extension_case_count': len(outside),
        'unverified_extension_cases_are_not_passed_or_removed': True,
        'implemented_scope_success_does_not_mean_full_datasheet_success': True,
    }
    unresolved = []
    for item in feedback:
        assessment = item['case_assessment']
        if assessment['required_for_implemented_scope'] and item['status'] != PASS:
            unresolved.append({'case_id': item['case_id'], 'symbol': item['symbol'],
                               'category': assessment['category'],
                               'target_verdict_usable': assessment['target_verdict_usable'],
                               'reason': item.get('reason'), 'gate_issues': item['gate_issues'],
                               'next_action': assessment['next_action']})
    return scope, {'unresolved_required_cases': unresolved,
                   'unresolved_required_case_count': len(unresolved),
                   'verification_extension_case_ids': outside}
