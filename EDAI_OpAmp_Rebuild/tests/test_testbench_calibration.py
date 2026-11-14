import unittest
from opamp_pipeline.tb_02_ltspice import parse_measurements
from opamp_pipeline.tb_03_validate_reference import judge

class CalibrationTests(unittest.TestCase):
    def test_real_and_cartesian_scalar_logs(self):
        text="a: V(out) =2.5 at 0.001\nb: mag(V(out)) =(0.707,0) at 159\nc: ph(V(out)) =(-45,0) at 159"
        self.assertEqual(parse_measurements(text,['a','b','c']),{'a':2.5,'b':.707,'c':-45})
    def test_failed_duplicate_complex_and_db_not_silently_accepted(self):
        for text in ['Measurement: a FAIL​ED','a: x =1 at 1\na: x =2 at 1','a: x =(1,2) at 1','a: x =(3dB,0°) at 1','a: x =1e999 at 1']:
            with self.subTest(text=text):self.assertEqual(parse_measurements(text,['a']),{})
    def test_missing_and_nonfinite_fail(self):
        for value in (None,float('nan'),float('inf')):self.assertFalse(judge(value,1,1))
        self.assertFalse(judge(2.5,3,.01))
