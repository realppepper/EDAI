import unittest
from opamp_pipeline.support.content_audit import compare_content, explicit_quantity, check_conditions


class ContentAudit(unittest.TestCase):
    def test_missing_source_sentence_is_reported(self):
        result=compare_content('Gain 100 dB\nLoad 20 pF', 'Gain 100 dB')
        self.assertTrue(result['possible_omissions'])
        self.assertFalse(result['semantic_completeness_verified'])

    def test_notation_normalization(self):
        self.assertFalse(compare_content('Current 50 µA', 'Current 50 uA')['possible_omissions'])

    def test_quantities_and_prefixes(self):
        self.assertEqual(explicit_quantity('VS = 36 V','VS','V')[0],36)
        self.assertEqual(explicit_quantity('TA = –40°C to +85°C','TA','°C')[0],{'min':-40,'max':85})
        self.assertEqual(explicit_quantity('f = 1 kHz','f','Hz')[0],1000)
        self.assertEqual(explicit_quantity('CL = 100 pF','CL','F',1e12)[0],100)

    def test_wrong_condition_and_missing_override(self):
        row={'conditions':{'overrides':{'supply_voltage_V':5}},
             'original_cell_evidence':{'raw_parameter_and_conditions':[{'text':'VS = 36 V; CL = 100 pF (1)'}]}}
        result=check_conditions(row,{},'(1) Guaranteed by design')
        self.assertEqual(result['status'],'conflict')
        self.assertTrue(any(f['field']=='load_capacitance_pF' and f['status']=='conflict' for f in result['fields']))
        self.assertEqual(result['footnote_references'],['1'])
        self.assertFalse(result['semantic_accuracy_verified'])

    def test_unhandled_expression_remains_review(self):
        row={'conditions':{'overrides':{'output_voltage_expression':'V_minus'}},
             'original_cell_evidence':{'raw_parameter_and_conditions':[{'text':'VO = V–'}]}}
        self.assertEqual(check_conditions(row,{},'')['fields'][0]['status'],'review_required')

    def test_default_scope_does_not_leak_into_local_rows(self):
        row={'conditions':{'inherits':'common','overrides':{}},
             'original_cell_evidence':{'raw_parameter_and_conditions':[{'text':'Gain'}]}}
        page='VS = (V+) – (V–) = 5 V – 36 V\nPARAMETER\nVS = 3 V to 36 V'
        result=check_conditions(row,{'common':{'supply_voltage_V':{'min':5,'max':36}}},page)
        self.assertEqual(result['fields'][0]['status'],'explicit_quantity_supported')
        self.assertIsNone(explicit_quantity('VO = 3.53 VRMS','VO','V'))
        self.assertIsNone(explicit_quantity('+85°C(1) TA = -40°C to','TA','°C'))
