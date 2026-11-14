"""Source-bound extended fixtures. Numeric grids/waveforms are explicit project settings."""
from pathlib import Path
from .tb_06_loop_gain import dual_probe_deck


def header(model,f,subckt='FIRSTAMP',load=True,cap=True):
    rails=f['rails_V'];mid=(rails['V_plus']+rails['V_minus'])/2
    text=f'''* Extended source-case fixture; generic models only
.include "{Path(model).resolve()}"
.temp 25
.options plotwinsize=0 meascplxfmt=cartesian numdgt=15 reltol=1e-6 vntol=1e-10 abstol=1e-14
.save V(*) I(*)
VDD vp 0 {rails['V_plus']:.12g}
VSS vm 0 {rails['V_minus']:.12g}
VMID mid 0 {mid:.12g}
XDUT inp inn vp vm dout {subckt}
VSENSE dout out 0
'''
    if load:
        item=f['load'];node={'rail_midpoint':'mid','V_minus':'vm','V_plus':'vp'}.get(item.get('connection'),'mid')
        if item['kind']=='resistance' and item.get('value_Ohm'):text+=f"RL out {node} {item['value_Ohm']:.12g}\n"
        elif item['kind']=='forced_current':
            current=item['magnitude_A']*(1 if item['direction_selected_by_rail']=='V_plus' else -1)
            text+=f'ILOAD out mid {current:.12g}\n'
    if cap and f.get('load_capacitance_pF'):text+=f"CL out mid {f['load_capacitance_pF']*1e-12:.12g}\n"
    return text


def servo(target='mid',common='mid',dynamic=False):
    if dynamic:
        return f'Lservo out sfb 1e15\nCservo sfb {target} 1\nBservo vid 0 V=1e5*(V({target})-V(sfb))\nEP inp {common} vid 0 0.5\nEN inn {common} vid 0 -0.5\n'
    return f'Bservo vid 0 V=1e5*(V({target})-V(out))\nEP inp {common} vid 0 0.5\nEN inn {common} vid 0 -0.5\n'


def build_fixture(model,item,case,variant='default',subckt='FIRSTAMP'):
    f=case['fixture'];kind=item['method']['kind'];vs=f['supply_voltage_V'];mid=sum(f['rails_V'].values())/2
    base=header(model,f,subckt,load=kind!='iq',cap=kind not in {'iq','vos','ib','ios'})
    meta={'kind':kind,'variant':variant,'analysis':None,'names':[],'assumptions':[],
        'servo_error_limit_V':1e-5,'linear_servo_vid_limit_V':.05}
    if kind in {'iq','vos','ib','ios'}:
        deck=base+servo()+'.op\n';meta['analysis']='op'
    elif kind in {'vcm','cmrr','aol','psrr'}:
        meta['analysis']='dc';points=200
        if kind=='vcm':
            lo=f['input_common_mode_sweep_V']['min'];hi=f['input_common_mode_sweep_V']['max']
            start,end,delta=lo,hi,(hi-lo)/points
            if variant in {'lower','upper'}:
                start=lo+(hi-lo)/2;end=lo if variant=='lower' else hi
                delta*= -1 if variant=='lower' else 1
                meta['vcm_sweep_policy']='center_out_complete_grid_v1'
            deck=base+f'VIN inp 0 {start:.12g}\nVFB out inn 0\n.dc VIN {start:.12g} {end:.12g} {delta:.12g}\n'
        elif kind=='cmrr':
            lo=f['input_common_mode_sweep_V']['min'];hi=f['input_common_mode_sweep_V']['max']
            deck=base+f'VCM cm 0 {lo}\n'+servo(common='cm')+f'.dc VCM {lo} {hi} {(hi-lo)/points:.12g}\n'
        elif kind=='aol':
            lo=f['output_voltage_sweep']['min'];hi=f['output_voltage_sweep']['max']
            deck=base+f'VSET target 0 {lo}\n'+servo(target='target')+f'.dc VSET {lo} {hi} {(hi-lo)/points:.12g}\n'
        else:
            # Change total supply symmetrically around a fixed absolute midpoint.
            # CM remains at rail midpoint; this avoids mixing CMRR into PSRR.
            supply=item['resolved_conditions']['values']['supply_voltage_V'];delta=.1
            lo=max(supply['min'],vs-delta);hi=min(supply['max'],vs+delta)
            base=base.replace(f"VDD vp 0 {f['rails_V']['V_plus']:.12g}",f'BVP vp 0 V={mid:.12g}+V(vsw)/2')
            base=base.replace(f"VSS vm 0 {f['rails_V']['V_minus']:.12g}",f'BVN vm 0 V={mid:.12g}-V(vsw)/2')
            deck=base+f'VSW vsw 0 {vs}\n'+servo()+f'.dc VSW {lo:.12g} {hi:.12g} {(hi-lo)/10:.12g}\n'
            meta['assumptions']+=['PSRR total-supply perturbation is symmetric about fixed midpoint; absolute Vminus may shift slightly. CM/output remain VS/2 relative to Vminus.']
        meta['grid_points']=points+1 if kind!='psrr' else 11
        if kind=='vcm' and variant in {'lower','upper'}:meta['grid_points']=points//2+1
        meta['finite_grid_not_continuous_proof']=True
    elif kind=='gbw':
        deck=base+'VIN inp mid DC 0 AC 1\nLFB out inn 1e15\nCFB inn mid 1\n.ac dec 200 0.01 1Gig\n';meta['analysis']='ac'
        meta['assumptions']+=['GBW search extended to1GHz to avoid treating absence of a crossing below100MHz as a measured numerical failure. High-frequency generic-model results are not fabrication claims.']
    elif kind in {'pm','capacitive_drive'} and variant not in {'rising','falling'}:
        if f['rails_V']['V_minus']!=0:raise ValueError('Extended PM adapter currently requires nominal negative rail0V')
        deck=dual_probe_deck(model,subckt,load_R=f['load']['value_Ohm'],load_C=f['load_capacitance_pF']*1e-12)
        deck=deck.replace('VDD vp 0 5',f'VDD vp 0 {vs:.12g}').replace('VMID mid 0 2.5',f'VMID mid 0 {mid:.12g}')
        meta['analysis']='ac';return deck,meta
    elif kind in {'sr','settling','capacitive_drive'}:
        amplitude=.1 if kind=='capacitive_drive' else 2
        initial=mid-amplitude/2 if kind!='settling' else .2*vs
        final=initial+amplitude
        if variant=='falling':initial,final=final,initial
        step={'initial_V':initial,'final_V':final,'start_s':5e-6,'transition_s':1e-8,
              'stop_s':40e-6,'max_step_s':2e-9,'error_fraction':.001}
        if kind=='sr':meta['assumptions']+=['SR2V waveform is centered on source midrail bias; baseline replaces earlier proposed0.2VS starting point. No SR waveform baseline is specified in source.']
        deck=base+f'VIN inp 0 PWL(0 {initial:.12g} 5u {initial:.12g} 5.01u {final:.12g} 40u {final:.12g})\nVFB out inn 0\n.tran 0 40u 0 2n\n'
        meta.update(analysis='tran',step=step)
    elif kind=='vswing':
        polarity=1 if f['forced_output_rail']=='V_plus' else -1
        deck=base+f'VPIN inp 0 {mid+polarity*.5:.12g}\nVNIN inn 0 {mid-polarity*.5:.12g}\n.op\n'
        meta.update(analysis='op',overdrive_V=polarity,assumptions=['Fixed1V differential overdrive at specified common-mode; exact manufacturer drive protocol not asserted.'])
    elif kind in {'iout','isc'}:
        conditions=f['source_case_conditions']
        diff=conditions.get('differential_input_voltage_V',1 if variant=='source' else -1)
        if kind=='isc':diff=1 if variant=='source' else -1
        clamp=f['output_dc_bias_V'];deck=base+f'VPIN inp 0 {mid+diff/2:.12g}\nVNIN inn 0 {mid-diff/2:.12g}\nVCLAMP out 0 {clamp:.12g}\n.op\n'
        meta.update(analysis='op',direction='source' if diff>0 else 'sink',clamp_V=clamp,
                    assumptions=['VSENSE directly measures DUT terminal current; external RL current is not mistakenly added. ISC overdrive1V is a project setting.'])
    elif kind=='noise_density':
        deck=base+'VIN inp mid DC 0 AC 1\nLFB out inn 1e15\nCFB inn mid 1\n.noise V(out) VIN dec 100 1 100k\n.meas NOISE en_1k FIND V(inoise) AT=1k\n'
        meta.update(analysis='noise',names=['en_1k'],assumptions=['Thermal-only lower bound: frozen generic MOS models omit calibrated flicker parameters. Fixture load noise included; no full-noise pass claim.'])
    elif kind=='ro':
        deck=base+servo(dynamic=True)+'ITEST 0 out DC 0 AC 1\n.ac lin 1 1Meg 1Meg\n';meta['analysis']='ac'
    else:raise NotImplementedError('No validated adapter for '+kind)
    return deck+'.end\n',meta
