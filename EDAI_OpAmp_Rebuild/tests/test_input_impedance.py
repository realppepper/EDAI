import math,unittest
from copy import deepcopy
from run_input_impedance_extension import seed_for_supply,measure_dut_pair,failed_measurement_case
import subprocess
from opamp_pipeline.verify_04_input_impedance import modal_admittance,parallel_fit


def passive_ports(frequencies,reverse=False):
    d={'frequency':[complex(f) for f in frequencies],'v(inp)':[],'v(inn)':[],'i(bp)':[],'i(bn)':[]}
    c={k:list(v) if k=='frequency' else [] for k,v in d.items()}
    for f in frequencies:
        yd=1e-7+2j*math.pi*f*.1e-12;yg=1/4e9+2j*math.pi*f*1.5e-12
        for raw,p,n in [(d,.5,-.5),(c,1,1)]:
            ip=yd*(p-n)+yg*p;inn=yd*(n-p)+yg*n;sign=1 if reverse else -1
            raw['v(inp)'].append(complex(p));raw['v(inn)'].append(complex(n));raw['i(bp)'].append(sign*ip);raw['i(bn)'].append(sign*inn)
    return d,c


class InputImpedanceTests(unittest.TestCase):
    def test_dut_timeout_is_explicit_without_changing_fixture_or_hiding_next_case(self):
        fixture={'supply_voltage_V':5,'input_common_mode_V':2.5}
        def failed(*args):raise subprocess.TimeoutExpired(['simulator'],45)
        m=measure_dut_pair(failed,'dut_5','candidate.inc',fixture,None)
        c={'case_id':'ZID-5','fixture':fixture};record=failed_measurement_case(c,m)
        self.assertEqual(record['status'],'execution_error')
        self.assertEqual(record['case_id'],c['case_id']);self.assertEqual(record['fixture'],fixture)
        self.assertFalse(record['measurement_executed']);self.assertEqual(record['tests'],[])
        success=measure_dut_pair(lambda *args:{'known':'measurement'},'dut_9','candidate.inc',{'supply_voltage_V':9},None)
        self.assertEqual(success['measured'],{'known':'measurement'})

    def test_missing_startup_seed_uses_fixture_op_without_erasing_failure(self):
        baseline={'startup_seeds':{'15':{'seeds':{'node':1.2}}},
                  'startup_seed_failures':{'5':{'error':'did not settle'}}}
        before=deepcopy(baseline)
        self.assertIsNone(seed_for_supply(baseline,5))
        self.assertIsNone(seed_for_supply({},36))
        self.assertEqual(seed_for_supply(baseline,15),{'node':1.2})
        self.assertEqual(baseline,before)
        with self.assertRaises(KeyError):
            seed_for_supply({'startup_seeds':{'5':{}}},5)

    def test_removes_common_mode_loading_from_differential_bridge(self):
        f=[1,10,100,1000,1e6];data=modal_admittance(*passive_ports(f))
        d=parallel_fit(f,data['differential_branch_Y']);c=parallel_fit(f,data['common_per_pin_Y'])
        self.assertAlmostEqual(d['resistance_Ohm']/1e7,1)
        self.assertAlmostEqual(d['capacitance_F']/.1e-12,1)
        self.assertAlmostEqual(c['resistance_Ohm']/4e9,1)
        self.assertAlmostEqual(c['capacitance_F']/1.5e-12,1)
        self.assertLess(max(data['cross_coupling_ratio']),1e-12)

    def test_reversed_current_cannot_be_certified_as_positive_rc(self):
        f=[1,10,1e6];data=modal_admittance(*passive_ports(f,True));fit=parallel_fit(f,data['differential_branch_Y'])
        self.assertTrue(fit['fit_issues']);self.assertIsNone(fit['resistance_Ohm'])

    def test_zero_leakage_does_not_create_infinite_resistance_pass(self):
        f=[1,10,100];fit=parallel_fit(f,[2j*math.pi*x*1e-12 for x in f])
        self.assertIsNone(fit['resistance_Ohm']);self.assertEqual(fit['fit_issues'],[])

    def test_unequal_common_mode_pins_are_not_hidden_by_averaging(self):
        f=[1,10,1e6];d,c=passive_ports(f)
        for raw in (d,c):
            for i,hz in enumerate(f):
                p,n=raw['v(inp)'][i],raw['v(inn)'][i];yd=1e-7+2j*math.pi*hz*.1e-12
                yp=1/4e9+2j*math.pi*hz*1e-12;yn=1/4e9+2j*math.pi*hz*3e-12
                raw['i(bp)'][i]=-(yd*(p-n)+yp*p);raw['i(bn)'][i]=-(yd*(n-p)+yn*n)
        data=modal_admittance(d,c)
        p=parallel_fit(f,data['common_pin_p_Y']);n=parallel_fit(f,data['common_pin_n_Y'])
        self.assertAlmostEqual(p['capacitance_F']/1e-12,1)
        self.assertAlmostEqual(n['capacitance_F']/1e-12,3)

    def test_mismatched_or_singular_excitation_is_rejected(self):
        d,c=passive_ports([1,10,100]);c['frequency'][-1]=101
        with self.assertRaises(ValueError):modal_admittance(d,c)
        d,c=passive_ports([1,10,100]);c['v(inp)']=[0j]*3;c['v(inn)']=[0j]*3
        with self.assertRaises(ValueError):modal_admittance(d,c)

    def test_frequency_dependent_network_cannot_be_a_constant_rc(self):
        f=[1,10,1000];fit=parallel_fit(f,[1e-7+2j*math.pi*x*(1e-12 if x<100 else 3e-12) for x in f])
        self.assertTrue(fit['fit_issues']);self.assertIsNone(fit['resistance_Ohm'])
