import json
from pathlib import Path
import unittest
from copy import deepcopy
from opamp_pipeline.optuna_01_parameters import validate_space,apply_parameters,physical_score
from opamp_pipeline.validation_02_spice_reader import number

ROOT=Path(__file__).resolve().parents[1]
TEXT='''.model GNM NMOS (LEVEL=1 KP=100u)
.subckt FIRSTAMP P N VP VM OUT
RBREF VP BC 100k
MINL DREF N TAIL VM GNM W=20u L=2u
MINR X P TAIL VM GNM W=20u L=2u
CCOMP CZ YH 28p
.ends FIRSTAMP
'''


class OptunaParameterTests(unittest.TestCase):
    def config(self):return json.loads((ROOT/'settings/optuna_tl071_pilot.json').read_text(encoding='utf-8'))

    def test_group_edit_preserves_nodes_models_and_unselected_dimensions(self):
        config=self.config();values=validate_space(TEXT,config);values['input_pair_width_m']=30e-6
        changed=apply_parameters(TEXT,config,values)
        for name in ('MINL','MINR'):
            before=next(l.split() for l in TEXT.splitlines() if l.startswith(name+' '))
            after=next(l.split() for l in changed.splitlines() if l.startswith(name+' '))
            self.assertEqual(before[:6],after[:6]);self.assertEqual(before[-1],after[-1])
            self.assertAlmostEqual(number(after[-2].split('=')[1]),30e-6)
        self.assertEqual(TEXT.splitlines()[0],changed.splitlines()[0])

    def test_baseline_must_match_every_group_member(self):
        with self.assertRaises(ValueError):validate_space(TEXT.replace('MINR X P TAIL VM GNM W=20u','MINR X P TAIL VM GNM W=10u'),self.config())

    def test_unknown_or_model_bindings_rejected(self):
        for element in ('UNKNOWN','.model'):
            config=self.config();config['parameters'][0]['elements']=[element]
            with self.assertRaises(ValueError):validate_space(TEXT,config)

    def test_overlapping_fields_rejected(self):
        config=self.config();duplicate=deepcopy(config['parameters'][0]);duplicate['name']='duplicate';config['parameters'].append(duplicate)
        with self.assertRaises(ValueError):validate_space(TEXT,config)

    def test_bounds_and_missing_parameters_rejected(self):
        config=self.config();values=validate_space(TEXT,config)
        for invalid in (float('nan'),True,0,1e9):
            bad=deepcopy(values);bad['bias_resistance_Ohm']=invalid
            with self.assertRaises(ValueError):apply_parameters(TEXT,config,bad)
        values.pop('input_pair_width_m')
        with self.assertRaises(ValueError):apply_parameters(TEXT,config,values)

    def test_multiple_subcircuits_require_explicit_future_adapter(self):
        with self.assertRaises(ValueError):validate_space(TEXT+'\n.subckt SECOND P OUT\n.ends SECOND\n',self.config())

    def case(self,status='passed_sampled_model_case',value=.002,supply=30):
        return {'case_id':'iq30','kind':'iq','status':status,'supply_V':supply,'parts':[{'value':value}]}

    def test_power_objective_uses_worst_case_and_source_supply(self):
        cases=[self.case(),{**self.case(value=.003,supply=20),'case_id':'iq20'}]
        score=physical_score(cases);self.assertTrue(score['feasible_for_screening']);self.assertAlmostEqual(score['objective_power_mW'],60)

    def test_unknown_and_failed_metrics_are_not_feasible(self):
        for status in ('unverified_model','execution_contract_error','failed_in_model'):
            self.assertFalse(physical_score([self.case(status)])['feasible_for_screening'])

    def test_missing_or_invalid_power_is_not_a_reward(self):
        for value in (None,0,-1,float('inf')):
            with self.assertRaises(ValueError):physical_score([self.case(value=value)])
        with self.assertRaises(ValueError):physical_score([])


if __name__=='__main__':unittest.main()
