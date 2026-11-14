import unittest
from copy import deepcopy
from opamp_pipeline.loop_04_extended_policy import compare_extended
from opamp_pipeline.design_03_cascoded_bias import cascoded_bias,enhanced_output
from opamp_pipeline.loop_02_handoff import validate_dut
from opamp_pipeline.design_04_folded_input import folded_candidate,buffered_sink_candidate,damped_sink_candidate


def sample():
    def case(key,vs,status):return {'case_id':key,'supply_V':vs,'fixture':{'supply_voltage_V':vs},'status':status,'parts':[]}
    rows={
        'iq':{'symbol':'IQ','kind':'iq','target':{'limit':.0008},'cases':[case('i36',36,'failed_in_model')]},
        'psrr':{'symbol':'PSRR','kind':'psrr','target':{'limit':15e-6},'cases':[case('p'+str(v),v,'failed_in_model') for v in (5,15,36)]},
        'gbw':{'symbol':'GBW','kind':'gbw','target':{'limit':1.2e6},'cases':[case('g5',5,'passed_sampled_model_case')]},
        'noise':{'symbol':'en','kind':'noise_density','target':{'limit':40e-9},'cases':[case('n5',5,'unverified_model')]}}
    return {'rows':rows,'source_cases_required':6,'source_rows_required':4}


class ExtendedDesignLoopTests(unittest.TestCase):
    def test_custom_priority_selection_and_invalid_identifiers(self):
        baseline=sample();new=deepcopy(baseline)
        result=compare_extended(baseline,new,priority_case_ids=['g5'])
        self.assertEqual(result['summary']['priority_passed'],1)
        self.assertTrue(result['adoptable_without_losing_previous_passes'])
        for ids in ([],['missing'],['g5','g5']):
            with self.subTest(ids=ids),self.assertRaises(ValueError):
                compare_extended(baseline,new,priority_case_ids=ids)

    def test_folded_designs_keep_frozen_models_and_allowed_devices(self):
        self.assertTrue(validate_dut(folded_candidate()))
        self.assertTrue(validate_dut(buffered_sink_candidate()))
        self.assertTrue(validate_dut(damped_sink_candidate(20e-12)))

    def test_priorities_pass_but_regression_prevents_adoption(self):
        baseline=sample();new=deepcopy(baseline)
        for key in ('iq','psrr'):
            for c in new['rows'][key]['cases']:c['status']='passed_sampled_model_case'
        new['rows']['gbw']['cases'][0]['status']='failed_in_model'
        comparison=compare_extended(baseline,new)
        self.assertTrue(comparison['priority_goals_passed'])
        self.assertFalse(comparison['adoptable_without_losing_previous_passes'])
        self.assertEqual(comparison['summary']['new_regressions'],1)

    def test_unknowns_remain_and_previous_passes_preserved(self):
        baseline=sample();new=deepcopy(baseline)
        for key in ('iq','psrr'):
            for c in new['rows'][key]['cases']:c['status']='passed_sampled_model_case'
        comparison=compare_extended(baseline,new)
        self.assertTrue(comparison['adoptable_without_losing_previous_passes'])
        self.assertEqual(comparison['summary']['unverified'],1)
        self.assertFalse(comparison['whole_datasheet_success'])

    def test_source_changes_or_missing_cases_rejected(self):
        for fault in ('target','fixture','missing','promote_unknown'):
            baseline=sample();new=deepcopy(baseline)
            if fault=='target':new['rows']['iq']['target']['limit']=1
            elif fault=='fixture':new['rows']['iq']['cases'][0]['fixture']['supply_voltage_V']=5
            elif fault=='missing':new['rows']['psrr']['cases'].pop();new['source_cases_required']-=1
            else:new['rows']['noise']['cases'][0]['status']='passed_sampled_model_case'
            with self.subTest(fault=fault),self.assertRaises(ValueError):compare_extended(baseline,new)

    def test_case_acceptance_rule_cannot_be_relaxed(self):
        baseline=sample();new=deepcopy(baseline)
        baseline['rows']['iq']['cases'][0]['tests']=[{'metric':'iq','limit':.0008,'operator':'<=','value':.004,'passed':False}]
        new['rows']['iq']['cases'][0]['tests']=[{'metric':'iq','limit':.008,'operator':'<=','value':.004,'passed':True}]
        with self.assertRaises(ValueError):compare_extended(baseline,new)

    def test_new_bias_designs_keep_frozen_models_and_allowed_devices(self):
        self.assertTrue(validate_dut(cascoded_bias()))
        self.assertTrue(validate_dut(enhanced_output()))
        with self.assertRaises(ValueError):cascoded_bias(0)
