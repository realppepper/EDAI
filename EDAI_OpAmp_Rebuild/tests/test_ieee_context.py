import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from opamp_pipeline.ref_01_ieee_server import search_metadata,load_key
from opamp_pipeline.ref_02_retrieve import normalize_paper,retrieve
from opamp_pipeline.ref_03_design_context import make_context,make_prompt


class IEEEContextTests(unittest.TestCase):
    def test_missing_key_is_explicit(self):
        self.assertFalse(search_metadata('amplifier',3,None)['ok'])

    def test_metadata_is_not_full_text_or_design_rules(self):
        p=normalize_paper({'title':'<i>Amp</i> &amp; B','doi':'10.123/test','abstract':'Text'})
        self.assertEqual(p['title'],'Amp & B')
        self.assertEqual(p['url'],'https://doi.org/10.123/test')
        self.assertFalse(p['full_text_retrieved']);self.assertFalse(p['design_equations_verified'])

    def test_credentials_only_selected_key(self):
        with tempfile.TemporaryDirectory() as folder,patch.dict('os.environ',{},clear=True):
            f=Path(folder)/'config';f.write_text('OTHER_KEY=ignore\nIEEE_API_KEY="example-key"\n',encoding='utf-8')
            self.assertEqual(load_key(f),'example-key')

    def test_cache_reuse_does_not_call_mcp(self):
        def fake(*args):return {'ok':True,'papers':[{'title':'Amp','doi':'10.1/x'}]}
        with tempfile.TemporaryDirectory() as folder:
            with patch('opamp_pipeline.ref_02_retrieve._invoke',fake):
                first=retrieve('amp',3,folder,'unused','unused')
            with patch('opamp_pipeline.ref_02_retrieve._invoke',side_effect=AssertionError('network forbidden')):
                second=retrieve('amp',3,folder,'unused','unused')
            self.assertEqual(first['external_search_calls'],1)
            self.assertEqual(second['external_search_calls'],0);self.assertTrue(second['cache_hit'])

    def test_search_failure_never_invents_references(self):
        c=make_context({'measurements':[]},[{'ok':False,'papers':[{'id':'fake'}]}])
        self.assertEqual(c['reference_papers'],[]);self.assertFalse(c['llm_invoked'])

    def test_prompt_shortening_does_not_mutate_saved_abstract(self):
        p=normalize_paper({'title':'x','abstract':'a'*2500})
        c=make_context({'measurements':[]},[{'ok':True,'papers':[p]}])
        self.assertEqual(len(p['abstract']),2500)
        self.assertTrue(c['reference_papers'][0]['abstract_truncated_for_prompt'])

    def test_compact_input_keeps_unimplemented_targets(self):
        context={'required_rows':[{'row_id':'r1','symbol':'noise','target':{'max':40},'source_page':6,
                 'analyses':['noise'],'cases':[{'case_id':'future'}]}],
                 'previous_experiment':None,'current_candidate_netlist':None,'reference_papers':[],
                 'reference_rules':[],'source_priority':[],'provenance':{}}
        prompt=make_prompt(context)
        self.assertEqual(prompt['required_rows'][0]['target'],{'max':40})
        self.assertEqual(prompt['required_rows'][0]['current_adapter_status'],'not_qualified_in_current_loop')
        self.assertTrue(prompt['omitted_conditions_are_not_proven_or_waived'])

    def test_broken_cache_is_refetched(self):
        def fake(*args):return {'ok':True,'papers':[]}
        with tempfile.TemporaryDirectory() as folder,patch('opamp_pipeline.ref_02_retrieve._invoke',fake):
            retrieve('amp',3,folder,'unused','unused')
            next(Path(folder).glob('*.json')).write_text('{broken',encoding='utf-8')
            result=retrieve('amp',3,folder,'unused','unused')
            self.assertTrue(result['ok']);self.assertFalse(result['cache_hit'])
