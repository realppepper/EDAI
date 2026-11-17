from copy import deepcopy
from pathlib import Path
import unittest
from unittest.mock import patch
from opamp_pipeline.optuna_04_designer import designer_policy,validate_proposal,proposal_contract
from opamp_pipeline import harness_03_loop as fixed
from opamp_pipeline import optuna_03_loop_bridge as bridge

TEXT='''.subckt FIRSTAMP P N VP VM OUT
RBREF VP BC 100k
CCOMP CZ YH 84p
MINL D N TAIL VM GNM W=20u L=2u
MINR X P TAIL VM GNM W=20u L=2u
.ends FIRSTAMP
'''


class DesignerSizingTests(unittest.TestCase):
    def inputs(self):
        policy=designer_policy(5,1)
        request={'request_id':'request1','numeric_sizing_proposal':{'enabled':True,'candidate_file_sha256':'circuit_hash'},
                 'feedback':[{'case_id':'gbw30','status':'failed_in_model'}]}
        response={'action':'propose_sizing','request_id':'request1','request_sha256':'request_hash','based_on_candidate_sha256':'circuit_hash',
                  'sizing_proposal':{'reason':'Compensation may influence GBW and slew.','evidence_case_ids':['gbw30'],
                                    'risks':['Phase margin may decrease.'],'trials':3,
                                    'parameters':[{'name':'compensation_F','elements':['CCOMP'],'field':'value',
                                                   'low':20e-12,'high':84e-12,'log':True,'reason':'Bound the compensation search.'}]}}
        return policy,request,response

    def validate(self,response=None,request=None,text=TEXT):
        p,r,s=self.inputs();return validate_proposal(request or r,response or s,text,p,'request_hash')

    def test_current_value_read_from_dut_not_invented_by_designer(self):
        config,trials=self.validate()
        self.assertEqual(config['parameters'][0]['baseline'],84e-12)
        self.assertEqual(trials,3);self.assertEqual(config['seed'],17)
        self.assertEqual(config['objective'],'minimize_worst_case_quiescent_power_mW')

    def test_old_request_other_candidate_and_disabled_routes_rejected(self):
        for key in ('request_id','request_sha256','based_on_candidate_sha256'):
            _,_,response=self.inputs();response[key]='wrong'
            with self.assertRaises(ValueError):self.validate(response)
        _,request,_=self.inputs();request['numeric_sizing_proposal']['enabled']=False
        with self.assertRaises(ValueError):self.validate(request=request)

    def test_no_circuit_edits_paths_or_changed_objectives(self):
        for key in ('netlist','candidate_file','command','config_path'):
            _,_,response=self.inputs();response[key]='not allowed'
            with self.assertRaises(ValueError):self.validate(response)
        _,_,response=self.inputs();response['sizing_proposal']['objective']='relax_gain'
        with self.assertRaises(ValueError):self.validate(response)

    def test_bounds_and_trial_caps_are_enforced(self):
        for value in (0,1,6,True):
            _,_,response=self.inputs();response['sizing_proposal']['trials']=value
            with self.assertRaises(ValueError):self.validate(response)
        for low,high in [(float('nan'),84e-12),(40e-12,20e-12),(20e-12,40e-12),(0,84e-12)]:
            _,_,response=self.inputs();response['sizing_proposal']['parameters'][0].update(low=low,high=high)
            with self.assertRaises(ValueError):self.validate(response)

    def test_unknown_elements_models_and_wrong_baseline_rejected(self):
        for element in ('MISSING','.model'):
            _,_,response=self.inputs();response['sizing_proposal']['parameters'][0]['elements']=[element]
            with self.assertRaises(ValueError):self.validate(response)
        _,_,response=self.inputs();response['sizing_proposal']['parameters'][0]['baseline']=28e-12
        with self.assertRaises(ValueError):self.validate(response)

    def test_matching_group_must_have_consistent_current_values(self):
        _,_,response=self.inputs();response['sizing_proposal']['parameters']=[
            {'name':'input_width','elements':['MINL','MINR'],'field':'W','low':10e-6,'high':40e-6,'reason':'Keep the pair matched.'}]
        self.validate(response)
        with self.assertRaises(ValueError):self.validate(response,text=TEXT.replace('MINR X P TAIL VM GNM W=20u','MINR X P TAIL VM GNM W=10u'))

    def test_reason_risk_and_measured_evidence_required(self):
        for key,value in [('reason',''),('risks',[]),('evidence_case_ids',['unknown']),('evidence_case_ids',[])]:
            _,_,response=self.inputs();response['sizing_proposal'][key]=value
            with self.assertRaises(ValueError):self.validate(response)

    def test_designer_mode_asks_instead_of_automatically_running_fixed_config(self):
        from test_optuna_loop_bridge import example
        state,current,document=example();state['optuna']=designer_policy()
        with patch.object(fixed,'read',return_value=document),patch.object(fixed,'save'),patch.object(fixed,'prepare') as ask,patch.object(bridge,'execute') as execute:
            fixed.advance(Path('.'),state,'ltspice')
            ask.assert_called_once();execute.assert_not_called()

    def test_host_budget_configuration_is_bounded(self):
        for value in (1,21,True):
            with self.assertRaises(ValueError):designer_policy(value)


if __name__=='__main__':unittest.main()
