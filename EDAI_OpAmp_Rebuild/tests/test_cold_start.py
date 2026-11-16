import unittest
import tempfile
from pathlib import Path
from copy import deepcopy
from unittest.mock import patch
from opamp_pipeline import startup_01_initial_design as initial
from opamp_pipeline.design_01_cmos_candidate import candidate, MODELS
from opamp_pipeline.plan_02_measurements import build_measurements
from opamp_pipeline.spec_02_enrich_rows import apply_enrichment
from opamp_pipeline.support.source_checks import fingerprint
from opamp_pipeline import startup_02_datasheet as startup
from opamp_pipeline.loop_02_handoff import write_json
from opamp_pipeline.support.execution_state import file_hash


class ColdStartTests(unittest.TestCase):
    def data(self):
        doc={'ready_for_design':False,'target_product':'X','source_sha256':'hash',
             'verification_summary':{'source_rows_missing_from_document':0},
             'electrical_specs':[{'id':key,'verification':{'status':'semantic_review_required',
                 'llm_semantic_review':{'status':status}}} for key,status in [('r','reviewed_match'),('n','uncertain')]]}
        selected={'items':[{'row_id':k,'required_in_project':True} for k in ['r','n']]}
        plan={'measurements':[{'row_id':k,'symbol':k,'source':{},'target':{},'resolved_conditions':{},
                              'method':{'kind':kind},'cases':[{'case_id':k,'fixture':{}}]}
                             for k,kind in [('r','gbw'),('n','noise_density')]]}
        return doc,selected,plan

    def admit(self,doc,selection,plan):
        with patch.object(initial,'require_current_spec',return_value=doc), \
             patch.object(initial,'require_current_hkg',return_value={}), \
             patch.object(initial,'require_current_pdg',return_value={'summary':{'channels':2}}):
            return initial.admission('new_run',selection,plan)

    def test_scoped_admission_keeps_uncertain_unsupported_source_tracked(self):
        doc,s,p=self.data();a=self.admit(doc,s,p)
        self.assertTrue(a['admitted']);self.assertEqual(a['deferred_source_review_row_ids'],['n'])
        self.assertFalse(a['source_ready_for_design_flag_preserved']);self.assertFalse(doc['ready_for_design'])

    def test_unreviewed_required_source_and_coverage_holes_block_design(self):
        d,s,p=self.data();d['electrical_specs'][0]['verification']['llm_semantic_review']['status']='uncertain'
        self.assertFalse(self.admit(d,s,p)['admitted'])
        d,s,p=self.data();d['verification_summary']['source_rows_missing_from_document']=1
        self.assertFalse(self.admit(d,s,p)['admitted'])

    def test_plan_cannot_silently_omit_selected_source_rows(self):
        d,s,p=self.data();p['measurements'].pop()
        with self.assertRaises(ValueError):self.admit(d,s,p)

    def test_first_request_has_models_and_goals_but_no_starting_circuit(self):
        d,s,p=self.data();a=self.admit(d,s,p)
        packet=initial.make_initial_request(p,a,initial.load_harness.__defaults__[0])
        self.assertEqual(packet['frozen_model_prefix'],MODELS)
        self.assertNotIn('candidate_netlist',packet);self.assertNotIn('feedback',packet)
        self.assertFalse(packet['past_designs_provided']);self.assertFalse(packet['past_measurements_provided'])
        self.assertTrue(packet['requirements'][0]['required_for_implemented_scope'])
        self.assertTrue(packet['requirements'][1]['source_review_deferred'])
        r={'request_id':packet['request_id'],'request_sha256':'sha','netlist':candidate(),'summary':'New fixture architecture'}
        self.assertTrue(initial.validate_initial(packet,r,'sha'))
        r['request_sha256']='old'
        with self.assertRaises(ValueError):initial.validate_initial(packet,r,'sha')

    def test_initial_model_boundary_and_case_ids_are_enforced(self):
        d,s,p=self.data();packet=initial.make_initial_request(p,self.admit(d,s,p),initial.load_harness.__defaults__[0])
        r={'request_id':packet['request_id'],'request_sha256':'sha','netlist':candidate().replace('VTO=0.65','VTO=0.2'),'summary':'Invalid model'}
        with self.assertRaises(ValueError):initial.validate_initial(packet,r,'sha')
        r['netlist']=candidate();r['hypotheses']=[{'case_ids':['not-provided']}]
        with self.assertRaises(ValueError):initial.validate_initial(packet,r,'sha')

    def test_source_context_string_list_rejected_before_downstream_crash(self):
        from test_sequential_specs import fixture
        d,a=fixture();a['document_annotations']={'operating_conditions':['unsupported string']}
        with self.assertRaisesRegex(ValueError,'list of source-context'):apply_enrichment(d,a)

    def test_unspecified_step_node_needs_explicit_project_binding(self):
        from test_measurement_plan import build
        h,p,policy,s,m,e=build();selected=deepcopy(s)
        row=next(x for x in selected['items'] if x['source']['symbol']=='ts')
        overrides=row['source']['conditions']['overrides'];step=overrides.pop('input_step_V');overrides['step_amplitude_V']=step
        with self.assertRaisesRegex(ValueError,'engineering input-step binding'):build_measurements(selected,h,policy['engineering_defaults'])
        profile={**policy['engineering_defaults'],'settling_input_step_V':step}
        result=build_measurements(selected,h,profile);recipe=next(x for x in result['measurements'] if x['symbol']=='ts')['method']['definition']
        self.assertEqual(recipe['input_step_V'],step)
        self.assertEqual(recipe['input_signal_binding_origin'],'explicit_project_policy_not_source_node_identification')
        profile['settling_input_step_V']=step+1
        with self.assertRaisesRegex(ValueError,'differs from source'):build_measurements(selected,h,profile)

    def test_source_rail_aliases_are_normalized_and_unknown_rails_rejected(self):
        from test_measurement_plan import build
        h,p,policy,s,m,e=build();selection=deepcopy(s)
        changed=next(x for x in selection['items'] if x['required_in_project'] and x['source']['symbol']=='VO')
        row=changed['source'];source_rail=row['conditions']['overrides']['output_rail']
        alias={'V_plus':'positive','V_minus':'negative'}[source_rail]
        row['conditions']['overrides']['output_rail']=alias
        plan=build_measurements(selection,h,policy['engineering_defaults'])
        item=next(x for x in plan['measurements'] if x['row_id']==row['id'])
        self.assertEqual(item['resolved_conditions']['values']['output_rail'],alias)
        for case in item['cases']:
            self.assertEqual(case['fixture']['forced_output_rail'],source_rail)
            self.assertEqual(case['fixture']['load']['direction_selected_by_rail'],source_rail)
        row['conditions']['overrides']['output_rail']='unrecognized'
        with self.assertRaisesRegex(ValueError,'explicit positive/negative'):build_measurements(selection,h,policy['engineering_defaults'])

    def prepared_session(self,folder):
        pdf=folder/'source.pdf';pdf.write_bytes(b'Injected source fixture, not a physical PDF test')
        settings=folder/'settings.json';write_json(settings,{})
        doc=folder/'job/document';doc.mkdir(parents=True)
        write_json(doc/'01_pdf_inventory.json',{'sha256':file_hash(pdf)})
        write_json(doc/'02_page_plan.json',{'target_product':'X'})
        write_json(doc/'04_parse_summary.json',{'all_requested_pages_succeeded':True})
        write_json(doc/'spec_pipeline/spec_02_input_packet.json',{'source_document_fingerprint':'fixture'})
        s=startup.start(folder/'job',pdf,'X',settings)
        return pdf,s

    def test_document_start_cannot_skip_handoffs_and_source_changes_block_resume(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp);pdf,s=self.prepared_session(folder)
            self.assertEqual(s['status'],'awaiting_spec_annotations')
            self.assertFalse(s['past_circuit_imported']);self.assertFalse(s['history_imported'])
            pdf.write_bytes(b'changed')
            with self.assertRaises(ValueError):startup.resume(folder/'job')

    def test_bad_initial_reply_can_be_corrected_then_joins_operational_loop(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp);_,s=self.prepared_session(folder);job=folder/'job'
            d,selection,plan=self.data();packet=initial.make_initial_request(plan,self.admit(d,selection,plan),initial.load_harness.__defaults__[0])
            req=job/'initial/REQUEST.json';write_json(req,packet)
            s.update(status='awaiting_initial_design',pending_request={'path':str(req),'sha256':file_hash(req)})
            startup._save(job,s)
            reply={'request_id':packet['request_id'],'request_sha256':'wrong','summary':'Fixture new design','netlist':candidate()}
            path=folder/'response.json';write_json(path,reply)
            with self.assertRaises(ValueError):startup.submit(job,path)
            self.assertFalse((job/'initial/candidate.inc').exists())
            reply['request_sha256']=file_hash(req);write_json(path,reply)
            accepted=startup.submit(job,path)
            self.assertEqual(accepted['status'],'validating_initial_design')
            self.assertEqual(accepted['invalid_initial_responses'],1)
            def begin(*args):
                write_json(Path(args[0])/'STATE.json',{'synthetic':True})
            with patch.object(startup,'run_pipeline') as sim, \
                 patch.object(startup.workflow,'start',side_effect=begin) as begin_loop, \
                 patch.object(startup.workflow,'resume',return_value={'status':'awaiting_chat_designer','pending_request':{'path':'new-request'}}):
                resumed=startup.resume(job,'injected-EDA')
            sim.assert_called_once();begin_loop.assert_called_once()
            self.assertEqual(resumed['status'],'operational_loop')
            self.assertEqual(Path(begin_loop.call_args.args[2]),job/'initial/candidate.inc')


if __name__=='__main__':unittest.main()
