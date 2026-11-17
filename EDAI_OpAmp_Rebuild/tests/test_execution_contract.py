import copy
import json
from pathlib import Path
import tempfile
import unittest
from opamp_pipeline.verify_01_fixtures import build_fixture
from opamp_pipeline.verify_02_metrics import measure
from opamp_pipeline.verify_03_calibrate import calibration_measurements
from opamp_pipeline.validation_01_results import existing_report
from opamp_pipeline.validation_02_spice_reader import number
from opamp_pipeline.validation_03_execution_contract import validate_execution,ExecutionContractError


def settling():
    f={'supply_voltage_V':30,'rails_V':{'V_plus':30,'V_minus':0},'temperature_C':25,
       'load':{'kind':'resistance','value_Ohm':2000,'connection':'rail_midpoint'},
       'load_capacitance_pF':100,'closed_loop_gain':1}
    item={'method':{'kind':'settling','definition':{'input_step_V':20,'error_percent':20,
          'baseline_fraction_of_supply':.2,'reference_time':'end_of_input_transition',
          'metric':'last_entry_and_residence_until_end_of_observation'}}}
    return item,{'fixture':f}


class ExecutionContracts(unittest.TestCase):
    def forced_current(self,rail='V_plus',magnitude=.001):
        item,case=settling();item={'method':{'kind':'vswing'}}
        case['fixture']['forced_output_rail']=rail
        case['fixture']['load']={'kind':'forced_current','magnitude_A':magnitude,'direction_selected_by_rail':rail}
        return item,case

    def test_forced_current_uses_direction_without_resistor_connection(self):
        for rail in ('V_plus','V_minus'):
            item,case=self.forced_current(rail)
            deck,meta=build_fixture('dummy.inc',item,case)
            self.assertEqual(validate_execution(deck,meta)['status'],'passed')

    def test_forced_current_tampered_sign_or_terminal_is_rejected(self):
        item,case=self.forced_current();deck,meta=build_fixture('dummy.inc',item,case)
        for after in ('ILOAD out mid -0.001','ILOAD out vm 0.001'):
            with self.subTest(after=after),self.assertRaises(ExecutionContractError):
                validate_execution(deck.replace('ILOAD out mid 0.001',after),meta)

    def test_forced_current_invalid_direction_or_magnitude_is_rejected(self):
        for rail,magnitude in [('unbound',.001),('V_plus',-.001),('V_plus',True)]:
            item,case=self.forced_current(rail,magnitude)
            with self.subTest(rail=rail,magnitude=magnitude),self.assertRaises(ValueError):
                build_fixture('dummy.inc',item,case)

    def build(self,direction='rising'):
        item,case=settling()
        return build_fixture('dummy.inc',item,case,direction)

    def test_20V_20percent_both_directions(self):
        for direction in ('rising','falling'):
            deck,meta=self.build(direction)
            result=validate_execution(deck,meta)
            self.assertEqual(result['status'],'passed')
            self.assertEqual(meta['step']['error_fraction'],.2)
            self.assertEqual(abs(meta['step']['final_V']-meta['step']['initial_V']),20)

    def test_plan20_actual2_rejected(self):
        deck,meta=self.build()
        with self.assertRaises(ExecutionContractError):
            validate_execution(deck.replace('5.01u 26','5.01u 8').replace('40u 26','40u 8'),meta)

    def test_plan20percent_actual_point1percent_rejected(self):
        deck,meta=self.build();meta['step']['error_fraction']=.001
        with self.assertRaises(ExecutionContractError):validate_execution(deck,meta)

    def test_deck_mutations_rejected(self):
        deck,meta=self.build()
        for before,after in [('VDD vp 0 30','VDD vp 0 3'),('VDD vp 0 30','VDD orphan 0 30'),
                             ('RL out mid 2000','RL out vm 2000'),('CL out mid 1e-10','CL out mid 2e-10'),
                             ('.temp 25','.temp 27'),('.tran 0 40u 0 2n','.tran 0 4u 0 2n')]:
            self.assertIn(before,deck)
            with self.subTest(after=after),self.assertRaises(ExecutionContractError):
                validate_execution(deck.replace(before,after),meta)

    def test_equivalent_si_suffixes(self):
        deck,meta=self.build()
        self.assertEqual(validate_execution(deck.replace('RL out mid 2000','RL out mid 2k'),meta)['status'],'passed')
        self.assertEqual(number('1Meg'),1e6);self.assertEqual(number('1M'),.001)

    def test_bipolar_translation(self):
        item,case=settling();case['fixture']['rails_V']={'V_plus':15,'V_minus':-15}
        deck,meta=build_fixture('x.inc',item,case,'falling')
        self.assertEqual(validate_execution(deck,meta)['status'],'passed')
        self.assertEqual(meta['step']['final_V'],-9)

    def test_nondefault_temperature_consumed(self):
        item,case=settling();case['fixture']['temperature_C']=27
        deck,meta=build_fixture('x.inc',item,case,'rising')
        self.assertIn('.temp 27',deck);validate_execution(deck,meta)

    def test_wrong_metric_semantics_blocked(self):
        item,case=settling();item['method']['definition']['reference_time']='start_of_input_transition'
        deck,meta=build_fixture('x.inc',item,case,'rising')
        with self.assertRaises(ExecutionContractError):validate_execution(deck,meta)

    def test_wrong_dispatch_and_fixture_rejected(self):
        deck,meta=self.build()
        for args in ({'kind':'sr'},{'fixture':{}}):
            with self.assertRaises(ExecutionContractError):validate_execution(deck,meta,**args)

    def test_measure_checks_before_reading_raw(self):
        deck,meta=self.build();meta['step']['error_fraction']=.001
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'bench.cir';path.write_text(deck,encoding='ascii')
            with self.assertRaises(ExecutionContractError):
                measure(path,'settling',meta['execution_contract']['fixture'],meta,{})

    def test_receipt_preserves_error_not_physical_failure(self):
        deck,meta=self.build()
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(ExecutionContractError) as caught:
                validate_execution(deck.replace('.temp 25','.temp 0'),meta,receipt_dir=temp)
            receipt=json.loads(next(Path(temp).glob('*.json')).read_text(encoding='utf-8'))
            self.assertEqual(receipt['status'],'failed')
            self.assertFalse(caught.exception.physical_spec_failure_established)
            self.assertIn('code_sha256',receipt['evidence'])

    def test_calibrations_do_not_borrow_product_voltage_bounds(self):
        for item in calibration_measurements()['measurements']:
            case=item['cases'][0]
            variants=('lower','upper') if item['method']['kind']=='vcm' else ('rising','falling') if item['method']['kind']=='sr' else ('default',)
            for variant in variants:
                deck,meta=build_fixture('ref.inc',item,case,variant,'CALX')
                self.assertEqual(validate_execution(deck,meta)['status'],'passed')
                self.assertEqual(meta['execution_contract']['role'],'analytical_reference')

    def test_pm_dual_deck(self):
        item,case=settling();item['method']={'kind':'pm'}
        deck,meta=build_fixture('x.inc',item,case)
        validate_execution(deck,meta)
        with self.assertRaises(ExecutionContractError):validate_execution(deck.replace('Rloadi yi mid 2000','Rloadi yi 0 2000'),meta)

    def test_zero_is_not_missing(self):
        item,case=settling();case['fixture']['load']['value_Ohm']=0
        with self.assertRaises(ValueError):build_fixture('x.inc',item,case)
        case['fixture']['load']['value_Ohm']=None;case['fixture']['load_capacitance_pF']=0
        deck,meta=build_fixture('x.inc',item,case)
        validate_execution(deck,meta)
        self.assertEqual(meta['execution_contract']['fixture']['load_capacitance_pF'],0)

    def test_legacy_not_claimed_passed(self):
        self.assertEqual(validate_execution('* legacy',{})['status'],'not_checked')

    def test_common_envelope_preserves_native_verdict(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'result.json';path.write_text('{"status":"additional_scope_failed"}')
            wrapped=existing_report(path,'spec03')
            self.assertEqual(wrapped['status'],'native_result_preserved')
            self.assertEqual(wrapped['evidence']['native_result']['status'],'additional_scope_failed')


if __name__=='__main__':unittest.main()
