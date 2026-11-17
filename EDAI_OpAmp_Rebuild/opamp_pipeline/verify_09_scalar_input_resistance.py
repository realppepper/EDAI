"""DC input resistance without imposing an R||C equivalent on source data."""
import math
from .verify_01_fixtures import header,servo
from .tb_05_waveform_metrics import read_real_raw


def resistance_fit(voltage,current,floor_S=1e-15):
    if len(voltage)!=len(current) or len(voltage)<3:raise ValueError('Insufficient DC samples')
    if any(not math.isfinite(v) for v in [*voltage,*current]):raise ValueError('Nonfinite DC samples')
    if any(b<=a for a,b in zip(voltage,voltage[1:])):raise ValueError('DC voltage must increase')
    if not math.isfinite(floor_S) or floor_S<=0:raise ValueError('Invalid declared conductance resolution')
    centre=sum(voltage)/len(voltage);average=sum(current)/len(current)
    g=sum((v-centre)*(i-average) for v,i in zip(voltage,current))/sum((v-centre)**2 for v in voltage)
    span=max(voltage)-min(voltage)
    residual=max(abs(i-average-g*(v-centre)) for v,i in zip(voltage,current))/max(abs(g)*span,floor_S*span)
    issues=[]
    if g< -floor_S:issues.append('Negative input conductance')
    if residual>.05:issues.append('DC current/voltage relation not linear within5percent')
    resolved=g>floor_S and not issues
    return {'conductance_S':g,'resistance_Ohm':1/g if resolved else None,
        'status':'resolved' if resolved else 'unresolved','resolution_floor_S':floor_S,
        'relative_fit_residual':residual,'gate_issues':issues,
        'unresolved_is_not_infinite_resistance_or_a_pass':True}


def resistance_deck(model,fixture,subckt='FIRSTAMP',half_span_V=.1,points=20):
    if not math.isfinite(half_span_V) or half_span_V<=0 or not isinstance(points,int) or points<2:
        raise ValueError('Invalid resistance probe grid')
    mid=sum(fixture['rails_V'].values())/2
    if mid-half_span_V<fixture['rails_V']['V_minus'] or mid+half_span_V>fixture['rails_V']['V_plus']:
        raise ValueError('Resistance probe exceeds rails')
    return header(model,fixture,subckt)+f'VCM cm 0 {mid}\n'+servo(common='cm')+f'''.save V(cm) V(inp) V(inn) V(out) V(mid) V(vid) I(EP) I(EN)
.dc VCM {mid-half_span_V:.12g} {mid+half_span_V:.12g} {2*half_span_V/points:.12g}
.end
'''


def measure_resistance(path):
    raw=read_real_raw(path);gates=[]
    if any(abs(a-b)>=1e-5 or abs(d)>=.05 for a,b,d in zip(raw['v(out)'],raw['v(mid)'],raw['v(vid)'])):
        gates.append('Linear midpoint operating state unavailable')
    pins={p:resistance_fit(raw['v(cm)'],[-i for i in raw[f'i({source})']])
          for p,source in [('P','ep'),('N','en')]}
    gates.extend(g for p in pins.values() for g in p['gate_issues'])
    return {'pins':pins,'gate_issues':gates,'definition':'local common-mode DC input resistance per pin; capacitance not fitted',
        'probe_range_V':[min(raw['v(cm)']),max(raw['v(cm)'])],
        'source_frequency_not_specified':True,'local_probe_is_engineering_policy':True}


def calibrate_resistance(folder,execute):
    folder.mkdir(parents=True,exist_ok=True);checks=[]
    f={'supply_voltage_V':30,'rails_V':{'V_plus':30,'V_minus':0},
       'load':{'kind':'resistance','value_Ohm':None,'connection':'rail_midpoint'},'load_capacitance_pF':None}
    for label,resistance in [('one_tera',1e12),('quarter_tera',2.5e11),('open',None)]:
        resistors='' if resistance is None else f'RP P VM {resistance:.12g}\nRN N VM {resistance:.12g}\n'
        model=folder/(label+'.inc')
        model.write_text('.subckt RREF P N VP VM OUT\n'+resistors+
            'BOUT OUT 0 V=(V(VP)+V(VM))/2+1e4*V(P,N)\n.ends RREF\n',encoding='ascii')
        from .validation_03_execution_contract import make_contract
        contract=make_contract(model,{'method':{'kind':'input_resistance'}},{'fixture':f},subckt='RREF')
        meta={**contract['metric'],'execution_contract':contract}
        job=execute('cal_input_resistance_'+label,resistance_deck(model,f,'RREF'),meta)
        from .validation_03_execution_contract import validate_execution
        validate_execution(job['path'].read_text(encoding='ascii'),meta,phase='before_metric')
        measured=measure_resistance(job['path'].with_suffix('.raw'))
        passed=not measured['gate_issues']
        if resistance is None:passed &= all(p['status']=='unresolved' and p['resistance_Ohm'] is None for p in measured['pins'].values())
        else:passed &= all(p['status']=='resolved' and abs(p['resistance_Ohm']/resistance-1)<.001 for p in measured['pins'].values())
        checks.append({'name':label,'expected_resistance_Ohm':resistance,'measured':measured,'passed':bool(passed),
                       'expected_1T_target_pass':None if resistance is None else resistance>=1e12})
    return checks
