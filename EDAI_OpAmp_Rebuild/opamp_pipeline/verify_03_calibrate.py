"""Known-answer checks for new source-bound fixture methods before DUT verdicts."""
import math
from copy import deepcopy
from .verify_01_fixtures import build_fixture
from .verify_02_metrics import measure
from .tb_06_loop_gain import dual_probe_deck,measure_dual_probe
from .verify_04_dc_coverage import require_complete_vcm_case

REFERENCE='''* Analytical fixture-validation model, NOT an IC design
.subckt CALX P N VP VM OUT
Berr e 0 V=10000*(V(P,N)-0.001-20u*((V(P)+V(N))/2-2.5)-5u*(V(VP,VM)-5))
Rp e x 1k
Cp x 0 1.59154943091895u
Bdrv d 0 V=(V(VP)+V(VM))/2+V(x)
Rout d OUT 100
Ibias VP VM 100u
.ends CALX
'''
OUTPUT_REFERENCE='''* Clipped-voltage source with exact100Ohm output resistance, calibration only
.subckt OUTREF P N VP VM OUT
Bdrv d 0 V=limit((V(VP)+V(VM))/2+10000*V(P,N),V(VM),V(VP))
Rout d OUT 100
.ends OUTREF
'''


def calibrate(out,measurements,execute):
    folder=out/'calibration';folder.mkdir(exist_ok=True)
    model=folder/'reference.inc';model.write_text(REFERENCE,encoding='ascii')
    output_model=folder/'output_reference.inc';output_model.write_text(OUTPUT_REFERENCE,encoding='ascii')
    checks=[]
    def check(name,value,expected,tol):
        checks.append({'name':name,'measured':value,'expected':expected,'tolerance':tol,
            'passed':value is not None and math.isfinite(value) and abs(value-expected)<=tol})
    def run(symbol,variant='default',model=model,subckt='CALX'):
        item=next(m for m in measurements['measurements'] if m['symbol']==symbol)
        case=next((c for c in item['cases'] if c['fixture']['supply_voltage_V']==5),item['cases'][0])
        deck,meta=build_fixture(model,item,case,variant,subckt)
        job=execute('cal_'+symbol+'_'+variant,deck,meta)
        return measure(job['path'],item['method']['kind'],case['fixture'],meta,job['measurements']),meta
    for symbol,expected,tol in [('VOS',.001,1e-7),('PSRR',5e-6,1e-8),('CMRR',20e-6,1e-8),('AOL',10000/1.01,2),('GBW',10000/1.01*(1-10e-6)*100,2000),('RO',100,.01)]:
        result,_=run(symbol);check(symbol,result['value'],expected,tol)
        checks.append({'name':symbol+'_linear_fixture_gates','passed':not result['gate_issues']})
    for variant in ('rising','falling'):
        result,meta=run('SR',variant);step=meta['step'];K=10000/1.01;a=20e-6
        final=(2.5+K*((1-a/2)*step['final_V']-.001+a*2.5))/(1+K*(1+a/2))
        sign=1 if variant=='rising' else -1;amp=2
        v10=step['initial_V']+sign*.1*amp;v90=step['initial_V']+sign*.9*amp
        tau=1/(2*math.pi*100*(1+K*(1+a/2)))
        expected=.8*amp/(tau*math.log(abs((final-v10)/(final-v90))))
        check('SR_'+variant,result['value'],expected,expected*.005)
    # Check current sign and separation of external load current from DUT terminal current.
    for row in [m for m in measurements['measurements'] if m['symbol']=='IO'][:2]:
        c=row['cases'][0];deck,meta=build_fixture(output_model,row,c,subckt='OUTREF')
        job=execute('cal_current_'+meta['direction'],deck,meta)
        result=measure(job['path'],'iout',c['fixture'],meta,job['measurements'])
        check('output_current_'+meta['direction'],result['value'],.15,1e-7)
    for supply in (5,15,36):
        for cap in (20e-12,100e-12):
            deck=dual_probe_deck(model,'CALX',load_C=cap).replace('VDD vp 0 5',f'VDD vp 0 {supply}').replace('VMID mid 0 2.5',f'VMID mid 0 {supply/2}')
            job=execute(f'cal_pm_{supply}_{cap}',deck,{'names':[],'analysis':'ac'})
            measured=measure_dual_probe(job['path'].with_suffix('.raw'))
            gain=10000/1.01*(1+10e-6);pole2=(1/100+1/10000)/(2*math.pi*cap)
            lo=1.;hi=1e8
            for _ in range(80):
                mid=math.sqrt(lo*hi)
                if abs(gain/(1+1j*mid/100)/(1+1j*mid/pole2))>1:lo=mid
                else:hi=mid
            frequency=math.sqrt(lo*hi);pm=180-math.degrees(math.atan(frequency/100)+math.atan(frequency/pole2))
            check(f'PM_{supply}V_{cap*1e12:.0f}pF',measured['phase_margin_deg'],pm,.05)
    noise='''* Known resistor thermal noise calibration
.temp 25
VIN inp 0 AC 1
R1 inp out 10k
RL out 0 1e12
.noise V(out) VIN dec 100 1 100k
.meas NOISE en_1k FIND V(inoise) AT=1k
.end
'''
    job=execute('cal_noise',noise,{'analysis':'noise','names':['en_1k']})
    check('resistor_noise_density',job['measurements']['en_1k'],math.sqrt(4*1.380649e-23*298.15*10000),1e-10)
    # Separate positive and negative controls for the complete center-out grid.
    dc_checks=[]
    item=next(m for m in measurements['measurements'] if m['method']['kind']=='vcm')
    case=next(c for c in item['cases'] if c['fixture']['supply_voltage_V']==5)
    bad_model=folder/'vcm_bad_reference.inc'
    bad_model.write_text(REFERENCE.replace('-0.001-20u','-0.03-20u'),encoding='ascii')
    for policy,variants in [('center_out_complete_grid_v1',('lower','upper')),('full_ascending',('default',))]:
        for name,reference,expected_pass in [('vcm_good',model,True),('vcm_bad',bad_model,False)]:
            parts=[]
            for variant in variants:
                deck,meta=build_fixture(reference,item,case,variant,'CALX')
                job=execute('cal_'+name+'_'+policy+'_'+variant,deck,meta)
                part=measure(job['path'],'vcm',case['fixture'],meta,job['measurements'])
                part['variant']=variant;parts.append(part)
            coverage=require_complete_vcm_case(case['fixture'],parts)
            observed=all(part['value']<=.01 and not part['gate_issues'] for part in parts)
            dc_checks.append({'name':name,'policy':policy,'expected_spec_pass':expected_pass,'observed_spec_pass':observed,
                             'coverage':coverage,'max_tracking_error_V':max(p['value'] for p in parts),
                             'passed':observed==expected_pass})
    return {'status':'passed' if all(c['passed'] for c in checks+dc_checks) else 'failed','checks':checks,
            'dc_grid_validation':dc_checks,
            'note':'Controlled-source calibration only. MOS flicker/leakage accuracy is not calibrated.'}
