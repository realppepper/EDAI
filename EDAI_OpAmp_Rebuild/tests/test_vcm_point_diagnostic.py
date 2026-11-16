import unittest
from opamp_pipeline.diag_04_vcm_points import point_deck, assess_point


SOURCE = '.include "old.inc"\n.temp 25\n.options reltol=1e-6\n.save V(out) V(inp)\nVDD vp 0 15\nVIN inp 0 0\nVFB out inn 0\n.dc VIN 0 13.5 0.0675\n.options solver=alt\n.nodeset V(xdut:bias)=.85\n.end\n'


class VCMPointDiagnosticTests(unittest.TestCase):
    def test_only_analysis_stimulus_and_observers_change(self):
        deck = point_deck(SOURCE, .0675, 'new.inc', 'original_startup_hint')
        self.assertIn('.op\n', deck)
        self.assertNotIn('.dc ', deck)
        for line in ('.temp 25', '.options reltol=1e-6', 'VDD vp 0 15', 'VFB out inn 0', '.nodeset V(xdut:bias)=.85'):
            self.assertIn(line, deck)
        self.assertNotIn('old.inc', deck)

    def test_normal_policy_removes_only_initial_hint_and_alternate_solver(self):
        deck = point_deck(SOURCE, 0, 'new.inc', 'normal_no_hint')
        self.assertNotIn('.nodeset', deck)
        self.assertNotIn('solver=alt', deck)
        self.assertIn('.options reltol=1e-6', deck)
        with self.assertRaises(ValueError):
            point_deck(SOURCE, 14, 'new.inc', 'normal_no_hint')

    def test_computed_wrong_output_is_not_a_numerical_failure_or_sweep_pass(self):
        raw = {'v(inp)': [0], 'v(out)': [.1], 'v(inn)': [.1], 'i(vdd)': [-.0001], 'v(xdut:bias)': [.85]}
        result = assess_point(raw, 0, .01)
        self.assertEqual(result['classification'], 'computed_tracking_outside_limit')
        self.assertFalse(result['full_sweep_qualified'])
        with self.assertRaises(ValueError):
            assess_point(raw, .1, .01)

    def test_nonfinite_or_incomplete_results_rejected(self):
        with self.assertRaises(ValueError):
            assess_point({'v(inp)': [0]}, 0, .01)
