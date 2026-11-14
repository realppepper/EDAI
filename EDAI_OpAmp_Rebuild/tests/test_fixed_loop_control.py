import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from opamp_pipeline.harness_03_loop import advance,load,prepare,submit
from opamp_pipeline.pipeline_01_verification import check_chain
from opamp_pipeline.loop_02_handoff import write_json
from opamp_pipeline.support.execution_state import file_hash


class FixedLoopControlTests(unittest.TestCase):
    def test_regressed_candidate_does_not_replace_best_when_budget_ends(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);old={'index':0,'candidate_path':'old','assessment':{'score':[0,2],'scope_passed':False,'failed_case_ids':['a','b'],'counts':{}}}
            new={'index':1,'candidate_path':'new','assessment':{'score':[0,3],'scope_passed':False,'failed_case_ids':['a','b','c'],'counts':{}}}
            s={'candidates':[old,new],'best_index':0,'max_candidates':2,'harness_sha256':'fixed'}
            advance(p,s);self.assertEqual(s['best_index'],0);self.assertEqual(s['status'],'candidate_budget_exhausted')

    def test_success_preserves_best_and_stops_without_another_request(self):
        with tempfile.TemporaryDirectory() as d:
            s={'candidates':[{'index':0,'candidate_path':'old','assessment':{'score':[0,1],'scope_passed':False,'failed_case_ids':['a'],'counts':{}}},
                {'index':1,'candidate_path':'new','assessment':{'score':[0,0],'scope_passed':True,'failed_case_ids':[],'counts':{}}}],
                'best_index':0,'max_candidates':3,'harness_sha256':'fixed'}
            with patch('opamp_pipeline.harness_03_loop.prepare') as request:
                advance(Path(d),s);request.assert_not_called()
            self.assertEqual(s['status'],'implemented_scope_passed');self.assertEqual(s['best_index'],1)

    def test_execution_failure_feedback_is_explicitly_old_measurements(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);model=p/'candidate.inc';model.write_text('bad candidate');plan=p/'plan.json';data=p/'result.json';write_json(plan,{});write_json(data,{})
            s={'candidates':[{'candidate_path':str(model),'ledger_path':str(data)},{'candidate_path':str(model),'ledger_path':None,'execution_error':'solver failed'}],
               'best_index':0,'plan_path':str(plan),'harness_path':'fixed'}
            with patch('opamp_pipeline.harness_03_loop.make_request',return_value={'request_id':'initial'}):prepare(p,s)
            r=json.loads(Path(s['pending_request']['path']).read_text())
            self.assertEqual(r['current_execution_failure'],'solver failed');self.assertIn('not this failed execution',r['feedback_notice'])

    def test_changing_frozen_harness_prevents_resume(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);h=p/'h.json';plan=p/'p.json';h.write_text('{}');plan.write_text('{}')
            write_json(p/'STATE.json',{'harness_path':str(h),'harness_sha256':file_hash(h),'plan_path':str(plan),'plan_sha256':file_hash(plan),'code_signatures':{},'candidates':[]})
            load(p);h.write_text('{"changed":true}')
            with self.assertRaises(ValueError):load(p)

    def test_same_raw_response_is_idempotent_without_validation_work(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);r=p/'response.json';r.write_text('{ "format" : "preserved" }')
            state={'candidates':[{'submitted_response_sha256':file_hash(r)}]}
            with patch('opamp_pipeline.harness_03_loop.load',return_value=state),patch('opamp_pipeline.harness_03_loop.run_pipeline') as execute:
                self.assertEqual(submit(p,r,'spice'),state);execute.assert_not_called()

    def test_empty_calibration_list_cannot_qualify_imported_stage(self):
        core=Path('core/RESULT.json');plan=Path('plan.json')
        a={'status':'completed_with_explicit_unverified_cases','calibration_passed':True,'input_signatures':{str(plan.resolve()):'hash'},'job_cache':{}}
        b={'status':'extension_completed_with_explicit_model_limitations','calibration':[]}
        cal={'status':'passed','checks':[{'passed':True}]*23,
             'dc_grid_validation':[{'passed':True,'policy':policy,'expected_spec_pass':v,'coverage':{'complete':True,'unique_full_grid_points':201}} for policy in ('center_out_complete_grid_v1','full_ascending') for v in (True,False)]}
        with patch('opamp_pipeline.pipeline_01_verification.read',side_effect=[a,b,{},cal]),patch('opamp_pipeline.pipeline_01_verification.file_hash',return_value='hash'):
            with self.assertRaises(ValueError):check_chain(core,'imp/RESULT.json','over/RESULT.json','model.inc',plan)
