import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from opamp_pipeline import ref_07_datasheet as refs
from opamp_pipeline.support.execution_state import file_hash
from opamp_pipeline.support.source_checks import fingerprint
from opamp_pipeline.loop_02_handoff import write_json


class DatasheetReferenceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.doc=self.root/'document';self.doc.mkdir()
        pdf=self.doc/'source.pdf';pdf.write_bytes(b'fixed-test-source');sha=file_hash(pdf)
        write_json(self.doc/'01_pdf_inventory.json',{'source_pdf':str(pdf),'sha256':sha})
        pages=[{'pdf_page':n,'category':'reference_candidate' if n!=6 else 'primary_candidate',
            'roles':['behavior_and_structure_reference'],'evidence':[{'title':'Operation'}]} for n in [6,25,26,27]]
        write_json(self.doc/'02_page_plan.json',{'source_sha256':sha,'target_product':'TEST','pages':pages})
        imgs=[]
        for n in [25,26,27]:
            img=self.doc/f'p{n}.png';img.write_bytes(b'opaque-image-'+str(n).encode())
            imgs.append({'pdf_page':n,'image_path':str(img),'image_sha256':file_hash(img),'roles':['behavior_and_structure_reference']})
            write_json(self.doc/f'pages/page_{n:04d}.json',{'pdf_page':n,'source_sha256':sha,'image_sha256':file_hash(img),
                'status':'ok','roles':imgs[-1]['roles'],'blocks':[{'type':'text','text':'Physical behavior. '*400},
                    {'type':'picture','text':'unverified transistor connections'},
                    {'type':'chart','text':'unverified numeric estimates'}]})
        write_json(self.doc/'03_render_manifest.json',{'source_sha256':sha,'images':imgs})
        self.request={'requirements':[{'cases':[{'case_id':'case1'}]}],'response_schema':{},'candidate_netlist':'unchanged'}
        refs.add_catalog(self.request,self.doc)
        self.request['request_id']=fingerprint(self.request)
        self.req=self.root/'REQUEST.json';write_json(self.req,self.request)
        self.choice={'source_request_id':self.request['request_id'],'needed':True,'reason':'Need physical context',
            'pages':[{'pdf_page':25,'reason':'Architecture reference','case_ids':['case1']}]}

    def prepare(self,decision=None):
        d=self.root/'decision.json';write_json(d,decision or self.choice)
        p=self.root/'SUPPLEMENT.json'
        return p,refs.prepare(self.req,d,p)

    def test_catalog_has_metadata_only_and_skip_reads_no_reference(self):
        c=refs.read(self.request['optional_datasheet_references']['reference_catalog']['path'])
        self.assertNotIn('text',str(c));self.assertNotIn(6,[p['pdf_page'] for p in c['pages']])
        with patch.object(refs,'catalog',side_effect=AssertionError('No page material needed')):
            _,p=self.prepare({'source_request_id':self.request['request_id'],'needed':False,'reason':'Routine sizing'})
        self.assertEqual(p['references'],[]);self.assertEqual(p['external_calls'],0)

    def test_selected_pages_bounded_text_and_real_image_pointer(self):
        path,p=self.prepare()
        r=p['references'][0]
        self.assertEqual([r['pdf_page']],[25]);self.assertLessEqual(p['text_characters'],4000)
        self.assertNotIn('unverified numeric',str(r));self.assertFalse(r['acceptance_criterion'])
        self.assertTrue(Path(r['page_image']['path']).exists())
        self.assertEqual(refs.load_packet(path,self.req),p)
        self.assertFalse(r['page_image']['visual_interpretation_verified'])

    def test_source_image_and_recomputed_forgery_rejected(self):
        path,p=self.prepare();p['references'][0]['text_excerpts'][0]['text']='invented'
        p.pop('fingerprint');p['fingerprint']=fingerprint(p);write_json(path,p)
        with self.assertRaises(ValueError):refs.load_packet(path,self.req)
        img=self.doc/'p25.png';img.write_bytes(b'changed')
        with self.assertRaises(ValueError):refs._build(self.req,self.choice)

    def test_unknown_pages_duplicate_ids_limits_and_stale_request_rejected(self):
        for change in [{'pages':[{'pdf_page':6,'reason':'not reference'}]},
                {'pages':self.choice['pages']*2}, {'pages':self.choice['pages']*3},
                {'source_request_id':'stale'}, {'pages':[{'pdf_page':25,'reason':'x','case_ids':['bad']}]}]:
            with self.subTest(change=change),self.assertRaises(ValueError):refs._build(self.req,{**self.choice,**change})

    def test_usage_is_exact_and_declared_once(self):
        _,p=self.prepare();r={**self.request,'datasheet_reference':p}
        with self.assertRaises(ValueError):refs.validate_usage(r,{})
        response={'datasheet_reference_use':[],'datasheet_reference_not_used_reason':'Not relevant to selected MOS topology'}
        refs.validate_usage(r,response)
        use={'reference_id':'DS-P25','excerpt_ids':[],'image_viewed':True,'application':'Architecture only'}
        response={'datasheet_reference_use':[use]};refs.validate_usage(r,response)
        with self.assertRaises(ValueError):refs.validate_usage(r,{'datasheet_reference_use':[{**use,'image_viewed':False}]})
        with self.assertRaises(ValueError):refs.validate_usage(r,{'datasheet_reference_use':[{**use,'excerpt_ids':['fake']}]})
        s={};refs.record_usage(s,r,response);refs.record_usage(s,r,response)
        self.assertEqual(len(s['datasheet_reference_use_reports']),1)

    def test_attach_versions_request_without_changing_targets_or_running_eda(self):
        from opamp_pipeline import harness_03_loop as fixed
        path,p=self.prepare();s={'status':'awaiting_chat_designer',
            'pending_request':{'path':str(self.req),'sha256':file_hash(self.req),'request_id':self.request['request_id']}}
        before=self.req.read_bytes()
        with patch.object(fixed,'load',return_value=s),patch.object(fixed,'save'),patch('subprocess.run',side_effect=AssertionError('No EDA')):
            refs.attach(self.root,path)
        new=refs.read(s['pending_request']['path'])
        self.assertEqual(self.req.read_bytes(),before)
        self.assertEqual(new['candidate_netlist'],self.request['candidate_netlist'])
        self.assertEqual(new['requirements'],self.request['requirements'])
        self.assertIn('datasheet_reference',new);self.assertEqual(s['datasheet_reference_history'][0]['design_budget_consumed'],0)

    def test_initial_attach_uses_initial_controller(self):
        from opamp_pipeline import startup_02_datasheet as startup
        path,_=self.prepare();s={'status':'awaiting_initial_design','pending_request':{
            'path':str(self.req),'sha256':file_hash(self.req),'request_id':self.request['request_id']}}
        with patch.object(startup,'load',return_value=s),patch.object(startup,'_save') as save:
            refs.attach(self.root,path,'initial')
        self.assertTrue(save.called)

    def test_derived_plan_catalog_link_requires_same_pdf_and_product(self):
        from opamp_pipeline import harness_03_loop as fixed
        derived=self.root/'derived';spec=derived/'spec_pipeline/spec_03_result.json'
        sha=refs.read(self.doc/'01_pdf_inventory.json')['sha256']
        write_json(spec,{'source_sha256':'wrong-pdf','target_product':'TEST'})
        bare={'requirements':self.request['requirements'],'response_schema':{},'request_id':'bare'}
        request=self.root/'BARE.json';write_json(request,bare)
        s={'status':'awaiting_chat_designer','run_dir':str(derived),
            'pending_request':{'path':str(request),'sha256':file_hash(request),'request_id':'bare'}}
        with patch.object(fixed,'load',return_value=s),patch.object(fixed,'save'):
            with self.assertRaises(ValueError):refs.connect_catalog(self.root,self.doc)
            write_json(spec,{'source_sha256':sha,'target_product':'TEST'})
            refs.connect_catalog(self.root,self.doc)
        new=refs.read(s['pending_request']['path'])
        self.assertIn('reference_catalog',new['optional_datasheet_references'])
        self.assertNotIn('datasheet_reference',new)
        self.assertEqual(refs.read(request),bare)
