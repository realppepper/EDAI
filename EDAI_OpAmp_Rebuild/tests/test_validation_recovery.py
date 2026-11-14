import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from opamp_pipeline.harness_03_loop import execute_pending, load, resume, save, start, submit
from opamp_pipeline.loop_02_handoff import write_json
from opamp_pipeline.support.execution_state import file_hash


def document(status):
    return {'source_cases_required':1,'rows':{'r':{'symbol':'GBW','kind':'gbw','target':{'min':1},
            'cases':[{'case_id':'case','fixture':{},'status':status}]}}}


class ValidationRecoveryTests(unittest.TestCase):
    def fixture(self, p):
        baseline=p/'baseline.json';write_json(baseline,document('failed_in_model'))
        old=p/'old.inc';old.write_text('old')
        folder=p/'candidate_001';folder.mkdir();candidate=folder/'candidate.inc';candidate.write_text('same pending design')
        response=folder/'RESPONSE.json';write_json(response,{})
        plan=p/'plan.json';policy=p/'policy.json';write_json(plan,{});write_json(policy,{})
        state={'status':'validating_candidate','run_dir':str(p),'plan_path':str(plan),'plan_sha256':file_hash(plan),
               'harness_path':str(policy),'harness_sha256':file_hash(policy),'code_signatures':{},
               'max_candidates':2,'best_index':0,'invalid_submissions':0,'scope_case_ids':['case'],
               'pending_request':None,'automatic_validation_retries':1,
               'candidates':[{'index':0,'candidate_path':str(old),'candidate_sha256':file_hash(old),
                   'ledger_path':str(baseline),'ledger_sha256':file_hash(baseline),
                   'assessment':{'score':[0,1],'scope_passed':False,'failed_case_ids':['case'],'counts':{}}}],
               'pending_candidate':{'index':1,'candidate_path':str(candidate),'candidate_sha256':file_hash(candidate),
                   'response_path':str(response),'response_sha256':file_hash(response),
                   'submitted_response_sha256':file_hash(response)}}
        save(p,state)
        return state

    def pipeline(self, p, status='passed_sampled_model_case', compute=None):
        def run(*args,**kwargs):
            out=p/'candidate_001/validation';out.mkdir(exist_ok=True)
            if compute is not None and not (out/'LEDGER.json').exists():compute.append('simulation')
            write_json(out/'LEDGER.json',document(status));write_json(out/'STATE.json',{'status':'completed'})
            return {'execution_seconds':1}
        return run

    def test_transient_worker_interruption_retries_same_design_and_updates_best(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);state=self.fixture(p);real=self.pipeline(p);calls=[]
            def flaky(*a,**kw):
                calls.append((a,kw))
                if len(calls)==1:raise OSError('injected worker interruption')
                return real(*a,**kw)
            with patch('opamp_pipeline.harness_03_loop.run_pipeline',side_effect=flaky),patch('opamp_pipeline.harness_03_loop.prepare') as design:
                execute_pending(p,state,'unused')
            self.assertEqual(len(calls),2)
            self.assertEqual(calls[0][0][0],calls[1][0][0])
            self.assertEqual(len(state['candidates']),2)
            self.assertEqual(state['best_index'],1)
            self.assertEqual(state['status'],'implemented_scope_passed')
            self.assertEqual([e['status'] for e in state['candidates'][1]['validation_attempts']],['interrupted','completed'])
            design.assert_not_called()

    def test_persistent_worker_failure_pauses_without_spending_another_proposal(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);state=self.fixture(p)
            with patch('opamp_pipeline.harness_03_loop.run_pipeline',side_effect=RuntimeError('worker stopped')) as work:
                execute_pending(p,state,'unused')
            self.assertEqual(work.call_count,2)
            self.assertEqual(state['status'],'validation_interrupted')
            self.assertEqual(state['best_index'],0)
            self.assertEqual(len(state['candidates']),1)
            self.assertIsNotNone(state['pending_candidate'])
            self.assertIsNone(state['pending_request'])
            with patch('opamp_pipeline.harness_03_loop.run_pipeline',side_effect=self.pipeline(p)):
                recovered=resume(p,'unused')
            self.assertEqual(len(recovered['candidates']),2)
            self.assertEqual(recovered['max_candidates'],2)
            self.assertEqual(len(recovered['candidates'][1]['validation_attempts']),3)

    def test_completed_measured_miss_is_not_retried_as_infrastructure(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);state=self.fixture(p)
            with patch('opamp_pipeline.harness_03_loop.run_pipeline',side_effect=self.pipeline(p,'failed_in_model')) as work:
                execute_pending(p,state,'unused')
            self.assertEqual(work.call_count,1)
            self.assertEqual(state['status'],'candidate_budget_exhausted')
            self.assertIsNone(state['pending_candidate'])

    def test_integrity_exception_is_not_automatically_retried(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);state=self.fixture(p)
            with patch('opamp_pipeline.harness_03_loop.run_pipeline',side_effect=ValueError('source changed')) as work:
                execute_pending(p,state,'unused')
            self.assertEqual(work.call_count,1)
            self.assertEqual(state['status'],'validation_interrupted')

    def test_pending_response_and_candidate_changes_block_resume(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);state=self.fixture(p)
            Path(state['pending_candidate']['candidate_path']).write_text('changed')
            with self.assertRaises(ValueError):load(p)

    def test_duplicate_pending_submission_does_not_create_or_run_a_second_candidate(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);state=self.fixture(p);response=Path(state['pending_candidate']['response_path'])
            with patch('opamp_pipeline.harness_03_loop.run_pipeline') as work:
                result=submit(p,response,'unused')
            work.assert_not_called()
            self.assertEqual(len(result['candidates']),1)
            self.assertEqual(result['pending_candidate']['index'],1)

    def test_report_failure_after_state_commit_is_repaired_without_resimulation(self):
        from opamp_pipeline.harness_03_loop import atomic_write_text as real_text
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);state=self.fixture(p)
            def blocked(path,text):
                if state['status']=='implemented_scope_passed':raise PermissionError('report locked')
                real_text(path,text)
            with patch('opamp_pipeline.harness_03_loop.run_pipeline',side_effect=self.pipeline(p)),patch('opamp_pipeline.harness_03_loop.atomic_write_text',side_effect=blocked):
                with self.assertRaises(PermissionError):execute_pending(p,state,'unused')
            self.assertEqual(load(p)['status'],'implemented_scope_passed')
            with patch('opamp_pipeline.harness_03_loop.run_pipeline') as work:recovered=resume(p)
            work.assert_not_called()
            self.assertEqual(recovered['best_index'],1)
            self.assertIn('최선 후보',(p/'REPORT.md').read_text(encoding='utf-8'))

    def test_state_commit_failure_reuses_completed_pipeline_exactly_once(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);state=self.fixture(p);compute=[];real_write=write_json
            def blocked(path,value):
                if Path(path).name=='STATE.json' and value.get('status')=='implemented_scope_passed':raise PermissionError('state locked')
                real_write(path,value)
            with patch('opamp_pipeline.harness_03_loop.run_pipeline',side_effect=self.pipeline(p,compute=compute)),patch('opamp_pipeline.harness_03_loop.write_json',side_effect=blocked):
                with self.assertRaises(PermissionError):execute_pending(p,state,'unused')
            saved=load(p);self.assertEqual(len(saved['candidates']),1)
            with patch('opamp_pipeline.harness_03_loop.run_pipeline',side_effect=self.pipeline(p,compute=compute)):
                recovered=resume(p,'unused')
            self.assertEqual(compute,['simulation'])
            self.assertEqual(len(recovered['candidates']),2)
            self.assertEqual(recovered['candidates'][1]['validation_attempts'][0]['status'],'uncommitted_before_resume')

    def test_initial_validation_has_a_persisted_checkpoint_before_running(self):
        from opamp_pipeline.design_01_cmos_candidate import MODELS
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);model=p/'input.inc'
            model.write_text(MODELS+'.subckt FIRSTAMP P N VP VM OUT\nRb BIAS VM 1Meg\nRo OUT VM 1k\n.ends FIRSTAMP\n',encoding='ascii')
            plan=p/'run/measurement_plan/plan_02_measurements.json';write_json(plan,{})
            session=p/'session'
            with patch('opamp_pipeline.harness_03_loop.run_pipeline') as work:
                state=start(session,model,p/'run',max_candidates=2,defer_validation=True)
            work.assert_not_called()
            self.assertEqual(state['status'],'validating_initial')
            self.assertEqual(len(load(session)['candidates']),0)
            self.assertEqual(json.loads((session/'BEST.json').read_text()),None)
            def run(*args,**kwargs):
                out=session/'candidate_000/validation';out.mkdir()
                write_json(out/'LEDGER.json',document('passed_sampled_model_case'))
                return {'execution_seconds':1}
            with patch('opamp_pipeline.harness_03_loop.run_pipeline',side_effect=run):state=resume(session,'unused')
            self.assertEqual(len(state['candidates']),1)
            self.assertEqual(state['candidates'][0]['origin'],'declared_initial_candidate')
            self.assertEqual(state['status'],'implemented_scope_passed')

    def test_orphan_receipt_after_interrupted_submit_is_reused_without_new_candidate(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);state=self.fixture(p);response=Path(state['pending_candidate']['response_path'])
            payload={'request_id':'same','netlist':'same pending design'};write_json(response,payload)
            request=p/'REQUEST.json';write_json(request,{'request_id':'same'})
            state.update(status='awaiting_chat_designer',pending_candidate=None,pending_request={'path':str(request),'sha256':file_hash(request)})
            save(p,state)
            with patch('opamp_pipeline.harness_03_loop.validate_response'):
                result=submit(p,response,None,defer_validation=True)
            self.assertEqual(len(result['candidates']),1)
            self.assertEqual(result['pending_candidate']['index'],1)
            self.assertEqual(len(list(p.glob('candidate_*'))),1)

    def test_conflicting_unrecorded_candidate_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);state=self.fixture(p);candidate=Path(state['pending_candidate']['candidate_path']);original=candidate.read_bytes()
            response=p/'other_response.json';write_json(response,{'request_id':'same','netlist':'different design'})
            request=p/'REQUEST.json';write_json(request,{'request_id':'same'})
            state.update(status='awaiting_chat_designer',pending_candidate=None,pending_request={'path':str(request),'sha256':file_hash(request)})
            save(p,state)
            with patch('opamp_pipeline.harness_03_loop.validate_response'):
                with self.assertRaises(ValueError):submit(p,response,None,defer_validation=True)
            self.assertEqual(candidate.read_bytes(),original)
