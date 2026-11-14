"""Tian dual-injection, following LTspice Educational/LoopGain2.asc.

Vprobe is positive at feedback x, negative at amplifier output y.
Iprobe injects from ground into x. Two identical circuit copies share ideal rails.
Let Vv,Iv be x voltage/probe current for voltage injection, Vi,Ii for current.
S=2*(Iv*Vi - Vv*Ii)+Vv+Ii; T=-S/(S-1), with unit injections.
"""
import cmath,math
from pathlib import Path
from .tb_02_ltspice import decode_log

METHOD='tian_dual_injection_ltspice_loopgain2'
SOURCE='LTspice examples/Educational/LoopGain2.asc; Tian et al., Striving for Small-Signal Stability, 2001'


def dual_probe_deck(model,subckt,load_R=10000,load_C=20e-12,points=300):
    if load_R<=0 or load_C<0:raise ValueError('Invalid external load')
    lines=['* Dual injection at amplifier output, two DC-identical copies',
        f'.include "{Path(model).resolve()}"','.temp 25','.options plotwinsize=0 meascplxfmt=cartesian',
        'VDD vp 0 5','VMID mid 0 2.5']
    for suffix,voltage,current in [('v',1,0),('i',0,1)]:
        lines += [f'XD{suffix} mid x{suffix} vp 0 y{suffix} {subckt}',
            f'Rload{suffix} y{suffix} mid {load_R:.12g}',
            f'Vprobe{suffix} x{suffix} y{suffix} DC 0 AC {voltage}',
            f'Iprobe{suffix} 0 x{suffix} DC 0 AC {current}']
        if load_C:lines += [f'Cload{suffix} y{suffix} mid {load_C:.12g}']
    lines += ['.op',f'.ac dec {points} 0.01 100Meg','.end']
    return '\n'.join(lines)+'\n'


def read_complex_raw(path):
    text=decode_log(path)
    if 'Flags: complex' not in text or 'Values:' not in text:raise ValueError('Expected ASCII complex raw')
    header,body=text.split('Values:',1)
    count=int(next(s.split(':',1)[1] for s in header.splitlines() if s.startswith('No. Points:')))
    names=[s.split()[1].lower() for s in header.split('\nVariables:',1)[1].strip().splitlines()]
    tokens=body.split();width=len(names)+1
    if len(names)!=len(set(names)) or len(tokens)!=count*width:raise ValueError('Truncated or ambiguous AC data')
    columns={name:[] for name in names}
    for index in range(count):
        row=tokens[index*width:(index+1)*width]
        if int(row[0])!=index:raise ValueError('AC point index mismatch')
        for name,value in zip(names,row[1:]):
            real,imag=value.strip('()').split(',');z=complex(float(real),float(imag))
            if not math.isfinite(z.real) or not math.isfinite(z.imag):raise ValueError('Nonfinite AC data')
            columns[name].append(z)
    return columns


def tian_from_raw(raw):
    frequencies=[];values=[]
    for f,vv,iv,vi,ii in zip(raw['frequency'],raw['v(xv)'],raw['i(vprobev)'],raw['v(xi)'],raw['i(vprobei)']):
        if abs(f.imag)>1e-12 or f.real<=0:raise ValueError('Invalid frequency')
        s=2*(iv*vi-vv*ii)+vv+ii
        if abs(s-1)<1e-14:raise ValueError('Ill-conditioned Tian denominator')
        frequencies.append(f.real);values.append(-s/(s-1))
    return frequencies,values


def loop_margins(frequencies,values):
    if len(frequencies)!=len(values) or len(values)<3:raise ValueError('Insufficient loop samples')
    if any(f<=0 or not math.isfinite(f) for f in frequencies) or any(b<=a for a,b in zip(frequencies,frequencies[1:])):
        raise ValueError('Frequency must be finite, positive, increasing')
    magnitude=[];phases=[]
    for z in values:
        if not math.isfinite(z.real) or not math.isfinite(z.imag) or abs(z)==0:raise ValueError('Invalid loop gain')
        magnitude.append(20*math.log10(abs(z)));phase=math.degrees(cmath.phase(z))
        if phases:
            while phase-phases[-1]>180:phase-=360
            while phase-phases[-1]<-180:phase+=360
        phases.append(phase)
    crossings=[]
    for i in range(len(values)-1):
        if magnitude[i]>0>=magnitude[i+1] or magnitude[i]<0<=magnitude[i+1]:
            ratio=-magnitude[i]/(magnitude[i+1]-magnitude[i])
            f=math.exp(math.log(frequencies[i])+ratio*math.log(frequencies[i+1]/frequencies[i]))
            phase=phases[i]+ratio*(phases[i+1]-phases[i])
            crossings.append({'frequency_Hz':f,'phase_unwrapped_deg':phase,'phase_margin_deg':180+phase,
                'direction':'down' if magnitude[i]>magnitude[i+1] else 'up'})
    suitable=(len(crossings)==1 and crossings[0]['direction']=='down' and magnitude[0]>0 and abs(phases[0])<30 and magnitude[-1]<0)
    return {'method':METHOD,'source':SOURCE,'crossings':crossings,
        'single_crossover_applicable':suitable,'phase_margin_deg':crossings[0]['phase_margin_deg'] if suitable else None,
        'unity_Hz':crossings[0]['frequency_Hz'] if suitable else None,
        'multiple_or_missing_crossings_require_further_analysis':not suitable,
        'scope':'One external feedback loop. PM alone is not a universal Nyquist proof for arbitrary internal unstable loops.',
        'phase_unwrapping_applied':True}


def measure_dual_probe(raw_path):
    raw=read_complex_raw(raw_path);f,t=tian_from_raw(raw)
    margins=loop_margins(f,t)
    # This comparison diagnoses the limitation of voltage-only injection.
    single=[-y/x for y,x in zip(raw['v(yv)'],raw['v(xv)'])]
    margins['voltage_only_comparison']=loop_margins(f,single)
    return margins


def reference_model(poles,output_R=100,input_R=None):
    lines=['* Analytic calibration model ONLY; controlled sources, no physical IC claim',
           '.subckt PMREF P N VP VM OUT','Eerror drive0 0 P N 100k']
    previous='drive0'
    for i,pole in enumerate(poles,1):
        lines += [f'Rp{i} {previous} n{i} 1k',f'Cp{i} n{i} 0 {1/(2*math.pi*1000*pole):.15g}',
                  f'Ebuf{i} drive{i} 0 n{i} 0 1']
        previous=f'drive{i}'
    lines += [f'Boutput drv 0 V=(V(VP)+V(VM))/2+V({previous})',f'Rout drv OUT {output_R}']
    if input_R:lines += [f'Rinput P N {input_R}']
    lines+=['.ends PMREF'];return '\n'.join(lines)+'\n'


def analytical_margin(poles,output_R=100,input_R=None,load_R=10000):
    gain=1e5/(1+output_R/load_R+(output_R/input_R if input_R else 0))
    def loop(f):
        value=complex(gain)
        for pole in poles:value/=1+1j*f/pole
        return value
    low=1e-4;high=1e9
    for _ in range(100):
        mid=math.sqrt(low*high)
        if abs(loop(mid))>1:low=mid
        else:high=mid
    unity=math.sqrt(low*high)
    phase=-sum(math.degrees(math.atan(unity/pole)) for pole in poles)
    return {'unity_Hz':unity,'phase_margin_deg':180+phase,'effective_dc_loop_gain':gain}
