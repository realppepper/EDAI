import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from opamp_pipeline.pdf_03_render_pages import save_json
from opamp_pipeline.pdf_04_parse_layout import cache_key, decode_layout, parse_layout


class LayoutSteps(unittest.TestCase):
    def test_decode_keeps_layout_coordinates_and_rejects_truncation(self):
        content = '<x_0.1><y_0.2>GBW 1.2 MHz<x_0.8><y_0.3><class_Table>'
        result = decode_layout({'content': content, 'finish_reason': 'stop'})
        self.assertEqual(result['document_text'], 'GBW 1.2 MHz')
        self.assertEqual(result['blocks'][0]['coordinates_normalized'][0], {'axis': 'x', 'value': 0.1})
        with self.assertRaises(ValueError):
            decode_layout({'content': content, 'finish_reason': 'length'})
        self.assertNotEqual(cache_key('a','url',8000), cache_key('a','url',12000))

    def test_resume_reuses_only_matching_successful_results(self):
        # Temporary data is restricted to this test directory, never user folders.
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as directory:
            root = Path(directory)
            image = root/'page.png'
            image.write_bytes(b'test image')
            manifest = {'completed': True, 'source_sha256': 'pdf-hash', 'requested_pages': [6],
                        'images': [{'pdf_page': 6, 'roles': ['target_specs'], 'image_path': str(image),
                                    'image_sha256': hashlib.sha256(image.read_bytes()).hexdigest()}]}
            save_json(root/'manifest.json',manifest)
            response = {'content': 'Table text<class_Table>', 'finish_reason': 'stop', 'usage': {'output_tokens': 4}}
            with patch('opamp_pipeline.pdf_04_parse_layout.request_page', return_value=response) as request:
                first = parse_layout(str(root/'manifest.json'), str(root), 'test-key')
                second = parse_layout(str(root/'manifest.json'), str(root), 'test-key')
            self.assertEqual(request.call_count, 1)
            self.assertTrue(first['all_requested_pages_succeeded'])
            self.assertEqual(second['reused_pages'], [6])
            self.assertEqual(second['new_api_attempts'], 0)
            saved = json.loads((root/'pages/page_0006.json').read_text(encoding='utf-8'))
            self.assertEqual(saved['raw_response'],response)
            self.assertNotIn('test-key',json.dumps(saved))


if __name__ == '__main__':
    unittest.main()
