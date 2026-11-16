import unittest,tempfile
from unittest.mock import patch
from pathlib import Path
from copy import deepcopy
from opamp_pipeline.verify_07_startup_gate import startup_gate,gate_assessment
from opamp_pipeline.harness_03_loop import assessment
from opamp_pipeline.support.execution_state import file_hash
from opamp_pipeline.harness_06_evolution import outcome
from opamp_pipeline.harness_02_request import make_request


class StartupGateTests(unittest.TestCase):
    def test_missing_startup_blocks_completion_without_inflating_source_cases(self):
        p={'measurements':[{'cases':[{'fixture':{'supply_voltage_V':5}}]}]}
        g=startup_gate({},p)
        self.assertFalse(g['passed']);self.assertEqual(g['datasheet_case_count_increment'],0)
        base={'rows':{},'source_cases_required':0,'operational_startup':g}
        a=assessment(base,base,[])
        self.assertFalse(a['scope_passed']);self.assertEqual(a['failed_case_ids'],[])
        self.assertEqual(a['failed_requirement_ids'],['OPERATIONAL-STARTUP'])

    def test_qualified_receipt_and_tamper_detection(self):
        with tempfile.TemporaryDirectory() as d:
            paths=[]
            for n in ('cir','raw','log'):
                p=Path(d)/('a.'+n);p.write_text(n);paths.append(p)
            core={'startup_seeds':{'5':{'details':{'max_internal_tail_span_V':.001,'output_final_V':2.5,'bias_final_V':1},
                   'artifacts':{str(p):file_hash(p) for p in paths}}}}
            plan={'measurements':[{'cases':[{'fixture':{'supply_voltage_V':5}}]}]}
            g=startup_gate(core,plan);self.assertTrue(g['passed'])
            paths[0].write_text('changed')
            with self.assertRaises(ValueError):startup_gate(core,plan)
            with self.assertRaises(ValueError):gate_assessment({'operational_startup':g},{})
            bad=deepcopy(g);bad['policy']['stop_time_s']=.001
            with self.assertRaises(ValueError):gate_assessment({'operational_startup':g},{'operational_startup':bad})

    def test_incomplete_gate_cannot_claim_pass(self):
        g={'required':True,'passed':True,'policy':{},'supplies_V':[5,15],'cases':[{'supply_V':5,'passed':True}]}
        self.assertFalse(gate_assessment({}, {'operational_startup':g})['startup_passed'])

    def test_startup_regression_is_not_eligible_for_adoption(self):
        g={'required':True,'passed':True,'policy':{},'supplies_V':[5],'cases':[{'supply_V':5,'passed':True}]}
        base={'rows':{},'source_cases_required':0,'operational_startup':g}
        bad=deepcopy(base);bad['operational_startup']['passed']=False;bad['operational_startup']['cases'][0]['passed']=False
        verdict=outcome(base,bad,[])
        self.assertFalse(verdict['eligible']);self.assertFalse(verdict['scope_passed'])
        self.assertIn('OPERATIONAL-STARTUP',verdict['regressions_from_baseline'])

    def test_startup_failure_is_transmitted_to_designer(self):
        g={'required':True,'passed':False,'policy':{},'supplies_V':[5],'cases':[{'supply_V':5,'passed':False}]}
        result={'rows':{},'source_cases_required':0,'case_status_counts':{},'input_signatures':{},'operational_startup':g}
        with patch('opamp_pipeline.harness_02_request.validate_candidate'):
            request=make_request({'measurements':[]},result,'test')
        self.assertEqual(request['operational_startup'],g)
        self.assertIn('Required',request['feedback_interpretation']['startup_gate'])
