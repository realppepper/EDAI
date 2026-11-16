import json
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

from opamp_pipeline import harness_06_evolution as h2
from opamp_pipeline import harness_03_loop as fixed
from opamp_pipeline.design_01_cmos_candidate import candidate
from opamp_pipeline.harness_01_fixed import load_harness
from opamp_pipeline.loop_02_handoff import write_json
from opamp_pipeline.support.execution_state import file_hash


def result(passed=False):
    case = {'case_id': 'g', 'fixture': {'supply_voltage_V': 5},
            'status': 'passed_sampled_model_case' if passed else 'failed_in_model',
            'tests': [{'metric': 'gbw', 'value': 1.3e6 if passed else 8e5,
                       'operator': '>=', 'limit': 1e6, 'unit': 'Hz', 'passed': passed}]}
    row = {'symbol': 'GBW', 'kind': 'gbw', 'target': {'rules': []}, 'cases': [case]}
    unknown = {'symbol': 'noise', 'kind': 'noise', 'target': {}, 'cases': [
        {'case_id': 'n', 'fixture': {}, 'status': 'unverified_adapter'}]}
    return {'source_rows_required': 2, 'source_cases_required': 2,
            'input_signatures': {}, 'rows': {'g': row, 'n': unknown},
            'case_status_counts': {case['status']: 1, 'unverified_adapter': 1}}


class HarnessEvolutionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name); self.session = self.root / 'evolution'
        self.model = self.root / 'candidate.inc'; self.model.write_text(candidate(), encoding='ascii')
        self.run_dir = self.root / 'run'; self.plan = self.run_dir / 'measurement_plan/plan_02_measurements.json'
        write_json(self.plan, {'measurements': []})
        self.base, _ = load_harness()
        self.request = {'request_id': 'request', 'baseline_design_request': {
            'evaluation_scope': {'implemented_scope_case_ids': ['g']}}}
        self.response = {'request_id': 'request', 'request_sha256': 'sha', 'proposals': [
            {'id': 'conditional', 'title': 'Check compensation tradeoffs', 'rules': [
                {'component_id': 'C3', 'when': 'Measured recovery fails with valid gates.',
                 'text': 'Evaluate compensation together with output resistance and stability.',
                 'evidence_case_ids': ['g'], 'expected_effect': 'Recovery may improve.',
                 'risks': 'Output resistance or phase margin may worsen.'}]}]}

    def start(self, passed=False):
        packet = {'evaluation_scope': {'implemented_scope_case_ids': ['g']}}
        with patch.object(h2, '_pipeline_evidence', return_value=(['core', 'imp', 'over'], result(passed))), \
                patch.object(h2, 'make_request', return_value=packet):
            return h2.start(self.session, self.root / 'pipeline', self.model, self.run_dir)

    def proposal(self, state):
        response = deepcopy(self.response)
        response['request_id'] = state['proposal_request']['request_id']
        response['request_sha256'] = state['proposal_request']['sha256']
        path = self.root / 'proposal.json'; write_json(path, response)
        return path

    def test_append_only_preserves_original_rules_and_enforced_fields(self):
        before = deepcopy(self.base)
        tree = h2.build_variants(self.base, self.response, self.request, 'sha')['conditional']
        self.assertEqual(self.base, before)
        self.assertEqual(tree['components'][2]['rules'][:-1], self.base['components'][2]['rules'])
        for key in ('mode', 'harness2_enabled', 'instruction_evolution_enabled',
                    'qualified_measurement_families', 'iteration_history'):
            self.assertEqual(tree[key], self.base[key])
        self.assertFalse(tree['harness2_enabled'])  # outer controller evolves, inner policy is fixed

    def test_guardrails_and_unrecognized_fields_cannot_be_edited(self):
        for component in ('C1', 'C2', 'C4', 'C7', 'C8'):
            response = deepcopy(self.response)
            response['proposals'][0]['rules'][0]['component_id'] = component
            with self.assertRaises(ValueError): h2.build_variants(self.base, response, self.request, 'sha')
        response = deepcopy(self.response); response['qualified_measurement_families'] = []
        with self.assertRaises(ValueError): h2.build_variants(self.base, response, self.request, 'sha')

    def test_proposal_binding_and_evidence_are_enforced(self):
        for key in ('request_id', 'request_sha256'):
            response = deepcopy(self.response); response[key] = 'different'
            with self.assertRaises(ValueError): h2.build_variants(self.base, response, self.request, 'sha')
        response = deepcopy(self.response)
        response['proposals'][0]['rules'][0]['evidence_case_ids'] = ['unknown']
        with self.assertRaises(ValueError): h2.build_variants(self.base, response, self.request, 'sha')

    def test_path_like_duplicate_control_and_excess_variants_are_rejected(self):
        for name in ('../escape', 'control', '/tmp/escape', ''):
            response = deepcopy(self.response); response['proposals'][0]['id'] = name
            with self.assertRaises(ValueError): h2.build_variants(self.base, response, self.request, 'sha')
        response = deepcopy(self.response); response['proposals'] *= 2
        with self.assertRaises(ValueError): h2.build_variants(self.base, response, self.request, 'sha')
        response['proposals'] *= 2
        with self.assertRaises(ValueError): h2.build_variants(self.base, response, self.request, 'sha')

    def test_proposal_text_is_bounded_and_risks_required(self):
        for text in ('', 'x' * 1601):
            response = deepcopy(self.response); response['proposals'][0]['rules'][0]['risks'] = text
            with self.assertRaises(ValueError): h2.build_variants(self.base, response, self.request, 'sha')

    def test_successful_baseline_does_not_launch_unnecessary_evolution(self):
        state = self.start(passed=True)
        self.assertEqual(state['status'], 'no_unmet_cases')
        self.assertFalse((self.session / 'PROPOSE_REQUEST.json').exists())
        self.assertEqual(state['branches'], {})

    def test_start_freezes_baseline_and_does_not_change_default(self):
        state = self.start(); request = json.loads((self.session / 'PROPOSE_REQUEST.json').read_text())
        self.assertEqual(state['status'], 'awaiting_harness_proposal')
        self.assertEqual(request['request_id'], state['proposal_request']['request_id'])
        self.assertEqual(Path(state['baseline_candidate']).read_bytes(), self.model.read_bytes())
        self.assertFalse(state['global_default_modified'])
        self.assertTrue(state['harness2_enabled'])
        self.assertEqual(h2.load(self.session)['plan_sha256'], file_hash(self.plan))
        write_json(self.plan, {'changed': True})
        with self.assertRaises(ValueError): h2.load(self.session)

    def test_probes_use_same_baseline_imports_and_one_revision_budget(self):
        state = self.start(); response = self.proposal(state)
        with patch.object(h2.fixed, 'start') as begin:
            out = h2.propose(self.session, response)
        self.assertEqual(set(out['branches']), {'control', 'conditional'})
        self.assertEqual(begin.call_count, 2)
        for call in begin.call_args_list:
            self.assertEqual(call.kwargs['max_candidates'], 2)
            self.assertEqual(call.kwargs['imports'], state['baseline_imports'])
            self.assertEqual(call.args[1], state['baseline_candidate'])
        self.assertEqual(out['status'], 'awaiting_probe_designs')

    def test_interrupted_probe_setup_is_idempotent_and_preserves_receipt(self):
        state = self.start(); response = self.proposal(state)
        with patch.object(h2.fixed, 'start', side_effect=OSError('interrupted')):
            with self.assertRaises(OSError): h2.propose(self.session, response)
        self.assertEqual(h2.load(self.session)['status'], 'preparing_probes')
        with patch.object(h2.fixed, 'start'):
            self.assertEqual(h2.propose(self.session, response)['status'], 'awaiting_probe_designs')

    def test_tied_control_keeps_baseline_instructions(self):
        failed = {'failed_case_ids': ['g'], 'eligible': True}
        self.assertFalse(h2.choose({'control': failed, 'variant': deepcopy(failed)})['adopted'])
        passed = {'failed_case_ids': [], 'eligible': True}
        self.assertFalse(h2.choose({'control': passed, 'variant': deepcopy(passed)})['adopted'])

    def test_whole_tested_variant_must_strictly_improve_control(self):
        control = {'failed_case_ids': ['a', 'b'], 'eligible': True}
        improve = {'failed_case_ids': ['a'], 'eligible': True}
        swap = {'failed_case_ids': ['c'], 'eligible': True}
        out = h2.choose({'control': control, 'good': improve, 'swapped_failure': swap})
        self.assertEqual(out['selected_branch'], 'good'); self.assertTrue(out['adopted'])
        self.assertFalse(out['composed_untested_policy'])

    def test_invalid_probe_and_invalid_control_cannot_support_adoption(self):
        control = {'failed_case_ids': ['a'], 'eligible': True}
        invalid = {'failed_case_ids': [], 'eligible': False}
        self.assertFalse(h2.choose({'control': control, 'bad': invalid})['adopted'])
        self.assertEqual(h2.choose({'control': invalid, 'good': control})['selected_branch'], 'baseline')

    def test_measured_regressed_control_does_not_veto_safe_superior_variant(self):
        control = {'failed_case_ids': ['new_miss'], 'eligible': False,
                   'unusable_case_ids': [], 'comparison_usable': True,
                   'regressions_from_baseline': ['new_miss']}
        variant = {'failed_case_ids': [], 'eligible': True}
        decision = h2.choose({'control': control, 'safe_variant': variant})
        self.assertTrue(decision['adopted'])
        self.assertEqual(decision['selected_branch'], 'safe_variant')
        self.assertTrue(decision['control_comparison_usable'])
        self.assertFalse(decision['control_retainable'])

    def test_old_outcome_with_explicit_validity_can_be_reassessed(self):
        control = {'failed_case_ids': ['new_miss'], 'eligible': False,
                   'unusable_case_ids': [], 'regressions_from_baseline': ['new_miss']}
        self.assertTrue(h2.choose({'control': control,
            'safe_variant': {'failed_case_ids': [], 'eligible': True}})['adopted'])

    def test_unmeasured_control_still_blocks_superiority_claim(self):
        control = {'failed_case_ids': ['missing'], 'eligible': False,
                   'unusable_case_ids': ['missing'], 'comparison_usable': False}
        decision = h2.choose({'control': control,
            'safe_variant': {'failed_case_ids': [], 'eligible': True}})
        self.assertFalse(decision['adopted'])
        self.assertFalse(decision['control_comparison_usable'])

    def test_regressed_control_is_never_retained_when_variant_does_not_dominate(self):
        control = {'failed_case_ids': ['new_miss'], 'eligible': False,
                   'unusable_case_ids': [], 'comparison_usable': True}
        decision = h2.choose({'control': control,
            'other': {'failed_case_ids': ['different_miss'], 'eligible': True}})
        self.assertEqual(decision['selected_branch'], 'baseline')

    def test_model_unknown_promotion_target_and_fixture_changes_rejected(self):
        base = result(); current = result(True)
        for edit in (lambda r:r['rows']['n']['cases'][0].update(status='passed_sampled_model_case'),
                     lambda r:r['rows']['g']['target'].update(changed=True),
                     lambda r:r['rows']['g']['cases'][0]['fixture'].update(supply_voltage_V=15)):
            data = deepcopy(current); edit(data)
            with self.assertRaises(ValueError): h2.outcome(base, data, ['g'])

    def test_measurement_error_and_prerequisite_failure_are_not_improvements(self):
        for status, gates in (('execution_error', []), ('failed_in_model', ['Not stationary'])):
            current = result(); current['rows']['g']['cases'][0].update(status=status, gate_issues=gates)
            self.assertFalse(h2.outcome(result(), current, ['g'])['eligible'])
        current = result(); self.assertTrue(h2.outcome(result(), current, ['g'])['eligible'])
        regressed = h2.outcome(result(True), current, ['g'])
        self.assertFalse(regressed['eligible'])
        self.assertTrue(regressed['comparison_usable'])

    def test_decision_requires_completed_actual_probe_not_best_baseline(self):
        state = self.start(); response = self.proposal(state)
        with patch.object(h2.fixed, 'start'): h2.propose(self.session, response)
        with patch.object(h2.fixed, 'load', return_value={'status': 'validation_interrupted', 'candidates': []}):
            with self.assertRaises(ValueError): h2.decide(self.session)

    def test_decision_and_rollback_keep_original_and_record_active_hashes(self):
        state = self.start(); response = self.proposal(state)
        with patch.object(h2.fixed, 'start'): state = h2.propose(self.session, response)
        records = {}
        for name, branch in state['branches'].items():
            folder = Path(branch['session']); folder.mkdir(parents=True, exist_ok=True)
            model = folder / 'candidate.inc'; model.write_text(candidate(), encoding='ascii')
            ledger = folder / 'LEDGER.json'; write_json(ledger, result(name != 'control'))
            records[name] = {'status': 'candidate_budget_exhausted', 'candidates': [{},
                {'candidate_path': str(model), 'ledger_path': str(ledger)}]}
        def inner(path): return records[Path(path).parent.name]
        def evidence(folder, model, plan): return [], read(Path(folder) / 'LEDGER.json')
        def read(path): return json.loads(Path(path).read_text(encoding='utf-8'))
        with patch.object(h2.fixed, 'load', side_effect=inner), patch.object(h2, '_pipeline_evidence', side_effect=evidence):
            decided = h2.decide(self.session)
        self.assertTrue(decided['decision']['adopted'])
        self.assertEqual(decided['decision']['selected_branch'], 'conditional')
        rolled = h2.rollback(self.session, 'Manual local-evidence review')
        self.assertEqual(rolled['status'], 'rolled_back')
        self.assertEqual(read(self.session / 'ACTIVE.json')['policy_path'], state['baseline_policy'])
        self.assertEqual(read(self.session / 'DECISION.json')['decision'], decided['decision'])
        self.assertEqual(len(rolled['rollback_events']), 1)
        h2.load(self.session)

    def test_existing_different_artifact_is_not_overwritten(self):
        path = self.root / 'saved'; h2._put(path, b'original'); h2._put(path, b'original')
        with self.assertRaises(ValueError): h2._put(path, b'different')
        self.assertEqual(path.read_bytes(), b'original')

    def test_real_file_handoffs_and_inner_controller_through_decision(self):
        """Only EDA chain/execution are replaced; real request/response controllers run."""
        base = result()
        write_json(self.plan, {'measurements': [
            {'row_id': key, 'symbol': row['symbol'], 'kind': row['kind'],
             'target': row['target'], 'source': {'source': {'pdf_page': 1}},
             'method': 'test fixture', 'resolved_conditions': {'values': {}},
             'cases': [{'case_id': c['case_id'], 'fixture': c['fixture']} for c in row['cases']]}
            for key, row in base['rows'].items()]})

        def evidence(folder, model, plan):
            path = Path(folder) / 'LEDGER.json'
            return ['core', 'imp', 'over'], h2.read(path) if path.exists() else deepcopy(base)

        def pipeline(model, run_dir, out, ltspice=None, **kwargs):
            passed = 'conditional' in str(out) and Path(out).parent.name == 'candidate_001'
            data = result(passed)
            data['input_signatures'] = {str(Path(model).resolve()): file_hash(model)}
            write_json(Path(out) / 'LEDGER.json', data)
            return {'execution_seconds': 0.0}

        with patch.object(h2, '_pipeline_evidence', side_effect=evidence), \
                patch.object(fixed, 'run_pipeline', side_effect=pipeline):
            state = h2.start(self.session, self.root / 'pipeline', self.model, self.run_dir)
            state = h2.propose(self.session, self.proposal(state))
            for name, branch in state['branches'].items():
                inner = fixed.load(branch['session'])
                req = h2.read(inner['pending_request']['path'])
                response = {'request_id': req['request_id'],
                    'netlist': req['candidate_netlist'] + '\n* probe design\n',
                    'summary': 'Injected backend controller test, not physical simulation.',
                    'changes': ['Probe comment; deterministic backend controls verdict.']}
                path = self.root / (name + '_response.json'); write_json(path, response)
                accepted = h2.submit(self.session, name, path, defer_validation=True)
                self.assertEqual(accepted['status'], 'validating_candidate')
                measured = h2.resume(self.session, name, 'injected-EDA')
                self.assertEqual(len(measured['candidates']), 2)
            state = h2.decide(self.session)
            self.assertTrue(state['decision']['adopted'])
            self.assertEqual(state['decision']['selected_branch'], 'conditional')
            active = h2.read(self.session / 'ACTIVE.json')
            self.assertEqual(active['policy_sha256'], file_hash(active['policy_path']))
            self.assertFalse(active['global_default_modified'])


if __name__ == '__main__': unittest.main()
