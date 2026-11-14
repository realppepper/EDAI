import json
from pathlib import Path
import tempfile
import unittest
from opamp_pipeline.pdf_03_render_pages import save_json
from opamp_pipeline.pdf_05_check_layout import table_warnings
from opamp_pipeline.legacy_comparison.spec_01_extract_rows import extract_rows


class SpecStages(unittest.TestCase):
    def test_header_column_mismatch_is_not_silent(self):
        table = r'\begin{tabular}{ccccccc}\multicolumn{2}{c}{PARAMETER}&\multicolumn{2}{c}{CONDITIONS}&MIN&TYP&MAX&UNIT\\x\end{tabular}'
        self.assertTrue(any('7 columns' in issue and '8' in issue for issue in table_warnings(table)))
        self.assertTrue(table_warnings(r'\begin{tabular}{cc}'))

    def test_manual_adapter_cannot_import_unrelated_pdf(self):
        class WrongSource:
            def extract(self, packet):
                return {'source_sha256': 'wrong-pdf', 'electrical_specs': []}
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as directory:
            root = Path(directory)
            save_json(root/'05_layout_checks.json', {'source_sha256': 'correct-pdf', 'blocked_pages': [],
                                                    'pages': [{'pdf_page': 6, 'warnings': []}]})
            save_json(root/'pages/page_0006.json', {'roles': ['target_specs'], 'document_text': 'TYP MAX'})
            with self.assertRaisesRegex(ValueError, 'source hash'):
                extract_rows(str(root), WrongSource(), [6])

    def test_source_reviewed_iq_and_drift_regression(self):
        path = Path(__file__).resolve().parents[1]/'manual_inputs/lm358b_assistant_candidates.json'
        data = json.loads(path.read_text(encoding='utf-8'))
        iq = next(r for r in data['electrical_specs'] if r['symbol'] == 'IQ' and r['conditions']['overrides']['supply_voltage_V'] == 36)
        drift = next(r for r in data['electrical_specs'] if r['symbol'] == 'dIOS/dT')
        self.assertEqual(iq['limits'], {'min': None, 'typ': None, 'max': 800})
        self.assertEqual(drift['limits'], {'min': None, 'typ': 10, 'max': None})


if __name__ == '__main__':
    unittest.main()
