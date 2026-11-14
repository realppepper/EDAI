import unittest
from opamp_pipeline.pdf_02_page_plan import plan_pages, _role


class PagePlan(unittest.TestCase):
    def test_target_product_does_not_match_ba_only_heading(self):
        self.assertEqual(_role('5.5 Electrical Characteristics: LM358BA', 'LM358B'), 'other_product_specs')
        self.assertEqual(_role('5.5 Electrical Characteristics: LM358B and LM358BA', 'LM358B'), 'target_specs')
        self.assertEqual(_role('Electrical Characteristics: LM741-MIL', 'LM741'), 'other_product_specs')

    def test_bookmark_range_keeps_continuation_and_unreadable_pages(self):
        inventory = {'page_count': 9, 'sha256': 'test', 'bookmarks': [
            {'level': 1, 'title': 'Table of Contents', 'pdf_page': 2},
            {'level': 1, 'title': '5 Specifications', 'pdf_page': 4},
            {'level': 2, 'title': '5.5 Electrical Characteristics: LM358B and LM358BA', 'pdf_page': 6},
            {'level': 2, 'title': '5.6 Electrical Characteristics: LM2904B', 'pdf_page': 8}],
            'pages': [{'pdf_page': n, 'text': '', 'flags': ['little_or_no_native_text'] if n == 9 else []} for n in range(1,10)]}
        plan = plan_pages(inventory, 'LM358B')
        self.assertEqual(len(plan['pages']), 9)
        self.assertIn('document_index', plan['pages'][1]['roles'])
        self.assertIn('target_specs', plan['pages'][5]['roles'])
        self.assertIn('target_specs', plan['pages'][6]['roles'])
        self.assertNotIn('target_specs', plan['pages'][7]['roles'])
        self.assertTrue(plan['pages'][8]['requires_review'])
        self.assertFalse(plan['selection_is_final'])

    def test_generic_and_family_headings_remain_review_candidates(self):
        self.assertEqual(_role('5.7 Electrical Characteristics', 'OPA2134'), 'specs_product_scope_review')
        self.assertEqual(_role('5.8 Electrical Characteristics for TL07xC', 'TL071'), 'specs_product_scope_review')
        inv = {'page_count': 1, 'sha256': 'test', 'bookmarks': [], 'pages': [
            {'pdf_page': 1, 'text': 'Electrical Characteristics\nMIN TYP MAX', 'words': [{'text': 'private evidence'}], 'flags': []}]}
        plan = plan_pages(inv, 'LM741')
        self.assertEqual(plan['pages'][0]['category'], 'primary_candidate')
        self.assertTrue(plan['pages'][0]['requires_review'])
        self.assertNotIn('words', plan['pages'][0])
        self.assertNotIn('text', plan['pages'][0])


if __name__ == '__main__':
    unittest.main()
