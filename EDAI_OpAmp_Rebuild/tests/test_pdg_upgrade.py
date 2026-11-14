from copy import deepcopy
from html.parser import HTMLParser
import json
from pathlib import Path
import unittest
from opamp_pipeline.pdg_03_audit import audit_pdg
from opamp_pipeline.pdg_04_schedule import generate_schedule,policy_templates,pdg_signature
from opamp_pipeline.pdg_05_visualize import render_pdg_inspector


def graph_fixture():
    path=Path(__file__).resolve().parents[1]/'runs/lm358b_overview_20261112/pdg_pipeline/pdg_01_graph.json'
    if not path.exists():path=Path(__file__).resolve().parent/'fixtures/lm358b/pdg_01_graph.json'
    return json.loads(path.read_text(encoding='utf-8'))


def policy_fixture(graph,analysis='tran'):
    p=policy_templates(graph)[analysis];p.update({'policy_id':'software_test_only','channels':['channel1'],
        'rationale':'Synthetic software fixture; not a recommended LM358B measurement policy','initialization':'dc_operating_point'})
    if analysis=='tran':
        p['events']=[{'id':'stim','kind':'apply_stimulus','ports':['IN1+'],'time_s':1e-6,'after':[],
                     'origin':'engineering_policy','rationale':'Software fixture'},
                    {'id':'measure','kind':'start_measurement','ports':['OUT1'],'time_s':3e-6,'after':['stim'],
                     'requires_gates':['pre_measurement_conditions_valid'],'origin':'engineering_policy','rationale':'Software fixture'},
                    {'id':'stop','kind':'stop_simulation','ports':[],'time_s':7e-6,'after':['measure'],
                     'origin':'engineering_policy','rationale':'Software fixture'}]
    return p


class PDGUpgrade(unittest.TestCase):
    def test_actual_channels_and_provenance(self):
        audit=audit_pdg(graph_fixture())
        self.assertEqual(audit['status'],'functional_checks_passed')
        self.assertEqual(audit['summary']['expected_signal_paths'],4)
        self.assertEqual(audit['summary']['present_signal_paths'],4)
        self.assertEqual(audit['summary']['origin_counts'],{'engineering_interpretation':8,'datasheet_statement':4})
        self.assertIsNone(audit['semantic_accuracy_score'])

    def test_missing_signal_cross_channel_missing_supply_and_validity_detected(self):
        for problem in ('signal','cross','supply','validity'):
            g=graph_fixture();nodes={n['source_key']:n['id'] for n in g['nodes']}
            if problem=='signal':g['edges']=[e for e in g['edges'] if not (e['source']==nodes['IN1+'] and e['relation']=='signal_dependency')]
            if problem=='supply':g['edges']=[e for e in g['edges'] if not (e['source']==nodes['V-'] and e['relation']=='contributes_to_supply')]
            if problem=='validity':g['edges']=[e for e in g['edges'] if not (e['source']==nodes['valid_common_mode1'] and e['relation']=='validity_dependency')]
            if problem=='cross':
                e=deepcopy(next(e for e in g['edges'] if e['source']==nodes['IN1+'] and e['relation']=='signal_dependency'))
                e['target']=nodes['OUT2'];e['id']='cross';g['edges'].append(e)
            with self.subTest(problem=problem):
                self.assertEqual(audit_pdg(g)['status'],'failed')
                with self.assertRaises(ValueError):generate_schedule(g)

    def test_no_policy_does_not_invent_waits(self):
        result=generate_schedule(graph_fixture())
        self.assertEqual(result['status'],'awaiting_execution_policy');self.assertEqual(result['events'],[])
        self.assertFalse(result['ready_for_test_execution'])

    def test_op_ac_have_no_transient_timestamps(self):
        g=graph_fixture()
        for analysis in ('op','ac'):
            p=policy_fixture(g,analysis);r=generate_schedule(g,p)
            self.assertEqual(r['events'],[]);self.assertIn('solve_dc_operating_point',r['operation_sequence'])
            self.assertFalse(r['ready_for_test_execution'])
        p=policy_fixture(g,'ac');p['events']=[{'id':'bad','kind':'apply_stimulus','ports':['IN1+'],'time_s':0}]
        with self.assertRaises(ValueError):generate_schedule(g,p)

    def test_explicit_transient_policy_and_provenance(self):
        g=graph_fixture();p=policy_fixture(g);before=deepcopy(g);r=generate_schedule(g,p)
        self.assertEqual(r['status'],'policy_schedule_generated');self.assertEqual(g,before)
        self.assertEqual([e['time_s'] for e in r['events']],[1e-6,3e-6,7e-6])
        self.assertFalse(r['timing_values_are_datasheet_requirements']);self.assertFalse(r['ready_for_test_execution'])
        self.assertEqual(r['gate_results']['pre_measurement_conditions_valid'],'not_evaluated')

    def test_invalid_policy_times_roles_gates_or_source_rejected(self):
        for problem in ('stale','nan','negative','order','origin','gate','channel','role','startup'):
            g=graph_fixture();p=policy_fixture(g)
            if problem=='stale':p['pdg_fingerprint']='old'
            if problem=='nan':p['events'][0]['time_s']=float('nan')
            if problem=='negative':p['events'][0]['time_s']=-1
            if problem=='order':p['events'][1]['time_s']=0
            if problem=='origin':p['events'][0]['origin']='datasheet_statement'
            if problem=='gate':p['required_gates']=[]
            if problem=='channel':p['events'][0]['ports']=['IN2+']
            if problem=='role':p['events'][0]['ports']=['V+']
            if problem=='startup':p['initialization']='explicit_startup'
            with self.subTest(problem=problem),self.assertRaises(ValueError):generate_schedule(g,p)

    def test_run_provenance_does_not_invalidate_policy_for_unchanged_facts(self):
        g=graph_fixture();sig=pdg_signature(g);g['_execution']={'run_id':'new'}
        self.assertEqual(pdg_signature(g),sig)

    def test_viewer_is_self_contained_and_json_is_script_safe(self):
        g=graph_fixture();g['nodes'][0]['label']='</script><script>alert(1)</script>'
        page=render_pdg_inspector(g,audit_pdg(g),generate_schedule(g),policy_templates(g))
        class DataParser(HTMLParser):
            def __init__(self):super().__init__();self.inside=False;self.data=[]
            def handle_starttag(self,tag,attrs):
                if tag=='script' and dict(attrs).get('id')=='pdg-data':self.inside=True
            def handle_endtag(self,tag):
                if tag=='script':self.inside=False
            def handle_data(self,data):
                if self.inside:self.data.append(data)
        parser=DataParser();parser.feed(page)
        parsed=json.loads(''.join(parser.data));self.assertEqual(parsed['graph']['nodes'][0]['label'],g['nodes'][0]['label'])
        self.assertNotIn('https://',page);self.assertNotIn('fetch(',page)
