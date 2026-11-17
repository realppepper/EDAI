from copy import deepcopy
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from opamp_pipeline.verify_01_fixtures import build_fixture
from opamp_pipeline.diag_02_startup_seed import startup_deck
from opamp_pipeline.diag_03_solver_attempts import run_with_fallback
from opamp_pipeline.verify_04_input_impedance import impedance_deck
from opamp_pipeline.verify_05_overload_recovery import recovery_deck
from opamp_pipeline.validation_03_execution_contract import validate_execution,ExecutionContractError
from opamp_pipeline.validation_04_execution_paths import execution_signature,reusable_job
from opamp_pipeline.validation_05_special_fixtures import startup_meta,impedance_meta,overload_meta,calibration_noise_meta


def inputs():
    f={'supply_voltage_V':5,'rails_V':{'V_plus':5,'V_minus':0},'temperature_C':25,
       'load':{'kind':'resistance','value_Ohm':10000,'connection':'rail_midpoint'},'load_capacitance_pF':20}
    return {'method':{'kind':'settling','definition':{'input_step_V':2,'error_percent':.1}}},{'fixture':f}


class ExecutionPathTests(unittest.TestCase):
    def test_unbound_job_cannot_enter_verified_cache(self):
        with self.assertRaises(ExecutionContractError):execution_signature('.op\n.end\n',{'analysis':'op','names':[]})
    def fixture(self,folder):
        model=Path(folder)/'reference.inc';model.write_text('.subckt FIRSTAMP P N VP VM OUT\nR1 OUT VM 1k\n.ends FIRSTAMP\n')
        item,case=inputs();deck,meta=build_fixture(model,item,case,'rising')
        return model,deck,meta

    def test_retry_only_on_numerical_failure(self):
        with tempfile.TemporaryDirectory() as folder:
            _,deck,meta=self.fixture(folder);p=Path(folder)/'bench.cir';p.write_text(deck)
            fallback=deck.replace('.end','.options solver=norm\n.end')
            with patch('opamp_pipeline.diag_03_solver_attempts.run_bench',side_effect=[TimeoutError('injected'),{'measurements':{}}]) as native:
                result=run_with_fallback('fake',p,[],True,1,fallback,meta)
            self.assertEqual(native.call_count,2);self.assertEqual(len(result['attempts']),2)

    def test_bad_fallback_never_calls_native(self):
        with tempfile.TemporaryDirectory() as folder:
            _,deck,meta=self.fixture(folder);p=Path(folder)/'bench.cir';p.write_text(deck)
            for bad in (deck.replace('VDD vp 0 5','VDD vp 0 4'),deck.replace('reltol=1e-6','reltol=1e-2'),deck.replace('.end','Rhidden out 0 1\n.end')):
                with patch('opamp_pipeline.diag_03_solver_attempts.run_bench') as native:
                    with self.assertRaises(ExecutionContractError):run_with_fallback('fake',p,[],True,1,bad,meta)
                    native.assert_not_called()

    def cached(self,folder):
        _,deck,meta=self.fixture(folder);p=Path(folder)/'bench.cir';p.write_text(deck)
        p.with_suffix('.raw').write_text('reference raw');p.with_suffix('.log').write_text('reference log')
        signature=execution_signature(deck,meta)
        entry={'completed':True,'path':str(p),'measurements':{},'execution_signature':signature,
               'artifacts':{str(q):hashlib.sha256(q.read_bytes()).hexdigest() for q in [p,p.with_suffix('.raw'),p.with_suffix('.log')]}}
        return deck,meta,signature,entry

    def test_same_job_reused_and_cross_directory_equivalence(self):
        with tempfile.TemporaryDirectory() as first,tempfile.TemporaryDirectory() as second:
            deck,meta,sig,entry=self.cached(first)
            self.assertTrue(reusable_job(entry,deck,meta,sig)['cache_reused'])
            _,deck2,meta2=self.fixture(second);sig2=execution_signature(deck2,meta2)
            self.assertEqual(sig,sig2)
            self.assertTrue(reusable_job(entry,deck2,meta2,sig2)['cache_reused'])

    def test_corrupted_raw_and_missing_binding_are_cache_misses(self):
        with tempfile.TemporaryDirectory() as folder:
            deck,meta,sig,entry=self.cached(folder)
            legacy=deepcopy(entry);legacy.pop('execution_signature')
            self.assertIsNone(reusable_job(legacy,deck,meta,sig))
            Path(entry['path']).with_suffix('.raw').write_text('corrupted')
            self.assertIsNone(reusable_job(entry,deck,meta,sig))

    def test_cached_scalars_must_match_actual_log(self):
        with tempfile.TemporaryDirectory() as folder:
            deck,meta,sig,entry=self.cached(folder)
            entry['measurements']={'invented_scalar':1}
            self.assertIsNone(reusable_job(entry,deck,meta,sig))

    def test_include_free_noise_reference_is_reusable(self):
        deck='.temp 25\nVIN inp 0 AC 1\nR1 inp out 10k\nRL out 0 1e12\n.noise V(out) VIN dec 100 1 100k\n.meas NOISE en_1k FIND V(inoise) AT=1k\n.end\n'
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/'noise.cir';p.write_text(deck);p.with_suffix('.raw').write_text('raw')
            p.with_suffix('.log').write_text('en_1k: v(inoise)=1e-8 at 1000\n')
            meta=calibration_noise_meta();sig=execution_signature(deck,meta)
            entry={'completed':True,'path':str(p),'measurements':{'en_1k':1e-8},'execution_signature':sig,
                   'artifacts':{str(q):hashlib.sha256(q.read_bytes()).hexdigest() for q in (p,p.with_suffix('.raw'),p.with_suffix('.log'))}}
            self.assertIsNotNone(reusable_job(entry,deck,meta,sig))
            entry['measurements']['en_1k']=1e-12
            self.assertIsNone(reusable_job(entry,deck,meta,sig))

    def test_changed_metric_or_model_does_not_hit_old_cache(self):
        with tempfile.TemporaryDirectory() as folder:
            deck,meta,sig,entry=self.cached(folder)
            changed=deepcopy(meta);changed['step']['error_fraction']=.2
            self.assertNotEqual(execution_signature(deck,changed)['key'],sig['key'])
            self.assertIsNone(reusable_job(entry,deck,changed,execution_signature(deck,changed)))
            model=Path(folder)/'reference.inc';model.write_text(model.read_text()+'* model revision\n')
            self.assertNotEqual(execution_signature(deck,meta)['key'],sig['key'])
            self.assertIsNone(reusable_job(entry,deck,meta,execution_signature(deck,meta)))

    def test_changed_checker_code_invalidates_cache(self):
        with tempfile.TemporaryDirectory() as folder:
            deck,meta,sig,entry=self.cached(folder)
            from opamp_pipeline import validation_04_execution_paths as module
            original=module._file_hash
            with patch.object(module,'_file_hash',side_effect=lambda p:'changed' if Path(p).name=='verify_02_metrics.py' else original(p)):
                changed=execution_signature(deck,meta)
            self.assertNotEqual(changed['key'],sig['key']);self.assertIsNone(reusable_job(entry,deck,meta,changed))

    def test_nested_model_changes_detected(self):
        with tempfile.TemporaryDirectory() as folder:
            _,deck,meta=self.fixture(folder);child=Path(folder)/'child.inc';child.write_text('* child1')
            model=Path(folder)/'reference.inc';model.write_text(model.read_text()+'.include "child.inc"\n')
            before=execution_signature(deck,meta);child.write_text('* child2')
            self.assertNotEqual(before['key'],execution_signature(deck,meta)['key'])

    def test_startup_pwl_and_binding(self):
        with tempfile.TemporaryDirectory() as folder:
            model,_,_=self.fixture(folder);deck=startup_deck(model,5);meta=startup_meta(model,5)
            validate_execution(deck,meta)
            for bad in (deck.replace('15u 5','15u 4'),deck.replace('RL out mid 10k','RL out mid 1k'),deck.replace('.end','.ic V(out)=2.5\n.end')):
                with self.assertRaises(ExecutionContractError):validate_execution(bad,meta)

    def test_impedance_mode_and_overload_protocol(self):
        with tempfile.TemporaryDirectory() as folder:
            model,_,_=self.fixture(folder);item,case=inputs()
            for mode in ('differential','common'):
                deck=impedance_deck(model,case['fixture'],mode);meta=impedance_meta(model,case['fixture'],mode)
                validate_execution(deck,meta)
                with self.assertRaises(ExecutionContractError):validate_execution(deck.replace('.ac dec 40 1 1Meg','.ac dec 40 1 10Meg'),meta)
            case['fixture']['closed_loop_gain']=-10
            item['method']={'kind':'overload_recovery','definition':{'gain':-10,'initial_input_offset_fraction_of_supply':.12,'output_error_band_fraction_of_supply':.001}}
            for direction in ('high','low'):
                deck,profile=recovery_deck(model,item,case,direction)
                meta=overload_meta(model,item,case,direction,profile);validate_execution(deck,meta)
                with self.assertRaises(ExecutionContractError):validate_execution(deck.replace('RF out inn 100k','RF out inn 10k'),meta)
                meta['recovery_profile']['error_band_V']*=10
                with self.assertRaises(ExecutionContractError):validate_execution(deck,meta)

    def test_reference_noise_contract(self):
        deck='.temp 25\nVIN inp 0 AC 1\nR1 inp out 10k\nRL out 0 1e12\n.noise V(out) VIN dec 100 1 100k\n.meas NOISE en_1k FIND V(inoise) AT=1k\n.end\n'
        validate_execution(deck,calibration_noise_meta())


if __name__=='__main__':unittest.main()
