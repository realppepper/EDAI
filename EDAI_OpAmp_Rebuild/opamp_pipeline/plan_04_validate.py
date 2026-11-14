"""Validate source retention, goal provenance, fixtures and policy link coverage."""
import math
from .plan_01_select_targets import source_specs
from .pdg_04_schedule import generate_schedule
from .plan_02_measurements import classify,target_criteria,resolved_conditions,make_fixture


def validate_plan(selection,measurements,policies,hkg,pdg,profile):
    source={r['id']:r for r in source_specs(hkg)}
    decisions={r['row_id']:r for r in selection['items']}
    if set(source)!=set(decisions):raise ValueError('Source rows missing from scope accounting')
    for row_id,item in decisions.items():
        if item['source']!=source[row_id]:raise ValueError('Source snapshot changed in target selection')
        if item['source_temperature_rewritten'] is not False:raise ValueError('Source temperature must be preserved')
    included={key for key,item in decisions.items() if item['required_in_project']}
    actual={m['row_id']:m for m in measurements['measurements']}
    if set(actual)!=included or len(actual)!=len(measurements['measurements']):raise ValueError('Required measurement rows omitted/duplicated')
    cases={};case_owners={}
    sets={n['label']:n['data'] for n in hkg['nodes'] if n['type']=='ConditionSet'}
    for row_id,item in actual.items():
        row=source[row_id]
        if item['source']!=row or item['target']['source_limits_preserved']!=row['limits']:
            raise ValueError('Project target changed original source values')
        if item['evaluation_temperature_C']!=25 or item['executed'] or item['ready_for_test_execution']:
            raise ValueError('Planning must not imply execution or other temperatures')
        if item['resolved_conditions']['source_conditions']!=row['conditions']:raise ValueError('Original condition provenance changed')
        kind,analyses,_=classify(row)
        if item['method']['kind']!=kind or item['method']['analyses']!=analyses:raise ValueError('Measurement method differs from source classification')
        expected_target=target_criteria(row,kind,profile,isinstance(decisions[row_id]['source_temperature_condition_C'],dict))
        if item['target']!=expected_target:raise ValueError('Project target differs from source-bound conversion/project policy')
        for rule in item['target']['rules']:
            value=rule.get('value')
            if isinstance(value,(int,float)) and not isinstance(value,bool) and not math.isfinite(value):raise ValueError('Nonfinite target')
        for case in item['cases']:
            key=case['case_id']
            if key in cases:raise ValueError('Duplicate fixture case')
            cases[key]=case;case_owners[key]=item
            f=case['fixture'];vs=f['supply_voltage_V'];rails=f['rails_V']
            expected_fixture,_=make_fixture(row,kind,resolved_conditions(row,sets),vs,profile)
            if f!=expected_fixture:raise ValueError('Fixture differs from source conditions/project interpretation')
            if f['temperature_C']!=25 or abs(rails['V_plus']-rails['V_minus']-vs)>1e-9:raise ValueError('Invalid fixture rail/temperature binding')
            source_supply=item['resolved_conditions']['values']['supply_voltage_V']
            if isinstance(source_supply,dict) and not source_supply['min']<=vs<=source_supply['max']:raise ValueError('Supply sample outside source range')
            if isinstance(source_supply,(int,float)) and source_supply!=vs:raise ValueError('Fixture changed explicit supply')
            if case['full_continuous_source_range_verified'] is not False:raise ValueError('Finite samples do not verify a continuous range')
    seen=set();covered=set();detailed_coverage=set()
    channels=[n['source_key'] for n in pdg['nodes'] if n['type']=='Channel']
    for entry in policies['policies']:
        p=entry['policy'];key=p['policy_id']
        if key in seen:raise ValueError('Duplicate execution policy')
        seen.add(key)
        case=cases.get(p['case_id'])
        if not case or p['row_id']!=case_owners[p['case_id']]['row_id']:raise ValueError('Policy refers to a different case/row')
        if p['case_fixture']!=case['fixture']:raise ValueError('Policy fixture differs from measurement fixture')
        if entry['schedule']!=generate_schedule(pdg,p):raise ValueError('Policy schedule differs from validated policy')
        if entry['schedule']['ready_for_test_execution'] is not False:raise ValueError('An unbound test cannot be ready')
        waveform=p.get('analysis_parameters',{}).get('waveform',{})
        for field in ('initial_V','final_V'):
            if field in waveform:
                f=case['fixture']
                if not f['rails_V']['V_minus']<=waveform[field]<=f['rails_V']['V_plus']:
                    raise ValueError('Project input waveform exceeds selected supply rails')
        covered.add((p['case_id'],p['analysis']))
        detailed_coverage.add((p['case_id'],p['analysis'],tuple(sorted(p['channels'])),p.get('variant','default')))
    required={(case['case_id'],analysis) for item in actual.values() for case in item['cases'] for analysis in item['method']['analyses']}
    if required!=covered:raise ValueError('A required case/analysis has no execution policy')
    expected_detailed=set()
    for item in actual.values():
        kind=item['method']['kind'];groups=[channels] if kind in {'iq','channel_separation'} else [[c] for c in channels]
        for case in item['cases']:
            for analysis in item['method']['analyses']:
                variants=['rising','falling'] if kind=='sr' and analysis=='tran' else ['default']
                for group in groups:
                    for variant in variants:expected_detailed.add((case['case_id'],analysis,tuple(sorted(group)),variant))
    if expected_detailed!=detailed_coverage:raise ValueError('Channel/direction policy coverage is incomplete')
    return {'status':'source_scope_goals_fixtures_and_policy_integrity_passed','source_rows':len(source),
        'included_rows':len(actual),'fixture_cases':len(cases),'execution_policies':len(seen),
        'source_values_changed':False,'simulations_executed':0,'testbenches_created':0,
        'scope':'Planning integrity only. Numerical performance and testbench adapters have not been verified by SPICE.'}
