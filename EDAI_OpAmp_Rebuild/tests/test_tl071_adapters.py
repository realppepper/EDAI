import unittest
from opamp_pipeline.plan_02_measurements import target_criteria,make_fixture
from opamp_pipeline.plan_01_select_targets import select_targets
from opamp_pipeline.verify_01_fixtures import build_fixture
class TL071Adapters(unittest.TestCase):
    def test_symmetric_swing_uses_both_rail_headrooms(self):
        row={'symbol':'VOM','limits':{'min':12,'typ':13.5,'max':None},'unit':'V',
             'printed_notation':{'min':'±12','typ':'±13.5'},'conditions':{'overrides':{'supply_voltage_V':30}}}
        self.assertEqual(target_criteria(row,'vswing',{})['rules'][0]['value'],3)
        f,_=make_fixture(row,'vswing',{'values':{}},30,{})
        self.assertEqual(f['forced_output_rail'],'both')
        for direction,rail in [('upper','V_plus'),('lower','V_minus')]:
            _,meta=build_fixture('x.inc',{'method':{'kind':'vswing'}},{'fixture':f},direction)
            self.assertEqual(meta['measured_output_rail'],rail)
    def test_calibration_does_not_require_product_rows(self):
        from opamp_pipeline.verify_03_calibrate import calibration_measurements
        rows=calibration_measurements()['measurements']
        self.assertEqual(sum(r['symbol']=='IO' for r in rows),2)
        sr=next(r for r in rows if r['symbol']=='SR')
        self.assertIsNone(sr['cases'][0]['fixture']['load_capacitance_pF'])
    def test_mixed_si_prefix_range(self):
        from opamp_pipeline.support.content_audit import explicit_quantity
        value,_=explicit_quantity('f = 10 Hz to 10 kHz','f','Hz')
        self.assertEqual(value,{'min':10,'max':10000})
    def test_ohm_unicode_alias(self):
        from opamp_pipeline.support.source_checks import normalized_unit
        self.assertEqual(normalized_unit('Ω'),normalized_unit('Ohm'))
    def test_db_rejection_maps_to_sensitivity_upper_bound(self):
        for kind in ['cmrr','psrr']:
            r=target_criteria({'limits':{'min':70,'typ':100,'max':None},'unit':'dB'},kind,{})
            self.assertEqual(r['rules'][0]['operator'],'<=')
            self.assertAlmostEqual(r['rules'][0]['value'],10**(-3.5))
    def test_symmetric_common_mode_translates_rails(self):
        r={'limits':{'min':11,'typ':None,'max':None},'printed_notation':{'min':'±11'}}
        f,_=make_fixture(r,'vcm',{'values':{}},30,{})
        self.assertEqual(f['input_common_mode_sweep_V'],{'min':4,'max':26})
    def test_aol_point_is_local_not_full_range(self):
        f,a=make_fixture({},'aol',{'values':{'output_voltage_V':0}},30,{'aol_local_half_span_V':.01})
        self.assertEqual(f['output_voltage_sweep'],{'min':14.99,'max':15.01})
        self.assertTrue(any('local finite difference' in s for s in a))
    def test_slew_deck_uses_planned_step(self):
        f={'supply_voltage_V':30,'rails_V':{'V_plus':30,'V_minus':0},'load':{'kind':'resistance','value_Ohm':2000,'connection':'rail_midpoint'},'load_capacitance_pF':100}
        deck,meta=build_fixture('new.inc',{'method':{'kind':'sr','definition':{'step_V':10}}},{'fixture':f})
        self.assertEqual(meta['step']['final_V']-meta['step']['initial_V'],10)
        self.assertIn('5u 10',deck)
if __name__=='__main__':unittest.main()
