import tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from opamp_pipeline.diag_03_solver_attempts import run_with_fallback,SolverAttemptsError,measured_trace_deck


class SolverAttemptsTests(unittest.TestCase):
    def test_trace_selection_preserves_waveform_timepoints_and_tolerances(self):
        deck='.save V(*) I(*)\n.options reltol=1e-6 plotwinsize=0\n.tran 0 40u 0 2n\n.end\n'
        changed=measured_trace_deck(deck,{'analysis':'tran','kind':'settling'})
        self.assertEqual(changed.replace('.save V(out) V(inp)','.save V(*) I(*)'),deck)

    def test_phase_trace_keeps_all_dual_injection_variables(self):
        changed=measured_trace_deck('.ac dec 100 1 1Meg\n.end\n',{'analysis':'ac','kind':'pm'})
        for name in ('V(xv)','V(xi)','V(yv)','V(yi)','I(Vprobev)','I(Vprobei)'):self.assertIn(name,changed)

    def test_noise_data_selection_is_unchanged(self):
        deck='.save V(*) I(*)\n.noise V(out) VIN dec 100 1 100k\n.end\n'
        self.assertEqual(measured_trace_deck(deck,{'analysis':'noise','kind':'noise_density'}),deck)

    def test_success_never_runs_a_second_attempt(self):
        with tempfile.TemporaryDirectory() as d,patch('opamp_pipeline.diag_03_solver_attempts.run_bench',return_value={'measurements':{}}) as run:
            p=Path(d)/'bench.cir';p.write_text('.op\n.end\n');r=run_with_fallback('spice',p,[],True,10,'.op\n.end\n')
            self.assertEqual(run.call_count,1);self.assertEqual(r['path'],p)

    def test_failure_preserves_both_decks_and_passes_exact_fallback(self):
        fallback='.options reltol=1e-6\nR1 a 0 10000\n.op\n.end\n'
        with tempfile.TemporaryDirectory() as d,patch('opamp_pipeline.diag_03_solver_attempts.run_bench',side_effect=[TimeoutError('slow'),{'measurements':{}}]):
            p=Path(d)/'bench.cir';p.write_text('seeded original');r=run_with_fallback('spice',p,[],True,10,fallback)
            self.assertEqual(p.read_text(),'seeded original');self.assertEqual(r['path'].read_text(),fallback)
            self.assertEqual([x['status'] for x in r['attempts']],['execution_error','computed'])

    def test_both_failures_are_reported(self):
        with tempfile.TemporaryDirectory() as d,patch('opamp_pipeline.diag_03_solver_attempts.run_bench',side_effect=TimeoutError('slow')):
            p=Path(d)/'bench.cir';p.write_text('original')
            with self.assertRaises(SolverAttemptsError) as raised:run_with_fallback('spice',p,[],True,10,'fallback')
            self.assertEqual(len(raised.exception.attempts),2)
