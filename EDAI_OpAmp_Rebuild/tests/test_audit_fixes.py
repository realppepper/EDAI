from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from opamp_pipeline.pdf_03_render_pages import save_json
from opamp_pipeline.pdf_04_parse_layout import parse_layout
from opamp_pipeline.support.parse_identity import parse_image_issues
from opamp_pipeline.support.execution_state import PipelineExecution,require_current_spec
from opamp_pipeline.support.source_checks import fingerprint
from opamp_pipeline.support.graph_conditions import graph_condition_annotations
from opamp_pipeline.support.condition_annotations import validate_condition_annotations
from opamp_pipeline.chart_02_verify import apply_chart_review,link_to_specs
from test_chart_references import fixture


class AuditFixes(unittest.TestCase):
    def test_aol_style_missing_replacement_is_detected(self):
        sets={'default':{'output_voltage_expression':'VS/2'}}
        c={'inherits':'default','overrides':{'output_voltage_V':{'min':1,'max':11}}}
        self.assertTrue(validate_condition_annotations(c,sets))
        c['inheritance_replacements']={'output_voltage_expression':'output_voltage_V'}
        self.assertEqual(validate_condition_annotations(c,sets),[])

    def test_graph_links_are_idempotent(self):
        c,r=fixture();refs=apply_chart_review(c,r)
        specs={'source_sha256':'hash','target_product':'OP','electrical_specs':[{'id':'R1','symbol':'VO'}]}
        once=link_to_specs(specs,refs);twice=link_to_specs(once,refs)
        self.assertEqual(once,twice)
        self.assertEqual(twice['electrical_specs'][0]['related_graph_ids'],['G1'])

    def test_graph_aliases_supply_sweep_and_trace_conditions(self):
        metadata={'conditions':{'original_common_conditions':{'supply_voltage_V':36,'rails_V':[18,-18],
            'load_connected_to':'VS/2','load_resistance_Ohm':10000},
            'local_overrides':{'load_connection':'V_minus','load_resistance':'open','supply_voltage_V':15},
            'swept_quantity':'Supply Voltage'},'traces':[{'label':'VS=5V'}]}
        before=deepcopy(metadata);result=graph_condition_annotations(metadata)
        self.assertEqual(result['local_conditions_canonical']['load_connected_to'],'V_minus')
        self.assertEqual(result['local_conditions_canonical']['load_resistance_Ohm'],{'kind':'open_circuit'})
        self.assertIn('rails_V',result['invalidated_common_fields'])
        self.assertIn('supply_voltage_V',result['invalidated_common_fields'])
        self.assertEqual(result['trace_conditions'][0]['overrides']['supply_voltage_V'],5)
        self.assertFalse(result['effective_conditions_generated']);self.assertEqual(metadata,before)

    def test_parse_and_image_hash_mismatch_is_detected(self):
        img={'pdf_page':3,'image_sha256':'new','roles':['target_specs']}
        parsed={'pdf_page':3,'source_sha256':'pdf','image_sha256':'old','roles':['target_specs']}
        self.assertTrue(parse_image_issues(parsed,img,'pdf',verify_bytes=False))

    def test_printed_frequency_is_not_automatically_a_fixed_sweep_condition(self):
        m={'conditions':{'original_common_conditions':{},'local_overrides':{'input_frequency_Hz_printed':1000},'swept_quantity':'Frequency'}}
        result=graph_condition_annotations(m)
        self.assertNotIn('input_frequency_Hz_printed',result['local_conditions_canonical'])
        self.assertEqual(result['unresolved_printed_annotations']['input_frequency_Hz_printed'],1000)
        self.assertIn('frequency_Hz',result['swept_fields'])

    def test_cache_rebinds_identity_and_recovers_corrupt_json(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);image=root/'page.png';image.write_bytes(b'pixels')
            manifest={'completed':True,'source_sha256':'first','requested_pages':[6],
                'images':[{'pdf_page':6,'roles':['old'],'image_path':str(image),'image_sha256':hashlib.sha256(b'pixels').hexdigest()}]}
            path=root/'manifest.json';save_json(path,manifest)
            response={'content':'Content<class_Text>','finish_reason':'stop'}
            with patch('opamp_pipeline.pdf_04_parse_layout.request_page',return_value=response) as request:
                parse_layout(path,root,'dummy')
                manifest['source_sha256']='second';manifest['images'][0]['roles']=['new'];save_json(path,manifest)
                result=parse_layout(path,root,'dummy')
                self.assertEqual(request.call_count,1);self.assertEqual(result['new_api_attempts'],0)
                saved=json.loads((root/'pages/page_0006.json').read_text())
                self.assertEqual(saved['source_sha256'],'second');self.assertEqual(saved['roles'],['new'])
                (root/'pages/page_0006.json').write_text('{bad')
                parse_layout(path,root,'dummy');self.assertEqual(request.call_count,2)

    def test_generation_rejects_pending_stale_inputs_and_modified_final(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);out=root/'spec_pipeline';source=root/'input.json';save_json(source,{'v':1})
            base={'base':1};enriched={'enriched':1};final={'electrical_specs':[],'source_sha256':'hash','target_product':'OP'}
            with PipelineExecution(out,[source]) as job:
                save_json(out/'spec_01_rows.json',base);save_json(out/'spec_02_enriched_rows.json',enriched)
                job.update(base_fingerprint=fingerprint(base),enriched_document_fingerprint=fingerprint(enriched))
                final['_execution']=job.provenance();save_json(out/'spec_03_result.json',final)
                job.complete(out/'spec_03_result.json',stage='done')
            self.assertEqual(require_current_spec(root,out/'spec_03_result.json'),final)
            save_json(source,{'v':2})
            with self.assertRaises(ValueError):require_current_spec(root,out/'spec_03_result.json')
            save_json(source,{'v':1});changed=deepcopy(final);changed['target_product']='OTHER';save_json(out/'spec_03_result.json',changed)
            with self.assertRaises(ValueError):require_current_spec(root,out/'spec_03_result.json')
            save_json(out/'spec_03_result.json',final)
            with PipelineExecution(out,[source]) as job:job.update(stage='awaiting_annotations')
            with self.assertRaises(ValueError):require_current_spec(root,out/'spec_03_result.json')

    def test_failed_execution_does_not_publish_complete(self):
        with tempfile.TemporaryDirectory() as directory:
            out=Path(directory)
            with self.assertRaises(RuntimeError):
                with PipelineExecution(out) as job:raise RuntimeError('Failure')
            state=json.loads((out/'STATUS.json').read_text())
            self.assertFalse(state['completed']);self.assertEqual(state['stage'],'failed')

    def test_cli_failure_invalidates_old_result_before_graph_consumer(self):
        import sys
        import run_spec_pipeline
        import run_chart_references
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);out=root/'spec_pipeline'
            for n in ('01_pdf_inventory.json','02_page_plan.json','03_render_manifest.json'):save_json(root/n,{})
            save_json(out/'spec_03_result.json',{'old_result':True})
            with patch.object(sys,'argv',['runner','--run-dir',str(root)]),patch.object(run_spec_pipeline,'check_layout',side_effect=RuntimeError('bad input')):
                with self.assertRaises(RuntimeError):run_spec_pipeline.main()
            status=json.loads((out/'STATUS.json').read_text())
            self.assertFalse(status['completed']);self.assertEqual(status['stage'],'failed')
            with patch.object(sys,'argv',['runner','--run-dir',str(root)]),patch.object(run_chart_references,'collect_charts') as collect:
                with self.assertRaisesRegex(ValueError,'not complete'):run_chart_references.main()
                collect.assert_not_called()

    def test_final_generation_must_match_publisher(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            with self.assertRaises(ValueError):
                with PipelineExecution(root) as job:
                    save_json(root/'final.json',{'_execution':{'run_id':'old'}})
                    job.complete(root/'final.json')
            self.assertFalse(json.loads((root/'STATUS.json').read_text())['completed'])
