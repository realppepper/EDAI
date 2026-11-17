"""Input two-port admittance and a declared symmetric parallel-R/C interpretation."""
import math
from pathlib import Path
from .verify_01_fixtures import header
from .tb_06_loop_gain import read_complex_raw
from .tb_05_waveform_metrics import read_real_raw
from .validation_05_special_fixtures import IMPEDANCE_POLICY

REFERENCE='''* Known passive input network plus isolated amplifier; calibration only
.subckt ZREF P N VP VM OUT
RD P N 10Meg
CD P N 0.1p
RP P VM 4Gig
RN N VM 4Gig
CP P VM 1.5p
CN N VM 1.5p
Bdrive drive 0 V=(V(VP)+V(VM))/2+10000*V(P,N)
RO drive OUT 100
.ends ZREF
'''


def impedance_deck(model,fixture,mode,subckt='FIRSTAMP'):
    if mode not in {'differential','common'}:raise ValueError('Unknown port excitation')
    a,b=(.5,-.5) if mode=='differential' else (1,1)
    return header(model,fixture,subckt)+f'''* DC-only output servo; AC port voltages are measured, not assumed
Lservo out sfb 1e15
Cservo sfb mid 1
Bservo vid 0 V=1e5*(V(mid)-V(sfb))
VTEST test 0 DC 0 AC 1
BP inp mid V=0.5*V(vid)+{a}*V(test)
BN inn mid V=-0.5*V(vid)+{b}*V(test)
.save V(inp) V(inn) V(out) V(mid) V(vid) I(BP) I(BN)
.op
.ac dec 40 1 1Meg
.end
'''


def parallel_fit(frequencies,admittance):
    if len(frequencies)!=len(admittance) or len(frequencies)<3:raise ValueError('Insufficient impedance samples')
    if any(not math.isfinite(f) or f<=0 for f in frequencies) or any(b<=a for a,b in zip(frequencies,frequencies[1:])):
        raise ValueError('Frequency grid must be positive and increasing')
    if any(not (math.isfinite(y.real) and math.isfinite(y.imag)) for y in admittance):raise ValueError('Nonfinite admittance')
    low=[y.real for f,y in zip(frequencies,admittance) if f<=frequencies[0]*10]
    conductance=sum(low)/len(low)
    omega=[2*math.pi*f for f in frequencies]
    capacitance=sum(w*y.imag for w,y in zip(omega,admittance))/sum(w*w for w in omega)
    residual=max(abs(y-complex(conductance,w*capacitance))/max(abs(y),1e-18) for w,y in zip(omega,admittance))
    floor=IMPEDANCE_POLICY['conductance_floor_S'];issues=[];cap_issues=[];res_issues=[]
    point_caps=[y.imag/w for w,y in zip(omega,admittance)]
    cap_dispersion=max(abs(c-capacitance) for c in point_caps)/max(abs(capacitance),1e-18)
    g_dispersion=max(abs(y.real-conductance) for y in admittance)/max(abs(conductance),floor)
    if capacitance<0:cap_issues.append('Negative equivalent capacitance')
    if cap_dispersion>IMPEDANCE_POLICY['relative_tolerance']:cap_issues.append('Capacitance dispersion exceeds5% over project band')
    if conductance < -floor:res_issues.append('Negative equivalent conductance')
    if g_dispersion>IMPEDANCE_POLICY['relative_tolerance']:res_issues.append('Conductance is not constant within5% over project band')
    issues+=cap_issues+res_issues
    if residual>IMPEDANCE_POLICY['relative_tolerance']:issues.append('Parallel R/C fit residual exceeds declared5% across project1Hz–1MHz band')
    resolved=conductance>floor and not issues
    return {'conductance_S':conductance,'resistance_Ohm':1/conductance if resolved else None,
            'diagnostic_inverse_conductance_Ohm':1/conductance if conductance>floor else None,
            'resistance_resolution_floor_S':floor,'resistance_status':'resolved_numeric_equivalent' if resolved else 'constant_positive_resistance_not_qualified',
            'capacitance_F':capacitance,'max_relative_fit_residual':residual,'fit_issues':issues,
            'capacitance_fit_issues':cap_issues,'resistance_fit_issues':res_issues,
            'relative_capacitance_dispersion':cap_dispersion,'relative_conductance_dispersion':g_dispersion,
            'pointwise_capacitance_range_F':[min(point_caps),max(point_caps)],
            'frequency_min_Hz':frequencies[0],'frequency_max_Hz':frequencies[-1]}


def modal_admittance(differential,common):
    freq=[v.real for v in differential['frequency']]
    if len(freq)!=len(common['frequency']) or any(abs(a-b.real)>1e-9*max(1,a) for a,b in zip(freq,common['frequency'])):
        raise ValueError('Excitation grids differ')
    result={'frequency_Hz':freq,'differential_branch_Y':[],'common_per_pin_Y':[],'common_pin_p_Y':[],'common_pin_n_Y':[],'cross_coupling_ratio':[]}
    for i in range(len(freq)):
        def port(raw):
            p,n=raw['v(inp)'][i],raw['v(inn)'][i];ip,inn=-raw['i(bp)'][i],-raw['i(bn)'][i]
            return p-n,(p+n)/2,(ip-inn)/2,ip+inn
        vd,vc,id_,ic=port(differential);wd,wc,jd,jc=port(common);det=vd*wc-wd*vc
        if abs(det)<1e-12:raise ValueError('Singular port excitation matrix')
        ydd=(id_*wc-jd*vc)/det;ydc=(-id_*wd+jd*vd)/det
        ycd=(ic*wc-jc*vc)/det;ycc=(-ic*wd+jc*vd)/det
        # The modal differential port includes half of each-to-ground admittance.
        result['differential_branch_Y'].append(ydd-ycc/4)
        result['common_per_pin_Y'].append(ycc/2)
        result['common_pin_p_Y'].append(ycc/2+ydc)
        result['common_pin_n_Y'].append(ycc/2-ydc)
        result['cross_coupling_ratio'].append(max(abs(ydc),abs(ycd))/max(abs(ydd),abs(ycc),1e-18))
    return result


def measure_pair(differential_path,common_path,metas=None):
    paths=[Path(differential_path),Path(common_path)];gates=[]
    if metas is not None:
        from .validation_03_execution_contract import validate_execution
        if len(metas)!=2:raise ValueError('Both input-mode contracts are required')
        for path,meta in zip(paths,metas):
            meta['fit_policy']=dict(IMPEDANCE_POLICY)
            validate_execution(path.read_text(encoding='ascii'),meta,phase='impedance_before_metric')
    for path in paths:
        op=read_real_raw(path.with_suffix('.op.raw'))
        if abs(op['v(out)'][0]-op['v(mid)'][0])>=1e-5 or abs(op['v(vid)'][0])>=.05:
            gates.append('No valid small-differential midpoint operating point')
    data=modal_admittance(*(read_complex_raw(p.with_suffix('.raw')) for p in paths))
    differential_issues=[]
    if max(data['cross_coupling_ratio'])>.05:differential_issues.append('More than5% cross-mode coupling; symmetric differential-branch interpretation not qualified')
    return {'differential':parallel_fit(data['frequency_Hz'],data['differential_branch_Y']),
            'common':parallel_fit(data['frequency_Hz'],data['common_per_pin_Y']),
            'common_pin_p':parallel_fit(data['frequency_Hz'],data['common_pin_p_Y']),
            'common_pin_n':parallel_fit(data['frequency_Hz'],data['common_pin_n_Y']),
            'differential_interpretation_issues':differential_issues,
            'max_cross_coupling_ratio':max(data['cross_coupling_ratio']),'gate_issues':gates,
            'definition':'Differential bridge admittance Ydd-Ycc/4; common-mode admittance per pin Ycc/2. Actual voltage/current excitation matrix inverted.',
            'excitation':'Equivalent voltage/current method: applied AC voltage and measured input current; no feedback-bootstrapped follower impedance.',
            'source_frequency_not_specified':True,'fit_band_is_project_policy':True}
