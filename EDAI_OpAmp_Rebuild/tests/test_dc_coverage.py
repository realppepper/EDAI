import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, Mock, call

from opamp_pipeline.verify_04_dc_coverage import dc_sweep_coverage, require_complete_dc_sweep, require_complete_vcm_case, collect_vcm_with_numerical_fallback, IncompleteDCSweep, normal_vcm_recovery_deck
from opamp_pipeline.verify_02_metrics import measure


class DCCoverageTests(unittest.TestCase):
    def coverage(self, command, values):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'bench.cir'
            path.write_text(command + '\n.end\n', encoding='ascii')
            return dc_sweep_coverage(path, {command.split()[1].lower(): values})

    def test_complete_increasing_and_decreasing_sweeps(self):
        self.assertTrue(self.coverage('.dc VIN 0 .4 .1', [0, .1, .2, .3, .4])['complete'])
        self.assertTrue(self.coverage('.dc VIN .4 0 -.1', [.4, .3, .2, .1, 0])['complete'])

    def test_interior_missing_point_cannot_hide_between_correct_endpoints(self):
        result = self.coverage('.dc VIN 0 .4 .1', [0, .1, .3, .4])
        self.assertFalse(result['complete'])
        self.assertEqual(result['missing_count'], 1)
        self.assertAlmostEqual(result['missing_samples'][0], .2)

    def test_same_sample_count_with_duplicate_cannot_hide_a_missing_point(self):
        result = self.coverage('.dc VIN 0 .4 .1', [0, .1, .1, .3, .4])
        self.assertEqual(result['observed_points'], result['expected_points'])
        self.assertFalse(result['complete'])

    def test_extra_duplicate_endpoint_is_allowed_with_complete_grid(self):
        result = self.coverage('.dc VSW 35.9 36 .01', [35.9 + i*.01 for i in range(11)] + [36])
        self.assertTrue(result['complete'])
        self.assertEqual(result['duplicate_expected_points'], 1)

    def test_off_grid_and_reversed_traversal_rejected(self):
        self.assertFalse(self.coverage('.dc VIN 0 .2 .1', [0, .1, .15, .2])['complete'])
        self.assertFalse(self.coverage('.dc VIN 0 .2 .1', [0, .2, .1])['complete'])

    def test_tracking_measurement_cannot_pass_using_only_remaining_good_samples(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'bench.cir'
            path.write_text('.dc VIN 0 .4 .1\n.end\n', encoding='ascii')
            raw = {'vin': [0, .1, .3, .4], 'v(inp)': [0, .1, .3, .4], 'v(out)': [0, .1, .3, .4]}
            with patch('opamp_pipeline.verify_02_metrics.read_real_raw', return_value=raw):
                with self.assertRaises(IncompleteDCSweep) as error:
                    measure(path, 'vcm', {}, {'analysis': 'dc'}, {})
            self.assertEqual(error.exception.coverage['missing_count'], 1)

    def test_reject_missing_axis_and_unsupported_nested_contract(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'bench.cir'
            path.write_text('.dc VIN 0 1 .1\n.end\n', encoding='ascii')
            with self.assertRaises(ValueError):
                require_complete_dc_sweep(path, {'v(inp)': [0, 1]})
            path.write_text('.dc VIN 0 1 .1 VDD 3 5 1\n.end\n', encoding='ascii')
            with self.assertRaises(ValueError):
                require_complete_dc_sweep(path, {'vin': [0, 1]})

    def branches(self):
        fixture={'input_common_mode_sweep_V':{'min':0.,'max':3.5}}
        parts=[]
        for variant,stop,step in [('lower',0.,-.0175),('upper',3.5,.0175)]:
            coverage=self.coverage(f'.dc VIN 1.75 {stop} {step}',[1.75+i*step for i in range(101)])
            parts.append({'variant':variant,'metrics':{'dc_sweep_coverage':coverage,'initial_output_V':1.749}})
        return fixture,parts

    def test_two_complete_branches_cover_exact_original_201_points(self):
        fixture,parts=self.branches()
        result=require_complete_vcm_case(fixture,parts)
        self.assertEqual(result['unique_full_grid_points'],201)
        self.assertFalse(result['cold_startup_at_each_input_verified'])

    def test_only_one_half_cannot_be_treated_as_full_range(self):
        fixture,parts=self.branches()
        with self.assertRaises(ValueError):require_complete_vcm_case(fixture,parts[:1])

    def test_two_complete_halves_with_wrong_boundary_are_rejected(self):
        fixture,parts=self.branches()
        parts[0]['metrics']['dc_sweep_coverage']['stop']=.1
        with self.assertRaises(ValueError):require_complete_vcm_case(fixture,parts)

    def test_conflicting_midpoint_operating_solutions_are_rejected(self):
        fixture,parts=self.branches()
        parts[1]['metrics']['initial_output_V']=1.8
        with self.assertRaises(ValueError):require_complete_vcm_case(fixture,parts)

    def missing_error(self):
        return IncompleteDCSweep(self.coverage('.dc VIN 0 .2 .1',[0,.2]))

    def test_valid_measured_spec_miss_does_not_trigger_numerical_fallback(self):
        parts=[{'value':.03}]
        collect=Mock(return_value=parts)
        measured,attempts=collect_vcm_with_numerical_fallback(collect)
        self.assertEqual(measured,parts)
        self.assertEqual(collect.call_args_list,[call(('lower','upper'))])
        self.assertEqual(len(attempts),1)

    def test_incomplete_measurement_retries_full_original_grid_once(self):
        parts=[{'value':.001}]
        collect=Mock(side_effect=[self.missing_error(),parts])
        measured,attempts=collect_vcm_with_numerical_fallback(collect)
        self.assertEqual(measured,parts)
        self.assertEqual(collect.call_args_list,[call(('lower','upper')),call(('default',))])
        self.assertEqual(attempts[0]['coverage']['missing_count'],1)

    def test_solver_failure_retries_without_changing_spec(self):
        from opamp_pipeline.diag_03_solver_attempts import SolverAttemptsError
        collect=Mock(side_effect=[SolverAttemptsError([{'path':'bench','error':'timeout'}]),[{'value':.03}]])
        measured,attempts=collect_vcm_with_numerical_fallback(collect)
        self.assertEqual(measured[0]['value'],.03)
        self.assertEqual(len(attempts),2)

    def test_both_incomplete_strategies_raise_and_keep_attempt_history(self):
        collect=Mock(side_effect=[self.missing_error(),self.missing_error()])
        with self.assertRaises(IncompleteDCSweep) as error:collect_vcm_with_numerical_fallback(collect)
        self.assertEqual(len(error.exception.numerical_attempts),2)
        self.assertEqual(collect.call_count,2)

    def test_programming_error_is_not_hidden_by_an_alternative_strategy(self):
        collect=Mock(side_effect=KeyError('bad schema'))
        with self.assertRaises(KeyError):collect_vcm_with_numerical_fallback(collect)
        self.assertEqual(collect.call_count,1)

    def test_missing_points_enable_one_normal_recovery(self):
        collect=Mock(side_effect=[self.missing_error(),self.missing_error()])
        normal=Mock(return_value=[{'value':.003}])
        parts,attempts=collect_vcm_with_numerical_fallback(collect,normal)
        self.assertEqual(parts,[{'value':.003}])
        normal.assert_called_once_with()
        self.assertEqual(len(attempts),3)
        self.assertEqual(attempts[-1]['policy'],'full_ascending_normal_no_hint_once')
        self.assertEqual(attempts[1]['coverage']['missing_count'],1)

    def test_normal_failure_is_terminal_and_keeps_prior_coverage(self):
        collect=Mock(side_effect=[self.missing_error(),self.missing_error()])
        normal=Mock(side_effect=TimeoutError('Budget exhausted'))
        with self.assertRaises(TimeoutError) as error:
            collect_vcm_with_numerical_fallback(collect,normal)
        normal.assert_called_once_with()
        self.assertEqual(len(error.exception.numerical_attempts),3)
        self.assertEqual(error.exception.numerical_attempts[1]['coverage']['missing_count'],1)

    def test_normal_incomplete_result_cannot_trigger_another_attempt(self):
        collect=Mock(side_effect=[self.missing_error(),self.missing_error()])
        normal=Mock(side_effect=self.missing_error())
        with self.assertRaises(IncompleteDCSweep):collect_vcm_with_numerical_fallback(collect,normal)
        normal.assert_called_once_with()

    def test_normal_recovered_measurement_may_still_be_a_spec_miss(self):
        normal=Mock(return_value=[{'value':.03}])
        collect=Mock(side_effect=[self.missing_error(),self.missing_error()])
        parts,_=collect_vcm_with_numerical_fallback(collect,normal)
        self.assertGreater(parts[0]['value'],.01)
        # Conversely, a complete miss must not authorize a different numeric solve.
        collect=Mock(return_value=[{'value':.03}]);normal.reset_mock()
        parts,_=collect_vcm_with_numerical_fallback(collect,normal)
        normal.assert_not_called()

    def test_bad_axis_or_schema_does_not_authorize_normal_recovery(self):
        for failure in (KeyError('bad schema'),IncompleteDCSweep(self.coverage('.dc VIN 0 .2 .1',[0,.15,.2]))):
            collect=Mock(side_effect=[self.missing_error(),failure]);normal=Mock()
            with self.assertRaises(type(failure)):collect_vcm_with_numerical_fallback(collect,normal)
            normal.assert_not_called()

    def test_normal_deck_preserves_contract_and_tolerances(self):
        source='.include "dut.inc"\n.temp 25\n.options solver=alt reltol=1e-6 vntol=1e-10\nVDD vp 0 15\nRL out mid 10000\nVIN inp 0 0\nVFB out inn 0\n.dc VIN 0 13.5 .0675\n.nodeset V(xdut:bias)=.85\n.end\n'
        deck=normal_vcm_recovery_deck(source)
        self.assertNotIn('.nodeset',deck)
        self.assertNotIn('solver=alt',deck)
        self.assertEqual(deck.count('solver=norm'),1)
        self.assertTrue(deck.endswith('.end\n'))
        self.assertNotIn('\n.options \n',normal_vcm_recovery_deck(source.replace('solver=alt reltol=1e-6 vntol=1e-10','solver=alt')))
        for line in ('.include "dut.inc"','.temp 25','reltol=1e-6 vntol=1e-10','VDD vp 0 15','RL out mid 10000','VIN inp 0 0','VFB out inn 0','.dc VIN 0 13.5 .0675'):
            self.assertIn(line,deck)
        with self.assertRaises(ValueError):normal_vcm_recovery_deck(source.replace('.dc VIN 0 13.5 .0675','.dc VIN 0 13.5 .0675 VDD 5 15 5'))
