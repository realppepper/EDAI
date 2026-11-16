"""Explicit project overload protocol, saturation evidence and finite-window recovery."""
import math,statistics,re
from .verify_01_fixtures import header
from .tb_05_waveform_metrics import read_real_raw,settling_metrics


def recovery_profile(item,case,direction):
    definition=item['method']['definition'];f=case['fixture'];vs=f['supply_voltage_V'];mid=sum(f['rails_V'].values())/2
    gain=definition['gain'];fraction=definition['initial_input_offset_fraction_of_supply']
    if direction not in {'high','low'} or gain!=-10 or f['closed_loop_gain']!=-10:raise ValueError('Unsupported overload fixture')
    if not math.isfinite(fraction) or fraction<=0 or abs(gain*fraction)<=1:raise ValueError('Requested input does not overdrive the output')
    band=definition['output_error_band_fraction_of_supply']*vs
    if not 0<band<vs/10:raise ValueError('Invalid recovery band')
    return {'direction':direction,'supply_V':vs,'rails_V':f['rails_V'],'mid_V':mid,'gain':gain,
            'input_offset_V':fraction*vs*(-1 if direction=='high' else 1),'error_band_V':band,
            'overload_start_s':5e-6,'transition_s':10e-9,'release_start_s':25e-6,'stop_s':60e-6,'max_step_s':2e-9,
            'feedback_resistance_Ohm':100000,'input_resistance_Ohm':10000,
            'overload_duration_is_project_policy':True,'manufacturer_protocol_equivalence_claimed':False}


def recovery_deck(model,item,case,direction,subckt='FIRSTAMP',calibration_stimulus_port=False):
    profile=recovery_profile(item,case,direction);mid=profile['mid_V'];over=mid+profile['input_offset_V']
    base=header(model,case['fixture'],subckt)
    if calibration_stimulus_port:
        base=base.replace(f'dout {subckt}',f'dout stim {subckt}')
    base=re.sub(r'^\.save[^\r\n]*','.save V(out) V(stim) V(inp) V(inn)',base,flags=re.M)
    return base+f'''* Declared project overload: Rin10k, Rf100k, nominal noninverting bias VS/2
VPIN inp 0 {mid:.12g}
VIN stim 0 PWL(0 {mid:.12g} 5u {mid:.12g} 5.01u {over:.12g} 25u {over:.12g} 25.01u {mid:.12g} 60u {mid:.12g})
RIN stim inn 10k
RF out inn 100k
.options solver=alt itl4=100
.tran 0 60u 0 2n
.end
''',profile


def recovery_metrics(raw,profile):
    t=raw['time'];out=raw['v(out)'];stim=raw['v(stim)'];p=raw['v(inp)'];n=raw['v(inn)']
    if len(t)<3 or any(len(v)!=len(t) for v in (out,stim,p,n)):raise ValueError('Incomplete recovery signals')
    if any(not math.isfinite(v) for seq in (t,out,stim,p,n) for v in seq) or any(b<=a for a,b in zip(t,t[1:])):
        raise ValueError('Invalid recovery waveform')
    vs=profile['supply_V'];mid=profile['mid_V'];start=profile['release_start_s'];end=start+profile['transition_s']
    if t[0]>0 or t[-1]<profile['stop_s']-profile['max_step_s']:raise ValueError('Incomplete recovery observation')
    before=[i for i,x in enumerate(t) if 2e-6<=x<=4e-6]
    overload=[i for i,x in enumerate(t) if start-3e-6<=x<=start]
    after=[i for i,x in enumerate(t) if x>=end+1e-6]
    if not before or not overload or not after:raise ValueError('Missing required observation segment')
    level=statistics.median(out[i] for i in overload);input_level=statistics.median(stim[i] for i in overload)
    diff=statistics.median(p[i]-n[i] for i in overload);span=max(out[i] for i in overload)-min(out[i] for i in overload)
    sign=1 if profile['direction']=='high' else -1
    ideal=mid+profile['gain']*(input_level-mid)
    evidence={'overload_output_V':level,'overload_input_V':input_level,'overload_differential_input_V':diff,
              'overload_output_span_V':span,'ideal_unclipped_output_V':ideal,
              'common_mode_range_V':[min((a+b)/2 for a,b in zip(p,n)),max((a+b)/2 for a,b in zip(p,n))]}
    gates=[]
    if max(abs(out[i]-mid) for i in before)>profile['error_band_V']:gates.append('Initial linear midpoint not established')
    if abs(input_level-(mid+profile['input_offset_V']))>1e-6*vs:gates.append('Declared overload stimulus not applied')
    if abs(profile['gain']*(input_level-mid))<=vs:gates.append('VIN amplitude times gain does not exceed supply')
    if sign*(level-mid)<.1*vs or sign*diff<.01*vs:gates.append('No measured output compression and differential-error evidence of requested saturation')
    stationarity_limit=.02*vs
    if span>stationarity_limit:gates.append('Overload state not sufficiently stationary in declared hold window')
    if max(abs(stim[i]-mid) for i in after)>1e-6*vs:gates.append('Input did not return to midpoint')
    amplitude=abs(level-mid)
    if not amplitude:raise ValueError('No overload excursion')
    step={'initial_V':level,'final_V':mid,'start_s':start,'transition_s':profile['transition_s'],
          'stop_s':profile['stop_s'],'max_step_s':profile['max_step_s'],'error_fraction':profile['error_band_V']/amplitude}
    measured=settling_metrics(t,out,step)
    return {'value':measured['settling_s'],'metrics':measured,'overload_evidence':evidence,'gate_issues':gates,
            'qualification_checks':[{'name':'overload_stationarity','metric':'overload_output_span_V',
                'value':span,'operator':'<=','limit':stationarity_limit,'unit':'V','passed':span<=stationarity_limit,
                'origin':'existing_project_measurement_gate_not_a_datasheet_spec'}],
            'model_scope':'Frozen generic MOS dynamics,25C. Project protocol; not a reproduction of the manufacturer silicon test.'}


def reference_model(capacitance):
    if capacitance<=0 or not math.isfinite(capacitance):raise ValueError('Invalid reference capacitor')
    return f'''* Analytical RC reference only: stimulus-aware clipping, not a physical IC
.subckt ORREF P N VP VM OUT STIM
Btarget drive 0 V=limit((V(VP)+V(VM))/2-10*(V(stim)-(V(VP)+V(VM))/2),V(VM),V(VP))
RSTATE drive OUT 1k
CSTATE OUT VM {capacitance:.15g}
.ends ORREF
'''


def analytic_recovery(profile,capacitance,load_resistance=10000):
    """Exact affine-forcing RC solution, including finite overload hold and both10ns ramps."""
    vs=profile['supply_V'];mid=profile['mid_V'];offset=profile['input_offset_V'];gain=profile['gain'];edge=profile['transition_s']
    resistance=profile['input_resistance_Ohm']+profile['feedback_resistance_Ohm']
    conductance=1/1000+1/load_resistance+1/resistance;tau=capacitance/conductance
    def equilibrium(fraction):
        vin=mid+offset*fraction;drive=max(profile['rails_V']['V_minus'],min(profile['rails_V']['V_plus'],mid+gain*offset*fraction))
        return (drive/1000+mid/load_resistance+vin/resistance)/conductance
    crossing=(vs/2)/abs(gain*offset)
    points=[(0,0),(profile['overload_start_s'],0),(profile['overload_start_s']+edge*crossing,crossing),
            (profile['overload_start_s']+edge,1),(profile['release_start_s'],1),
            (profile['release_start_s']+edge*(1-crossing),crossing),(profile['release_start_s']+edge,0)]
    y=mid
    for (t0,f0),(t1,f1) in zip(points,points[1:]):
        dt=t1-t0;a,b=equilibrium(f0),equilibrium(f1);s=(b-a)/dt
        y=b-s*tau+(y-a+s*tau)*math.exp(-dt/tau)
    return max(0,tau*math.log(abs(y-mid)/profile['error_band_V']))
