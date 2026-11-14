"""Compare measurements against analytical values; absent/nonfinite never pass."""
import math

def judge(value,expected,tolerance):
    if not isinstance(value,(int,float)) or not math.isfinite(value):return False
    return abs(value-expected)<=tolerance

def validate_reference(values,expected):
    return {name:{'measured':values.get(name),'expected':goal,'absolute_tolerance':tol,
                  'passed':judge(values.get(name),goal,tol)} for name,(goal,tol) in expected.items()}
