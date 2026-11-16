import unittest
from copy import deepcopy
from opamp_pipeline.harness_04_feedback import describe_case, implemented_scope_case_ids, scope_and_task_summary
from opamp_pipeline.harness_01_fixed import load_harness


def record(status='unverified_adapter', **extra):
    return {'kind': 'overload_recovery', 'symbol': 'tOR',
            'case': {'status': status, **extra}}


class FeedbackContractTests(unittest.TestCase):
    def test_part_gate_and_evidence_preserved_without_promoting_numbers(self):
        source = record(parts=[{'direction': 'high', 'value': 24e-6,
            'gate_issues': ['Not stationary'], 'overload_evidence': {'span': 2.16},
            'qualification_checks': [{'value': 2.16, 'limit': .72, 'passed': False}]}])
        before = deepcopy(source)
        result = describe_case(source, True)
        self.assertEqual(result['gate_issues'], ['Not stationary'])
        self.assertEqual(result['part_diagnostics'][0]['qualification_checks'],
                         source['case']['parts'][0]['qualification_checks'])
        self.assertFalse(result['case_assessment']['target_verdict_usable'])
        self.assertTrue(result['case_assessment']['required_for_implemented_scope'])
        self.assertEqual(source, before)

    def test_scope_is_registry_not_current_status(self):
        records = {'gate': record(gate_issues=['Gate']),
                   'model': record('unverified_model'),
                   'extension': {'kind': 'future_adapter', 'symbol': 'other',
                                 'case': {'status': 'unverified_adapter'}}}
        policy = {'qualified_measurement_families': ['overload_recovery']}
        self.assertEqual(implemented_scope_case_ids(records, policy), ['gate', 'model'])
        feedback = [{'case_id': k, 'symbol': r['symbol'], 'status': r['case']['status'],
                     **describe_case(r, k != 'extension')} for k, r in records.items()]
        scope, tasks = scope_and_task_summary(records, policy, feedback)
        self.assertEqual(scope['verification_extension_case_ids'], ['extension'])
        self.assertEqual(tasks['unresolved_required_case_count'], 2)
        self.assertTrue(feedback[2]['case_assessment']['retained_in_full_plan'])

    def test_execution_error_retains_coverage_and_attempts(self):
        source = record('execution_error', measurement_coverage={'actual': 193, 'expected': 201},
                        numerical_attempts=[{'attempt': 1, 'error': 'Incomplete'}])
        result = describe_case(source, True)
        self.assertEqual(result['measurement_coverage'], source['case']['measurement_coverage'])
        self.assertEqual(result['numerical_attempts'], source['case']['numerical_attempts'])
        self.assertEqual(result['case_assessment']['category'], 'measurement_execution_error')
        self.assertFalse(result['case_assessment']['physical_failure_cause_confirmed'])

    def test_model_limitation_is_host_review_even_inside_registry(self):
        result = describe_case(record('unverified_model'), True)
        self.assertEqual(result['case_assessment']['category'], 'model_scope_review_needed')
        self.assertTrue(result['case_assessment']['required_for_implemented_scope'])

    def test_only_qualified_verdicts_are_acceptance_evidence(self):
        for status in ('passed_sampled_model_case', 'failed_in_model'):
            self.assertTrue(describe_case(record(status), True)['case_assessment']['target_verdict_usable'])
        for status in ('unverified_adapter', 'execution_error', 'unverified_model'):
            self.assertFalse(describe_case(record(status), True)['case_assessment']['target_verdict_usable'])

    def test_inconsistent_pass_is_rejected(self):
        with self.assertRaises(ValueError):
            describe_case(record('passed_sampled_model_case', parts=[{'gate_issues': ['Gate']}]), True)
        with self.assertRaises(ValueError):
            describe_case(record('passed_sampled_model_case'), False)

    def test_policy_version_clarifies_scope_without_enabling_evolution(self):
        policy, _ = load_harness()
        self.assertEqual(policy['id'], 'opamp_fixed_v3_history')
        self.assertFalse(policy['harness2_enabled'])
        self.assertFalse(policy['external_designer_api_enabled'])
