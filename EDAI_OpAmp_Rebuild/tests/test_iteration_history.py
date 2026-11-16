import json,tempfile,unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
from collections import Counter
from opamp_pipeline.harness_05_history import build_iteration_history
from opamp_pipeline.harness_03_loop import prepare
from opamp_pipeline.harness_02_request import make_request
from opamp_pipeline.harness_01_fixed import load_harness
from opamp_pipeline.design_01_cmos_candidate import candidate
from opamp_pipeline.support.execution_state import file_hash
from opamp_pipeline.support.source_checks import fingerprint


class IterationHistoryTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.folder=Path(self.temp.name)
        self.fixture={'supply_voltage_V':5}
        self.target={'rules':[{'metric':'gbw','operator':'>=','value':1e6,'unit':'Hz'}]}

    def record(self,index,value=8e5,status='failed_in_model',gate=None,measured=True):
        folder=self.folder/str(index);folder.mkdir()
        model=folder/'candidate.inc';model.write_text(candidate()+f'* candidate{index}\n',encoding='ascii')
        record={'index':index,'candidate_path':str(model),'candidate_sha256':file_hash(model)}
        if not measured:
            record['execution_error']='Worker interrupted';return record
        case={'case_id':'g','fixture':deepcopy(self.fixture),'status':status,
              'tests':[{'metric':'gbw','value':value,'operator':'>=','limit':1e6,'unit':'Hz','passed':status=='passed_sampled_model_case'}]}
        if gate:case['parts']=[{'gate_issues':[gate]}]
        unknown={'case_id':'n','fixture':deepcopy(self.fixture),'status':'unverified_adapter'}
        doc={'source_cases_required':2,'source_rows_required':2,'input_signatures':{str(model):file_hash(model)},
             'rows':{'g':{'symbol':'GBW','kind':'gbw','target':deepcopy(self.target),'cases':[case]},
                     'n':{'symbol':'noise_pp','kind':'noise_pp','target':{},'cases':[unknown]}},
             'case_status_counts':dict(Counter([status,'unverified_adapter']))}
        path=folder/'LEDGER.json';path.write_text(json.dumps(doc),encoding='utf-8')
        record.update(ledger_path=str(path),ledger_sha256=file_hash(path))
        if index:
            response=folder/'RESPONSE.json';response.write_text(json.dumps({'netlist':model.read_text(encoding='ascii'),'changes':['declared change']}),encoding='utf-8')
            record.update(response_path=str(response),response_sha256=file_hash(response))
        return record

    def change_document(self,record,edit):
        path=Path(record['ledger_path']);doc=json.loads(path.read_text(encoding='utf-8'));edit(doc)
        path.write_text(json.dumps(doc),encoding='utf-8');record['ledger_sha256']=file_hash(path)

    def test_observed_diff_and_valid_numeric_delta_not_declared_causality(self):
        a,b=self.record(0),self.record(1,1.2e6,'passed_sampled_model_case')
        history=build_iteration_history([a,b],['g'])
        transition=history['transitions'][0];metric=transition['case_changes'][0]['test_changes'][0]
        self.assertIn('+* candidate1',transition['actual_netlist_diff'])
        self.assertEqual(metric['after_minus_before'],4e5)
        self.assertEqual(transition['newly_passed_case_ids'],['g'])
        self.assertEqual(transition['llm_declared_changes_unverified'],['declared change'])
        self.assertFalse(transition['physical_causes_confirmed'])

    def test_invalid_old_measurement_never_becomes_numeric_improvement(self):
        a,b=self.record(0,5e5,'unverified_adapter','Not stationary'),self.record(1,1.2e6,'passed_sampled_model_case')
        change=build_iteration_history([a,b],['g'])['transitions'][0]['case_changes'][0]
        self.assertFalse(change['numeric_comparison_valid']);self.assertEqual(change['test_changes'],[])

    def test_regression_and_unmeasured_candidate_are_distinct(self):
        a,b=self.record(0,1.2e6,'passed_sampled_model_case'),self.record(1)
        self.assertEqual(build_iteration_history([a,b],['g'])['transitions'][0]['previously_passed_now_not_passed_case_ids'],['g'])
        c=self.record(2,measured=False)
        item=build_iteration_history([b,c],['g'])['transitions'][0]
        self.assertFalse(item['both_candidate_measurements_completed']);self.assertEqual(item['case_changes'],[])

    def test_initial_empty_history_and_recent_bound(self):
        records=[self.record(i) for i in range(5)]
        self.assertEqual(build_iteration_history(records[:1],['g'])['transitions'],[])
        history=build_iteration_history(records,['g'],2)
        self.assertEqual(len(history['transitions']),2);self.assertEqual(history['older_candidates_omitted'],2)
        self.assertEqual(history['transitions'][0]['before']['candidate_index'],2)

    def test_changed_or_unbound_artifacts_are_rejected(self):
        a=self.record(0)
        Path(a['candidate_path']).write_text('changed')
        with self.assertRaises(ValueError):build_iteration_history([a],['g'])
        b=self.record(1)
        self.change_document(b,lambda doc:doc.update(input_signatures={}))
        with self.assertRaises(ValueError):build_iteration_history([b],['g'])

    def test_changed_targets_fixtures_or_case_inventory_are_rejected(self):
        a,b=self.record(0),self.record(1)
        original=Path(b['ledger_path']).read_text()
        edits=[lambda d:d['rows']['g']['target'].update(other=1),
               lambda d:d['rows']['g']['cases'][0]['fixture'].update(supply_voltage_V=15),
               lambda d:d.update(source_cases_required=1,rows={'g':d['rows']['g']})]
        for edit in edits:
            Path(b['ledger_path']).write_text(original);b['ledger_sha256']=file_hash(b['ledger_path'])
            self.change_document(b,edit)
            with self.assertRaises(ValueError):build_iteration_history([a,b],['g'])

    def test_response_text_and_hash_must_match(self):
        a,b=self.record(0),self.record(1)
        response=Path(b['response_path']);data=json.loads(response.read_text());data['netlist']='different'
        response.write_text(json.dumps(data));b['response_sha256']=file_hash(response)
        with self.assertRaises(ValueError):build_iteration_history([a,b],['g'])

    def test_bool_metric_is_not_subtracted_as_numeric(self):
        a,b=self.record(0),self.record(1)
        for rec,val in [(a,False),(b,True)]:
            self.change_document(rec,lambda d,val=val:d['rows']['g']['cases'][0]['tests'][0].update(value=val))
        metric=build_iteration_history([a,b],['g'])['transitions'][0]['case_changes'][0]['test_changes'][0]
        self.assertNotIn('after_minus_before',metric)

    def test_split_and_full_sweep_preserve_status_without_pairwise_delta(self):
        a,b=self.record(0,1.2e6,'passed_sampled_model_case'),self.record(1,1.3e6,'passed_sampled_model_case')
        self.change_document(a,lambda d:d['rows']['g']['cases'][0]['tests'].append(
            dict(d['rows']['g']['cases'][0]['tests'][0],value=1.4e6)))
        t=build_iteration_history([a,b],['g'])['transitions'][0]
        c=t['case_changes'][0]
        self.assertTrue(c['measurement_layout_changed'])
        self.assertFalse(c['numeric_comparison_valid'])
        self.assertEqual(c['test_changes'],[])
        self.assertEqual(t['previously_passed_now_not_passed_case_ids'],[])
        self.assertEqual(c['after_status'],'passed_sampled_model_case')

    def test_different_limits_still_rejected_despite_part_count_difference(self):
        a,b=self.record(0),self.record(1)
        self.change_document(a,lambda d:d['rows']['g']['cases'][0]['tests'].append(
            dict(d['rows']['g']['cases'][0]['tests'][0],limit=2e6)))
        with self.assertRaises(ValueError):build_iteration_history([a,b],['g'])

    def test_prepare_adds_history_and_hash_binds_complete_request(self):
        a,b=self.record(0),self.record(1)
        policy,_=load_harness();plan=self.folder/'plan.json';plan.write_text('{}')
        state={'candidates':[a,b],'best_index':0,'plan_path':str(plan),'harness_path':'unused'}
        packet={'request_id':'old','iteration_history_configuration':policy['iteration_history'],
                'evaluation_scope':{'implemented_scope_case_ids':['g']}}
        with patch('opamp_pipeline.harness_03_loop.make_request',return_value=packet):prepare(self.folder,state)
        request=json.loads(Path(state['pending_request']['path']).read_text(encoding='utf-8'))
        self.assertEqual(len(request['iteration_history']['transitions']),1)
        self.assertEqual(request['request_id'],fingerprint({k:v for k,v in request.items() if k!='request_id'}))

    def test_v2_is_kept_and_default_v3_does_not_enable_harness_squared(self):
        v3,_=load_harness();v2,_=load_harness(Path(__file__).resolve().parents[1]/'harness/fixed_v2.json')
        self.assertEqual(v3['components'],v2['components'])
        self.assertEqual(v3['qualified_measurement_families'],v2['qualified_measurement_families'])
        self.assertTrue(v3['iteration_history']['enabled'])
        self.assertNotIn('iteration_history',v2)
        self.assertFalse(v3['harness2_enabled']);self.assertFalse(v3['instruction_evolution_enabled'])
