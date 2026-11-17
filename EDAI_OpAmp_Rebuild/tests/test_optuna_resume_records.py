import unittest
from run_optuna_sizing import mark_interrupted_trial


class ResumeRecordTests(unittest.TestCase):
    def test_running_trial_updated_without_extra_budget_entry(self):
        records=[{'number':0,'status':'screened'},{'number':1,'status':'running','candidate':'trial1.inc','params':{'x':2}}]
        result=mark_interrupted_trial(records,1)
        self.assertEqual(len(records),2)
        self.assertEqual(result['status'],'interrupted_execution')
        self.assertEqual(result['candidate'],'trial1.inc');self.assertEqual(result['params'],{'x':2})

    def test_repeated_interruption_marking_is_idempotent(self):
        records=[];mark_interrupted_trial(records,3);mark_interrupted_trial(records,3)
        self.assertEqual(len(records),1);self.assertTrue(records[0]['artifacts_preserved'])

    def test_legacy_duplicate_metadata_is_not_dropped(self):
        records=[{'number':1,'status':'running','params':{'x':2}},
                 {'number':1,'status':'interrupted_execution','artifacts_preserved':True},
                 {'number':2,'status':'screened'}]
        mark_interrupted_trial(records,1)
        self.assertEqual([r['number'] for r in records],[1,2]);self.assertEqual(records[0]['params'],{'x':2})


if __name__=='__main__':unittest.main()
