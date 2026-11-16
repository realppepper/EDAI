import unittest
from opamp_pipeline.harness_06_evolution import choose


class OperationalAdoptionTests(unittest.TestCase):
    def test_startup_only_failure_is_counted_for_strict_improvement(self):
        control={'eligible':False,'comparison_usable':True,'failed_case_ids':[],
                 'failed_requirement_ids':['OPERATIONAL-STARTUP']}
        variant={'eligible':True,'comparison_usable':True,'failed_case_ids':[],'failed_requirement_ids':[]}
        self.assertEqual(choose({'control':control,'variant':variant})['selected_branch'],'variant')

    def test_startup_failure_is_not_treated_as_a_tie_with_success(self):
        control={'eligible':True,'comparison_usable':True,'failed_case_ids':[],'failed_requirement_ids':[]}
        bad={'eligible':False,'comparison_usable':True,'failed_case_ids':[],'failed_requirement_ids':['OPERATIONAL-STARTUP']}
        self.assertEqual(choose({'control':control,'variant':bad})['selected_branch'],'control')
