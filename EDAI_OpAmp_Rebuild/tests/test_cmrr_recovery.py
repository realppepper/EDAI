import unittest
from opamp_pipeline.verify_04_dc_coverage import collect_cmrr_with_numerical_fallback,normal_vcm_recovery_deck,IncompleteDCSweep


class CMRRRecoveryTests(unittest.TestCase):
    def test_missing_endpoint_retries_full_grid_once(self):
        calls=[]
        def collect(normal):
            calls.append(normal)
            if not normal:raise IncompleteDCSweep({'unique_expected_points_observed':200,'expected_points':201,'missing_samples':[0.0],'missing_count':1,'unexpected_count':0,'direction_errors':0})
            return ['fully measured']
        parts,attempts=collect_cmrr_with_numerical_fallback(collect)
        self.assertEqual(calls,[False,True]);self.assertEqual(parts,['fully measured'])
        self.assertEqual(attempts[-1]['status'],'computed')

    def test_valid_miss_and_bad_grid_not_retried(self):
        calls=[]
        parts,_=collect_cmrr_with_numerical_fallback(lambda n:calls.append(n) or [{'passed':False}])
        self.assertEqual(calls,[False]);self.assertFalse(parts[0]['passed'])
        def bad(n):raise IncompleteDCSweep({'unique_expected_points_observed':200,'expected_points':201,'missing_samples':[0.0],'missing_count':1,'unexpected_count':1,'direction_errors':0})
        with self.assertRaises(IncompleteDCSweep):collect_cmrr_with_numerical_fallback(bad)

    def test_recovery_preserves_sweep_and_tolerances(self):
        deck='* test\n.options reltol=1e-6 solver=alt\n.nodeset V(x)=1\n.dc VCM 0 1 0.005\n.end\n'
        out=normal_vcm_recovery_deck(deck,'VCM')
        self.assertIn('.dc VCM 0 1 0.005',out);self.assertIn('reltol=1e-6',out)
        self.assertIn('solver=norm',out);self.assertNotIn('.nodeset',out)
        with self.assertRaises(ValueError):normal_vcm_recovery_deck(deck)
