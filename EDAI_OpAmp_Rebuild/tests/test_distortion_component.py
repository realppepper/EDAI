import unittest
import numpy as np
from opamp_pipeline.verify_08_distortion import harmonic_metrics


class DistortionComponentTests(unittest.TestCase):
    def test_known_harmonics_and_dc(self):
        t=np.linspace(0,.012,24001);phase=2*np.pi*1000*t
        for ratio in (0,.005,.02):
            v=18+5*np.sin(phase)+5*ratio*np.cos(2*phase)
            m=harmonic_metrics(t,v,1000,.008,.012,80000)
            self.assertAlmostEqual(m['thd_ratio'],ratio,places=9)
            self.assertAlmostEqual(m['fundamental_Vrms'],5/np.sqrt(2),places=9)
            self.assertFalse(m['thdn_compliance_established'])

    def test_invalid_waveforms_rejected(self):
        t=np.linspace(0,.012,1201);v=np.sin(2*np.pi*1000*t)
        with self.assertRaises(ValueError):harmonic_metrics(t,v,1000,.008,.012,80000)
        with self.assertRaises(ValueError):harmonic_metrics(t,v,1000,.008,.0125,10000)
