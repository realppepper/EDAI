"""Interpret extended simulations with validity gates and explicit model limitations."""
import math
from pathlib import Path
from .tb_05_waveform_metrics import read_real_raw,settling_metrics
from .tb_06_loop_gain import read_complex_raw,loop_margins,measure_dual_probe
from .verify_04_dc_coverage import require_complete_dc_sweep


def coefficient(x,y,valid=None,invert=False):
    if len(x)!=len(y) or len(x)<2:raise ValueError('Insufficient sweep samples')
    valid=valid or [True]*len(x);values=[]
    for i in range(len(x)-1):
        if valid[i] and valid[i+1]:
            dx=x[i+1]-x[i];dy=y[i+1]-y[i]
            if abs(dx)<=1e-12*max(1,abs(x[i]),abs(x[i+1])):
                if abs(dy)>1e-9:raise ValueError('Same sweep coordinate has inconsistent operating solutions')
                continue # LTspice may repeat a numerically identical DC endpoint.
            if invert:
                if dy==0:continue
                values.append(dx/dy)
            else:values.append(abs(dy/dx))
    return values


def first_crossing(time,output,level,start,direction):
    for i in range(len(time)-1):
        if time[i+1]<start:continue
        a,b=output[i],output[i+1]
        if (direction>0 and a<level<=b) or (direction<0 and a>level>=b):
            t=time[i]+(level-a)*(time[i+1]-time[i])/(b-a)
            if t>=start:return t
    return None


def slew_metrics(time,output,step):
    amplitude=abs(step['final_V']-step['initial_V']);sign=1 if step['final_V']>step['initial_V'] else -1
    first=first_crossing(time,output,step['initial_V']+sign*.1*amplitude,step['start_s'],sign)
    last=first_crossing(time,output,step['initial_V']+sign*.9*amplitude,first if first is not None else step['start_s'],sign)
    valid=first is not None and last is not None and last>first
    return {'rate_V_per_s':.8*amplitude/(last-first) if valid else None,'crossing10_s':first,'crossing90_s':last,
            'valid':valid,'definition':'project10–90% average of specified2V step; not maximum numerical derivative'}


def measure(path,kind,fixture,meta,scalars):
    path=Path(path);gates=[];metrics={};value=None;limitations=[]
    if meta['analysis']=='op':
        raw=read_real_raw(path.with_suffix('.raw'));v={k:x[0] for k,x in raw.items()}
        metrics={'output_V':v['v(out)'],'dut_output_current_A':v['i(vsense)']}
        if kind in {'iq','vos','ib','ios'}:
            vid=v['v(vid)'];error=abs(v['v(out)']-v['v(mid)'])
            gates += [] if error<meta['servo_error_limit_V'] and abs(vid)<=meta['linear_servo_vid_limit_V'] else ['Cannot establish linear midpoint bias with small differential input']
            metrics.update(vid_V=vid,servo_error_V=error,iq_A=-v['i(vdd)'])
            if kind=='iq':
                value=-v['i(vdd)']
                if value<=0 or abs(v['i(vsense)'])>1e-8:gates.append('Nonpositive supply current or nonzero quiescent output current')
            elif kind=='vos':value=abs(vid)
            else:
                currents=[-v['i(ep)'],-v['i(en)']];value=abs(sum(currents)/2) if kind=='ib' else abs(currents[0]-currents[1])
                metrics['input_currents_A']=currents;limitations.append('MOS gate leakage/bias mismatch absent in frozen LEVEL1 model; near-zero result is not validated bias-current accuracy.')
        elif kind=='vswing':
            rail=fixture['forced_output_rail'];value=fixture['rails_V']['V_plus']-v['v(out)'] if rail=='V_plus' else v['v(out)']-fixture['rails_V']['V_minus']
            if not fixture['rails_V']['V_minus']-1e-6<=v['v(out)']<=fixture['rails_V']['V_plus']+1e-6:gates.append('Forced load cannot be supported within supply rails')
        else:
            current=v['i(vsense)'];direction=meta['direction'];value=current if direction=='source' else -current
            metrics['direction']=direction
            if value<0:gates.append('DUT current has wrong direction')
    elif meta['analysis']=='dc':
        raw=read_real_raw(path.with_suffix('.raw'));out=raw['v(out)']
        coverage=require_complete_dc_sweep(path,raw)
        if kind=='vcm':
            inputs=raw['v(inp)'];errors=[abs(a-b) for a,b in zip(inputs,out)];value=max(errors)
            valid=[err<=.01 for err in errors];metrics={'max_tracking_error_V':value,'points':len(errors),
                'valid_sample_count':sum(valid),'invalid_sample_count':len(valid)-sum(valid),
                'initial_input_V':inputs[0],'initial_output_V':out[0],
                'valid_input_samples_V':[v for v,ok in zip(inputs,valid) if ok],'finite_grid_only':True}
        else:
            axis=raw['v(cm)'] if kind=='cmrr' else raw['v(vsw)'] if kind=='psrr' else raw['v(out)']
            target=raw['v(target)'] if kind=='aol' else raw['v(mid)'];vid=raw['v(vid)']
            valid=[abs(a-b)<meta['servo_error_limit_V'] and abs(d)<meta['linear_servo_vid_limit_V'] for a,b,d in zip(out,target,vid)]
            if not all(valid):gates.append('Required DC sweep includes points outside small-differential linear operating range')
            slopes=coefficient(axis,vid,valid,invert=kind=='aol')
            value=min(slopes) if kind=='aol' and slopes else max(slopes) if slopes else None
            if kind=='aol' and any(s<=0 for s in slopes):gates.append('Wrong-sign open-loop differential gain')
            metrics={'coefficient':value,'points':len(valid),'valid_points':sum(valid),'invalid_points':len(valid)-sum(valid),
                'finite_grid_only':True,'valid_subset_value_is_not_full_range_result':not all(valid)}
        metrics['dc_sweep_coverage']=coverage
    elif meta['analysis']=='tran':
        raw=read_real_raw(path.with_suffix('.raw'));time=raw['time'];out=raw['v(out)'];step=meta['step']
        if time[-1]<step['stop_s']-step['max_step_s']:gates.append('Incomplete transient observation')
        if kind=='sr':
            metrics=slew_metrics(time,out,step);value=metrics['rate_V_per_s']
            if not metrics['valid']:gates.append('Missing/wrong-direction10–90% crossings')
            if abs(out[-1]-step['final_V'])>.01:gates.append('Output did not reach commanded final voltage')
        else:
            metrics=settling_metrics(time,out,step);value=metrics['settling_s']
            if kind=='capacitive_drive':
                early=[abs(v-step['final_V']) for t,v in zip(time,out) if 10e-6<=t<=20e-6]
                late=[abs(v-step['final_V']) for t,v in zip(time,out) if t>=30e-6]
                metrics['finite_window_non_growing_response']=max(late)<max(.001,max(early)*1.1)
                if not metrics['finite_window_non_growing_response']:gates.append('Growing/nondecaying response in finite observation window')
    elif kind in {'pm','capacitive_drive'}:
        metrics=measure_dual_probe(path.with_suffix('.raw'));value=metrics['phase_margin_deg']
        op=read_real_raw(path.with_suffix('.op.raw'))
        dc_delta=max(abs(op['v(xv)'][0]-op['v(xi)'][0]),abs(op['v(yv)'][0]-op['v(yi)'][0]))
        metrics['probe_dc_difference_V']=dc_delta
        if dc_delta>1e-8:gates.append('Dual-probe DC operating points differ')
        if not metrics['single_crossover_applicable']:gates.append('Missing/ambiguous unity crossing or incorrect low-frequency sign')
    elif kind=='gbw':
        raw=read_complex_raw(path.with_suffix('.raw'));freq=[f.real for f in raw['frequency']]
        margins=loop_margins(freq,raw['v(out)']);value=margins['unity_Hz'];metrics=margins
        metrics['low_frequency_gain_dB']=20*math.log10(abs(raw['v(out)'][0]))
        if not margins['single_crossover_applicable']:gates.append('Missing/ambiguous GBW unity crossing')
    elif kind=='ro':
        raw=read_complex_raw(path.with_suffix('.raw'));loaded=raw['v(out)'][0]
        r=fixture['load']['value_Ohm'];z=1/(1/loaded-1/r)
        value=abs(z);metrics={'open_loop_impedance_magnitude_Ohm':value,'loaded_impedance_real_Ohm':loaded.real,
                             'loaded_impedance_imag_Ohm':loaded.imag,'external_RL_deembedded':True}
    elif kind=='noise_density':
        value=scalars['en_1k'];metrics={'input_referred_thermal_density_V_per_sqrt_Hz':value,'frequency_Hz':1000,
            'calibrated_flicker_noise_present':False,'external_fixture_load_noise_included':True}
        limitations.append('Thermal-only lower bound; no calibrated1/f noise. Below-limit value cannot establish full noise compliance.')
    return {'value':value,'metrics':metrics,'gate_issues':gates,'model_limitations':limitations}
