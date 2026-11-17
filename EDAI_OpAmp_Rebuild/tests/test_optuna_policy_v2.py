"""Regression tests for startup repair, bounded whole-scope selection and ties."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from opamp_pipeline.optuna_06_startup import observe, startup_feedback, repair_evidence
from opamp_pipeline.optuna_05_acceptance import ranked_candidates, full_assessment, validate_shortlist
from opamp_pipeline.optuna_04_designer import proposal_contract, validate_proposal
from opamp_pipeline.optuna_03_loop_bridge import routing_reason
from opamp_pipeline.optuna_02_screening import screen_candidate
from opamp_pipeline import harness_03_loop as fixed
from opamp_pipeline.diag_02_startup_seed import startup_deck
from opamp_pipeline.support.execution_state import file_hash
from test_optuna_loop_bridge import example
import test_optuna_designer_proposal as designer_tests
TEXT = designer_tests.TEXT


def waveform(bias=.8):
    return {'time': [0, 80e-6, 90e-6, 100e-6], 'v(xdut:bias)': [0, bias, bias, bias],
            'v(out)': [0, 2.5, 2.5, 2.5]}


def candidate(n, power=20., margin=.1, feasible=True):
    return {'number': n, 'status': 'screened', 'feasible_for_screening': feasible,
            'objective_power_mW': power, 'screening_margin': margin, 'total_normalized_violation': .3}


class OptunaPolicyV2Tests(unittest.TestCase):
    def test_complete_inactive_startup_is_numeric_failure_not_execution_error(self):
        case, _ = observe(waveform(.5), 5, ['BIAS'])
        self.assertFalse(case['passed'])
        self.assertGreater(startup_feedback([case])['total_normalized_violation'], 0)

    def test_screen_covers_supplies_outside_partial_screen_and_never_seeds_failed_startup(self):
        with tempfile.TemporaryDirectory() as temp:
            model = Path(temp)/'candidate.inc'; model.write_text(TEXT)
            path = Path(temp)/'bench.cir'; path.write_text('placeholder')
            plan = {'measurements':[
                {'method':{'kind':'iq'},'cases':[{'fixture':{'supply_voltage_V':5}}]},
                {'method':{'kind':'overload_recovery'},'cases':[{'fixture':{'supply_voltage_V':3}}]}]}
            def observation(raw, supply, nodes):
                raw = waveform(.5 if supply == 3 else .8)
                raw['v(out)'] = [0,supply/2,supply/2,supply/2]
                return observe(raw,supply,['BIAS'])
            with patch('opamp_pipeline.optuna_02_screening.NativeExecutor') as executor, \
                 patch('opamp_pipeline.optuna_02_screening.validate_execution'), \
                 patch('opamp_pipeline.optuna_02_screening.read_real_raw'), \
                 patch('opamp_pipeline.optuna_02_screening.observe',side_effect=observation), \
                 patch('opamp_pipeline.optuna_02_screening.measure') as measure:
                executor.return_value.return_value = {'path':path}
                result = screen_candidate(model,plan,['iq'],Path(temp)/'screen','ltspice')
            self.assertEqual([c['supply_V'] for c in result['startup']],[3,5])
            self.assertEqual(result['status'],'startup_failed')
            self.assertIsNone(result['objective_power_mW']); measure.assert_not_called()

    def test_bias_boundary_is_strict(self):
        self.assertFalse(observe(waveform(.65), 5, ['BIAS'])[0]['passed'])
        self.assertTrue(observe(waveform(.650001), 5, ['BIAS'])[0]['passed'])

    def test_incomplete_nonfinite_or_nonphysical_axis_never_gets_violation_score(self):
        for change in (lambda r: r['time'].__setitem__(-1, 90e-6),
                       lambda r: r['v(out)'].__setitem__(2, float('nan')),
                       lambda r: r['time'].__setitem__(0, 10e-6),
                       lambda r: r['v(out)'].pop()):
            raw = waveform(); change(raw)
            with self.assertRaises(ValueError): observe(raw, 5, ['BIAS'])

    def test_outside_screen_measured_failure_is_eligible_but_missing_data_is_not(self):
        state, current, doc = example(); doc['rows']['r']['kind'] = 'overload_recovery'
        self.assertEqual(routing_reason(state, current, doc), 'numeric_repair_eligible')
        doc['rows']['r']['cases'][0]['tests'][0]['value'] = None
        self.assertEqual(routing_reason(state, current, doc), 'missing_numeric_feedback')

    def test_startup_evidence_requires_current_dut_and_physical_deck(self):
        with tempfile.TemporaryDirectory() as temp:
            model = Path(temp)/'candidate.inc'; model.write_text(TEXT)
            deck = Path(temp)/'start.cir'; deck.write_text(startup_deck(model, 5), encoding='ascii')
            startup = {'passed': False, 'required': True, 'supplies_V': [5],
                       'cases': [{'supply_V': 5, 'passed': False, 'artifact_paths': [str(deck)]}]}
            with patch('opamp_pipeline.optuna_06_startup.read_real_raw', return_value=waveform(.5)), \
                 patch('opamp_pipeline.optuna_06_startup.internal_nodes', return_value=['BIAS']):
                self.assertTrue(repair_evidence(startup, model, file_hash(model)))
                self.assertFalse(repair_evidence(startup, model, 'wrong'))
                deck.write_text(deck.read_text()+'.ic V(out)=2.5\n')
                self.assertFalse(repair_evidence(startup, model, file_hash(model)))

    def test_real_advance_offers_startup_sizing(self):
        state, current, doc = example(); doc['operational_startup']['passed'] = False
        with patch('opamp_pipeline.optuna_06_startup.repair_evidence', return_value=True), \
             patch.object(fixed, 'read', return_value=doc), patch.object(fixed, 'save'), \
             patch('opamp_pipeline.optuna_03_loop_bridge.execute') as optimize:
            fixed.advance(Path('.'), state, 'ltspice')
            optimize.assert_called_once()

    def test_startup_proposal_has_bound_operational_evidence(self):
        policy, request, response = designer_tests.DesignerSizingTests().inputs()
        request['numeric_sizing_proposal']['routing_reason'] = 'startup_repair_eligible'
        request['operational_startup'] = {'passed': False}
        response['sizing_proposal']['evidence_case_ids'] = ['OPERATIONAL-STARTUP']
        validate_proposal(request, response, TEXT, policy, 'request_hash')
        request['numeric_sizing_proposal']['routing_reason'] = 'numeric_repair_eligible'
        with self.assertRaises(ValueError): validate_proposal(request, response, TEXT, policy, 'request_hash')

    def test_power_noise_does_not_override_performance_headroom(self):
        rows = [candidate(1,20,.3), candidate(4,20-1e-12,.01)]
        self.assertEqual(ranked_candidates(rows)[0]['number'], 1)
        rows[1]['objective_power_mW'] = 19
        self.assertEqual(ranked_candidates(rows)[0]['number'], 4)

    def test_stable_tie_and_invalid_measurements_excluded(self):
        rows = [candidate(2), candidate(1), {'number': 0, 'status': 'execution_error'},
                {'number': 3, 'status': 'startup_failed'}]
        self.assertEqual([r['number'] for r in ranked_candidates(rows)], [1,2])

    def test_partial_screen_failure_falls_through_to_full_pass(self):
        called = []
        def verify(record, rank):
            called.append(record['number']); good = record['number'] == 2
            return {'number': record['number'], 'rank': rank,
                    'assessment': {'scope_passed': good, 'failed_requirement_ids': [] if good else ['TOR36']}}
        selected, attempts = validate_shortlist([candidate(1),candidate(2),candidate(3)], 3, verify)
        self.assertEqual(called,[1,2]); self.assertEqual(selected['number'],2)
        self.assertTrue(selected['assessment']['scope_passed'])

    def test_shortlist_budget_does_not_invent_success(self):
        def verify(record, rank):
            return {'number': record['number'], 'rank': rank,
                    'assessment': {'scope_passed':False, 'failed_requirement_ids':['TOR36']}}
        selected, attempts = validate_shortlist([candidate(1),candidate(2)],1,verify)
        self.assertEqual(len(attempts),1); self.assertFalse(selected['assessment']['scope_passed'])

    def test_incomplete_full_measurement_is_not_selected_as_numeric_progress(self):
        def verify(record,rank):
            return {'number':record['number'],'rank':rank,'assessment':{
                'scope_passed':False,'failed_requirement_ids':['missing'], 'measurement_integrity_passed':False}}
        selected, attempts = validate_shortlist([candidate(1)],1,verify)
        self.assertIsNone(selected); self.assertEqual(len(attempts),1)

    def test_full_scope_keeps_structural_unknowns_and_requires_startup(self):
        _, _, doc = example(); doc['rows']['r']['cases'][0]['status'] = 'passed_sampled_model_case'
        doc['source_cases_required'] = 2
        unknown = deepcopy(doc['rows']['r']); unknown['kind'] = 'channel_separation'
        unknown['cases'][0].update(case_id='separation',status='unverified_adapter')
        doc['rows']['unknown'] = unknown
        doc['operational_startup'] = {'required':True,'passed':True,'policy':{},'supplies_V':[5],
                                      'cases':[{'supply_V':5,'passed':True}]}
        policy = {'qualified_measurement_families':['gbw']}
        self.assertTrue(full_assessment(doc,policy)['scope_passed'])
        doc['operational_startup']['cases'][0]['passed'] = False
        self.assertFalse(full_assessment(doc,policy)['scope_passed'])
        del doc['operational_startup']
        with self.assertRaises(ValueError): full_assessment(doc,policy)


if __name__ == '__main__': unittest.main()
