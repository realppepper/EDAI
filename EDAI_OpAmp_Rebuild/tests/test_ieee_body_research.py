import json,tempfile,unittest,urllib.error
from pathlib import Path
from copy import deepcopy
from unittest.mock import patch
from opamp_pipeline.ref_04_ieee_body import parse_body,fetch_article_body
from opamp_pipeline.ref_02_retrieve import read_body,normalize_paper
from opamp_pipeline.ref_05_research import search,read_selected,make_supplement,load_supplement,validate_usage,enrich_request,record_usage
from opamp_pipeline.ref_06_attach import attach
from opamp_pipeline.support.source_checks import fingerprint
from opamp_pipeline.support.execution_state import file_hash
from opamp_pipeline.loop_02_handoff import write_json

XML='<response><body><sec id="s1"><title>Compensation</title><p>'+('Compensation stability depends on the loop and load. '*12)+'</p><p>'+('A design requires current and phase margin tradeoffs. '*12)+'</p><fig id="f1"><caption>A caption is not a retrieved circuit image.</caption></fig></sec></body></response>'


class IEEEBodyResearchTests(unittest.TestCase):
    def seed(self,p,needed=True):
        request={'request_id':'request-1','requirements':[{'cases':[{'case_id':'c1'}]}],
                 'candidate_sha256':'candidate','response_schema':{'netlist':'complete'}}
        decision={'source_request_id':'request-1','needed':needed,'reason':'Understand compensation constraints',
                  'query':'amplifier compensation','keywords':['compensation','stability'],'case_ids':['c1']}
        write_json(p/'request.json',request);write_json(p/'decision.json',decision)
        papers=[normalize_paper({'title':'Compensation','article_number':str(i),'doi':f'10.1/{i}','abstract':'Abstract only'}) for i in (1,2,3)]
        with patch('opamp_pipeline.ref_05_research.retrieve',return_value={'ok':True,'papers':papers,'external_search_calls':1}):
            search(p/'request.json',p/'decision.json',p/'research','unused','unused')
        return request,decision

    def body_packet(self,p):
        request,decision=self.seed(p)
        with patch('opamp_pipeline.ref_02_retrieve._invoke_read',return_value=parse_body(XML,'1')):
            read_selected(p/'research','1','unused','unused',p/'cache')
        return request,make_supplement(p/'research')

    def test_body_and_figure_caption_have_explicit_scopes(self):
        result=parse_body(XML,'1')
        self.assertTrue(result['full_text_retrieved']);self.assertEqual(len(result['blocks']),3)
        self.assertFalse(result['schematic_retrieved']);self.assertFalse(result['design_equations_verified'])

    def test_metadata_abstract_and_entities_not_accepted_as_full_text(self):
        for bad in ['<response><abstract>Only metadata</abstract></response>',
                    '<body><abstract><p>'+('x'*900)+'</p></abstract></body>',
                    '<html><body><p>'+('login '*100)+'</p><p>'+('terms '*100)+'</p></body></html>',
                    '<!DOCTYPE x><body><p>bad</p></body>']:
            with self.assertRaises(ValueError):parse_body(bad,'1')

    def test_http_error_never_exposes_key_or_claims_body(self):
        error=urllib.error.HTTPError('https://api/?apikey=private-key',403,'denied',None,None)
        with patch('urllib.request.urlopen',side_effect=error):r=fetch_article_body('1','private-key')
        self.assertFalse(r['full_text_retrieved']);self.assertTrue(r['access_denied'])
        self.assertNotIn('private-key',json.dumps(r))

    def test_body_cache_reuse_requires_no_network(self):
        with tempfile.TemporaryDirectory() as d:
            with patch('opamp_pipeline.ref_02_retrieve._invoke_read',return_value=parse_body(XML,'1')) as call:
                first=read_body('1','need',d,'unused','unused');self.assertEqual(call.call_count,1)
            with patch('opamp_pipeline.ref_02_retrieve._invoke_read',side_effect=AssertionError('network forbidden')):
                second=read_body('1','need',d,'unused','unused')
            self.assertEqual(first['external_body_calls'],1);self.assertEqual(second['external_body_calls'],0)

    def test_successful_metadata_payload_is_not_cached_as_body(self):
        with tempfile.TemporaryDirectory() as d,patch('opamp_pipeline.ref_02_retrieve._invoke_read',return_value={'ok':True,'abstract':'not body'}):
            r=read_body('1','need',d,'unused','unused')
            self.assertFalse(r['ok']);self.assertEqual(list(Path(d).glob('*.json')),[])

    def test_not_needed_means_zero_search_or_body_calls(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);request,decision=self.seed(p)
            decision['needed']=False;write_json(p/'skip.json',decision)
            with patch('opamp_pipeline.ref_05_research.retrieve',side_effect=AssertionError('network forbidden')):
                state=search(p/'request.json',p/'skip.json',p/'skipped','unused','unused')
            self.assertEqual(state['status'],'not_needed');self.assertEqual(state['external_search_calls'],0)

    def test_two_paper_budget_and_selection_boundary(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);self.seed(p)
            def read(number,*args):return {'ok':False,'full_text_retrieved':False,'external_body_calls':1,'cache_hit':False,'error':'denied'}
            with patch('opamp_pipeline.ref_05_research.read_body',side_effect=read):
                with self.assertRaises(ValueError):read_selected(p/'research','99','unused','unused')
                read_selected(p/'research','1','unused','unused');read_selected(p/'research','2','unused','unused')
                with self.assertRaises(ValueError):read_selected(p/'research','3','unused','unused')
            s=make_supplement(p/'research');self.assertEqual(s['body_excerpt_characters'],0)
            self.assertFalse(any(r['full_text_retrieved'] for r in s['reference_papers']))

    def test_excerpt_provenance_budget_and_stale_request(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);request,s=self.body_packet(p)
            self.assertGreater(s['body_excerpt_characters'],0);self.assertLessEqual(s['body_excerpt_characters'],6000)
            load_supplement(p/'research/SUPPLEMENT.json',p/'request.json')
            request['request_id']='other';write_json(p/'request.json',request)
            with self.assertRaises(ValueError):load_supplement(p/'research/SUPPLEMENT.json',p/'request.json')

    def test_forged_excerpt_rejected_even_with_recomputed_fingerprint(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);_,s=self.body_packet(p)
            s['reference_papers'][0]['body_excerpts'][0]['text']='invented finding'
            s['fingerprint']=fingerprint({k:v for k,v in s.items() if k!='fingerprint'})
            write_json(p/'research/SUPPLEMENT.json',s)
            with self.assertRaises(ValueError):load_supplement(p/'research/SUPPLEMENT.json',p/'request.json')

    def test_usage_requires_real_citations_or_reason_for_not_using(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);request,s=self.body_packet(p);r=enrich_request(request,s)
            with self.assertRaises(ValueError):validate_usage(r,{})
            validate_usage(r,{'literature_use':[],'literature_not_used_reason':'Different topology'})
            paper=s['reference_papers'][0];e=paper['body_excerpts'][0]
            validate_usage(r,{'literature_use':[{'paper_id':paper['id'],'excerpt_ids':[e['excerpt_id']],'application':'Hypothesis about compensation'}]})
            with self.assertRaises(ValueError):validate_usage(r,{'literature_use':[{'paper_id':paper['id'],'excerpt_ids':['invented'],'application':'claim'}]})

    def test_attach_versions_request_without_charging_design_budget(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);request,s=self.body_packet(p);old=(p/'request.json').read_bytes()
            state={'status':'awaiting_chat_designer','pending_request':{'path':str(p/'request.json'),'sha256':file_hash(p/'request.json'),'request_id':request['request_id']},'candidates':[{'index':0}],'max_candidates':3}
            with patch('opamp_pipeline.harness_03_loop.load',return_value=state),patch('opamp_pipeline.harness_03_loop.save'):
                result=attach(p,p/'research/SUPPLEMENT.json')
            updated=json.loads(Path(result['pending_request']['path']).read_text(encoding='utf-8'))
            self.assertEqual(updated['requirements'],request['requirements'])
            self.assertEqual(updated['candidate_sha256'],request['candidate_sha256'])
            self.assertEqual((p/'request.json').read_bytes(),old)
            self.assertNotEqual(updated['request_id'],request['request_id'])
            self.assertEqual(len(result['candidates']),1);self.assertEqual(result['max_candidates'],3)

    def test_initial_attach_uses_same_source_bound_interface(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);request,s=self.body_packet(p)
            state={'status':'awaiting_initial_design','pending_request':{'path':str(p/'request.json'),'sha256':file_hash(p/'request.json')}}
            with patch('opamp_pipeline.startup_02_datasheet.load',return_value=state),patch('opamp_pipeline.startup_02_datasheet._save'):
                result=attach(p,p/'research/SUPPLEMENT.json','initial')
            self.assertEqual(result['status'],'awaiting_initial_design')
            self.assertIn('request_id',result['pending_request'])

    def test_declared_usage_is_recorded_without_claiming_causality(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);request,s=self.body_packet(p);r=enrich_request(request,s)
            state={'pending_request':{'path':'new.json'},'literature_request_history':[{'new_request':'new.json','design_usage':'not_yet_reported'}]}
            response={'literature_use':[],'literature_not_used_reason':'Different stage count'}
            record_usage(state,r,response);record_usage(state,r,response)
            self.assertEqual(len(state['literature_use_reports']),1)
            self.assertEqual(state['literature_request_history'][0]['design_usage'],'declared_not_used')
            self.assertIn('not proof',state['literature_use_reports'][0]['meaning'])
