import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from opamp_pipeline.harness_03_loop import submit, execute_pending
from opamp_pipeline.loop_02_handoff import write_json
from opamp_pipeline.support.execution_state import file_hash


class FixedLoopResumeTests(unittest.TestCase):
    def test_deferred_submit_persists_pending_design_without_running_simulator(self):
        with tempfile.TemporaryDirectory() as directory:
            session = Path(directory)
            request = session / 'REQUEST.json'
            response = session / 'response.json'
            write_json(request, {'request_id': 'bound-request'})
            write_json(response, {'request_id': 'bound-request', 'netlist': 'accepted DUT'})
            state = {'status': 'awaiting_chat_designer', 'best_index': 0,
                     'harness_sha256': 'fixed', 'candidates': [
                         {'index': 0, 'candidate_path': 'baseline', 'assessment': {
                             'scope_passed': False, 'failed_case_ids': ['case'], 'counts': {}}}],
                     'pending_request': {'path': str(request), 'sha256': file_hash(request)}}
            with patch('opamp_pipeline.harness_03_loop.load', return_value=state), \
                    patch('opamp_pipeline.harness_03_loop.validate_response'), \
                    patch('opamp_pipeline.harness_03_loop.execute_pending') as run:
                result = submit(session, response, None, defer_validation=True)
            run.assert_not_called()
            self.assertEqual(result['status'], 'validating_candidate')
            self.assertEqual(len(result['candidates']), 1)
            self.assertEqual(Path(result['pending_candidate']['candidate_path']).read_text(), 'accepted DUT')
            self.assertTrue((session / 'STATE.json').is_file())
            self.assertEqual(result['best_index'], 0)

    def test_worker_failure_retains_best_and_same_pending_candidate(self):
        with tempfile.TemporaryDirectory() as directory:
            session = Path(directory)
            model = session / 'candidate.inc'
            response = session / 'response.json'
            plan = session / 'plan.json'
            result = session / 'baseline.json'
            model.write_text('accepted DUT')
            for path in (response, plan, result):
                write_json(path, {})
            baseline = {'index': 0, 'candidate_path': str(model), 'ledger_path': str(result),
                        'assessment': {'score': [0, 1], 'scope_passed': False,
                                       'failed_case_ids': ['case'], 'counts': {}}}
            state = {'candidates': [baseline], 'best_index': 0, 'max_candidates': 3,
                     'harness_sha256': 'fixed', 'harness_path': 'fixed',
                     'plan_path': str(plan), 'run_dir': 'unused', 'scope_case_ids': ['case'],
                     'pending_candidate': {'index': 1, 'candidate_path': str(model),
                         'candidate_sha256': file_hash(model), 'response_path': str(response),
                         'response_sha256': file_hash(response)}}
            with patch('opamp_pipeline.harness_03_loop.run_pipeline', side_effect=OSError('injected solver unavailable')), \
                    patch('opamp_pipeline.harness_03_loop.make_request') as request:
                execute_pending(session, state, 'unused',automatic_retries=0)
            self.assertEqual(state['best_index'], 0)
            self.assertEqual(state['status'], 'validation_interrupted')
            self.assertIsNotNone(state['pending_candidate'])
            self.assertEqual(len(state['candidates']),1)
            self.assertIn('injected solver unavailable',state['pending_candidate']['validation_attempts'][0]['error'])
            request.assert_not_called()
