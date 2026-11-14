from copy import deepcopy
import unittest
from opamp_pipeline.support.source_checks import verify_sources, normalized_unit
from opamp_pipeline.legacy_comparison.spec_03_merge_evidence import merge_evidence


def fixture():
    words=[(1,1,9,9,'MIN',0,0,0),(11,1,19,9,'TYP',0,0,1),(21,1,29,9,'MAX',0,0,2),
           (21,21,29,29,'800',0,1,0),(31,21,39,29,'uA',0,1,1)]
    cells={k:{'raw':'800' if k=='max' else '', 'value':800 if k=='max' else None,
              'bbox_points':[i*10,20,(i+1)*10,30], 'header_bbox_points':[i*10,0,(i+1)*10,10]}
           for i,k in enumerate(('min','typ','max'))}
    candidate={'source_sha256':'hash','target_product':'PART','electrical_specs':[
        {'id':'C1','symbol':'IQ','limits':{'min':None,'typ':None,'max':800},'unit':'uA',
         'source':{'pdf_page':1,'value_row_y_points':25},'conditions':{},'printed_notation':{}}]}
    native={'source_sha256':'hash','target_product':'PART','rows':[
        {'id':'N1','source':{'pdf_page':1,'row_bbox_points':[0,20,40,30]},'limit_cells':cells,
         'raw_unit':'uA','unit_cell_evidence':{'bbox_points':[30,20,40,30]},'raw_parameter_and_conditions':[]}]}
    return candidate,native,{1:words}


class VerificationMerge(unittest.TestCase):
    def test_matching_values_do_not_become_fully_verified(self):
        candidate,native,words=fixture();before=deepcopy(candidate)
        report=verify_sources(candidate,native,words,'hash')
        merged=merge_evidence(candidate,native,report)
        self.assertEqual(report['summary']['scalar_supported_rows'],1)
        self.assertFalse(merged['ready_for_design'])
        self.assertEqual(candidate,before)
        self.assertEqual(merged['electrical_specs'][0]['limits']['max'],800)

    def test_swapped_typ_max_is_conflict_and_not_silently_adopted(self):
        c,n,w=fixture();c['electrical_specs'][0]['limits']={'min':None,'typ':800,'max':None}
        report=verify_sources(c,n,w,'hash');merged=merge_evidence(c,n,report)
        self.assertEqual(report['summary']['conflict_rows'],1)
        self.assertIsNone(merged['electrical_specs'][0]['limits']['typ'])
        self.assertEqual(merged['electrical_specs'][0]['candidate_limits_before_merge']['typ'],800)

    def test_missing_and_duplicate_row_claims_are_reported(self):
        c,n,w=fixture();empty=deepcopy(c);empty['electrical_specs']=[]
        self.assertEqual(verify_sources(empty,n,w,'hash')['missing_candidate_native_ids'],['N1'])
        duplicate=deepcopy(c['electrical_specs'][0]);duplicate['id']='C2';c['electrical_specs'].append(duplicate)
        report=verify_sources(c,n,w,'hash')
        self.assertEqual(report['summary']['conflict_rows'],2)
        merged=merge_evidence(c,n,report)
        self.assertTrue(all(r['limits']['max'] is None for r in merged['electrical_specs']))

    def test_original_source_and_stale_report_protection(self):
        c,n,w=fixture();report=verify_sources(c,n,w,'hash')
        c['electrical_specs'][0]['limits']['max']=900
        with self.assertRaises(ValueError):merge_evidence(c,n,report)
        c,n,w=fixture();n['rows'][0]['limit_cells']['max']['value']=900
        self.assertEqual(verify_sources(c,n,w,'hash')['summary']['conflict_rows'],1)
        with self.assertRaises(ValueError):verify_sources(c,n,w,'different-pdf')

    def test_units_preserve_si_prefix_case_and_check_original(self):
        self.assertNotEqual(normalized_unit('MΩ'),normalized_unit('mΩ'))
        c,n,w=fixture();c['electrical_specs'][0]['unit']='mA'
        self.assertEqual(verify_sources(c,n,w,'hash')['summary']['conflict_rows'],1)
        c,n,w=fixture();n['rows'][0]['raw_unit']='mA'
        self.assertEqual(verify_sources(c,n,w,'hash')['summary']['conflict_rows'],1)


if __name__=='__main__':unittest.main()
