import cmath,json,math,tempfile,unittest
from pathlib import Path
from copy import deepcopy
from opamp_pipeline.tb_06_loop_gain import loop_margins,analytical_margin,read_complex_raw
from opamp_pipeline.loop_01_policy import make_policy,evaluate
from test_design_loop import context,experiment


class StabilityMethodTests(unittest.TestCase):
    def test_negative_margin_unwraps_instead_of_becoming_323_degrees(self):
        poles=[10,100000,100000];frequencies=[10**(-2+i*.01) for i in range(1001)]
        values=[]
        for f in frequencies:
            z=complex(1e5/1.01)
            for pole in poles:z/=1+1j*f/pole
            values.append(z)
        measured=loop_margins(frequencies,values);expected=analytical_margin(poles)
        self.assertTrue(measured['single_crossover_applicable'])
        self.assertLess(measured['phase_margin_deg'],0)
        self.assertAlmostEqual(measured['phase_margin_deg'],expected['phase_margin_deg'],delta=.01)

    def test_multiple_or_missing_crossings_are_not_single_pm_pass(self):
        for values in ([10,2,.5,2,.5],[10,5,4,3,2]):
            r=loop_margins([1,2,3,4,5],[complex(v) for v in values])
            self.assertFalse(r['single_crossover_applicable']);self.assertIsNone(r['phase_margin_deg'])

    def test_wrong_phase_sign_or_nonfinite_rejected(self):
        r=loop_margins([1,2,3],[complex(-10),complex(-2),complex(-.1)])
        self.assertFalse(r['single_crossover_applicable'])
        with self.assertRaises(ValueError):loop_margins([1,2,3],[1+0j,complex(float('nan')),1+0j])

    def test_complex_raw_missing_value_rejected(self):
        data='Flags: complex\nNo. Points: 2\nVariables:\n0 frequency frequency\n1 V(x) voltage\nValues:\n0 1,0\n2,-3\n1 2,0\n'
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/'test.raw';p.write_text(data,encoding='utf-8')
            with self.assertRaises(ValueError):read_complex_raw(p)

    def test_pm_cannot_use_old_unqualified_estimate(self):
        c=context();c['required_rows'].append({'symbol':'PM','row_id':'PM','target':{'origin':'test_typ','rules':[{'value':56,'operator':'>=','unit':'degree'}]},'cases':[{'fixture':{'supply_voltage_V':5}}]})
        policy=make_policy(c,include_pm=True);r=experiment()
        loop=next(b for b in r['benchmarks'] if b['name']=='opamp_loop')
        loop['metrics']['phase_margin_deg']=81
        self.assertFalse(evaluate(r,policy)['scope_passed'])
        r['pm_validation']={'qualified':True};self.assertTrue(evaluate(r,policy)['scope_passed'])
        loop['metrics']['phase_margin_deg']=-36
        assessed=evaluate(r,policy)
        self.assertFalse(assessed['scope_passed']);self.assertIn('PM',assessed['failed_keys'])
        self.assertEqual(next(x for x in assessed['checks'] if x['key']=='PM')['measured'],-36)
