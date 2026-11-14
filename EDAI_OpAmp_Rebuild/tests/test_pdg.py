from copy import deepcopy
import json
from pathlib import Path
import unittest
from opamp_pipeline.pdg_01_build import build_pdg,validate_annotations
from opamp_pipeline.pdg_02_validate import validate_pdg
from opamp_pipeline.support.source_checks import fingerprint


def fixture():
    hkg={'source_sha256':'hash','target_product':'AMP','nodes':[{'id':'H1','type':'SourcePage','label':'PDF1'}]}
    packet={'source_sha256':'hash','target_product':'AMP','hkg_fingerprint':fingerprint(hkg),
        'source_pages':{'1':{'text':'Positive input and output. Supply is connected.'}},'hkg_reference_index':hkg['nodes']}
    evidence=[{'pdf_page':1,'quote':'Positive input and output.'}]
    nodes=[{'key':key,'type':'Port','label':key,'data':{'role':role,'reference_pin_numbers':{'P8':number}},
        'evidence':deepcopy(evidence),'hkg_refs':['H1']} for key,role,number in [('IN','input',1),('OUT','output',2)]]
    annotation={'packet_fingerprint':fingerprint(packet),'reviewer':{'method':'test'},'nodes':nodes,
        'package_profiles':{'P8':{'pin_count':8}},'dependencies':[{'source':'IN','target':'OUT','relation':'signal_dependency',
        'basis':'engineering_interpretation','minimum_delay_s':None,'imposes_temporal_order':False,'evidence':evidence}],
        'timing_constraints':[],'ordering_exceptions':[]}
    return hkg,packet,annotation


class PDG(unittest.TestCase):
    def test_deterministic_dependency_graph_preserves_unknown_delay(self):
        h,p,a=fixture();before=deepcopy(a);g=build_pdg(h,p,a)
        self.assertEqual(g,build_pdg(h,p,a));self.assertEqual(a,before)
        self.assertIsNone(g['edges'][0]['minimum_delay_s']);self.assertFalse(g['ready_for_test_execution'])
        self.assertFalse(g['test_plan_generated']);self.assertEqual(validate_pdg(g,h,p,a)['edges'],1)

    def test_invalid_quotes_hkg_refs_pins_and_invented_timing_rejected(self):
        for problem in ('quote','hkg','pin','order','delay','relation','endpoint','stale'):
            h,p,a=fixture()
            if problem=='quote':a['nodes'][0]['evidence'][0]['quote']='Not in original source'
            if problem=='hkg':a['nodes'][0]['hkg_refs']=['UNKNOWN']
            if problem=='pin':a['nodes'][0]['data']['reference_pin_numbers']['P8']=9
            if problem=='order':a['dependencies'][0]['imposes_temporal_order']=True
            if problem=='delay':a['dependencies'][0]['minimum_delay_s']=4e-6
            if problem=='relation':a['dependencies'][0]['relation']='must_precede'
            if problem=='endpoint':a['dependencies'][0]['target']='IN'
            if problem=='stale':a['packet_fingerprint']='old'
            with self.subTest(problem=problem),self.assertRaises(ValueError):build_pdg(h,p,a)

    def test_duplicate_physical_pin_not_accepted(self):
        h,p,a=fixture();a['nodes'][1]['data']['reference_pin_numbers']['P8']=1
        with self.assertRaises(ValueError):validate_annotations(p,a)

    def test_modified_final_graph_rejected(self):
        h,p,a=fixture();g=build_pdg(h,p,a);g['edges'][0]['minimum_delay_s']=4e-6
        with self.assertRaises(ValueError):validate_pdg(g,h,p,a)

    def test_actual_lm358b_pins_and_no_mandatory_power_before_input(self):
        root=Path(__file__).resolve().parents[1];run=root/'runs/lm358b_overview_20261112'
        path=run/'pdg_pipeline/pdg_01_input_packet.json'
        if not path.exists():self.skipTest('No local fixture')
        p=json.loads(path.read_text(encoding='utf-8'))
        h=json.loads((run/'hkg_pipeline/hkg_01_graph.json').read_text(encoding='utf-8'))
        a=json.loads((root/'manual_inputs/lm358b_pdg_annotations.json').read_text(encoding='utf-8'))
        g=build_pdg(h,p,a);validate_pdg(g,h,p,a)
        ports={n['label']:n for n in g['nodes'] if n['type']=='Port'}
        self.assertEqual(len(ports),8);self.assertEqual(g['summary']['channels'],2)
        self.assertEqual(ports['IN1-']['data']['reference_pin_numbers']['8_pin_common'],2)
        self.assertEqual(ports['IN2-']['data']['reference_pin_numbers']['8_pin_common'],6)
        self.assertEqual(ports['V+']['data']['reference_pin_numbers']['8_pin_common'],8)
        self.assertEqual(len(g['timing_constraints']),0)
        self.assertTrue(g['ordering_exceptions'][0]['does_not_create_ordering_edge'])
        self.assertTrue(all(e['imposes_temporal_order'] is False and e['minimum_delay_s'] is None for e in g['edges']))
