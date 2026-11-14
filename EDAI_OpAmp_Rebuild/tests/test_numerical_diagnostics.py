import unittest
from opamp_pipeline.diag_01_convergence import numerical_deck
from opamp_pipeline.diag_02_startup_seed import internal_nodes,supply_from_deck,seeded_deck,seeds_from_waveform


class NumericalDiagnosticsTests(unittest.TestCase):
    def test_numerics_preserve_tolerances_and_do_not_force_a_solution(self):
        deck='.options reltol=1e-6\n.op\n.end\n'
        changed=numerical_deck(deck,'alternate_hint',2.5)
        self.assertIn('.options reltol=1e-6',changed)
        self.assertNotIn('.ic ',changed);self.assertNotIn('uic',changed)
        self.assertIn('.nodeset V(out)=2.5',changed)
        with self.assertRaises(ValueError):numerical_deck(deck,'unknown',2.5)

    def test_supply_parsing_includes_negative_rail_and_psrr(self):
        self.assertEqual(supply_from_deck('VDD vp 0 10\nVSS vm 0 -10\n'),(20,-10))
        self.assertEqual(supply_from_deck('BVP vp 0 V=2.5+V(vsw)/2\nVSW vsw 0 5\n'),(5,0))
        with self.assertRaises(ValueError):supply_from_deck('VDD vp 0 0\n')

    def test_nodeset_targets_both_probe_copies_and_shifts_absolute_rails(self):
        deck='XDv mid xv vp 0 yv FIRSTAMP\nXDi mid xi vp 0 yi FIRSTAMP\n.ac lin 1 1 1\n.end\n'
        changed=seeded_deck(deck,{'bias':.85,'pg':19.2},-10)
        self.assertIn('V(XDv:bias)=-9.15',changed)
        self.assertIn('V(XDi:pg)=9.2',changed)
        self.assertNotIn('.ic ',changed)
        with self.assertRaises(ValueError):seeded_deck(deck.replace('.end','.ic V(a)=1\n.end'),{'bias':.85})

    def test_only_internal_device_nodes_are_saved(self):
        text='.subckt FIRSTAMP P N VP VM OUT\nM1 X P VM VM GNM W=20u L=2u\nR1 OUT X 1k\nC1 X BIAS 1p\n.ends\n'
        self.assertEqual(internal_nodes(text),['BIAS','X'])

    def test_incomplete_or_unsettled_startup_is_rejected(self):
        raw={'time':[0,80e-6,100e-6],'v(out)':[0,2.5,2.5],'v(xdut:bias)':[0,.85,.85]}
        seeds,details=seeds_from_waveform(raw,5,['BIAS'])
        self.assertEqual(seeds,{'bias':.85});self.assertEqual(details['max_internal_tail_span_V'],0)
        raw['v(xdut:bias)'][-1]=.9
        with self.assertRaises(ValueError):seeds_from_waveform(raw,5,['BIAS'])
        raw['time'][-1]=90e-6
        with self.assertRaises(ValueError):seeds_from_waveform(raw,5,['BIAS'])
