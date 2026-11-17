import math
import unittest
from opamp_pipeline.support.content_audit import check_conditions
from opamp_pipeline.support.measurement_capabilities import measurement_capability
from opamp_pipeline.verify_01_fixtures import build_fixture
from opamp_pipeline.verify_09_scalar_input_resistance import resistance_fit
from opamp_pipeline.tb_05_waveform_metrics import settling_metrics


class FollowupAdapters(unittest.TestCase):
    def test_temperature_footnote_rejects_incorrect_other_grade(self):
        text='Full range is TA = 0°C to 70°C for the TL07xC, TL07xAC, and TL07xBC; TA = −40°C to +85°C for the TL07xI; and TA = −55°C to +125°C for the TL07xM.'
        for grade,temperature in [('TL07xI',{'min':-40,'max':85}),('TL07xM',{'min':-55,'max':125})]:
            row={'conditions':{'overrides':{'ambient_temperature_C':{'min':0,'max':70}}},
                 'original_cell_evidence':{'raw_parameter_and_conditions':[{'text':grade+' TA = Full range'}]}}
            self.assertEqual(check_conditions(row,{},text)['status'],'conflict')
            row['conditions']['overrides']['ambient_temperature_C']=temperature
            self.assertNotEqual(check_conditions(row,{},text)['status'],'conflict')

    def test_unknown_grade_is_not_assigned_an_invented_temperature(self):
        row={'conditions':{'overrides':{'ambient_temperature_C':{'min':0,'max':70}}},
             'original_cell_evidence':{'raw_parameter_and_conditions':[{'text':'OTHER TA = Full range'}]}}
        self.assertFalse(any(f['scope']=='grade_temperature_footnote' for f in check_conditions(row,{},'No grade footnote')['fields']))

    def test_grade_footnote_on_continuation_page_is_used(self):
        row={'conditions':{'overrides':{'ambient_temperature_C':{'min':0,'max':70}}},
             'original_cell_evidence':{'raw_parameter_and_conditions':[{'text':'TL07xM TA = Full range'}]}}
        following='Full range is TA = −55°C to +125°C for the TL07xM.'
        self.assertEqual(check_conditions(row,{},'First page, footnotes on next page',following)['status'],'conflict')

    def test_settling_deck_consumes_20V_20percent_in_both_directions(self):
        f={'supply_voltage_V':30,'rails_V':{'V_plus':30,'V_minus':0},'load':{'kind':'resistance','value_Ohm':2000,'connection':'rail_midpoint'},'load_capacitance_pF':100}
        item={'method':{'kind':'settling','definition':{'input_step_V':20,'error_percent':20,'baseline_fraction_of_supply':.2}}}
        for variant,initial,final in [('rising',6,26),('falling',26,6)]:
            deck,meta=build_fixture('model.inc',item,{'fixture':f},variant)
            self.assertEqual(meta['step']['initial_V'],initial)
            self.assertEqual(meta['step']['final_V'],final)
            self.assertEqual(meta['step']['error_fraction'],.2)
            self.assertIn(f'5.01u {final}',deck)

    def test_settling_last_entry_not_first_entry(self):
        s={'start_s':0,'transition_s':.1,'initial_V':0,'final_V':10,'error_fraction':.2,'stop_s':5,'max_step_s':.1}
        r=settling_metrics([0,.1,1,2,3,4,5],[0,0,9,13,9,10,10],s)
        self.assertAlmostEqual(r['settling_s'],2.15)

    def test_resistance_is_not_invented_for_ideal_gate(self):
        x=[14.9,15,15.1]
        for resistance in [1e12,2.5e11]:
            r=resistance_fit(x,[v/resistance for v in x]);self.assertAlmostEqual(r['resistance_Ohm']/resistance,1)
        self.assertIsNone(resistance_fit(x,[0,0,0])['resistance_Ohm'])
        self.assertEqual(resistance_fit(x,[-v/1e12 for v in x])['status'],'unresolved')

    def test_model_skip_never_becomes_a_pass(self):
        for symbol in ['RID','EN_RMS','in','EMIRR','THD+N','IB','IOS','en']:
            r=measurement_capability(symbol,{})
            self.assertEqual(r['status'],'unverified_model');self.assertFalse(r['passed'])
        self.assertEqual(measurement_capability('Channel separation, dc',{},1)['status'],'not_applicable')
        self.assertEqual(measurement_capability('RID',{'calibrated_gate_leakage':True})['status'],'adapter_available')


if __name__=='__main__':unittest.main()
