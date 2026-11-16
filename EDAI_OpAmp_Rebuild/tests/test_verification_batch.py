import unittest
from copy import deepcopy
from opamp_pipeline.verify_06_batch import select_batch


class VerificationBatchTests(unittest.TestCase):
    def plan(self):
        return {'measurements':[{'row_id':'a','target':{'value':10},'cases':[
            {'case_id':'a5','fixture':{'supply':5}}, {'case_id':'a15','fixture':{'supply':15}}]},
            {'row_id':'b','target':{'value':20},'cases':[{'case_id':'b5','fixture':{'supply':5}}]}]}

    def test_selected_subset_retains_unexecuted_inventory_and_immutable_targets(self):
        plan=self.plan();before=deepcopy(plan)
        rows,batch=select_batch(plan,['a15','b5'])
        self.assertEqual([c['case_id'] for r in rows for c in r['cases']],['a15','b5'])
        self.assertEqual(batch['not_executed_case_ids'],['a5'])
        self.assertTrue(batch['partial_run'])
        self.assertEqual(rows[0]['target'],plan['measurements'][0]['target'])
        rows[0]['cases'][0]['fixture']['supply']=99
        self.assertEqual(plan,before)

    def test_default_is_full_plan(self):
        rows,batch=select_batch(self.plan())
        self.assertFalse(batch['partial_run'])
        self.assertEqual(len(batch['selected_case_ids']),3)
        self.assertEqual(batch['not_executed_case_ids'],[])

    def test_unknown_duplicate_or_empty_subset_is_rejected(self):
        for ids in ([],['missing'],['a5','a5']):
            with self.assertRaises(ValueError):select_batch(self.plan(),ids)

    def test_requesting_all_ids_still_labels_explicit_diagnostic(self):
        _,batch=select_batch(self.plan(),['b5','a15','a5'])
        self.assertTrue(batch['partial_run'])
        self.assertEqual(batch['selected_case_ids'],['a5','a15','b5'])

    def test_duplicate_source_ids_are_rejected(self):
        plan=self.plan();plan['measurements'][1]['cases'][0]['case_id']='a5'
        with self.assertRaises(ValueError):select_batch(plan,['a5'])
