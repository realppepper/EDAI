"""Op-amp measurement recipes inspired by the legacy spec planner.

Uses structured conditions instead of re-parsing free-text fixture conditions.
No netlist, simulator invocation or measurement implementation is created here.
"""
from copy import deepcopy
import math
import re
from .support.source_checks import fingerprint


# Same measurement families as legacy spec_planner.KIND_RULES, extended to keep
# settling, overload, THD+N, noise-band and impedance cases instead of dropping them.
METHODS={
 'RID':('input_resistance',['dc'],'Measure local common-mode DC input resistance per pin; do not impose a capacitance target.'),
 'VOS':('vos',['op'],'Extract input-referred offset with an output-centering DC servo.'),
 'PSRR':('psrr',['dc'],'Measure absolute change in input-referred offset per supply-voltage change; do not treat uV/V as dB.'),
 'Channel separation, dc':('channel_separation',['ac'],'Drive the other channel and measure victim input-referred coupling over the stated frequency band.'),
 'VCM':('vcm',['dc'],'Sweep unity-buffer common-mode input across the source window; check phase and the project tracking-error criterion.'),
 'CMRR':('cmrr',['dc'],'Sweep common-mode voltage and extract worst input-referred offset sensitivity; coefficient is not dB.'),
 'IB':('ib',['op'],'Measure both input terminal bias-current magnitudes with explicit reference-current orientation.'),
 'IOS':('ios',['op'],'Measure the magnitude of the difference between input bias currents.'),
 'En':('noise_pp',['tran'],'Observe model-enabled input-referred noise after 0.1–10Hz filtering; evaluate peak-to-peak over explicitly chosen windows/seeds.'),
 'en':('noise_density',['noise'],'Read input-referred voltage-noise density at the source frequency using noise-capable device models.'),
 'ZID':('zid',['ac'],'Apply differential AC test current and fit the complex input impedance to the source parallel R/C model.'),
 'ZIC':('zic',['ac'],'Apply common-mode AC test current and fit the complex input impedance to the source parallel R/C model.'),
 'AOL':('aol',['dc'],'Use a DC servo to sample the specified output range and extract open-loop dVout/dVid; do not substitute a single midpoint measurement.'),
 'GBW':('gbw',['ac'],'Find the downward unity-gain crossing of open-loop differential transfer with a valid DC bias.'),
 'PM':('pm',['ac'],'Measure actual return-ratio loop gain in the stated unity-gain feedback/load fixture; unwrap phase at the unity crossing.'),
 'SR':('sr',['tran'],'Measure both rising and falling output slew rates over the 10–90% interval under the declared project step profile.'),
 'tOR':('overload_recovery',['tran'],'Release a controlled overload into the linear region and time recovery into a declared output-error band.'),
 'ts':('settling',['tran'],'Measure last entry and continued residence in the source error band, timed from the end of the input transition.'),
 'THD+N':('thdn',['tran','noise'],'Combine output harmonic distortion and model noise in the specified bandwidth; a deterministic FFT alone is not THD+N.'),
 'VO':('vswing',['dc'],'Force the requested load condition and measure distance from the specified rail; keep output within rails.'),
 'IO':('iout',['op'],'Clamp output voltage and differential input as specified; measure source/sink capacity with a sign-convention gate.'),
 'ISC':('isc',['op'],'Measure both short-circuit current directions at the explicitly stated supply rails/output clamp.'),
 'CLOAD':('capacitive_drive',['ac','tran'],'At the stated capacitive load, evaluate the separately declared project stability/phase-margin definition.'),
 'RO':('ro',['ac'],'Measure open-loop small-signal output impedance at the stated frequency with zero DC output current; de-embed any external load.'),
 'IQ':('iq',['op'],'Measure quiescent supply current, report total and per-amplifier values only after channel/bias binding is known.')}


def classify(row):
    symbol={'Θm':'PM','Iq':'IQ','VOM':'VO'}.get(row['symbol'],row['symbol'])
    if symbol in METHODS:return METHODS[symbol]
    # Deliberately limited name fallback; unknown rows require an explicit adapter.
    name=row.get('name','').lower()
    for pattern,key in [(r'quiescent.*current','IQ'),(r'gain.bandwidth','GBW'),(r'phase margin','PM'),(r'settling time','ts'),(r'slew rate','SR')]:
        if re.search(pattern,name):return METHODS[key]
    raise ValueError('Unclassified op-amp specification must not be silently dropped: '+row['symbol'])


def convert(value,unit):
    scales={'V':(1,'V'),'mV':(1e-3,'V'),'uV':(1e-6,'V'),'V/mV':(1e3,'V/V'),
        'uV/V':(1e-6,'V/V'),'A':(1,'A'),'mA':(1e-3,'A'),'uA':(1e-6,'A'),'nA':(1e-9,'A'),
        'Hz':(1,'Hz'),'kHz':(1e3,'Hz'),'MHz':(1e6,'Hz'),'us':(1e-6,'s'),'ns':(1e-9,'s'),'s':(1,'s'),
        'pA':(1e-12,'A'),'dB':(1,'dB'),'TOhm':(1e12,'Ohm'),
        'V/us':(1e6,'V/s'),'deg':(1,'degree'),'percent':(.01,'ratio'),'Ohm':(1,'Ohm'),
        'uVpp':(1e-6,'Vpp'),'nV/sqrt(Hz)':(1e-9,'V/sqrt(Hz)'),'pF':(1e-12,'F')}
    if unit not in scales:raise ValueError('Unmapped target unit: '+unit)
    scale,canonical=scales[unit];return float(value)*scale,canonical


def target_criteria(row,kind,profile,range_only=False):
    limits=row['limits'];rules=[]
    if kind=='vswing' and row['symbol']=='VOM':
        supply=row['conditions'].get('overrides',{}).get('supply_voltage_V')
        if not isinstance(supply,(int,float)):raise ValueError('Symmetric peak swing requires an explicit source total supply')
        slot='min' if isinstance(limits.get('min'),(int,float)) else 'typ'
        if not str(row.get('printed_notation',{}).get(slot,'')).startswith('±'):raise ValueError('Symmetric swing needs source ± notation')
        headroom=supply/2-abs(limits[slot])
        if headroom<0:raise ValueError('Peak swing exceeds source rails')
        return {'origin':'source_symmetric_peak_swing_to_each_rail_headroom',
            'rules':[{'metric':'vswing','operator':'<=','value':headroom,'unit':'V','source_slot':slot}],
            'source_limits_preserved':deepcopy(limits),'source_peak_V':abs(limits[slot]),
            'both_directions_required':True,'full_temperature_compliance_claimed':False}
    if kind in {'cmrr','psrr'} and row['unit']=='dB':
        slot='min' if isinstance(limits.get('min'),(int,float)) else 'typ'
        if not isinstance(limits.get(slot),(int,float)):raise ValueError('Rejection ratio needs a numeric dB target')
        return {'origin':'source_rejection_dB_converted_to_maximum_offset_sensitivity',
            'rules':[{'metric':kind,'operator':'<=','value':10**(-limits[slot]/20),'unit':'V/V','source_slot':slot}],
            'source_limits_preserved':deepcopy(limits),'full_temperature_compliance_claimed':False}
    if kind=='vcm':
        return {'origin':'source_window_plus_project_tracking_definition','rules':[
            {'metric':'valid_input_common_mode_window','operator':'covers_source_expression_range','value':deepcopy(limits),'unit':row['unit']},
            {'metric':'unity_tracking_abs_error','operator':'<=','value':profile['vcm_tracking_error_V'],'unit':'V','origin':'engineering_policy'}],
            'source_limits_preserved':deepcopy(limits),'not_a_guarantee_of_exact_datasheet_test_equivalence':True}
    if kind in {'zid','zic'}:
        model=limits.get('typ')
        if not isinstance(model,dict) or model.get('connection')!='parallel':raise ValueError('Input impedance model needs source interpretation')
        resistance=model['resistance'];cap=model['capacitance']
        factor={'MOhm':1e6,'GOhm':1e9}[resistance['unit']]
        return {'origin':'typical_value_adopted_as_project_objective','rules':[
            {'metric':'fitted_parallel_resistance','operator':'>=','value':resistance['value']*factor,'unit':'Ohm'},
            {'metric':'fitted_parallel_capacitance','operator':'<=','value':cap['value']*1e-12,'unit':'F'}],
            'source_limits_preserved':deepcopy(limits),'manufacturer_guarantee':False}
    if kind=='capacitive_drive':
        return {'origin':'source_typical_load_plus_engineering_stability_definition','rules':[
            {'metric':'test_load','operator':'==','value':limits['typ']*1e-12,'unit':'F'},
            {'metric':'phase_margin','operator':'>=','value':profile['capacitive_drive_min_pm_deg'],'unit':'degree','origin':'engineering_policy'},
            {'metric':'growing_or_sustained_oscillation','operator':'==','value':False,'origin':'engineering_policy'}],
            'source_limits_preserved':deepcopy(limits),'manufacturer_guarantee':False}
    slots=[slot for slot in ('min','max') if isinstance(limits.get(slot),(int,float))]
    origin='source_bound_at_25C' if not range_only else 'source_temperature_range_bound_evaluated_only_at_25C'
    if not slots:
        if not isinstance(limits.get('typ'),(int,float)):raise ValueError('No numeric target or interpreted model')
        slots=['typ'];origin='typical_value_adopted_as_project_objective'
    larger={'aol','gbw','pm','sr','iout','input_resistance'}
    for slot in slots:
        value,unit=convert(limits[slot],row['unit'])
        if kind in {'vos','ib','ios','isc','iout'}:value=abs(value)
        op=('>=' if kind in larger else '<=') if slot=='typ' else ('>=' if slot=='min' else '<=')
        if kind=='iout':op='>='
        rules.append({'metric':kind,'operator':op,'value':value,'unit':unit,'source_slot':slot})
    return {'origin':origin,'rules':rules,'source_limits_preserved':deepcopy(limits),
        'manufacturer_typical_is_not_a_guarantee':True,
        'full_temperature_compliance_claimed':False,
        'sign_convention_gate_required':kind in {'ib','ios','iout','isc'}}


def resolved_conditions(row,sets):
    original=row['conditions'];values=deepcopy(sets.get(original.get('inherits'),{}))
    for key in ('source_pages','applies_unless_overridden'):values.pop(key,None)
    replaced=[]
    for inherited,local in original.get('inheritance_replacements',{}).items():
        values.pop(inherited,None);replaced.append({'inherited_field':inherited,'replacement_field':local})
    values.update(deepcopy(original.get('overrides',{})))
    source_temp=deepcopy(values.get('ambient_temperature_C'));values['ambient_temperature_C']=25
    return {'values':values,'source_conditions':deepcopy(original),'source_common_conditions':deepcopy(sets.get(original.get('inherits'),{})),
        'source_temperature_condition_C':source_temp,'evaluation_temperature_C':25,'source_temperature_rewritten':False,
        'declared_replacements':replaced,'quantity_roles':deepcopy(original.get('quantity_roles',{}))}


def sample_supply(value,profile):
    if isinstance(value,(int,float)):return [float(value)]
    if not isinstance(value,dict) or not {'min','max'}<=set(value):raise ValueError('Supply condition must be resolved before planning')
    low,high=value['min'],value['max']
    return sorted({float(low),float(high),*[float(v) for v in profile['supply_sample_points_V'] if low<=v<=high]})


def voltage_expression(value,positive,negative):
    if isinstance(value,(int,float)):return float(value)
    if isinstance(value,dict):value=value.get('expression')
    if value=='VS/2':return (positive+negative)/2
    if value=='V_minus':return negative
    if value=='V_plus':return positive
    m=re.fullmatch(r'(V_minus|V_plus)\s*([+-])\s*([0-9.]+)\s*(m?V)',str(value))
    if not m:raise ValueError('Voltage expression needs an explicit adapter: '+str(value))
    base=negative if m[1]=='V_minus' else positive
    offset=float(m[3])*(.001 if m[4]=='mV' else 1)
    return base+offset*(1 if m[2]=='+' else -1)


def make_fixture(row,kind,resolved,vs,profile):
    values=deepcopy(resolved['values']);assumptions=[]
    negative=values.get('V_minus_V',0.0);positive=values.get('V_plus_V',negative+vs)
    if abs((positive-negative)-vs)>1e-9:raise ValueError('Fixture rail voltages contradict source supply')
    midpoint=(negative+positive)/2
    load=values.get('load_resistance_Ohm');connection=values.get('load_connected_to','VS/2')
    if isinstance(load,dict):
        load=load.get('min',load.get('max'))
        assumptions.append('Resistance inequality sampled at its stated boundary; not a proof for every resistance.')
    fixture={'supply_voltage_V':vs,'rails_V':{'V_plus':positive,'V_minus':negative},'temperature_C':25,
        'input_common_mode_bias_V':midpoint,'output_dc_bias_V':midpoint,
        'load':{'kind':'resistance','value_Ohm':load,'connection':'rail_midpoint' if connection=='VS/2' else connection},
        'load_capacitance_pF':values.get('load_capacitance_pF'),
        'closed_loop_gain':values.get('closed_loop_gain'),
        'dc_output_expression':values.get('output_voltage_expression'),
        'source_case_conditions':values,'actual_dut_binding':None}
    if 'input_common_mode_V' in values:fixture['input_common_mode_sweep']=deepcopy(values['input_common_mode_V'])
    if 'output_voltage_V' in values:fixture['output_voltage_condition']=deepcopy(values['output_voltage_V'])
    if 'output_voltage_Vrms' in values:fixture['output_ac_amplitude_Vrms']=values['output_voltage_Vrms']
    if kind=='aol':
        sweep=deepcopy(values['output_voltage_V'])
        if isinstance(sweep,(int,float)):
            centre=midpoint+sweep
            half=profile.get('aol_local_half_span_V',.01)
            if not isinstance(half,(int,float)) or half<=0:raise ValueError('Invalid local AOL probe span')
            sweep={'min':centre-half,'max':centre+half}
            assumptions.append('Source point output voltage is translated relative to rail midpoint; AOL uses a declared local finite difference, not a source output range.')
        fixture['output_dc_bias_V']=None;fixture['output_voltage_sweep']=sweep
    if kind=='vcm':
        fixture['input_common_mode_bias_V']=None;fixture['output_dc_bias_V']=None
        if str(row.get('printed_notation',{}).get('min','')).startswith('±'):
            bound=abs(row['limits']['min'])
            fixture['input_common_mode_sweep']={'min':midpoint-bound,'max':midpoint+bound}
            assumptions.append('Printed symmetric ± common-mode bound is translated from source bipolar zero to the fixture rail midpoint.')
        else:
            fixture['input_common_mode_sweep']={'min':row['limits']['min'],'max':row['limits']['max']}
        fixture['closed_loop_gain']=1
        assumptions.append('Unity-buffer tracking tolerance is a project measurement definition, not an extra datasheet limit.')
    if kind=='cmrr':fixture['input_common_mode_bias_V']=None
    if kind in {'vcm','cmrr'}:
        window=fixture['input_common_mode_sweep']
        fixture['input_common_mode_sweep_V']={
            'min':voltage_expression(window.get('min',window.get('min_expression')),positive,negative),
            'max':voltage_expression(window.get('max',window.get('max_expression')),positive,negative)}
    if kind=='vswing':
        if row['symbol']=='VOM':values['output_rail']='both'
        rail={'V_plus':'V_plus','positive':'V_plus','V_minus':'V_minus','negative':'V_minus'}.get(values.get('output_rail'))
        if values.get('output_rail')=='both':rail='both'
        if rail is None:raise ValueError('Output swing rail needs an explicit positive/negative supply binding')
        fixture['output_dc_bias_V']=None;fixture['forced_output_rail']=rail
        if 'output_current_uA' in values:
            fixture['load']={'kind':'forced_current','magnitude_A':abs(values['output_current_uA'])*1e-6,'direction_selected_by_rail':rail}
            assumptions.append('Explicit output-load current replaces the generic RL fixture; do not add the two loads.')
    if kind=='iout':fixture['output_dc_bias_V']=voltage_expression(values['output_voltage_expression'],positive,negative)
    if kind=='isc':fixture['output_dc_bias_V']=values['output_voltage_V']
    if kind=='capacitive_drive':fixture['load_capacitance_pF']=row['limits']['typ']
    if kind=='capacitive_drive':fixture['closed_loop_gain']=1
    if kind=='overload_recovery':
        fixture['closed_loop_gain']=-10
        fixture['output_dc_bias_V']=None
        assumptions.append('Recovery gain and error band are explicit project definitions; manufacturer-equivalent overload protocol is not asserted.')
    if kind=='noise_pp':
        fixture['closed_loop_noise_gain']=10
        assumptions.append('Noise test gain and finite observation windows/seeds are engineering definitions; resistor noise must be de-embedded.')
    if kind=='iq':
        fixture['quiescent_output_current_A']=0
        assumptions.append('Report total current and normalize per amplifier only after bound channel count and identical quiescent fixtures are verified.')
    if kind in {'zid','zic','ro','aol','gbw'}:fixture['measurement_fixture']='DC servo with the appropriate AC/open-loop or DC sensitivity measurement; not a naive closed-loop impedance/gain measurement.'
    assumptions.append('VS/2 bias is implemented at the rail midpoint; source expressions are preserved separately.')
    return fixture,assumptions


def build_measurements(selection,hkg,profile):
    sets={n['label']:n['data'] for n in hkg['nodes'] if n['type']=='ConditionSet'}
    measurements=[]
    for decision in selection['items']:
        if not decision['required_in_project']:continue
        row=decision['source'];kind,analyses,description=classify(row)
        conditions=resolved_conditions(row,sets)
        supplies=sample_supply(conditions['values'].get('supply_voltage_V'),profile)
        cases=[]
        for vs in supplies:
            fixture,assumptions=make_fixture(row,kind,conditions,vs,profile)
            cases.append({'case_id':'CASE-'+fingerprint([row['id'],vs,fixture])[:20],
                'fixture':fixture,'assumptions':assumptions,
                'supply_point_origin':'source_value' if isinstance(conditions['values']['supply_voltage_V'],(int,float)) else 'engineering_sampling_of_source_range',
                'full_continuous_source_range_verified':False})
        recipe={'kind':kind,'analyses':analyses,'description':description,
            'definition_origin':'source_conditions_plus_project_measurement_definition',
            'implementation_status':'testbench_adapter_not_yet_implemented',
            'gates':['source_operating_constraints_respected','test_specific_operating_state_valid','metric_defined_and_finite'],
            'requires_noise_capable_models':kind in {'noise_pp','noise_density','thdn'},
            'requires_two_channels':kind=='channel_separation'}
        if kind in {'ib','ios','iout','isc'}:recipe['gates'].append('source_current_sign_convention_verified')
        if kind=='vswing':recipe['gates'].append('output_between_supply_rails')
        if kind=='settling':
            values=conditions['values'];step=values.get('input_step_V')
            project_binding=step is None
            if project_binding:
                step=profile.get('settling_input_step_V')
                if not isinstance(step,(int,float)) or isinstance(step,bool) or step<=0:
                    raise ValueError('Source step signal is unspecified; explicit engineering input-step binding required')
                source_step=values.get('step_amplitude_V')
                if source_step is not None and source_step!=step:
                    raise ValueError('Project input step differs from source step amplitude')
            recipe['definition']={'error_percent':values['settling_error_percent'],
                'reference_time':'end_of_input_transition','metric':'last_entry_and_residence_until_end_of_observation',
                'input_step_V':step,'baseline_fraction_of_supply':profile['step_baseline_fraction']}
            if project_binding:
                recipe['definition']['input_signal_binding_origin']='explicit_project_policy_not_source_node_identification'
        if kind=='sr':recipe['definition']={'fraction_interval':[.1,.9],'required_directions':['rising','falling'],'step_V':profile['slew_step_V']}
        if kind=='overload_recovery':recipe['definition']={'gain':-10,'initial_input_offset_fraction_of_supply':.12,
            'final_input':'rail_midpoint','output_error_band_fraction_of_supply':profile['overload_error_fraction'],
            'note':'Project recovery definition, not a claim of exact manufacturer test equivalence.'}
        if kind=='noise_pp':recipe['definition']=deepcopy(profile['noise_pp_definition'])
        if kind in {'zid','zic'}:recipe['definition']={'fit_frequency_Hz':profile['impedance_fit_frequency_Hz'],'model':'R_parallel_C','source_frequency_not_specified':True}
        if kind=='channel_separation':recipe['definition']={'roles':'aggressor/victim, then swap channels','input_referred':True,'source_frequency_band_Hz':conditions['values']['frequency_Hz']}
        if kind=='thdn':
            values=conditions['values'];peak=math.sqrt(2)*values['output_voltage_Vrms']
            recipe['definition']={'metric':'sqrt(harmonic_power + noise_power) / fundamental_amplitude',
                'bandwidth_Hz':values['measurement_bandwidth_Hz'],'output_Vrms':values['output_voltage_Vrms'],
                'derived_peak_load_current_A':peak/values['load_resistance_Ohm'],
                'noise_analysis_required':True,'deterministic_fft_alone_is_not_thdn':True}
            current=values.get('output_current_uA',{})
            if isinstance(current,dict) and {'min','max'}<=set(current) and peak/values['load_resistance_Ohm']>max(abs(current['min']),abs(current['max']))*1e-6:
                raise ValueError('THD fixture exceeds source peak output-current condition')
        goal=target_criteria(row,kind,profile,isinstance(decision['source_temperature_condition_C'],dict))
        measurements.append({'measurement_id':'MEASURE-'+row['id'],'row_id':row['id'],'hkg_node_id':row['hkg_node_id'],
            'symbol':row['symbol'],'source':deepcopy(row),'source_temperature_condition_C':decision['source_temperature_condition_C'],
            'evaluation_temperature_C':25,'required_for_project_success':True,'resolved_conditions':conditions,
            'target':goal,'method':recipe,'cases':cases,'executed':False,'ready_for_test_execution':False})
    return {'stage':'plan_02_measurement_definitions','target_product':hkg['target_product'],'measurements':measurements,
        'summary':{'required_source_rows':len(measurements),'fixture_cases_before_channel_expansion':sum(len(m['cases']) for m in measurements)},
        'sampling_is_not_full_datasheet_range_validation':True,'circuit_or_testbench_created':False}
