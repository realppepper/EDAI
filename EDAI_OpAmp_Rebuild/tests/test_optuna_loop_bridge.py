from copy import deepcopy
from pathlib import Path
import tempfile
import json
import unittest
from unittest.mock import patch
from opamp_pipeline import harness_03_loop as fixed
from opamp_pipeline import optuna_03_loop_bridge as bridge


def example():
    case={'case_id':'gain','supply_V':30,'fixture':{},'status':'failed_in_model',
          'tests':[{'value':2e6,'limit':3e6}],'parts':[{'value':2e6,'gate_issues':[]}],'gate_issues':[]}
    document={'source_cases_required':1,'rows':{'r':{'kind':'gbw','symbol':'GBW','target':{},'cases':[case]}},'operational_startup':{'passed':True}}
    current={'index':0,'assessment':{'scope_passed':False,'score':[0,1],'failed_case_ids':['gain']},'ledger_path':'ledger.json'}
    state={'candidates':[current],'best_index':0,'max_candidates':3,'optuna':{'max_rounds':1,'screening_kinds':['iq','gbw','pm','sr']},'optuna_attempts':[]}
    return state,current,document


class OptunaLoopBridgeTests(unittest.TestCase):
    def test_numeric_miss_eligible(self):
        state,current,doc=example();self.assertEqual(bridge.routing_reason(state,current,doc),'numeric_repair_eligible')

    def test_already_satisfied_never_calls_optuna(self):
        state,current,doc=example();current['assessment']['scope_passed']=True
        with patch.object(fixed,'save'),patch.object(bridge,'execute') as optimize,patch.object(fixed,'prepare') as request:
            fixed.advance(Path('.'),state,'ltspice')
            optimize.assert_not_called();request.assert_not_called()
            self.assertEqual(state['status'],'implemented_scope_passed')

    def test_real_advance_calls_sizing_before_chat(self):
        state,current,doc=example()
        with patch.object(fixed,'read',return_value=doc),patch.object(fixed,'save'),patch.object(bridge,'execute') as optimize,patch.object(fixed,'prepare') as request:
            fixed.advance(Path('.'),state,'ltspice')
            optimize.assert_called_once();request.assert_not_called()

    def test_no_executable_persists_waiting_stage(self):
        state,current,doc=example()
        with patch.object(fixed,'read',return_value=doc),patch.object(fixed,'save'),patch.object(bridge,'execute') as optimize:
            fixed.advance(Path('.'),state)
            optimize.assert_not_called();self.assertEqual(state['status'],'awaiting_optuna_execution')

    def test_measurement_or_startup_errors_do_not_enter_sizing(self):
        for mutation,reason in [
            (lambda d:d['operational_startup'].update(passed=False),'startup_not_qualified'),
            (lambda d:d['rows']['r']['cases'][0].update(status='execution_contract_error'),'verification_or_model_issue'),
            (lambda d:d['rows']['r']['cases'][0].update(gate_issues=['invalid bias']),'measurement_prerequisites_not_qualified'),
            (lambda d:d['rows']['r']['cases'][0]['tests'][0].update(value=None),'missing_numeric_feedback')]:
            state,current,doc=example();mutation(doc)
            self.assertEqual(bridge.routing_reason(state,current,doc),reason)

    def test_exhausted_sizing_budget_returns_to_chat(self):
        state,current,doc=example();state['optuna_attempts']=[{'status':'completed'}]
        with patch.object(fixed,'read',return_value=doc),patch.object(fixed,'save'),patch.object(bridge,'execute') as optimize,patch.object(fixed,'prepare') as request:
            fixed.advance(Path('.'),state,'ltspice')
            optimize.assert_not_called();request.assert_called_once()

    def test_previous_pass_regressions_cannot_become_best(self):
        state,current,doc=example();worse=deepcopy(current);worse.update(index=1,eligible_for_best=False)
        worse['assessment']['score']=[0,0];state['candidates'].append(worse)
        with patch.object(fixed,'save'),patch.object(fixed,'prepare'):
            fixed.advance(Path('.'),state,allow_sizing=False)
        self.assertEqual(state['best_index'],0)

    def test_feedback_does_not_mutate_state(self):
        state,current,doc=example();state['optuna_attempts']=[{'status':'completed'}]
        info=bridge.feedback(state);info['attempts'][0]['status']='changed'
        self.assertEqual(state['optuna_attempts'][0]['status'],'completed')

    def test_bad_budgets_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)/'config.json';p.write_text(json.dumps({'screening_kinds':['iq']}))
            for value in (0,21,True,1.5):
                with self.assertRaises(ValueError):bridge.configure(p,value,1)

    def test_resume_ready_stage_does_not_run_worker_twice(self):
        state,current,doc=example();state['status']='optuna_ready_to_advance'
        with patch.object(fixed,'load',return_value=state),patch.object(fixed,'advance') as advance,patch.object(bridge,'execute') as optimize:
            fixed.resume(Path('.'),'ltspice')
            advance.assert_called_once_with(Path('.').resolve(),state,'ltspice',allow_sizing=False);optimize.assert_not_called()


if __name__=='__main__':unittest.main()
