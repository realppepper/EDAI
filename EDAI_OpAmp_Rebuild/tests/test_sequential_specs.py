from copy import deepcopy
import json
from pathlib import Path
import unittest
from opamp_pipeline.spec_01_build_rows import stable_row_id,build_rows
from opamp_pipeline.spec_02_enrich_rows import apply_enrichment
from opamp_pipeline.spec_03_verify_sources import verify_integrated
from opamp_pipeline.support.source_checks import fingerprint


def fixture():
    evidence={'limit_cells':{'min':{'status':'blank'},'typ':{'status':'needs_interpretation'},'max':{'status':'numeric'}}}
    base={'source_sha256':'hash','electrical_specs':[{'id':'ROW-A','limits':{'min':None,'typ':None,'max':800},
          'original_cell_evidence':evidence,'field_provenance':{},'semantic_status':'awaiting_enrichment'}]}
    annotation={'source_document_fingerprint':fingerprint(base),'row_annotations':[{
        'row_id':'ROW-A','fields':{'symbol':'IQ','name':'Current','unit':'uA','conditions':{}},
        'interpreted_limits':{'typ':{'expression':'V_plus - 1.5 V'}},
        'proposed_corrections':[{'field':'limits.max','proposed_value':900}]}]}
    return base,annotation


class SequentialSpecs(unittest.TestCase):
    def test_row_identity_and_locked_values_survive_enrichment(self):
        base,annotation=fixture();before=deepcopy(base)
        enriched=apply_enrichment(base,annotation)
        self.assertEqual(enriched['electrical_specs'][0]['id'],'ROW-A')
        self.assertEqual(enriched['electrical_specs'][0]['limits']['max'],800)
        self.assertEqual(enriched['electrical_specs'][0]['correction_proposals'][0]['proposed_value'],900)
        self.assertEqual(base,before)

    def test_ai_cannot_overwrite_numbers_or_source(self):
        for field in ['limits','source','id']:
            base,annotation=fixture();annotation['row_annotations'][0]['fields'][field]={}
            with self.assertRaises(ValueError):apply_enrichment(base,annotation)
        base,annotation=fixture();annotation['row_annotations'][0]['interpreted_limits']['max']={'expression':'900'}
        with self.assertRaises(ValueError):apply_enrichment(base,annotation)

    def test_unknown_duplicate_or_stale_annotations_fail(self):
        base,a=fixture();a['row_annotations'][0]['row_id']='UNKNOWN'
        with self.assertRaises(ValueError):apply_enrichment(base,a)
        base,a=fixture();a['row_annotations'].append(deepcopy(a['row_annotations'][0]))
        with self.assertRaises(ValueError):apply_enrichment(base,a)
        base,a=fixture();a['source_document_fingerprint']='stale'
        with self.assertRaises(ValueError):apply_enrichment(base,a)

    def test_stable_id_uses_original_geometry_and_document(self):
        source={'pdf_page':6,'row_bbox_points':[1,2,3,4]}
        self.assertEqual(stable_row_id('hash',source),stable_row_id('hash',deepcopy(source)))
        self.assertNotEqual(stable_row_id('hash',source),stable_row_id('other',source))

    def test_lm358_single_document_path(self):
        root=Path(__file__).resolve().parents[1];run=root/'runs/lm358b_overview_20261112'
        inv_path=run/'01_pdf_inventory.json'
        if not inv_path.exists():self.skipTest('Local source not available')
        inv=json.loads(inv_path.read_text(encoding='utf-8'))
        if not Path(inv['source_pdf']).exists():self.skipTest('Local source PDF not available')
        base=build_rows(str(run))
        annotation=json.loads((root/'manual_inputs/lm358b_semantic_annotations.json').read_text(encoding='utf-8'))
        enriched=apply_enrichment(base,annotation)
        final,report=verify_integrated(base,enriched,inv['source_pdf'])
        self.assertEqual([r['id'] for r in base['electrical_specs']],[r['id'] for r in final['electrical_specs']])
        self.assertEqual(report['summary']['scalar_supported_rows'],38)
        self.assertFalse(final['ready_for_design'])
        tampered=deepcopy(enriched);tampered['electrical_specs'][0]['limits']['max']=999
        with self.assertRaises(ValueError):verify_integrated(base,tampered,inv['source_pdf'])


if __name__=='__main__':unittest.main()
