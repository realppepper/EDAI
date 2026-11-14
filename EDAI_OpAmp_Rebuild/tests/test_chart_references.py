from copy import deepcopy
import json
from pathlib import Path
import unittest
from opamp_pipeline.chart_01_collect import match_caption,build_chart_review_packet,collect_charts
from opamp_pipeline.chart_02_verify import apply_chart_review,link_to_specs
from opamp_pipeline.support.source_checks import fingerprint


def fixture():
    graph={'id':'G1','source':{'caption_candidate':{'figure_number':'5-1','title':'Original title'}},
        'parsed_metadata':{'title':'Figure 5-9. Wrong title'},'review_status':'pending',
        'numeric_data':{'status':'unverified_parser_estimates'},'reference_only':True,'acceptance_criterion':False}
    candidates={'source_sha256':'hash','target_product':'OP','graphs':[graph]}
    patch={'graph_id':'G1','image_inspected':True,'explanation':'Source image checked',
        'reviewed_metadata':{'figure_number':'5-1','title':'Original title','axes':{'x':{'label':'Current'}},
            'temperature':{'kind':'series','values_C':[-40,25,125]},
            'traces':[{'temperature_C':25,'color':'red'}],'related_symbols':['VO']},
        'numeric_review':{'status':'not_verified'}}
    review={'packet_fingerprint':fingerprint(build_chart_review_packet(candidates)),
            'reviewer':{'method':'test'},'graph_reviews':[patch]}
    return candidates,review


class ChartReferences(unittest.TestCase):
    def test_preserve_temperature_and_only_select_25C_trace(self):
        c,r=fixture();before=deepcopy(c);result=apply_chart_review(c,r)
        g=result['graphs'][0]
        self.assertEqual(g['reviewed_metadata']['temperature']['values_C'],[-40,25,125])
        self.assertEqual(g['evaluation_applicability']['status'],'selected_temperature_trace_only')
        self.assertFalse(g['numeric_data']['approved_for_design'])
        self.assertFalse(g['acceptance_criterion']);self.assertEqual(c,before)
        self.assertEqual(result['summary']['caption_corrections'],1)

    def test_temperature_sweep_not_relabelled_as_25C(self):
        c,r=fixture();r['graph_reviews'][0]['reviewed_metadata']['temperature']={'kind':'sweep'}
        result=apply_chart_review(c,r)
        self.assertEqual(result['summary']['temperature_or_statistics_deferred_count'],1)
        self.assertEqual(result['summary']['reference_at_25C_count'],0)

    def test_stale_duplicate_wrong_figure_and_false_numeric_certification_rejected(self):
        for change in ('stale','duplicate','figure','numeric','temperature_trace','image'):
            c,r=fixture();p=r['graph_reviews'][0]
            if change=='stale':r['packet_fingerprint']='old'
            if change=='duplicate':r['graph_reviews'].append(deepcopy(p))
            if change=='figure':p['reviewed_metadata']['figure_number']='5-2'
            if change=='numeric':p['numeric_review']['status']='fully_verified'
            if change=='temperature_trace':p['reviewed_metadata']['traces']=[]
            if change=='image':p['image_inspected']=False
            with self.subTest(change=change),self.assertRaises(ValueError):apply_chart_review(c,r)

    def test_caption_matching_uses_position_not_parser_title(self):
        class Rect:width=600;height=800
        caps=[{'figure_number':'5-1','bbox_points':[50,305,280,320]},
              {'figure_number':'5-2','bbox_points':[340,305,560,320]}]
        self.assertEqual(match_caption([.1,.1,.48,.37],caps,Rect())['figure_number'],'5-1')

    def test_links_are_references_and_source_mismatch_fails(self):
        c,r=fixture();refs=apply_chart_review(c,r)
        specs={'source_sha256':'hash','target_product':'OP','electrical_specs':[{'id':'R1','symbol':'VO'}]}
        linked=link_to_specs(specs,refs)
        self.assertEqual(linked['electrical_specs'][0]['related_graph_ids'],['G1'])
        self.assertEqual(linked['characteristic_graphs'][0]['related_spec_ids'],['R1'])
        self.assertNotIn('related_graph_ids',specs['electrical_specs'][0])
        refs['source_sha256']='other'
        with self.assertRaises(ValueError):link_to_specs(specs,refs)

    def test_range_conditions_preserved_and_drift_not_a_25C_requirement(self):
        c,r=fixture();refs=apply_chart_review(c,r)
        specs={'source_sha256':'hash','target_product':'OP','electrical_specs':[
            {'id':'R1','symbol':'VO','conditions':{'overrides':{'ambient_temperature_C':{'min':-40,'max':85}}}},
            {'id':'R2','symbol':'dVOS/dT','conditions':{'overrides':{'ambient_temperature_C':{'min':-40,'max':85}}}}]}
        result=link_to_specs(specs,refs)
        self.assertEqual(result['electrical_specs'][0]['evaluation_temperature_scope']['status'],'range_contains_25C_bound_candidate_only')
        self.assertEqual(result['electrical_specs'][0]['conditions'],specs['electrical_specs'][0]['conditions'])
        self.assertEqual(result['electrical_specs'][1]['evaluation_temperature_scope']['status'],'deferred_temperature_coefficient')

    def test_actual_lm358b_coverage_and_visual_review(self):
        root=Path(__file__).resolve().parents[1];run=root/'runs/lm358b_overview_20261112'
        inv=run/'01_pdf_inventory.json'
        if not inv.exists():self.skipTest('No local fixture')
        source=json.loads(inv.read_text(encoding='utf-8'))['source_pdf']
        if not Path(source).exists():self.skipTest('Source PDF not available')
        c=collect_charts(run)
        review=json.loads((root/'manual_inputs/lm358b_chart_review.json').read_text(encoding='utf-8'))
        result=apply_chart_review(c,review)
        self.assertEqual(result['summary']['chart_count'],38)
        self.assertTrue(all(not p['unmatched_source_figures'] for p in c['coverage']['pages']))
        self.assertEqual(result['summary']['selected_25C_trace_count'],2)
        self.assertEqual(result['summary']['temperature_or_statistics_deferred_count'],10)
        gain=next(g for g in result['graphs'] if g['reviewed_metadata']['figure_number']=='5-5')
        self.assertEqual(gain['numeric_data']['status'],'rejected')
