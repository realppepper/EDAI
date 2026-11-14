import hashlib
import json
from pathlib import Path
import unittest
from opamp_pipeline.support.native_tables import NativeTableExtractor, parse_numeric_cell


class NativeTables(unittest.TestCase):
    def test_only_scalar_cells_are_converted(self):
        self.assertEqual(parse_numeric_cell('–35')['value'], -35)
        self.assertEqual(parse_numeric_cell('±0.3')['notation'], 'plus_minus')
        for raw in ['10 || 0.1', '(V+) - 1.5', '1 2']:
            result = parse_numeric_cell(raw)
            self.assertEqual(result['raw'], raw)
            self.assertIsNone(result['value'])
            self.assertEqual(result['status'], 'needs_interpretation')

    def test_lm358_original_header_coordinates_place_known_values(self):
        # Optional integration fixture: users can regenerate the overview on
        # their own machine; unit tests above do not need a private PDF path.
        root = Path(__file__).resolve().parents[1]
        inventory = root/'runs/lm358b_overview_20261112/01_pdf_inventory.json'
        if not inventory.exists(): self.skipTest('Local LM358 fixture not available')
        inv = json.loads(inventory.read_text(encoding='utf-8'))
        source = Path(inv['source_pdf'])
        if not source.exists(): self.skipTest('Source PDF not available on this machine')
        packet = {'source_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
                  'pages': [{'pdf_page': 6, 'roles': ['target_specs']}, {'pdf_page': 7, 'roles': ['target_specs']}]}
        result = NativeTableExtractor(str(source), 'LM358B').extract(packet)
        iq = next(r for r in result['rows'] if r['source']['pdf_page'] == 7 and r['limits']['max'] == 800)
        self.assertEqual(iq['limits'], {'min': None, 'typ': None, 'max': 800})
        self.assertTrue(iq['limit_cells']['max']['native_words'])
        self.assertEqual(len(result['excluded_rows']), 2)
        self.assertTrue(all('LM358BA' in r['raw_label'] for r in result['excluded_rows']))
        expressions = [r for r in result['rows'] if r['requires_review']]
        self.assertEqual(len(expressions), 4)
        self.assertFalse(result['source_accuracy_verified'])


if __name__ == '__main__':
    unittest.main()
