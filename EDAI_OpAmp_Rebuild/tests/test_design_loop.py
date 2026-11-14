import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from copy import deepcopy
from opamp_pipeline.loop_01_policy import make_policy,evaluate,REQUIRED_BENCHES
from opamp_pipeline.loop_02_handoff import validate_dut,accept_response,write_json
from opamp_pipeline.loop_03_controller import advance,execute_pending
from opamp_pipeline.design_01_cmos_candidate import candidate
from opamp_pipeline.support.execution_state import file_hash


def context():
    rows=[]
    for symbol,limit,op,unit in [('IQ',460e-6,'<=','A'),('VOS',.003,'<=','V'),('GBW',1.2e6,'>=','Hz'),('ts',4e-6,'<=','s')]:
        rows.append({'symbol':symbol,'row_id':symbol,'target':{'origin':'test_source','rules':[{'value':limit,'operator':op,'unit':unit}]},
            'cases':[{'fixture':{'supply_voltage_V':5}}]})
    return {'required_rows':rows}


def experiment():
    b={name:{'name':name,'status':'executed','metrics':{}} for name in REQUIRED_BENCHES}
    b['opamp_op']['metrics']={'iq_A':350e-6,'vos_V':-.0004,'servo_error_V':0}
    b['opamp_dc']['measurements']={'tracking_error':.0004}
    b['opamp_gbw']['metrics']={'unity_Hz':1.5e6}
    b['opamp_tran_rising']['metrics']={'settling_s':1e-6}
    b['opamp_tran_falling']['metrics']={'settling_s':3e-6}
    return {'status':'partial_experiment_completed','benchmarks':list(b.values())}


class DesignLoopTests(unittest.TestCase):
    def test_challenge_is_separate_and_source_unchanged(self):
        c=context();old=deepcopy(c);base=make_policy(c);challenge=make_policy(c,1.8e6)
        self.assertEqual(c,old);self.assertEqual(challenge['targets']['GBW']['source_target'],1.2e6)
        self.assertTrue(evaluate(experiment(),base)['scope_passed'])
        failed=evaluate(experiment(),challenge)
        self.assertEqual(failed['failed_keys'],['GBW']);self.assertFalse(failed['full_datasheet_success'])

    def test_missing_nonfinite_and_duplicate_analyses_cannot_pass(self):
        p=make_policy(context())
        for fault in ('missing','nan','duplicate'):
            r=experiment()
            if fault=='missing':r['benchmarks']=[b for b in r['benchmarks'] if b['name']!='opamp_gbw']
            elif fault=='nan':next(b for b in r['benchmarks'] if b['name']=='opamp_gbw')['metrics']['unity_Hz']=float('nan')
            else:r['benchmarks'].append(deepcopy(r['benchmarks'][0]))
            with self.subTest(fault=fault):
                assessed=evaluate(r,p)
                self.assertFalse(assessed['scope_passed'])
                json.dumps(assessed,allow_nan=False)

    def test_frozen_models_and_no_behavioral_dut(self):
        text=candidate();self.assertTrue(validate_dut(text))
        with self.assertRaises(ValueError):validate_dut(text.replace('VTO=0.65','VTO=0.5'))
        with self.assertRaises(ValueError):validate_dut(text.replace('.ends FIRSTAMP','Bmagic OUT 0 V=3\n.ends FIRSTAMP'))
        with self.assertRaises(ValueError):validate_dut(text.replace('6e-11','-6e-11'))
        with self.assertRaises(ValueError):validate_dut(text.replace('W=80u','W=-80u'))

    def test_worse_revision_preserves_better_prior_candidate(self):
        p=make_policy(context(),1.8e6)
        good=evaluate(experiment(),p);bad_result=experiment()
        next(b for b in bad_result['benchmarks'] if b['name']=='opamp_gbw')['metrics']['unity_Hz']=1e6
        bad=evaluate(bad_result,p)
        state={'policy':p,'candidates':[{'id':'old','assessment':good},{'id':'new','assessment':bad}],
               'best_candidate_id':'old','simulation_seconds':1}
        with patch('opamp_pipeline.loop_03_controller.prepare_request'),patch('opamp_pipeline.loop_03_controller.save'):
            advance('unused',state)
        self.assertEqual(state['best_candidate_id'],'old')

    def test_pass_and_budget_stop_without_another_request(self):
        p=make_policy(context());passed=evaluate(experiment(),p)
        state={'policy':p,'candidates':[{'id':'old','assessment':passed}], 'best_candidate_id':None,'simulation_seconds':0}
        with patch('opamp_pipeline.loop_03_controller.prepare_request') as ask,patch('opamp_pipeline.loop_03_controller.save'):
            advance('unused',state);ask.assert_not_called()
        self.assertEqual(state['status'],'partial_scope_passed')
        p=make_policy(context(),1.8e6);failed=evaluate(experiment(),p)
        state.update(policy=p,candidates=[{'id':str(i),'assessment':failed} for i in range(3)],best_candidate_id=None)
        with patch('opamp_pipeline.loop_03_controller.prepare_request') as ask,patch('opamp_pipeline.loop_03_controller.save'):
            advance('unused',state);ask.assert_not_called()
        self.assertEqual(state['status'],'candidate_budget_exhausted')

    def test_stale_design_response_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder);request=path/'request.json';write_json(request,{'request_id':'current'})
            response=path/'response.json';write_json(response,{'request_id':'old','based_on_request_sha256':file_hash(request)})
            state={'status':'awaiting_chat_design','pending_request':{'path':str(request),'sha256':file_hash(request),'request_id':'current'}}
            with self.assertRaises(ValueError):accept_response(path,state,response)

    def test_resume_reuses_complete_verified_result_without_simulation(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder);model=path/'candidate.inc';model.write_text(candidate(),encoding='ascii')
            receipt=path/'DESIGN_RESPONSE.json';write_json(receipt,{})
            output=path/'execution_01';output.mkdir();r=experiment()
            r.update(netlist_sha256=file_hash(model),measurement_plan_sha256='plan-hash',execution_seconds=2.5)
            write_json(output/'RESULT.json',r)
            pending={'folder':str(path),'candidate_path':str(model),'candidate_sha256':file_hash(model),
                     'response_sha256':file_hash(receipt),'execution_attempts':[{'path':str(output),'charged':False}]}
            state={'pending_candidate':pending,'simulation_seconds':0}
            with patch('opamp_pipeline.loop_03_controller.subprocess.run') as simulate,patch('opamp_pipeline.loop_03_controller.finish_pending',return_value=state):
                execute_pending(path,state,'unused');simulate.assert_not_called()
                execute_pending(path,state,'unused');simulate.assert_not_called()
            self.assertEqual(state['simulation_seconds'],2.5)

    def test_nonfinite_or_relaxed_challenge_rejected(self):
        for target in (float('nan'),float('inf'),1e6):
            with self.assertRaises(ValueError):make_policy(context(),target)
