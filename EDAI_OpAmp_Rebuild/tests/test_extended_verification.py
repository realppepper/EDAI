import math,unittest
from opamp_pipeline.verify_02_metrics import coefficient,slew_metrics
from run_extended_verification import case_verdict


class ExtendedVerificationTests(unittest.TestCase):
    def test_duplicate_endpoint_can_be_skipped_only_if_same_solution(self):
        values=coefficient([35.9,36,36],[.0026,.0026044,.0026044002])
        self.assertAlmostEqual(values[0],44e-6)
        self.assertEqual(len(values),1)
        with self.assertRaises(ValueError):coefficient([35.9,36,36],[.0026,.0026044,.003])

    def test_rejection_coefficient_is_volts_per_volt_not_db(self):
        slopes=coefficient([0,1,2],[.001,.00102,.00104])
        self.assertAlmostEqual(max(slopes),20e-6)

    def test_slew_from_known_exponential_and_no_crossing(self):
        t=[i*.005 for i in range(1001)];y=[2*(1-math.exp(-x)) for x in t]
        step={'initial_V':0,'final_V':2,'start_s':0}
        result=slew_metrics(t,y,step)
        self.assertTrue(result['valid'])
        self.assertAlmostEqual(result['rate_V_per_s'],1.6/math.log(9),delta=.0001)
        self.assertFalse(slew_metrics(t,[0]*len(t),step)['valid'])

    def test_noise_model_limit_never_becomes_pass(self):
        item={'method':{'kind':'noise_density'},'target':{'rules':[{'metric':'noise','value':40e-9,'operator':'<=','unit':'V/sqrt(Hz)'}]}}
        case={'case_id':'noise','fixture':{'supply_voltage_V':5}}
        part={'value':10e-9,'gate_issues':[],'model_limitations':['Missing flicker calibration'],'metrics':{}}
        verdict=case_verdict(item,case,[part])
        self.assertTrue(verdict['tests'][0]['passed'])
        self.assertEqual(verdict['status'],'unverified_model')

    def test_both_short_circuit_directions_must_meet_limit(self):
        item={'method':{'kind':'isc'},'target':{'rules':[{'metric':'isc','value':.06,'operator':'<=','unit':'A'}]}}
        case={'case_id':'isc','fixture':{'supply_voltage_V':20}}
        parts=[{'value':x,'gate_issues':[],'model_limitations':[],'metrics':{}} for x in (.1,.001)]
        self.assertEqual(case_verdict(item,case,parts)['status'],'failed_in_model')

    def test_capacitive_drive_requires_pm_and_non_growing_response(self):
        item={'method':{'kind':'capacitive_drive'}};case={'case_id':'cload','fixture':{'supply_voltage_V':5}}
        parts=[{'value':44,'gate_issues':[],'model_limitations':[],'metrics':{}},
               {'value':1e-6,'gate_issues':[],'model_limitations':[],'metrics':{'finite_window_non_growing_response':True}}]
        self.assertEqual(case_verdict(item,case,parts)['status'],'failed_in_model')
        parts[0]['value']=60
        self.assertEqual(case_verdict(item,case,parts)['status'],'passed_sampled_model_case')
