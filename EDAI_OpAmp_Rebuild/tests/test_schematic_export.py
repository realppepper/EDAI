import tempfile
import unittest
import re
from pathlib import Path
from unittest.mock import patch
from opamp_pipeline import schematic_01_export as schematic
from opamp_pipeline import harness_03_loop as fixed
from opamp_pipeline.design_01_cmos_candidate import candidate
from opamp_pipeline.support.execution_state import file_hash


class SchematicTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.source=self.root/'candidate.inc'
        self.source.write_text(candidate(),encoding='ascii')
        self.record={'candidate_path':str(self.source),'candidate_sha256':file_hash(self.source)}

    def test_arbitrary_sizes_and_added_parts_roundtrip(self):
        text=candidate().replace('.ends FIRSTAMP','Rextra OUT VM 123k\nCextra P N 2p\n.ends FIRSTAMP')
        asc=schematic.drawing(text)
        self.assertEqual(schematic.verify_drawing(text,asc),len(schematic._elements(text)))
        for altered in [re.sub(r'(FLAG \d+ \d+ )\S+',r'\1WRONG_NODE',asc,count=1),
                        asc.replace('SYMATTR Value GNM','SYMATTR Value GPM',1),
                        asc.replace('SYMATTR Value 123K','SYMATTR Value 124K',1)]:
            with self.assertRaises(ValueError):schematic.verify_drawing(text,altered)

    def test_export_idempotent_preserves_tampering_and_source(self):
        before=self.source.read_bytes();out=self.root/'schematic'
        one=schematic.export(self.source,out)
        mtimes={p:Path(p).stat().st_mtime_ns for p in one['artifact_hashes']}
        self.assertEqual(one,schematic.export(self.source,out))
        self.assertEqual(mtimes,{p:Path(p).stat().st_mtime_ns for p in mtimes})
        self.assertEqual(before,self.source.read_bytes())
        p=Path(one['schematic_path']);p.write_text('edited')
        with self.assertRaises(ValueError):schematic.export(self.source,out)
        self.assertEqual(p.read_text(),'edited')

    def test_export_failure_can_resume_without_simulation(self):
        s={}
        with patch.object(schematic,'export',side_effect=OSError('disk unavailable')):
            schematic.complete(self.root,s,self.record)
        self.assertFalse(s['deliverables_complete'])
        self.assertEqual(s['schematic']['status'],'export_failed')
        with patch('subprocess.run',side_effect=AssertionError('No simulation allowed')):
            schematic.complete(self.root,s,self.record)
        self.assertTrue(s['deliverables_complete'])
        self.source.write_text(candidate(18e-12),encoding='ascii')
        schematic.complete(self.root,s,self.record)
        self.assertFalse(s['deliverables_complete'])

    def test_only_successful_final_candidate_exported_on_fixed_save(self):
        # No source is accessed for a budget-exhausted or pending loop.
        record={**self.record,'index':0,'assessment':{'scope_passed':False,'counts':{},'failed_case_ids':['x']}}
        state={'status':'candidate_budget_exhausted','candidates':[record], 'best_index':0,'harness_sha256':'test'}
        fixed.save(self.root,state)
        self.assertFalse((self.root/'schematic').exists())
        record['assessment']['scope_passed']=True
        state['status']='implemented_scope_passed'
        with patch('subprocess.run',side_effect=AssertionError('No simulation allowed')):
            fixed.save(self.root,state)
        self.assertTrue(state['deliverables_complete'])
        self.assertIn('FIRSTAMP.asc',(self.root/'REPORT.md').read_text(encoding='utf-8'))
        self.assertEqual(state['schematic']['source_sha256'],self.record['candidate_sha256'])

    def test_workflow_and_datasheet_finish_publish_selected_circuit(self):
        from opamp_pipeline import harness_07_workflow as workflow
        from opamp_pipeline import startup_02_datasheet as startup
        s={'status':'implemented_scope_passed','active':{**self.record,'policy_path':'policy.json'},
           'rounds':[],'max_rounds':1,'revisions_per_round':1}
        workflow._save(self.root/'workflow',s)
        self.assertTrue(s['deliverables_complete'])
        initial={'status':'operational_loop','document_dir':str(self.root/'document'),
                 'workflow_session':str(self.root/'workflow')}
        with patch.object(startup,'load',return_value=initial),patch.object(workflow,'load',return_value=s):
            end=startup.resume(self.root/'datasheet')
        self.assertTrue(end['deliverables_complete'])
        self.assertEqual(end['schematic']['source_sha256'],self.record['candidate_sha256'])
