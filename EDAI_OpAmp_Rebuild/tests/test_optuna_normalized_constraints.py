import unittest
from copy import deepcopy
from opamp_pipeline.optuna_01_parameters import normalized_constraints


def measured(value,limit=8,operator='>=',metric='sr',case_id='sr30'):
    passed=(value>=limit if operator=='>=' else value<=limit if operator=='<=' else value==limit)
    return {'case_id':case_id,'status':'passed_sampled_model_case' if passed else 'failed_in_model',
            'tests':[{'metric':metric,'value':value,'limit':limit,'operator':operator,'passed':passed}],
            'parts':[{'gate_issues':[]}],'gate_issues':[]}


class NormalizedConstraintTests(unittest.TestCase):
    def test_near_miss_and_large_miss_have_different_distances(self):
        near=normalized_constraints([measured(7.48)])
        far=normalized_constraints([measured(2.84)])
        self.assertAlmostEqual(near['total_normalized_violation'],.065)
        self.assertAlmostEqual(far['total_normalized_violation'],.645)
        self.assertLess(near['total_normalized_violation'],far['total_normalized_violation'])

    def test_upper_limit_and_satisfied_margin_have_correct_sign(self):
        high=normalized_constraints([measured(.003,.0025,'<=','iq')])
        good=normalized_constraints([measured(.002,.0025,'<=','iq')])
        self.assertAlmostEqual(high['total_normalized_violation'],.2)
        self.assertAlmostEqual(next(iter(good['constraints'].values())),-.2)
        self.assertEqual(good['total_normalized_violation'],0)

    def test_scale_invariant_across_units(self):
        a=normalized_constraints([measured(7.48,8)])
        b=normalized_constraints([measured(7.48e6,8e6)])
        self.assertAlmostEqual(a['total_normalized_violation'],b['total_normalized_violation'])

    def test_directions_and_cases_keep_separate_constraints(self):
        a=measured(7.48);a['tests'].append(measured(10)['tests'][0])
        b=measured(7.2,case_id='sr24')
        result=normalized_constraints([a,b])
        self.assertEqual(len(result['constraints']),3)
        self.assertAlmostEqual(result['total_normalized_violation'],.165)

    def test_missing_invalid_or_unqualified_data_not_ranked(self):
        for status in ('execution_error','execution_contract_error','unverified_model','unverified_adapter'):
            case=measured(7.48);case['status']=status
            with self.assertRaises(ValueError):normalized_constraints([case])
        for value in (None,float('nan'),True):
            case=measured(7.48);case['tests'][0]['value']=value
            with self.assertRaises(ValueError):normalized_constraints([case])
        case=measured(7.48);case['parts'][0]['gate_issues']=['invalid bias']
        with self.assertRaises(ValueError):normalized_constraints([case])

    def test_numeric_rules_and_reported_verdict_must_agree(self):
        case=measured(7.48);case['tests'][0]['passed']=True
        with self.assertRaises(ValueError):normalized_constraints([case])
        case=measured(7.48);case['status']='passed_sampled_model_case'
        with self.assertRaises(ValueError):normalized_constraints([case])

    def test_zero_limit_requires_explicit_scale(self):
        case=measured(1,0,'<=')
        with self.assertRaises(ValueError):normalized_constraints([case])
        case['tests'][0]['normalization_scale']=2
        self.assertEqual(normalized_constraints([case])['total_normalized_violation'],.5)

    def test_duplicate_identifier_and_no_rules_rejected(self):
        case=measured(7.48)
        with self.assertRaises(ValueError):normalized_constraints([case,deepcopy(case)])
        case['tests']=[]
        with self.assertRaises(ValueError):normalized_constraints([case])


if __name__=='__main__':unittest.main()
