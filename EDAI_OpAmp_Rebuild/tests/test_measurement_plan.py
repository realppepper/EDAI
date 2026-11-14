from copy import deepcopy
import json
from pathlib import Path
import unittest
from opamp_pipeline.plan_01_select_targets import select_targets
from opamp_pipeline.plan_02_measurements import build_measurements,convert,voltage_expression
from opamp_pipeline.plan_03_execution_policies import build_policies
from opamp_pipeline.plan_04_validate import validate_plan
from opamp_pipeline.pdg_04_schedule import generate_schedule,policy_templates


def fixture():
    root=Path(__file__).resolve().parents[1];run=root/'runs/lm358b_overview_20261112'
    read=lambda path:json.loads(path.read_text(encoding='utf-8'))
    if (run/'hkg_pipeline/hkg_01_graph.json').exists():
        h=read(run/'hkg_pipeline/hkg_01_graph.json');p=read(run/'pdg_pipeline/pdg_01_graph.json')
        policy=read(root/'planning_inputs/lm358b_25c_project_policy.json')
    else:
        fixture=root/'tests/fixtures/lm358b'
        h=read(fixture/'hkg_01_graph.json');p=read(fixture/'pdg_01_graph.json')
        policy=read(fixture/'project_policy.json')
    return h,p,policy


def build():
    h,p,policy=fixture();selection=select_targets(h,p,policy)
    measurements=build_measurements(selection,h,policy['engineering_defaults'])
    execution=build_policies(measurements,p,policy['engineering_defaults'])
    return h,p,policy,selection,measurements,execution


class MeasurementPlan(unittest.TestCase):
    def test_scope_all_rows_accounted_and_not_executed(self):
        h,p,policy,s,m,e=build();v=validate_plan(s,m,e,h,p,policy['engineering_defaults'])
        self.assertEqual(s['summary'],{'source_rows':42,'included':32,'temperature_coefficients_deferred':2,'temperature_variants_not_separately_scheduled':8})
        self.assertEqual(v['simulations_executed'],0);self.assertEqual(v['included_rows'],32)
        self.assertTrue(all(x['evaluation_temperature_C']==25 and not x['executed'] for x in m['measurements']))

    def test_source_bound_typical_and_signed_limits(self):
        h,p,policy,s,m,e=build()
        iq=next(x for x in m['measurements'] if x['symbol']=='IQ' and x['resolved_conditions']['values']['supply_voltage_V']==36)
        self.assertEqual(iq['target']['rules'][0]['source_slot'],'max')
        self.assertAlmostEqual(iq['target']['rules'][0]['value'],800e-6)
        self.assertEqual(iq['source_temperature_condition_C'],{'min':-40,'max':85})
        self.assertEqual(iq['resolved_conditions']['values']['ambient_temperature_C'],25)
        ib=next(x for x in m['measurements'] if x['symbol']=='IB')
        self.assertEqual(ib['target']['rules'][0]['operator'],'<=');self.assertAlmostEqual(ib['target']['rules'][0]['value'],35e-9)
        source=next(x for x in m['measurements'] if x['symbol']=='IO' and x['resolved_conditions']['values'].get('current_direction')=='source')
        self.assertEqual(source['target']['rules'][0]['operator'],'>=');self.assertAlmostEqual(source['target']['rules'][0]['value'],.02)
        gbw=next(x for x in m['measurements'] if x['symbol']=='GBW')
        self.assertEqual(gbw['target']['origin'],'typical_value_adopted_as_project_objective')

    def test_rejection_units_parallel_model_and_split_rails(self):
        h,p,policy,s,m,e=build()
        psrr=next(x for x in m['measurements'] if x['symbol']=='PSRR')
        self.assertEqual(psrr['target']['rules'][0]['unit'],'V/V');self.assertAlmostEqual(psrr['target']['rules'][0]['value'],15e-6)
        zid=next(x for x in m['measurements'] if x['symbol']=='ZID')
        self.assertEqual(zid['target']['rules'][0]['value'],10e6)
        self.assertAlmostEqual(zid['target']['rules'][1]['value'],.1e-12)
        isc=next(x for x in m['measurements'] if x['symbol']=='ISC')
        f=isc['cases'][0]['fixture'];self.assertEqual(f['rails_V'],{'V_plus':10,'V_minus':-10});self.assertEqual(f['input_common_mode_bias_V'],0)
        self.assertEqual(voltage_expression('V_minus + 200 mV',15,0),.2)

    def test_no_double_load_and_aol_output_not_fixed_at_midpoint(self):
        h,p,policy,s,m,e=build()
        vo=next(x for x in m['measurements'] if x['symbol']=='VO' and 'output_current_uA' in x['resolved_conditions']['values'])
        self.assertEqual(vo['cases'][0]['fixture']['load']['kind'],'forced_current')
        aol=next(x for x in m['measurements'] if x['symbol']=='AOL')
        self.assertIsNone(aol['cases'][0]['fixture']['output_dc_bias_V'])
        self.assertEqual(aol['cases'][0]['fixture']['output_voltage_sweep'],{'min':1,'max':11})

    def test_noise_thdn_and_settling_policies(self):
        h,p,policy,s,m,e=build()
        for symbol in ('En','en'):
            item=next(x for x in m['measurements'] if x['symbol']==symbol)
            self.assertTrue(item['method']['requires_noise_capable_models'])
        thdn=next(x for x in m['measurements'] if x['symbol']=='THD+N')
        self.assertEqual(thdn['method']['analyses'],['tran','noise'])
        self.assertLess(thdn['method']['definition']['derived_peak_load_current_A'],50e-6)
        settling=next(x for x in e['policies'] if x['policy']['row_id']==next(m['row_id'] for m in m['measurements'] if m['symbol']=='ts'))
        events=settling['policy']['events'];self.assertAlmostEqual(events[1]['time_s']-events[0]['time_s'],policy['engineering_defaults']['input_transition_s'])
        self.assertFalse(settling['schedule']['ready_for_test_execution'])

    def test_scope_policy_staleness_or_missing_decision_rejected(self):
        for problem in ('stale','missing','duplicate'):
            h,p,policy=fixture()
            if problem=='stale':policy['input_hkg_fingerprint']='old'
            if problem=='missing':policy['row_decisions'].pop()
            if problem=='duplicate':policy['row_decisions'].append(deepcopy(policy['row_decisions'][0]))
            with self.subTest(problem=problem),self.assertRaises(ValueError):select_targets(h,p,policy)

    def test_missing_policy_direction_or_source_mutation_rejected(self):
        h,p,policy,s,m,e=build();bad=deepcopy(e)
        bad['policies'].pop(next(i for i,x in enumerate(bad['policies']) if x['policy']['variant']=='falling'))
        with self.assertRaises(ValueError):validate_plan(s,m,bad,h,p,policy['engineering_defaults'])
        corrupted=deepcopy(m);corrupted['measurements'][0]['source']['limits']['max']=999
        with self.assertRaises(ValueError):validate_plan(s,corrupted,e,h,p,policy['engineering_defaults'])

    def test_dc_noise_and_passive_observation_are_supported(self):
        h,p,policy,s,m,e=build()
        for analysis in ('dc','noise'):
            entry=next(x for x in e['policies'] if x['policy']['analysis']==analysis)
            self.assertEqual(entry['schedule']['events'],[])
            self.assertIn('dc_operating_point_valid',entry['schedule']['required_gates'])
        passive=next(x for x in e['policies'] if x['policy'].get('measurement_mode')=='passive_noise_observation')
        self.assertFalse(any(event['kind']=='apply_stimulus' for event in passive['policy']['events']))
        self.assertEqual(generate_schedule(p,passive['policy'])['status'],'policy_schedule_generated')

    def test_changed_goal_with_unchanged_source_is_rejected(self):
        h,p,policy,s,m,e=build()
        corrupted=deepcopy(m)
        target=next(x for x in corrupted['measurements'] if any(isinstance(r.get('value'),(int,float)) for r in x['target']['rules']))
        rule=next(r for r in target['target']['rules'] if isinstance(r.get('value'),(int,float)))
        rule['value']+=1
        with self.assertRaises(ValueError):validate_plan(s,corrupted,e,h,p,policy['engineering_defaults'])
