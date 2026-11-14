import unittest
from opamp_pipeline.design_02_check_bias import region


class BiasDiagnosticTests(unittest.TestCase):
    def test_cutoff_linear_saturation(self):
        self.assertEqual(region(.4,3,.65)['region_nominal'],'cutoff')
        self.assertEqual(region(1,.1,.65)['region_nominal'],'linear')
        self.assertEqual(region(1,2,.65)['region_nominal'],'saturation')
        self.assertAlmostEqual(region(1,2,.65)['saturation_margin_V'],1.65)
