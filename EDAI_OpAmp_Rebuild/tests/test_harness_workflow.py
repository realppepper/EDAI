"""Real file handoffs/state machines with only the EDA backend injected."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from opamp_pipeline import harness_07_workflow as workflow
from opamp_pipeline import harness_03_loop as fixed
from opamp_pipeline import harness_06_evolution as evolution
from opamp_pipeline.design_01_cmos_candidate import candidate
from opamp_pipeline.loop_02_handoff import write_json


def result(passes):
    cases = [{'case_id': key, 'fixture': {'supply_voltage_V': voltage},
              'status': 'passed_sampled_model_case' if key in passes else 'failed_in_model',
              'tests': [{'metric': 'gbw', 'value': 2e6 if key in passes else 5e5,
                         'operator': '>=', 'limit': 1e6, 'unit': 'Hz', 'passed': key in passes}]}
             for key, voltage in [('a', 5), ('b', 15), ('c', 36)]]
    return {'source_rows_required': 2, 'source_cases_required': 4, 'input_signatures': {},
        'rows': {'g': {'symbol': 'GBW', 'kind': 'gbw', 'target': {}, 'cases': cases},
                 'n': {'symbol': 'noise', 'kind': 'noise', 'target': {}, 'cases': [
                     {'case_id': 'n', 'fixture': {}, 'status': 'unverified_adapter'}]}},
        'case_status_counts': {'passed_sampled_model_case': len(passes),
                              'failed_in_model': 3-len(passes), 'unverified_adapter': 1}}


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name); self.session = self.root / 'workflow'
        self.source = self.root / 'initial.inc'
        self.source.write_text(candidate() + '\n* sample:initial\n', encoding='ascii')
        self.run_dir = self.root / 'run'
        self.plan = self.run_dir / 'measurement_plan/plan_02_measurements.json'
        base = result({'a'})
        write_json(self.plan, {'measurements': [
            {'row_id': key, 'symbol': row['symbol'], 'kind': row['kind'],
             'target': row['target'], 'source': {'source': {'pdf_page': 1}},
             'method': 'synthetic controller fixture', 'resolved_conditions': {'values': {}},
             'cases': [{'case_id': c['case_id'], 'fixture': c['fixture']} for c in row['cases']]}
            for key, row in base['rows'].items()]})
        self.initial_passes = {'a'}; self.interrupt = False; self.unknown_pass = False
        self.calls = []
        self.evidence_patch = patch.object(evolution, '_pipeline_evidence', side_effect=self.evidence)
        self.backend_patch = patch.object(fixed, 'run_pipeline', side_effect=self.pipeline)
        self.evidence_patch.start(); self.backend_patch.start()
        self.addCleanup(self.evidence_patch.stop); self.addCleanup(self.backend_patch.stop)

    def evidence(self, folder, model, plan):
        path = Path(folder) / 'LEDGER.json'
        return ['core', 'impedance', 'overload'], workflow.read(path) if path.exists() else result(self.initial_passes)

    def pipeline(self, model, run_dir, out, ltspice=None, **kwargs):
        text = Path(model).read_text(encoding='ascii'); self.calls.append(str(out))
        if '* sample:partial' in text: passes = {'a','b'}
        elif '* sample:complete' in text: passes = {'a','b','c'}
        elif '* sample:regress' in text: passes = {'c'}
        else: passes = self.initial_passes
        if self.interrupt and Path(out).parent.name != 'candidate_000':
            raise OSError('Injected worker interruption')
        data = result(passes)
        if self.unknown_pass and Path(out).parent.name != 'candidate_000':
            data['rows']['n']['cases'][0]['status'] = 'passed_sampled_model_case'
        from opamp_pipeline.support.execution_state import file_hash
        data['input_signatures'] = {str(Path(model).resolve()): file_hash(model)}
        write_json(Path(out) / 'LEDGER.json', data)
        return {'execution_seconds': .01}

    def start(self, rounds=2, revisions=1):
        return workflow.start(self.session, self.root / 'baseline_pipeline', self.source,
                              self.run_dir, max_rounds=rounds, revisions_per_round=revisions)

    def proposal(self, add=True, path_name='proposal.json'):
        state = workflow.load(self.session); pending = state['pending_request']
        packet = workflow.read(pending['path'])
        proposals = [{'id': 'conditional_method', 'title': 'Conditional method', 'rules': [
            {'component_id':'C6', 'when':'The supplied constraints are unmet.',
             'text':'Use conditional estimates and revalidate all conditions.',
             'evidence_case_ids':['b'], 'expected_effect':'Hypothesized local progress.',
             'risks':'Other constraints can regress.'}]}] if add else []
        path = self.root / path_name
        write_json(path, {'request_id':packet['request_id'], 'request_sha256':pending['sha256'],
                          'reason':'Use a conditional method.' if add else 'Keep the tested instructions.',
                          'proposals':proposals})
        return path

    def design(self, label, name=None):
        s = workflow.load(self.session); request = workflow.read(s['pending_request']['path'])
        path = self.root / (name or (label + '.json'))
        # Marker-only circuits deliberately exercise controller transitions with
        # a deterministic injected measurement backend, not physical EDA claims.
        text = candidate() + '\n* sample:' + label + '\n'
        write_json(path, {'request_id':request['request_id'], 'netlist':text,
            'summary':'Synthetic backend state-machine test.', 'changes':['Test marker: '+label]})
        return path

    def test_two_rounds_carry_adopted_policy_and_circuit_then_stop_on_success(self):
        self.start(); s = workflow.propose(self.session, self.proposal())
        self.assertEqual(s['status'], 'awaiting_chat_designer')
        s = workflow.submit(self.session, self.design('partial'), 'injected')
        self.assertEqual(s['status'], 'awaiting_harness_proposal')
        self.assertTrue(s['rounds'][0]['decision']['policy_adopted'])
        adopted = s['active']; req = workflow.read(s['pending_request']['path'])
        self.assertEqual(req['baseline_design_request']['candidate_sha256'], adopted['candidate_sha256'])
        self.assertTrue(req['recent_rounds'][0]['policy_adopted'])
        self.assertEqual(req['execution_capabilities']['design_revisions_this_round'], 1)
        s = workflow.propose(self.session, self.proposal(False, 'keep.json'))
        inner_req = workflow.read(s['pending_request']['path'])
        self.assertIn('H2-conditional_method-1', inner_req['system_instructions'])
        self.assertEqual(inner_req['candidate_sha256'], adopted['candidate_sha256'])
        s = workflow.submit(self.session, self.design('complete'), 'injected')
        self.assertEqual(s['status'], 'implemented_scope_passed')
        self.assertEqual(len(s['rounds']), 2); self.assertIsNone(s['pending_request'])
        self.assertEqual(s['active']['policy_sha256'], adopted['policy_sha256'])
        self.assertFalse(s['matched_control_experiment'])
        self.assertEqual(workflow.read(self.session / 'BEST.json'), workflow.read(self.session / 'ACTIVE.json'))
        self.assertFalse((self.session / 'round_003').exists())

    def test_multiple_inner_revisions_keep_best_even_if_last_candidate_regresses(self):
        self.start(rounds=1, revisions=2); workflow.propose(self.session, self.proposal())
        s = workflow.submit(self.session, self.design('partial'), 'injected')
        self.assertEqual(s['status'], 'awaiting_chat_designer')
        request = workflow.read(s['pending_request']['path'])
        self.assertEqual(len(request['iteration_history']['transitions']), 1)
        s = workflow.submit(self.session, self.design('regress'), 'injected')
        self.assertEqual(s['status'], 'round_budget_exhausted')
        self.assertIn('* sample:partial', Path(s['active']['candidate_path']).read_text())
        self.assertTrue(s['rounds'][0]['decision']['policy_adopted'])
        self.assertEqual(len(s['rounds'][0]['decision']['trials']), 2)
        count = len(self.calls); workflow.resume(self.session)
        self.assertEqual(len(self.calls), count)

    def test_rejected_policy_and_regressed_circuit_do_not_leak_to_next_round(self):
        s = self.start(); initial = s['active'].copy()
        workflow.propose(self.session, self.proposal())
        s = workflow.submit(self.session, self.design('regress'), 'injected')
        self.assertEqual(s['active'], initial)
        self.assertFalse(s['rounds'][0]['decision']['policy_adopted'])
        r = workflow.read(s['pending_request']['path'])
        self.assertEqual(r['baseline_design_request']['candidate_netlist'],
                         Path(initial['candidate_path']).read_text(encoding='ascii'))
        self.assertNotIn('H2-conditional_method', r['baseline_design_request']['system_instructions'])
        self.assertFalse(r['recent_rounds'][0]['circuit_improved'])

    def test_deferred_validation_and_interruption_resume_same_candidate(self):
        self.start(rounds=1); workflow.propose(self.session, self.proposal(False))
        path = self.design('partial'); calls = len(self.calls)
        s = workflow.submit(self.session, path, defer_validation=True)
        self.assertEqual(s['status'], 'validating_candidate'); self.assertEqual(len(self.calls), calls)
        self.interrupt = True; s = workflow.resume(self.session, 'injected')
        self.assertEqual(s['status'], 'validation_interrupted')
        self.assertEqual(len(s['accepted_design_sha256']), 1)
        inner = fixed.load(s['rounds'][0]['inner_session']); sha = inner['pending_candidate']['candidate_sha256']
        self.interrupt = False; s = workflow.resume(self.session, 'injected')
        self.assertEqual(s['status'], 'round_budget_exhausted')
        self.assertEqual(s['active']['candidate_sha256'], sha)
        self.assertEqual(len(s['accepted_design_sha256']), 1)

    def test_duplicate_responses_do_not_add_rounds_or_validation(self):
        self.start(); p = self.proposal(); workflow.propose(self.session, p)
        calls = len(self.calls); workflow.propose(self.session, p)
        self.assertEqual(len(self.calls), calls)
        response = self.design('partial'); workflow.submit(self.session, response, 'injected')
        calls = len(self.calls); s = workflow.submit(self.session, response, 'injected')
        self.assertEqual(len(self.calls), calls); self.assertEqual(len(s['rounds']), 1)
        workflow.propose(self.session, p)
        self.assertEqual(len(workflow.load(self.session)['rounds']), 1)

    def test_completed_resume_rebuilds_views_without_new_work(self):
        self.initial_passes = {'a','b','c'}; s = self.start()
        self.assertEqual(s['status'], 'implemented_scope_passed'); self.assertEqual(s['rounds'], [])
        for name in ('ACTIVE.json', 'BEST.json', 'NEXT_ACTION.json', 'REPORT.md'):
            (self.session / name).unlink()
        workflow.resume(self.session)
        self.assertTrue((self.session / 'BEST.json').is_file()); self.assertFalse(self.calls)

    def test_windows_source_bytes_are_preserved_while_request_uses_normalized_text(self):
        import hashlib
        source = (candidate() + '\n* sample:initial\n').replace('\n', '\r\n').encode('ascii')
        self.source.write_bytes(source); s = self.start()
        self.assertEqual(Path(s['active']['candidate_path']).read_bytes(), source)
        request = workflow.read(s['pending_request']['path'])['baseline_design_request']
        self.assertNotIn('\r', request['candidate_netlist'])
        self.assertEqual(request['candidate_sha256'], hashlib.sha256(
            request['candidate_netlist'].encode('ascii')).hexdigest())

    def test_invalid_proposal_budget_stops_and_preserves_best(self):
        initial = self.start()['active']; path = self.proposal()
        response = workflow.read(path); response['request_sha256'] = 'wrong'; write_json(path, response)
        for _ in range(3):
            with self.assertRaises(ValueError): workflow.propose(self.session, path)
        s = workflow.load(self.session)
        self.assertEqual(s['status'], 'invalid_proposal_budget_exhausted')
        self.assertEqual(s['active'], initial); self.assertEqual(s['rounds'], [])

    def test_unknown_promotion_is_not_a_workflow_success(self):
        initial = self.start(rounds=1)['active']; workflow.propose(self.session, self.proposal(False))
        self.unknown_pass = True
        s = workflow.submit(self.session, self.design('complete'), 'injected')
        self.assertEqual(s['status'], 'validation_interrupted'); self.assertEqual(s['active'], initial)

    def test_policy_tampering_and_invalid_budgets_are_rejected(self):
        for value in (0, -1, True, 21):
            with self.assertRaises(ValueError): self.start(rounds=value)
        s = self.start(); Path(s['active']['policy_path']).write_text('{}')
        with self.assertRaises(ValueError): workflow.load(self.session)


if __name__ == '__main__': unittest.main()
