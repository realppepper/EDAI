from copy import deepcopy
import unittest
from opamp_pipeline.support.condition_annotations import validate_condition_annotations


class ConditionAnnotations(unittest.TestCase):
    def test_replacement_is_annotation_not_fixture_generation(self):
        sets={'common':{'input_common_mode_expression':'VS/2'}}
        conditions={'inherits':'common','overrides':{'input_common_mode_V':{'min_expression':'V_minus','max_expression':'V_plus - 1.5 V'}},
            'inheritance_replacements':{'input_common_mode_expression':'input_common_mode_V'}}
        before=deepcopy(conditions)
        self.assertEqual(validate_condition_annotations(conditions,sets),[])
        self.assertEqual(conditions,before)
        conditions['inheritance_replacements']['missing']='other'
        self.assertTrue(validate_condition_annotations(conditions,sets))

    def test_dc_bias_and_ac_amplitude_can_coexist(self):
        sets={'common':{'output_voltage_expression':'VS/2'}}
        conditions={'inherits':'common','overrides':{'output_voltage_Vrms':3.53},
            'quantity_roles':{'output_voltage_expression':'dc_bias','output_voltage_Vrms':'ac_rms_amplitude'}}
        self.assertEqual(validate_condition_annotations(conditions,sets),[])

    def test_connection_conflict_not_silently_accepted(self):
        c={'overrides':{'load_resistance_Ohm':{'min':10000,'connected_to':'V_minus'},'load_connected_to':'VS/2'}}
        self.assertTrue(validate_condition_annotations(c,{}))

    def test_resolved_fixture_has_no_open_llm_rows(self):
        import json
        from pathlib import Path
        from opamp_pipeline.spec_02_enrich_rows import apply_enrichment
        from opamp_pipeline.support.semantic_review import build_review_packet,validate_review
        root=Path(__file__).resolve().parents[1];run=root/'runs/lm358b_overview_20261112'
        if not (run/'spec_pipeline/spec_01_rows.json').exists():self.skipTest('Local source not present')
        base=json.loads((run/'spec_pipeline/spec_01_rows.json').read_text(encoding='utf-8'))
        inv=json.loads((run/'01_pdf_inventory.json').read_text(encoding='utf-8'))
        if not Path(inv['source_pdf']).exists():self.skipTest('Original PDF not present')
        annotations=json.loads((root/'manual_inputs/lm358b_semantic_annotations.json').read_text(encoding='utf-8'))
        enriched=apply_enrichment(base,annotations)
        review=json.loads((root/'manual_inputs/lm358b_semantic_review.json').read_text(encoding='utf-8'))
        validated=validate_review(build_review_packet(enriched,inv['source_pdf']),review)
        self.assertEqual(len(validated['row_reviews']),42)
        for row in validated['row_reviews']:
            self.assertFalse(row.get('suggested_changes'))
            self.assertFalse(any(c['verdict'] in {'uncertain','needs_change'} for c in row['checks'].values()))
