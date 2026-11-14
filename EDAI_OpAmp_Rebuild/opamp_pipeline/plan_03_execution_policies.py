"""Attach explicit engineering execution policies to measurement cases."""
from copy import deepcopy
from .pdg_04_schedule import policy_templates,generate_schedule
from .support.source_checks import fingerprint


def stimulus_port(pdg,channel,negative=False):
    candidates=[n for n in pdg['nodes'] if n['type']=='Port' and n['data'].get('channel_key')==channel and n['data'].get('role')=='input']
    suffix='-' if negative else '+'
    selected=[n['source_key'] for n in candidates if n['source_key'].endswith(suffix) or n['data'].get('polarity')==('negative' if negative else 'positive')]
    if len(selected)!=1:raise ValueError('A unique input polarity binding is required before policy generation')
    return selected[0]


def event(key,kind,ports,time_s,after=(),**extra):
    return {'id':key,'kind':kind,'ports':ports,'time_s':time_s,'after':list(after),'origin':'engineering_policy',
        'rationale':'Explicit project sampling/observation policy; not a datasheet pin delay.',**extra}


def build_policies(measurements,pdg,profile):
    channels=[n for n in pdg['nodes'] if n['type']=='Channel'];all_channels=[n['source_key'] for n in channels]
    templates=policy_templates(pdg);result=[]
    for item in measurements['measurements']:
        kind=item['method']['kind']
        group=[all_channels] if kind in {'iq','channel_separation'} else [[name] for name in all_channels]
        for case in item['cases']:
            for analysis in item['method']['analyses']:
                directions=['rising','falling'] if kind=='sr' and analysis=='tran' else ['default']
                for selected in group:
                    for direction in directions:
                        policy=deepcopy(templates[analysis]);identity=[item['measurement_id'],case['case_id'],analysis,selected,direction]
                        policy.update({'policy_id':'POLICY-'+fingerprint(identity)[:20],'channels':selected,
                            'rationale':'Project 25 C measurement policy. Preserve source conditions; use declared engineering waveform/sampling assumptions.',
                            'measurement_id':item['measurement_id'],'row_id':item['row_id'],'case_id':case['case_id'],
                            'variant':direction,
                            'fixture_reference':case['case_id'],'fixture_binding':None,
                            'source_conditions_verified_against_hkg':True,'source_limits_are_not_execution_delays':True,
                            'case_fixture':deepcopy(case['fixture']),
                            'quiet_reference_channels':[c for c in all_channels if c not in selected],
                            'device_model_requirements':['noise_capable_models'] if item['method']['requires_noise_capable_models'] else [],
                            'metric_gates':deepcopy(item['method']['gates']),
                            'actual_dut_channel_count_verified':False})
                        if kind=='channel_separation':
                            if len(all_channels)<2:raise ValueError('Channel separation requires at least two reference channels')
                            policy['measurement_roles']=[{'aggressor':a,'victim':b} for a in all_channels for b in all_channels if a!=b]
                        if kind=='iq':policy['supply_current_normalization_gate']='Use actual bound amplifier count and quiescent load state, not a hardcoded divide by two.'
                        policy['analysis_parameters']={}
                        if analysis=='ac':
                            interval=profile['impedance_fit_frequency_Hz'] if kind in {'zid','zic'} else profile['ac_frequency_Hz']
                            if kind=='channel_separation':interval=item['resolved_conditions']['values']['frequency_Hz']
                            if kind=='ro':interval={'min':item['resolved_conditions']['values']['frequency_Hz'],'max':item['resolved_conditions']['values']['frequency_Hz']}
                            policy['analysis_parameters']={'frequency_Hz':interval,'points_per_decade':profile['ac_points_per_decade'],
                                'origin':'source_frequency_when_given_else_engineering_sweep'}
                        elif analysis=='dc':
                            policy['analysis_parameters']={'source_sweep_conditions':deepcopy(item['resolved_conditions']['values']),
                                'sampling_points_per_range':profile['dc_sampling_points'],
                                'finite_difference_relative_step':profile['dc_relative_perturbation'],
                                'clamp_perturbations_to_source_range':True,'full_continuous_range_coverage_claimed':False}
                        elif analysis=='noise':
                            values=item['resolved_conditions']['values']
                            policy['analysis_parameters']={'frequency_Hz':values.get('frequency_Hz'),
                                'integration_bandwidth_Hz':values.get('measurement_bandwidth_Hz'),
                                'intrinsic_device_noise_required':True,'input_referring_gain_must_be_measured':True}
                            if kind=='thdn':
                                policy['analysis_parameters']['integration_band_Hz']={
                                    'min':profile['thdn_noise_low_frequency_Hz'],'max':values['measurement_bandwidth_Hz']}
                                policy['analysis_parameters']['low_cutoff_origin']='engineering_policy; source states bandwidth only'
                        if analysis=='tran':
                            policy['initialization']='dc_operating_point'
                            outputs=[n['data']['output_port'] for n in channels if n['source_key'] in selected]
                            quiet=profile['transient_quiet_s'];rise=profile['input_transition_s'];stop=quiet+profile['transient_observation_s']
                            target_port=stimulus_port(pdg,selected[0],kind=='overload_recovery')
                            if kind=='noise_pp':
                                policy['measurement_mode']='passive_noise_observation'
                                stop=quiet+profile['noise_pp_definition']['observation_s']
                                policy['analysis_parameters']=deepcopy(profile['noise_pp_definition'])
                                policy['analysis_parameters']['backend_must_support_device_transient_noise']=True
                                policy['events']=[event('observe','start_measurement',outputs,quiet,requires_gates=['pre_measurement_conditions_valid']),
                                    event('stop','stop_simulation',[],stop,after=['observe'])]
                            else:
                                measure=quiet+rise
                                policy['analysis_parameters']={'max_step_s':profile['transient_max_step_s'],'input_transition_s':rise,
                                    'waveform_origin':'engineering_policy','source_does_not_specify_all_waveform_details':True}
                                vs=case['fixture']['supply_voltage_V'];vn=case['fixture']['rails_V']['V_minus'];mid=(vs/2)+vn
                                if kind=='settling':
                                    step=item['method']['definition']['input_step_V'];low=vn+profile['step_baseline_fraction']*vs
                                    policy['analysis_parameters']['waveform']={'initial_V':low,'final_V':low+step,'fixture_gain':1}
                                elif kind=='sr':
                                    low=vn+profile['step_baseline_fraction']*vs;high=low+profile['slew_step_V']
                                    policy['analysis_parameters']['waveform']={'initial_V':low if direction=='rising' else high,'final_V':high if direction=='rising' else low,'direction':direction}
                                elif kind=='overload_recovery':
                                    policy['analysis_parameters']['waveform']={'initial_fixture_input_V':mid+.12*vs,'final_fixture_input_V':mid,
                                        'through_fixture_gain':-10,'output_error_band_V':profile['overload_error_fraction']*vs}
                                elif kind=='thdn':
                                    values=item['resolved_conditions']['values'];freq=values['frequency_Hz']
                                    measure=quiet+profile['fft_warmup_cycles']/freq;stop=measure+profile['fft_measurement_cycles']/freq
                                    policy['analysis_parameters'].update({'fundamental_Hz':freq,'output_amplitude_Vrms':values['output_voltage_Vrms'],
                                        'warmup_cycles':profile['fft_warmup_cycles'],'measurement_cycles':profile['fft_measurement_cycles'],
                                        'max_step_s':1/(20*values['measurement_bandwidth_Hz']),
                                        'max_step_derivation':'1/(20 * source measurement bandwidth)',
                                        'noise_must_be_combined_with_fft':True})
                                elif kind=='capacitive_drive':
                                    policy['analysis_parameters']['waveform']={'initial_V':mid-.05,'final_V':mid+.05,'step_V':.1,'origin':'engineering_policy'}
                                waveform=policy['analysis_parameters'].get('waveform',{})
                                if 'initial_V' in waveform:
                                    policy['initialization_override']={'input_fixture_source_V':waveform['initial_V'],
                                        'expected_unity_output_initial_V':waveform['initial_V'],
                                        'origin':'engineering_waveform_initial_value_replaces_static_midpoint_for_this_transient'}
                                elif kind=='overload_recovery':
                                    policy['initialization_override']={'external_fixture_input_V':waveform['initial_fixture_input_V'],
                                        'allowed_initial_state':'intentionally_overloaded_output',
                                        'origin':'engineering_overload_protocol_not_a_direct_input_pin_voltage'}
                                policy['events']=[event('stimulus','apply_stimulus',[target_port],quiet,
                                    binding_semantics='via_measurement_fixture_not_direct_pin_drive'),
                                    event('observe','start_measurement',outputs,measure,after=['stimulus'],requires_gates=['pre_measurement_conditions_valid']),
                                    event('stop','stop_simulation',[],stop,after=['observe'])]
                        schedule=generate_schedule(pdg,policy)
                        result.append({'policy':policy,'schedule':schedule})
    return {'stage':'plan_03_execution_policies','policies':result,
        'summary':{'policy_count':len(result),'analyses':{a:sum(p['policy']['analysis']==a for p in result) for a in templates}},
        'all_policies_are_engineering_definitions':True,'simulations_executed':0,'testbenches_created':0}
