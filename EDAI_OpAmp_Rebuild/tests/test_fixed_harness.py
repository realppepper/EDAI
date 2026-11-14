import unittest,tempfile
from copy import deepcopy
from pathlib import Path
from opamp_pipeline.harness_01_fixed import load_harness,system_text,validate_candidate
from opamp_pipeline.harness_02_request import make_request,validate_response
from opamp_pipeline.harness_03_loop import assessment
from opamp_pipeline.design_01_cmos_candidate import candidate


def sample():
    target={'rules':[{'metric':'gbw','operator':'>=','value':1e6,'unit':'Hz'}]};fixture={'supply_voltage_V':5}
    cases=[{'case_id':'case1','fixture':fixture},{'case_id':'case2','fixture':fixture}]
    row={'row_id':'row1','symbol':'GBW','target':target,'method':{'kind':'gbw'},'resolved_conditions':{'values':{}},'source':{'source':{'pdf_page':6}},'cases':cases}
    recorded=[{**c,'status':'failed_in_model' if i==0 else 'unverified_model'} for i,c in enumerate(cases)]
    result={'source_cases_required':2,'source_rows_required':1,'rows':{'row1':{'kind':'gbw','symbol':'GBW','target':target,'cases':recorded}},'case_status_counts':{'failed_in_model':1,'unverified_model':1},'input_signatures':{}}
    return {'measurements':[row]},result


class FixedHarnessTests(unittest.TestCase):
    def test_fixed_policy_has_no_provider_evolution_or_subagent_execution(self):
        p,sha=load_harness();self.assertFalse(p['harness2_enabled']);self.assertFalse(p['external_designer_api_enabled'])
        self.assertFalse(next(c for c in p['components'] if c['id']=='C7')['enabled'])
        self.assertIn('frozen',system_text(p));self.assertEqual(len(sha),64)

    def test_dut_guard_does_not_ban_external_testbench_sources(self):
        self.assertTrue(validate_candidate(candidate()))
        with self.assertRaises(ValueError):validate_candidate(candidate().replace('.ends FIRSTAMP','Rbad X 0 1Meg\n.ends FIRSTAMP'))

    def test_full_plan_unknowns_and_actual_supplies_retained(self):
        plan,result=sample();request=make_request(plan,result,candidate())
        self.assertEqual(len(request['requirements'][0]['cases']),2)
        self.assertEqual(request['feedback'][1]['status'],'unverified_model')
        self.assertEqual(request['requirements'][0]['cases'][0]['fixture']['supply_voltage_V'],5)

    def test_wrong_fixture_or_missing_coverage_rejected(self):
        for fault in ('fixture','missing'):
            plan,result=sample()
            if fault=='fixture':result=deepcopy(result);result['rows']['row1']['cases'][0]['fixture']['supply_voltage_V']=15
            else:result['rows']['row1']['cases'].pop();result['source_cases_required']=1
            with self.assertRaises(ValueError):make_request(plan,result,candidate())

    def test_response_bound_and_frozen_models_enforced(self):
        plan,result=sample();r=make_request(plan,result,candidate());response={'request_id':r['request_id'],'summary':'Retune compensation','changes':['Ccomp'],'netlist':candidate(),'hypotheses':[]}
        self.assertTrue(validate_response(r,response))
        response['request_id']='stale'
        with self.assertRaises(ValueError):validate_response(r,response)
        response['request_id']=r['request_id'];response['netlist']=candidate().replace('VTO=0.65','VTO=0.6')
        with self.assertRaises(ValueError):validate_response(r,response)

    def test_optimization_cannot_promote_unknowns_or_relax_targets(self):
        _,old=sample();new=deepcopy(old);new['rows']['row1']['cases'][0]['status']='passed_sampled_model_case'
        self.assertTrue(assessment(old,new,['case1'])['scope_passed'])
        new['rows']['row1']['cases'][1]['status']='passed_sampled_model_case'
        with self.assertRaises(ValueError):assessment(old,new,['case1'])

    def test_unqualified_formatted_answer_is_not_accepted(self):
        plan,result=sample();r=make_request(plan,result,candidate())
        with self.assertRaises(ValueError):validate_response(r,{'request_id':r['request_id'],'summary':'','changes':[],'netlist':candidate()})
