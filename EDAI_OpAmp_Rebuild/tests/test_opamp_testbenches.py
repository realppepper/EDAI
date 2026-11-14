import tempfile,unittest
from pathlib import Path
from opamp_pipeline.tb_02_ltspice import parse_measurements
from opamp_pipeline.tb_04_opamp_fixtures import generate_fixtures
from opamp_pipeline.tb_05_waveform_metrics import read_real_raw,settling_metrics


class OpAmpFixtureTests(unittest.TestCase):
    def test_when_coordinate_is_not_threshold(self):
        text='unity_hz: mag(V(out))=1  AT 999823.130105\n'
        self.assertEqual(parse_measurements(text,['unity_hz']),{'unity_hz':999823.130105})

    def test_ring_reentry_uses_last_crossing(self):
        step={'start_s':0,'transition_s':1,'initial_V':0,'final_V':1,
              'error_fraction':.1,'stop_s':5,'max_step_s':.1}
        # First entry is not settling: a later excursion exits the band.
        r=settling_metrics([0,1,2,3,4,5],[0,.8,1,1.2,1.05,1],step)
        self.assertAlmostEqual(r['settling_s'],2+2/3)
        self.assertEqual(r['status'],'settled_within_observation_window')

    def test_unsettled_or_incomplete_not_pass(self):
        step={'start_s':0,'transition_s':1,'initial_V':0,'final_V':1,
              'error_fraction':.1,'stop_s':3,'max_step_s':.1}
        r=settling_metrics([0,1,2,3],[0,.8,1,1.2],step)
        self.assertIsNone(r['settling_s'])
        with self.assertRaises(ValueError):settling_metrics([0,1,2],[0,.8,1],step)
        with self.assertRaises(ValueError):settling_metrics([0,1,1,3],[0,.8,1,1],step)

    def test_ascii_raw_parser_and_truncation(self):
        text='Flags: real\nNo. Variables: 2\nNo. Points: 2\nVariables:\n0 time time\n1 V(out) voltage\nValues:\n0 0\n1\n1 .1\n2\n'
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/'x.raw';p.write_text(text,encoding='utf-8')
            self.assertEqual(read_real_raw(p),{'time':[0,.1],'v(out)':[1,2]})
            p.write_text(text.rsplit('2',1)[0],encoding='utf-8')
            with self.assertRaises(ValueError):read_real_raw(p)

    def test_all_analysis_families_and_explicit_single_channel_binding(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/'model.inc';p.write_text('* placeholder',encoding='ascii')
            decks=generate_fixtures(p)
            self.assertEqual([b['analysis'] for b in decks],['op','dc','ac','tran','tran'])
            for d in decks:self.assertIn('XDUT inp inn vp 0 out CALAMP',d['deck'])
            with self.assertRaises(ValueError):generate_fixtures(p,'invalid name')
