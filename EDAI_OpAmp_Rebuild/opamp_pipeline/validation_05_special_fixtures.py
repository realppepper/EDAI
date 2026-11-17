"""Independent project contracts for startup, impedance and overload adapters."""
from copy import deepcopy
from pathlib import Path
from .validation_01_results import digest
from .validation_02_spice_reader import model_signature
from .validation_03_execution_contract import VERSION,make_contract,validate_execution

IMPEDANCE_POLICY={'relative_tolerance':.05,'conductance_floor_S':1e-15,
                  'frequency_min_Hz':1,'frequency_max_Hz':1e6,'points_per_decade':40}
STARTUP_POLICY={'stop_time_s':100e-6,'tail_window_s':20e-6,'max_internal_tail_span_V':.005,
                'max_output_midpoint_error_V':.01,'min_bias_V':.65}


def _base(model,fixture,kind,analysis,subckt='FIRSTAMP'):
    f=deepcopy(fixture);rails=f.get('rails_V',{});mid=sum(rails.values())/2
    expected={'temperature_C':f.get('temperature_C',25),'mid_V':mid,'rails_V':rails,
              'include':str(Path(model).resolve()) if model else None,'dut':subckt.lower(),
              'elements':{},'absent':[],'commands':{},'connections':{}}
    if model and Path(model).is_file():expected['model_signature']=model_signature(model)
    meta={'kind':kind,'analysis':analysis,'names':[]}
    contract={'version':VERSION,'role':'source_case' if subckt=='FIRSTAMP' else 'analytical_reference',
              'plan_sha256':digest({'fixture':fixture,'kind':kind,'subckt':subckt}),
              'fixture':f,'source_evidence':{},'expected':expected,'metric':deepcopy(meta),
              'definition_origins':{'fixture':'declared_input_fixture','method':'explicit_project_adapter_policy'}}
    meta['execution_contract']=contract
    return meta,expected,contract


def _loads(expected,f):
    load=f['load'];node={'rail_midpoint':'mid','V_minus':'vm','V_plus':'vp'}[load['connection']]
    if load['kind']=='resistance' and load.get('value_Ohm') is not None:
        if load['value_Ohm']<=0:raise ValueError('Nonpositive planned resistance')
        expected['elements']['rl']=['out',node,load['value_Ohm']]
    else:expected['absent'].append('rl')
    if load['kind']!='resistance':raise ValueError('Special adapter supports resistance loads only')
    if f.get('load_capacitance_pF'):
        expected['elements']['cl']=['out','mid',f['load_capacitance_pF']*1e-12]
    else:expected['absent'].append('cl')
    expected['elements']['vsense']=['dout','out',0]
    expected['connections'].update(vdd=['vp','0'],vss=['vm','0'],vmid=['mid','0'])


def startup_meta(model,supply):
    f={'supply_voltage_V':supply,'rails_V':{'V_plus':supply,'V_minus':0},'temperature_C':25}
    meta,e,c=_base(model,f,'startup','tran')
    e.update(skip_mid_dc=True,skip_rail_dc=True,unity_feedback=False,pwl_source='vdd',
             pwl=[[0,0],[5e-6,0],[15e-6,supply],[100e-6,supply]],
             dut_bindings={'xdut':['mid','out','vp','0','out','firstamp']},
             expressions={'bmid':'v=v(vp)/2'})
    e['elements'].update(rl=['out','mid',10000],cl=['out','mid',20e-12])
    e['connections'].update(vdd=['vp','0'],bmid=['mid','0'])
    e['commands']['.tran']=[0,100e-6,0,200e-9]
    meta['startup_policy']=deepcopy(STARTUP_POLICY);c['metric']['startup_policy']=deepcopy(STARTUP_POLICY)
    c['role']='project_operational_startup'
    return meta


def impedance_meta(model,fixture,mode,subckt='FIRSTAMP'):
    if mode not in {'differential','common'}:raise ValueError('Unknown impedance mode')
    meta,e,c=_base(model,fixture,'input_impedance','ac',subckt);_loads(e,fixture)
    a,b=(.5,-.5) if mode=='differential' else (1,1)
    e['commands']['.ac']=['dec',40,1,1e6];e['allow_op']=True
    e['expressions']={'bp':f'v=0.5*v(vid)+{a}*v(test)','bn':f'v=-0.5*v(vid)+{b}*v(test)'}
    e['connections'].update(bp=['inp','mid'],bn=['inn','mid'],vtest=['test','0'])
    meta.update(mode=mode,fit_policy=deepcopy(IMPEDANCE_POLICY))
    c['metric'].update(mode=mode,fit_policy=deepcopy(IMPEDANCE_POLICY))
    c['plan_sha256']=digest({'fixture':fixture,'kind':'input_impedance','mode':mode})
    return meta


def overload_meta(model,item,case,direction,actual_profile,subckt='FIRSTAMP',calibration=False):
    f=case['fixture'];d=item['method']['definition'];vs=f['supply_voltage_V'];mid=sum(f['rails_V'].values())/2
    meta,e,c=_base(model,f,'overload_recovery','tran',subckt);_loads(e,f)
    profile={'direction':direction,'supply_V':vs,'rails_V':deepcopy(f['rails_V']),'mid_V':mid,'gain':d['gain'],
             'input_offset_V':d['initial_input_offset_fraction_of_supply']*vs*(-1 if direction=='high' else 1),
             'error_band_V':d['output_error_band_fraction_of_supply']*vs,'overload_start_s':5e-6,
             'transition_s':10e-9,'release_start_s':25e-6,'stop_s':60e-6,'max_step_s':2e-9,
             'feedback_resistance_Ohm':100000,'input_resistance_Ohm':10000,
             'overload_duration_is_project_policy':True,'manufacturer_protocol_equivalence_claimed':False}
    if f['closed_loop_gain']!=-10 or d['gain']!=-10:raise ValueError('Unsupported overload gain')
    over=mid+profile['input_offset_V']
    e.update(unity_feedback=False,pwl=[[0,mid],[5e-6,mid],[5.01e-6,over],[25e-6,over],[25.01e-6,mid],[60e-6,mid]],
             dut_bindings={'xdut':['inp','inn','vp','vm','dout']+(['stim'] if calibration else [])+[subckt.lower()]})
    e['elements'].update(vpin=['inp','0',mid],rin=['stim','inn',10000],rf=['out','inn',100000])
    e['connections']['vin']=['stim','0'];e['commands']['.tran']=[0,60e-6,0,2e-9]
    c['plan_sha256']=digest({'item':item,'case':case,'direction':direction,'calibration':calibration})
    meta['recovery_profile']=deepcopy(actual_profile);c['metric']['recovery_profile']=profile
    return meta


def calibration_pm_meta(model,supply,cap,load_R=10000):
    f={'supply_voltage_V':supply,'rails_V':{'V_plus':supply,'V_minus':0},'temperature_C':25,
       'load':{'kind':'resistance','value_Ohm':load_R,'connection':'rail_midpoint'},'load_capacitance_pF':cap*1e12}
    contract=make_contract(model,{'method':{'kind':'pm'}},{'fixture':f},subckt='CALX')
    return {**deepcopy(contract['metric']),'execution_contract':contract}


def calibration_noise_meta():
    meta,e,c=_base(None,{},'calibration_noise','noise','NO_DUT')
    e.update(skip_mid_dc=True,skip_rail_dc=True,dut_bindings={})
    e['elements'].update(r1=['inp','out',10000],rl=['out','0',1e12])
    e['connections']['vin']=['inp','0'];e['commands']['.noise']=['v(out)','vin','dec',100,1,1e5]
    e['noise_measure_frequency_Hz']=1000
    meta['names']=['en_1k'];c['metric']['names']=['en_1k']
    return meta
