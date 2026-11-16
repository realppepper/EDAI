"""Deterministic distortion component only. Never label this THD+N compliance."""
import math
from pathlib import Path
import numpy as np


def harmonic_metrics(time,voltage,frequency,start,stop,bandwidth):
    t=np.asarray(time,dtype=float);v=np.asarray(voltage,dtype=float)
    if t.shape!=v.shape or len(t)<10 or not np.isfinite(t).all() or not np.isfinite(v).all():
        raise ValueError('Invalid waveform')
    if np.any(np.diff(t)<=0) or t[0]>start or t[-1]<stop or stop<=start or start<0:
        raise ValueError('Incomplete/nonmonotonic analysis window')
    cycles=(stop-start)*frequency
    if frequency<=0 or bandwidth<2*frequency or abs(cycles-round(cycles))>1e-7:
        raise ValueError('Whole-period window and at least two harmonics required')
    mask=(t>start)&(t<stop)
    x=np.r_[start,t[mask],stop];y=np.interp(x,t,v)
    if np.diff(x).max()>1/(10*bandwidth):raise ValueError('Insufficient time resolution for harmonic bandwidth')
    n=int(math.floor(bandwidth/frequency));phase=2*np.pi*frequency*(x-start)
    A=np.column_stack([np.ones(len(x)),*[a for k in range(1,n+1) for a in (np.sin(k*phase),np.cos(k*phase))]])
    weights=np.r_[np.diff(x)[0]/2,(x[2:]-x[:-2])/2,np.diff(x)[-1]/2]
    w=np.sqrt(weights/weights.mean());c,_,rank,_=np.linalg.lstsq(A*w[:,None],y*w,rcond=None)
    if rank!=A.shape[1]:raise ValueError('Singular harmonic fit')
    amplitudes=np.hypot(c[1::2],c[2::2]);fundamental=amplitudes[0]/math.sqrt(2)
    if fundamental<=1e-9:raise ValueError('Missing fundamental')
    return {'fundamental_Vrms':float(fundamental),'dc_V':float(c[0]),
            'thd_ratio':float(np.linalg.norm(amplitudes[1:])/amplitudes[0]),
            'fit_residual_rms_V':float(np.sqrt(np.average((y-A@c)**2,weights=weights))),
            'harmonics_included':n,'bandwidth_Hz':bandwidth,'window_s':[start,stop],
            'noise_included':False,'thdn_compliance_established':False}


def distortion_deck(model,fixture,frequency=1000,output_Vrms=3.53,maxstep='500n',subckt='FIRSTAMP'):
    if fixture['closed_loop_gain']!=1:raise ValueError('Only explicit unity-gain fixture supported')
    vp=fixture['rails_V']['V_plus'];vm=fixture['rails_V']['V_minus'];mid=(vp+vm)/2
    load=fixture['load']
    if load['kind']!='resistance' or load['connection']!='rail_midpoint':raise ValueError('Unsupported load')
    return f'''* Deterministic distortion; no calibrated stochastic noise claim
.include "{Path(model).resolve()}"
.temp {fixture['temperature_C']}
.options plotwinsize=0 numdgt=15 reltol=1e-5 vntol=1e-8
VDD vp 0 {vp}
VSS vm 0 {vm}
VMID mid 0 {mid}
VIN inp 0 SINE({mid} {output_Vrms*math.sqrt(2):.15g} {frequency})
XDUT inp out vp vm out {subckt}
RL out mid {load['value_Ohm']}
.save V(inp) V(out) I(RL)
.tran 0 12m 0 {maxstep}
.end
'''
