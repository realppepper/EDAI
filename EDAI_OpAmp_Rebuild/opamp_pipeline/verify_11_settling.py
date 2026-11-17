"""First-order settling controls, including finite input-transition timing."""
import math
from .verify_01_fixtures import build_fixture
from .verify_02_metrics import measure


def calibrate_settling(out,item,case,execute):
    controls=[]
    for name,tau in [('fast',40e-9),('slow',200e-9)]:
        reference=out/(name+'_settling.inc')
        reference.write_text(f'.subckt SETREF P N VP VM OUT\nEDRIVE drive 0 P 0 1\nRPOLE drive pole 1k\nCPOLE pole VM {tau/1000:.15g}\nEOUT OUT 0 pole 0 1\n.ends SETREF\n',encoding='ascii')
        for direction in ('rising','falling'):
            deck,meta=build_fixture(reference,item,case,direction,'SETREF')
            job=execute('cal_settling_'+name+'_'+direction,deck,meta)
            observed=measure(job['path'],'settling',case['fixture'],meta,job['measurements'])
            transition=meta['step']['transition_s'];fraction=meta['step']['error_fraction']
            expected=max(0,tau*math.log(tau/transition*(-math.expm1(-transition/tau))/fraction))
            expected_pass=expected<=item['target_s']
            passed=not observed['gate_issues'] and observed['value'] is not None and abs(observed['value']-expected)<2e-9 and (observed['value']<=item['target_s'])==expected_pass
            controls.append({'name':name,'direction':direction,'expected_s':expected,'expected_target_pass':expected_pass,'measured':observed,'passed':bool(passed)})
    return controls
