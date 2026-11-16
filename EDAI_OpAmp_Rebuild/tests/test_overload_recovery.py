import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch
from run_overload_extension import recovery_job_path
from opamp_pipeline.diag_03_solver_attempts import run_with_fallback
from opamp_pipeline.verify_05_overload_recovery import recovery_profile,recovery_metrics,analytic_recovery


def profile(direction='high'):
    item={'method':{'definition':{'gain':-10,'initial_input_offset_fraction_of_supply':.12,'output_error_band_fraction_of_supply':.001}}}
    case={'fixture':{'supply_voltage_V':5,'rails_V':{'V_plus':5,'V_minus':0},'closed_loop_gain':-10}}
    return recovery_profile(item,case,direction)


def waveform(direction='high'):
    high=direction=='high';p=profile(direction);sign=1 if high else -1
    t=[x*1e-6 for x in (0,2,4,5,5.01,22,23,24,25,25.01,26,27,35,45,60)]
    out=[2.5]*4+[2.5+sign*2.25]*6+[2.5+sign*.5]+[2.5]*4
    stim=[2.5 if x<5.01e-6 or x>=25.01e-6 else 2.5+p['input_offset_V'] for x in t]
    # Select exact plateau values at the rounded time coordinates.
    for i,x in enumerate(t):
        if 22e-6<=x<=25e-6:stim[i]=2.5+p['input_offset_V']
        if x>=25.01e-6:stim[i]=2.5
    return {'time':t,'v(out)':out,'v(stim)':stim,'v(inp)':[2.5]*len(t),'v(inn)':[(10*v+y)/11 for v,y in zip(stim,out)]}


class OverloadRecoveryTests(unittest.TestCase):
    def test_distinct_jobs_can_both_use_normal_retry_without_folder_collision(self):
        with tempfile.TemporaryDirectory() as temp:
            seen=[]
            def runner(executable,path,*args,**kwargs):
                seen.append(str(path))
                if path.parent.name!='normal_retry':raise RuntimeError('injected primary failure')
                return {'computed':True}
            with patch('opamp_pipeline.diag_03_solver_attempts.run_bench',side_effect=runner):
                results=[]
                for index,direction in [(0,'high'),(0,'low'),(1,'high')]:
                    path=recovery_job_path(temp,index,5,direction);path.write_text('primary')
                    results.append(run_with_fallback('fake',path,[],True,60,'fallback'))
            self.assertEqual(len({str(r['path']) for r in results}),3)
            self.assertEqual(len(seen),6)
            self.assertTrue(all(len(r['attempts'])==2 for r in results))

    def test_both_saturation_directions_have_evidence_and_recover(self):
        for direction in ('high','low'):
            with self.subTest(direction=direction):
                m=recovery_metrics(waveform(direction),profile(direction))
                self.assertEqual(m['gate_issues'],[])
                self.assertGreater(m['value'],1e-6);self.assertLess(m['value'],3e-6)

    def test_no_overload_is_never_a_zero_time_pass(self):
        r=waveform();r['v(out)']=[2.5]*len(r['time']);r['v(stim)']=[2.5]*len(r['time']);r['v(inn)']=[2.5]*len(r['time'])
        with self.assertRaises(ValueError):recovery_metrics(r,profile())

    def test_stuck_output_and_truncated_observation(self):
        r=waveform()
        r['v(out)']=[3 if x>=26e-6 else y for x,y in zip(r['time'],r['v(out)'])]
        self.assertIsNone(recovery_metrics(r,profile())['value'])
        for k in r:r[k]=r[k][:-1]
        with self.assertRaises(ValueError):recovery_metrics(r,profile())

    def test_late_departure_from_error_band_counts_as_unrecovered(self):
        r=waveform();r['v(out)'][-2]=2.6
        self.assertGreater(recovery_metrics(r,profile())['value'],10e-6)

    def test_reference_fast_and_slow_straddle_ten_microseconds(self):
        for direction in ('high','low'):
            self.assertLess(analytic_recovery(profile(direction),1e-9),10e-6)
            self.assertGreater(analytic_recovery(profile(direction),5e-9),10e-6)
