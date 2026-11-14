"""Generate analysis-operation sequences or explicit-policy transient timing."""
from copy import deepcopy
import math
from .support.source_checks import fingerprint
from .pdg_03_audit import audit_pdg


OPERATIONS={
    'op':['configure_supplies_inputs_loads','solve_dc_operating_point','check_operating_point'],
    'dc':['configure_bias_and_dc_sweep','solve_operating_points_across_sweep','check_operating_point','collect_dc_sweep_results'],
    'ac':['configure_dc_bias_and_ac_sources','solve_dc_operating_point','check_operating_point','run_ac_sweep','collect_ac_results'],
    'noise':['configure_bias_and_noise_models','solve_dc_operating_point','check_operating_point','run_noise_spectrum','collect_noise_results'],
    'tran':['configure_transient_sources_and_initialization','run_transient_with_policy','check_pre_measurement_conditions','collect_transient_results']}


def pdg_signature(graph):
    return fingerprint({k:v for k,v in graph.items() if k!='_execution'})


def policy_templates(graph):
    channels=[n['source_key'] for n in graph['nodes'] if n['type']=='Channel']
    return {analysis:{'policy_id':'to_be_selected','pdg_fingerprint':pdg_signature(graph),'analysis':analysis,
        'channels':channels,'origin':'engineering_policy','rationale':None,'fixture_binding':None,
        'initialization':None,'events':[],
        'required_gates':['dc_operating_point_valid'] if analysis in {'op','dc','ac','noise'} else ['pre_measurement_conditions_valid'],
        'not_a_datasheet_timing_requirement':True} for analysis in OPERATIONS}


def number(value):
    return isinstance(value,(int,float)) and not isinstance(value,bool) and math.isfinite(value) and value>=0


def generate_schedule(graph,policy=None):
    audit=audit_pdg(graph)
    if audit['status']!='functional_checks_passed':raise ValueError('PDG audit failed; refuse to schedule')
    result={'pdg_fingerprint':pdg_signature(graph),'status':'awaiting_execution_policy','policy_applied':False,
        'analysis':None,'operation_sequence':[],'events':[],'ready_for_test_execution':False,
        'test_plan_generated':False,'testbench_generated':False,'hardware_run_performed':False}
    if policy is None:
        result['missing_inputs']=['analysis selection','fixture/port binding','execution policy and gate criteria']
        return result
    if policy.get('pdg_fingerprint')!=pdg_signature(graph):raise ValueError('Execution policy is stale')
    analysis=policy.get('analysis')
    if analysis not in OPERATIONS:raise ValueError('Analysis must be op/dc/ac/noise/tran')
    if policy.get('origin')!='engineering_policy' or not policy.get('rationale'):
        raise ValueError('Execution timing is an explicit engineering policy, not a datasheet fact')
    channels={n['source_key'] for n in graph['nodes'] if n['type']=='Channel'}
    selected=policy.get('channels',[])
    if not selected or not set(selected)<=channels or len(set(selected))!=len(selected):raise ValueError('Select known unique channels')
    ports={n['source_key']:n for n in graph['nodes'] if n['type']=='Port'}
    events=policy.get('events',[])
    if not isinstance(events,list):raise ValueError('Policy events must be a list')
    ids=[e.get('id') for e in events]
    if any(not isinstance(x,str) or not x for x in ids) or len(set(ids))!=len(ids):raise ValueError('Policy event IDs must be unique')
    for event in events:
        if not set(event.get('ports',[]))<=set(ports):raise ValueError('Event refers to unknown reference ports')
        if event.get('kind') not in {'set_supply','set_input','apply_stimulus','start_measurement','stop_simulation'}:
            raise ValueError('Unknown policy event kind')
        roles={ports[key]['data']['role'] for key in event.get('ports',[])}
        if event['kind']=='set_supply' and roles!={'supply'}:raise ValueError('Supply event must target supply ports')
        if event['kind'] in {'set_input','apply_stimulus'} and (not roles or not roles<={'input','control'}):raise ValueError('Input/stimulus event must target input/control ports')
        if event['kind']=='start_measurement' and roles!={'output'}:raise ValueError('Measurement event must target output ports')
        if event['kind']=='apply_stimulus' and any(ports[key]['data'].get('channel_key') not in selected for key in event['ports']):
            raise ValueError('Stimulus targets an unselected channel')
    required_gate='dc_operating_point_valid' if analysis in {'op','dc','ac','noise'} else 'pre_measurement_conditions_valid'
    if required_gate not in policy.get('required_gates',[]):raise ValueError('Required operating-condition gate is missing')
    if analysis in {'op','dc','ac','noise'}:
        if events:raise ValueError('DC/AC operation sequence must not receive transient timestamps')
    else:
        if policy.get('initialization') not in {'dc_operating_point','explicit_startup'}:raise ValueError('Transient initialization policy is required')
        if not events or any(not number(e.get('time_s')) for e in events):raise ValueError('Transient event times must be explicit finite nonnegative seconds')
        if any(e.get('origin')!='engineering_policy' or not e.get('rationale') for e in events):
            raise ValueError('Every event time needs engineering-policy provenance')
        by_id={e['id']:e for e in events}
        for event in events:
            for earlier in event.get('after',[]):
                if earlier not in by_id or by_id[earlier]['time_s']>=event['time_s']:
                    raise ValueError('Event ordering constraint violates its declared timestamps')
        measurements=[e for e in events if e['kind']=='start_measurement']
        stops=[e for e in events if e['kind']=='stop_simulation']
        stimuli=[e for e in events if e['kind']=='apply_stimulus']
        passive=policy.get('measurement_mode')=='passive_noise_observation'
        if len(measurements)!=1 or len(stops)!=1 or (not stimuli and not passive):raise ValueError('Transient policy needs stimulus or explicit passive-noise observation, one measurement start and one stop')
        outputs={key for key,node in ports.items() if node['data']['role']=='output' and node['data'].get('channel_key') in selected}
        if set(measurements[0]['ports'])!=outputs:raise ValueError('Measurement outputs do not match selected channels')
        if measurements[0].get('requires_gates')!=[required_gate]:raise ValueError('Measurement must explicitly require the condition-validity gate')
        if stops[0]['time_s']<=max(e['time_s'] for e in events if e['kind']!='stop_simulation'):
            raise ValueError('Simulation stop must follow every other event')
        if any(e['time_s']>measurements[0]['time_s'] for e in stimuli):raise ValueError('Measurement cannot start before its stimulus')
        for name in ([] if passive else selected):
            expected={n['source_key'] for n in ports.values() if n['data'].get('channel_key')==name and n['data']['role']=='input'}
            if not any(set(e.get('ports',[])) & expected for e in stimuli):raise ValueError('Selected channel has no stimulus event')
        if policy['initialization']=='explicit_startup':
            required_supplies={key for key,node in ports.items() if node['data']['role']=='supply'}
            initialized={key for e in events if e['kind']=='set_supply' and e['time_s']<=measurements[0]['time_s'] for key in e.get('ports',[])}
            if not required_supplies<=initialized:raise ValueError('Explicit startup must initialize supplies before a condition-valid measurement')
    result.update({'status':'policy_schedule_generated','policy_applied':True,'analysis':analysis,
        'operation_sequence':OPERATIONS[analysis],
        'events':sorted(deepcopy(events),key=lambda e:(e['time_s'],e['id'])) if analysis=='tran' else [],
        'policy':deepcopy(policy),'required_gates':policy['required_gates'],
        'gate_results':{key:'not_evaluated' for key in policy['required_gates']},
        'timing_values_are_datasheet_requirements':False,
        'readiness_blockers':['No DUT netlist/testbench has been bound or executed','Operating-condition gates have not been evaluated']})
    return result
