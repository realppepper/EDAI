import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from opamp_pipeline.pipeline_01_verification import run_pipeline
from opamp_pipeline.loop_02_handoff import write_json


class PipelineProcessRecoveryTests(unittest.TestCase):
    def run_scenario(self, failed_stage):
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory);model=p/'candidate.inc';model.write_text('test model')
            plan=p/'run/measurement_plan/plan_02_measurements.json';write_json(plan,{
                'measurements':[{'method':{'kind':k}} for k in ('zid','zic','overload_recovery')]})
            policy=p/'policy.json';write_json(policy,{})
            out=p/'validation';calls=[];failed=[]
            expected={'core':'completed_with_explicit_unverified_cases','impedance':'extension_completed_with_explicit_model_limitations','overload':'extension_completed'}
            def worker(command,**kwargs):
                name='core' if 'run_extended_verification.py' in command[1] else 'impedance' if 'run_input_impedance_extension.py' in command[1] else 'overload'
                flag='--resume' if '--resume' in command else '--output-dir';dest=Path(command[command.index(flag)+1]);dest.mkdir(parents=True,exist_ok=True)
                calls.append((name,flag,str(dest)))
                if name==failed_stage and not failed:
                    failed.append(True);write_json(dest/'RESULT.json',{'status':'error'})
                    return SimpleNamespace(returncode=1,stdout=b'first stdout',stderr=b'original worker failure')
                write_json(dest/'RESULT.json',{'status':expected[name]})
                return SimpleNamespace(returncode=0,stdout=b'recovered stdout',stderr=b'')
            result={'case_status_counts':{}}
            with patch('opamp_pipeline.pipeline_01_verification.validate_candidate'),patch('opamp_pipeline.pipeline_01_verification.subprocess.run',side_effect=worker),patch('opamp_pipeline.pipeline_01_verification.check_chain',return_value=result),patch('opamp_pipeline.pipeline_01_verification.make_request',return_value={}):
                with self.assertRaises(RuntimeError):run_pipeline(model,p/'run',out,'unused',harness=policy)
                first=out/failed_stage/'process_attempt_001/stderr.txt'
                self.assertEqual(first.read_bytes(),b'original worker failure')
                state=run_pipeline(model,p/'run',out,'unused',resume=True,harness=policy)
                self.assertEqual(state['status'],'completed')
                self.assertNotIn('error',state)
                self.assertEqual(len(state['error_history']),1)
                self.assertEqual(first.read_bytes(),b'original worker failure')
                self.assertEqual(len(state['stage_attempts'][failed_stage]),2)
                count=len(calls);run_pipeline(model,p/'run',out,'unused',resume=True,harness=policy)
                self.assertEqual(len(calls),count)
            if failed_stage=='core':self.assertEqual([flag for stage,flag,dest in calls if stage=='core'],['--output-dir','--resume'])
            else:
                self.assertEqual(sum(stage=='core' for stage,flag,dest in calls),1)
                self.assertTrue(any('attempt_002' in dest for stage,flag,dest in calls if stage=='impedance'))

    def test_failed_core_reuses_checkpoint_and_preserves_process_logs(self):
        self.run_scenario('core')

    def test_completed_core_is_not_rerun_when_later_stage_restarts(self):
        self.run_scenario('impedance')
