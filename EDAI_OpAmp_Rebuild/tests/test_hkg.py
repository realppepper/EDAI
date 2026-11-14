from copy import deepcopy
import json
from pathlib import Path
import unittest
from opamp_pipeline.hkg_01_build import build_hkg
from opamp_pipeline.hkg_02_validate import validate_hkg
from opamp_pipeline.hkg_query import specification_contexts


def fixture():
    rows=[]
    for index,symbol in enumerate(['En','en']):
        rows.append({'id':'R'+str(index),'symbol':symbol,'name':'Noise','unit':'uV' if index==0 else 'nV/sqrt(Hz)',
            'limits':{'min':None,'typ':3 if index==0 else 40,'max':None},'printed_notation':{},'notes':[],
            'conditions':{'inherits':'common','overrides':{'ambient_temperature_C':{'min':-40,'max':85}}},
            'source':{'pdf_page':6},'verification':{'status':'partial','llm_semantic_review':{'status':'reviewed_match'}},
            'original_cell_evidence':{},'evaluation_temperature_scope':{'adopted_as_design_target':False}})
    return {'source_sha256':'abcdef1234567890','source_filename':'source.pdf','target_product':'OP',
        'electrical_specs':rows,'condition_sets':{'common':{'source_pages':[6],'ambient_temperature_C':25}},
        'operating_conditions':[{'id':'OP1','source_page':5,'verification_status':'pending'}],
        'behavior_constraints':[],'deferred_information':[{'type':'pins','source_pages':[3],'status':'pending'}],
        'coverage':{'whole_document_requirements_complete':False},'characteristic_graphs':[]}


class HKG(unittest.TestCase):
    def test_incomplete_reference_generation_cannot_feed_hkg(self):
        import tempfile
        from opamp_pipeline.pdf_03_render_pages import save_json
        from opamp_pipeline.support.execution_state import PipelineExecution,require_current_references,spec_core
        from opamp_pipeline.support.source_checks import fingerprint
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);spec_out=root/'spec_pipeline';chart_out=root/'chart_pipeline'
            base={'a':1};enriched={'b':2};source=fixture();source.pop('characteristic_graphs')
            for row in source['electrical_specs']:row.pop('evaluation_temperature_scope',None)
            with PipelineExecution(spec_out) as job:
                save_json(spec_out/'spec_01_rows.json',base);save_json(spec_out/'spec_02_enriched_rows.json',enriched)
                job.update(base_fingerprint=fingerprint(base),enriched_document_fingerprint=fingerprint(enriched))
                source['_execution']=job.provenance();save_json(spec_out/'spec_03_result.json',source)
                job.complete(spec_out/'spec_03_result.json',stage='done')
            linked=deepcopy(source)
            linked['characteristic_graphs']=[]
            linked['linked_spec_document_fingerprint']=fingerprint(spec_core(linked))
            with PipelineExecution(chart_out) as job:
                linked['_graph_execution']=job.provenance();save_json(chart_out/'spec_with_chart_references.json',linked)
                job.complete(chart_out/'spec_with_chart_references.json',stage='done',linked_spec_complete=True)
            self.assertEqual(require_current_references(root),linked)
            state=json.loads((chart_out/'STATUS.json').read_text());state['completed']=False;save_json(chart_out/'STATUS.json',state)
            with self.assertRaises(ValueError):require_current_references(root)

    def test_deterministic_source_preserving_graph(self):
        source=fixture();before=deepcopy(source);graph=build_hkg(source,68)
        self.assertEqual(graph,build_hkg(source,68));self.assertEqual(source,before)
        self.assertEqual(validate_hkg(graph,source)['specifications'],2)
        context=specification_contexts(graph,symbol='En')
        self.assertEqual(len(context),1);self.assertEqual(context[0]['specification']['unit'],'uV')
        self.assertEqual(len(specification_contexts(graph,symbol='en')),1)
        self.assertFalse(context[0]['effective_conditions_generated'])
        conditions=context[0]['linked_context']['has_condition_interpretation'][0]['data']['source_conditions']
        self.assertEqual(conditions['overrides']['ambient_temperature_C'],{'min':-40,'max':85})

    def test_corrupt_values_links_or_review_state_rejected(self):
        for corruption in ('value','edge','review','context','local'):
            source=fixture();graph=build_hkg(source)
            if corruption=='value':next(n for n in graph['nodes'] if n['type']=='SpecLimit')['data']['value']=999
            if corruption=='edge':graph['edges'][0]['target']='MISSING'
            if corruption=='review':next(n for n in graph['nodes'] if n['type']=='Verification')['data']['status']='all_verified'
            if corruption=='context':next(n for n in graph['nodes'] if n['type']=='OperatingCondition')['data']['verification_status']='verified'
            if corruption=='local':next(n for n in graph['nodes'] if n['type']=='LocalConditions')['data']['overrides']={}
            with self.subTest(corruption=corruption),self.assertRaises(ValueError):validate_hkg(graph,source)

    def test_unknown_condition_duplicate_rows_and_invalid_pages_rejected(self):
        for corruption in ('condition','row','page'):
            source=fixture()
            if corruption=='condition':source['electrical_specs'][0]['conditions']['inherits']='UNKNOWN'
            if corruption=='row':source['electrical_specs'].append(deepcopy(source['electrical_specs'][0]))
            if corruption=='page':source['electrical_specs'][0]['source']['pdf_page']=69
            with self.subTest(corruption=corruption),self.assertRaises(ValueError):build_hkg(source,68)

    def test_actual_lm358b_round_trip_and_unverified_graph_state(self):
        root=Path(__file__).resolve().parents[1]
        path=root/'runs/lm358b_overview_20261112/chart_pipeline/spec_with_chart_references.json'
        if not path.exists():self.skipTest('No local fixture')
        source=json.loads(path.read_text(encoding='utf-8'));graph=build_hkg(source,68)
        checked=validate_hkg(graph,source)
        self.assertEqual(checked['specifications'],42);self.assertEqual(checked['reference_graphs'],38)
        aol=specification_contexts(graph,symbol='AOL');self.assertEqual(len(aol),2)
        for context in aol:
            interpretation=context['linked_context']['has_condition_interpretation'][0]['data']
            self.assertEqual(interpretation['source_conditions']['inheritance_replacements']['output_voltage_expression'],'output_voltage_V')
        for node in graph['nodes']:
            if node['type']=='CharacteristicGraph':self.assertFalse(node['data']['numeric_data']['approved_for_design'])
        self.assertFalse(graph['generated_pdg']);self.assertFalse(graph['generated_test_plan'])
