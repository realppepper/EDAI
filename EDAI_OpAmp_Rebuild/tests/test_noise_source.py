from copy import deepcopy
import unittest
from opamp_pipeline.verify_01_fixtures import build_fixture
from opamp_pipeline.validation_03_execution_contract import validate_execution,ExecutionContractError


def inputs(resistance=20,frequency=1000):
    f={'supply_voltage_V':30,'rails_V':{'V_plus':30,'V_minus':0},'temperature_C':25,
       'load':{'kind':'resistance','value_Ohm':None,'connection':'rail_midpoint'},'load_capacitance_pF':None,
       'source_case_conditions':{'source_resistance_Ohm':resistance,'frequency_Hz':frequency}}
    return {'method':{'kind':'noise_density'}},{'fixture':f}


class NoiseSourceTests(unittest.TestCase):
    def test_planned_series_source_and_noise_reference(self):
        item,case=inputs();deck,meta=build_fixture('x.inc',item,case)
        self.assertIn('VIN noise_src mid DC 0 AC 1',deck)
        self.assertIn('RSOURCE noise_src inp 20',deck)
        self.assertIn('.noise V(out) VIN',deck)
        self.assertEqual(validate_execution(deck,meta)['status'],'passed')

    def test_missing_wrong_or_rewired_resistance_rejected(self):
        item,case=inputs();deck,meta=build_fixture('x.inc',item,case)
        for bad in [deck.replace('RSOURCE noise_src inp 20\n',''),deck.replace('RSOURCE noise_src inp 20','RSOURCE noise_src inp 200'),
                    deck.replace('RSOURCE noise_src inp 20','RSOURCE noise_src mid 20'),
                    deck.replace('VIN noise_src mid DC 0 AC 1','VIN inp mid DC 0 AC 1')]:
            with self.assertRaises(ExecutionContractError):validate_execution(bad,meta)

    def test_wrong_stimulus_and_metadata_rejected(self):
        item,case=inputs();deck,meta=build_fixture('x.inc',item,case)
        with self.assertRaises(ExecutionContractError):validate_execution(deck.replace('AC 1','AC 2'),meta)
        altered=deepcopy(meta);altered['noise_definition']['source_resistance_Ohm']=0
        with self.assertRaises(ExecutionContractError):validate_execution(deck,altered)

    def test_zero_resistance_is_explicit_ideal_source(self):
        item,case=inputs(0);deck,meta=build_fixture('x.inc',item,case)
        self.assertNotIn('RSOURCE',deck);self.assertIn('VIN inp mid DC 0 AC 1',deck)
        validate_execution(deck,meta)

    def test_frequency_follows_the_plan_instead_of_fixed_1k(self):
        for frequency in [10000,200000,.5]:
            item,case=inputs(20,frequency);deck,meta=build_fixture('x.inc',item,case)
            self.assertEqual(meta['noise_definition']['frequency_Hz'],frequency)
            validate_execution(deck,meta)
            with self.assertRaises(ExecutionContractError):validate_execution(deck.replace('AT='+format(frequency,'.12g'),'AT=777'),meta)

    def test_invalid_explicit_conditions_fail_closed(self):
        for resistance in [None,-1,True,float('inf')]:
            item,case=inputs(resistance)
            with self.assertRaises(ValueError):build_fixture('x.inc',item,case)
        for frequency in [None,0,-1,True,float('nan')]:
            item,case=inputs(20,frequency)
            with self.assertRaises(ValueError):build_fixture('x.inc',item,case)


if __name__=='__main__':unittest.main()
