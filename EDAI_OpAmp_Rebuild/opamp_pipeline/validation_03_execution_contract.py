"""Plan -> actual deck -> consumed metric contract for source-case fixtures.

Expected facts come from the input plan and a named adapter policy, never from
parsing the generator's output. This is a bounded fixture reader, not SPICE LVS.
"""
from copy import deepcopy
from pathlib import Path
import json
import math
import re
from .validation_01_results import digest, check_result, report, save_report
from .validation_02_spice_reader import read_deck, element, dc_value, ac_value, pwl, command, number,model_signature

VERSION = 'source-case-execution/1'
POLICY = {'temperature_C': 25, 'start_s': 5e-6, 'transition_s': 1e-8,
          'stop_s': 40e-6, 'max_step_s': 2e-9, 'dc_intervals': 200,
          'gbw_ac': ['dec', 200, .01, 1e9], 'pm_ac': ['dec', 300, .01, 1e8],
          'noise': ['v(out)', 'vin', 'dec', 100, 1, 1e5],
          'ro_ac': ['lin', 1, 1e6, 1e6]}
LIMITS = ['Checks fixture conditions and selected metric definitions; does not prove DUT topology or source interpretation.',
          'This receipt alone does not prove retry equivalence, cache provenance, startup convergence or device-model accuracy.']


def save_contract_receipt(folder,phase,receipt):
    """Short filenames for nested Windows jobs; full digest remains in payload."""
    # Compare the representation actually written to JSON. Tuples/Paths in
    # in-memory evidence otherwise look different after a safe resume.
    body=json.loads(json.dumps({k:v for k,v in receipt.items() if k!='receipt_sha256'},
                               ensure_ascii=False,allow_nan=False,default=str))
    full=digest(body);payload={**body,'receipt_sha256':full}
    label=re.sub(r'[^A-Za-z0-9_-]','_',phase)[:24]
    path=Path(folder)/(label+'_'+full[:24]+'.json')
    if path.exists():
        if json.loads(path.read_text(encoding='utf-8'))!=payload:
            raise ValueError('Execution receipt filename collision; original preserved')
    save_report(path,payload)
    return path


class ExecutionContractError(ValueError):
    def __init__(self, result):
        self.validation = result
        self.physical_spec_failure_established = False
        failed = [c['check_id'] for c in result['checks'] if c['status'] == 'failed']
        super().__init__('Execution contract mismatch: ' + ', '.join(failed))


def same(a, b):
    if isinstance(a, bool) or isinstance(b, bool):
        return type(a) is type(b) and a == b
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return math.isfinite(a) and math.isfinite(b) and math.isclose(a, b, rel_tol=2e-10, abs_tol=1e-18)
    if isinstance(a, (list, tuple)) and isinstance(b, (list, tuple)):
        return len(a) == len(b) and all(same(x, y) for x, y in zip(a, b))
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(same(a[k], b[k]) for k in a)
    return a == b


def make_contract(model, item, case, variant='default', subckt='FIRSTAMP'):
    """Bind immutable plan evidence and independently derive expected fixture facts."""
    f = deepcopy(case['fixture']); kind = item['method']['kind']
    definition = deepcopy(item['method'].get('definition', {}))
    plus = f['rails_V']['V_plus']; minus = f['rails_V']['V_minus']; mid = (plus + minus) / 2
    vs = f['supply_voltage_V']
    if not same(plus-minus, vs):
        raise ValueError('Plan total supply contradicts plan rails')
    e = {'temperature_C': f.get('temperature_C', POLICY['temperature_C']), 'mid_V': mid,
         'rails_V': {'V_plus': plus, 'V_minus': minus}, 'elements': {}, 'absent': [], 'commands': {},
         'include': str(Path(model).resolve()), 'dut': subckt.lower()}
    e['connections']={'vdd':['vp','0'],'vmid':['mid','0']}
    if Path(model).is_file():e['model_signature']=model_signature(model)
    metric = {'kind': kind, 'variant': variant, 'names': [],
              'servo_error_limit_V': 1e-5, 'linear_servo_vid_limit_V': .05}
    dual = kind in {'pm', 'capacitive_drive'} and variant not in {'rising', 'falling'}
    load = f['load']; node_map = {'rail_midpoint': 'mid', 'V_minus': 'vm', 'V_plus': 'vp'}
    if load['kind'] not in {'resistance','forced_current'}:
        raise ValueError('Unknown planned load kind')
    if load['kind']=='resistance' and load.get('connection') not in node_map and kind != 'iq':
        raise ValueError('Unbound load connection in plan: ' + str(load.get('connection')))
    if load['kind']=='forced_current' and kind != 'iq':
        # Current direction is the plan's binding; unlike a resistor this
        # fixture does not require a load.connection field. The independent
        # contract below still checks ILOAD terminals, sign and magnitude.
        if load.get('direction_selected_by_rail') not in {'V_plus','V_minus'}:
            raise ValueError('Unbound forced-current load direction')
        magnitude=load.get('magnitude_A')
        if isinstance(magnitude,bool) or not isinstance(magnitude,(int,float)) or not math.isfinite(magnitude) or magnitude<0:
            raise ValueError('Invalid forced-current load magnitude')
    node = node_map.get(load.get('connection'), 'mid')
    resistance = load.get('value_Ohm') if load['kind'] == 'resistance' and kind != 'iq' else None
    capacitance = f.get('load_capacitance_pF') if kind not in {'iq', 'vos', 'ib', 'ios'} else None
    if resistance is not None and (isinstance(resistance,bool) or not math.isfinite(resistance) or resistance<=0):
        raise ValueError('Planned load resistance must be positive; zero is not an absent load')
    if capacitance is not None and (isinstance(capacitance,bool) or not math.isfinite(capacitance) or capacitance<0):
        raise ValueError('Invalid planned load capacitance')
    if dual:
        e['connections']={'vdd':['vp','0'],'vmid':['mid','0']}
        if minus != 0 or node != 'mid' or load['kind'] != 'resistance' or not resistance:
            raise ValueError('Dual-probe adapter cannot implement this planned rail/load connection')
        for suffix in ('v', 'i'):
            e['elements']['rload'+suffix] = ['y'+suffix, 'mid', resistance]
            if capacitance:
                e['elements']['cload'+suffix] = ['y'+suffix, 'mid', capacitance*1e-12]
            else:
                e['absent'].append('cload'+suffix)
        metric['analysis'] = 'ac'; e['commands']['.ac'] = POLICY['pm_ac']
    else:
        e['connections']['vss']=['vm','0']
        e['elements']['vsense']=['dout','out',0]
        if resistance is not None and resistance != 0:
            e['elements']['rl'] = ['out', node, resistance]
        else:
            e['absent'].append('rl')
        if kind != 'iq' and load['kind'] == 'forced_current':
            e['elements']['iload'] = ['out', 'mid', load['magnitude_A']*(1 if load['direction_selected_by_rail'] == 'V_plus' else -1)]
        else:
            e['absent'].append('iload')
        if capacitance:
            e['elements']['cl'] = ['out', 'mid', capacitance*1e-12]
        else:
            e['absent'].append('cl')
        if kind in {'iq', 'vos', 'ib', 'ios', 'vswing', 'iout', 'isc'}:
            metric['analysis'] = 'op'; e['commands']['.op'] = []
        elif kind in {'vcm', 'cmrr', 'aol', 'psrr', 'input_resistance'}:
            metric['analysis'] = 'dc'
            points = POLICY['dc_intervals']
            if kind in {'vcm', 'cmrr'}:
                window = f['input_common_mode_sweep_V']; lo, hi = window['min'], window['max']
                start, end, delta = lo, hi, (hi-lo)/points
                if kind == 'vcm' and variant in {'lower', 'upper'}:
                    start = (lo+hi)/2; end = lo if variant == 'lower' else hi
                    delta *= -1 if variant == 'lower' else 1
                source = 'vin' if kind == 'vcm' else 'vcm'
                e['connections'][source]=['inp','0'] if kind=='vcm' else ['cm','0']
            elif kind == 'aol':
                window = f['output_voltage_sweep']; start, end = window['min'], window['max']
                delta = (end-start)/points; source = 'vset'
                e['connections']['vset']=['target','0']
            elif kind == 'input_resistance':
                start, end, delta, source = mid-.1, mid+.1, .01, 'vcm'
                e['connections']['vcm']=['cm','0']
            else:
                supply = item['resolved_conditions']['values']['supply_voltage_V']
                start, end = max(supply['min'], vs-.1), min(supply['max'], vs+.1)
                delta = (end-start)/10; source = 'vsw'
                e['symmetric_psrr'] = True
                e['connections'].pop('vdd');e['connections'].pop('vss')
                e['connections'].update(bvp=['vp','0'],bvn=['vm','0'],vsw=['vsw','0'])
            e['commands']['.dc'] = [source, start, end, delta]
        elif kind == 'gbw':
            metric['analysis'] = 'ac'; e['commands']['.ac'] = POLICY['gbw_ac']
        elif kind in {'sr', 'settling', 'capacitive_drive'}:
            metric['analysis'] = 'tran'
            amplitude = .1 if kind == 'capacitive_drive' else definition.get('input_step_V', 2) if kind == 'settling' else definition.get('step_V', 2)
            initial = minus + definition.get('baseline_fraction_of_supply', .2)*vs if kind == 'settling' else mid-amplitude/2
            final = initial+amplitude
            if variant == 'falling': initial, final = final, initial
            fraction = definition.get('error_percent', .1)/100 if kind == 'settling' else .001
            metric['step'] = {'initial_V': initial, 'final_V': final, 'start_s': POLICY['start_s'],
                              'transition_s': POLICY['transition_s'], 'stop_s': POLICY['stop_s'],
                              'max_step_s': POLICY['max_step_s'], 'error_fraction': fraction}
            s = metric['step']
            e['pwl'] = [[0, initial], [s['start_s'], initial], [s['start_s']+s['transition_s'], final], [s['stop_s'], final]]
            e['connections']['vin']=['inp','0']
            e['commands']['.tran'] = [0, s['stop_s'], 0, s['max_step_s']]
            # These are postprocessor semantics, not voltages present in a deck.
            if kind == 'settling':
                e['metric_semantics'] = {
                    'reference_time': definition.get('reference_time', 'end_of_input_transition'),
                    'metric': definition.get('metric', 'last_entry_and_residence_until_end_of_observation')}
            if kind == 'sr':
                e['metric_semantics'] = {'fraction_interval': definition.get('fraction_interval', [.1, .9])}
        elif kind == 'ro':
            metric['analysis'] = 'ac'
            freq=f.get('source_case_conditions',{}).get('frequency_Hz',1e6)
            e['commands']['.ac'] = ['lin',1,freq,freq]
        elif kind == 'noise_density':
            conditions=f.get('source_case_conditions',{})
            frequency=conditions.get('frequency_Hz',1000);source_r=conditions.get('source_resistance_Ohm',0)
            if isinstance(source_r,bool) or not isinstance(source_r,(int,float)) or not math.isfinite(source_r) or source_r<0:
                raise ValueError('Invalid planned noise source resistance')
            if isinstance(frequency,bool) or not isinstance(frequency,(int,float)) or not math.isfinite(frequency) or frequency<=0:
                raise ValueError('Invalid planned noise measurement frequency')
            metric.update(analysis='noise',names=['en_density'],noise_definition={
                'source_resistance_Ohm':source_r,'frequency_Hz':frequency,'scalar_name':'en_density',
                'input_reference':'VIN_before_source_resistance','source_resistance_included_in_total_noise':True})
            e['commands']['.noise']=['v(out)','vin','dec',100,min(1,frequency),max(1e5,frequency)]
            e['noise_measure_frequency_Hz']=frequency;e['noise_measurement_name']='en_density'
            e['ac_sources']={'vin':1}
            if source_r>0:
                e['elements']['rsource']=['noise_src','inp',source_r]
                e['elements']['vin']=['noise_src','mid',0]
            else:
                e['absent'].append('rsource');e['elements']['vin']=['inp','mid',0]
        else:
            raise NotImplementedError('No execution contract for ' + kind)
    if kind == 'vswing':
        rail = f['forced_output_rail']
        if rail == 'both': rail = 'V_plus' if variant == 'upper' else 'V_minus'
        polarity = 1 if rail == 'V_plus' else -1
        metric.update(overdrive_V=polarity, measured_output_rail=rail)
        e['elements'].update(vpin=['inp', '0', mid+polarity*.5], vnin=['inn', '0', mid-polarity*.5])
    if kind in {'iout', 'isc'}:
        diff = f['source_case_conditions'].get('differential_input_voltage_V', 1 if variant == 'source' else -1)
        if kind == 'isc': diff = 1 if variant == 'source' else -1
        metric.update(direction='source' if diff > 0 else 'sink', clamp_V=f['output_dc_bias_V'])
        e['elements'].update(vpin=['inp', '0', mid+diff/2], vnin=['inn', '0', mid-diff/2], vclamp=['out', '0', f['output_dc_bias_V']])
    if kind in {'settling','sr','capacitive_drive','vcm'} and not dual:
        e['planned_gain']=f.get('closed_loop_gain')
    return {'version': VERSION, 'role': 'source_case' if subckt == 'FIRSTAMP' else 'analytical_reference',
            'plan_sha256': digest({'item': item, 'case': case}), 'fixture': f,
            'source_evidence': deepcopy(item.get('source', {})), 'expected': e, 'metric': metric,
            'policy': deepcopy(POLICY), 'definition_origins': {
                'fixture': 'measurement_plan_case', 'method': 'measurement_plan_definition',
                'grid_and_timing': 'named_adapter_numerical_policy', 'calibration': 'independent_analytical_fixture'}}


def validate_execution(deck, meta, *, fixture=None, kind=None, phase='preflight', receipt_dir=None):
    contract = meta.get('execution_contract')
    if contract is None:
        # Legacy/reference calls without a source-case binding are explicitly not certified.
        receipt=report('execution_contract', 'unbound_legacy_fixture', [], status='not_checked',
                       evidence={'phase':phase,'deck_sha256':digest(deck)},limits=LIMITS)
        folder=receipt_dir or meta.get('execution_contract_receipt_dir')
        if folder:save_contract_receipt(folder,phase,receipt)
        return receipt
    e = contract['expected']; checks = []
    def check(name, expected, get_actual, origin='measurement_plan_case'):
        try:
            actual = get_actual(); good = same(expected, actual)
        except (ValueError, KeyError, IndexError, TypeError,OSError) as error:
            actual = {'read_error': str(error)}; good = False
        checks.append(check_result(name, phase, expected, actual, good, origin))
    check('contract_version', VERSION, lambda: contract['version'], 'implementation_version')
    try:
        facts = read_deck(deck)
    except ValueError as error:
        facts = {'elements': {}, 'commands': {}, 'includes': []}
        check('deck_readable', True, lambda: str(error), 'independent_deck_reader')
    check('temperature_C', e['temperature_C'], lambda: number(command(facts, '.temp')[0]))
    if 'model_signature' in e:
        check('included_model_contents',e['model_signature'],lambda:model_signature(facts['includes'][0]) if len(facts['includes'])==1 else facts['includes'])
    elif e.get('include') is not None:
        check('included_model_path', e['include'], lambda: facts['includes'][0] if len(facts['includes']) == 1 else facts['includes'])
    if e.get('include') is None:
        check('no_model_include',[],lambda:facts['includes'])
    if not e.get('skip_mid_dc'):
        check('rail_midpoint_V', e['mid_V'], lambda: dc_value(facts, 'vmid'))
    if e.get('skip_rail_dc'):
        pass
    elif e.get('symmetric_psrr'):
        mid = e['mid_V']
        for name, sign in [('bvp', '+'), ('bvn', '-')]:
            # Restricted affine form only; accepting arbitrary expressions would hide errors.
            def read_expression(name=name, sign=sign):
                text = ''.join(element(facts, name)[3:]).lower()
                m = re.fullmatch(r'v=([+\-\d.e]+)' + re.escape(sign) + r'v\(vsw\)/2', text)
                if not m: raise ValueError('Unexpected symmetric supply expression')
                return float(m[1])
            check(name+'_fixed_midpoint', mid, read_expression)
        check('total_supply_V', contract['fixture']['supply_voltage_V'], lambda: dc_value(facts, 'vsw'))
    else:
        check('positive_rail_V', e['rails_V']['V_plus'], lambda: dc_value(facts, 'vdd'))
        check('negative_rail_V', e['rails_V']['V_minus'], lambda: dc_value(facts, 'vss') if 'vss' in facts['elements'] else 0)
    dual = 'rloadv' in e['elements']
    if 'dut_bindings' in e:
        for name,binding in e['dut_bindings'].items():
            check('dut_binding_'+name,binding,lambda name=name:element(facts,name)[1:])
    elif dual:
        for suffix in ('v', 'i'):
            check('dut_binding_'+suffix, ['mid', 'x'+suffix, 'vp', '0', 'y'+suffix, e['dut']], lambda suffix=suffix: element(facts, 'xd'+suffix)[1:])
    else:
        check('dut_binding', ['inp', 'inn', 'vp', 'vm', 'dout', e['dut']], lambda: element(facts, 'xdut')[1:])
    for name, value in e['elements'].items():
        check('element_'+name, value, lambda name=name: element(facts, name)[1:3]+[dc_value(facts, name)])
    for name,nodes in e['connections'].items():
        check('connection_'+name,nodes,lambda name=name:element(facts,name)[1:3])
    for name,value in e.get('ac_sources',{}).items():
        check('ac_source_'+name,value,lambda name=name:ac_value(facts,name))
    for name,expression in e.get('expressions',{}).items():
        check('expression_'+name,expression,lambda name=name:''.join(element(facts,name)[3:]).lower())
    for name in e['absent']:
        check('absent_'+name, False, lambda name=name: name in facts['elements'])
    for name, value in e['commands'].items():
        def read_command(name=name):
            return [number(t) if re.match(r'^[+\-\d.]', t) else t.lower() for t in command(facts, name)]
        check('analysis_'+name, value, read_command, 'named_adapter_numerical_policy_and_plan')
    allowed=set(e['commands'])|({'.op'} if dual or e.get('allow_op') else set())
    check('unexpected_analyses',[],lambda:sorted(set(facts['commands']).intersection({'.op','.dc','.ac','.noise','.tran'})-allowed))
    check('no_forced_initial_conditions',[],lambda:facts['commands'].get('.ic',[]),'unrestricted_operating_point_policy')
    if e.get('planned_gain') is not None:
        check('closed_loop_gain',e['planned_gain'],lambda:1,'plan_gain_vs_unity_fixture')
    if 'pwl' in e:
        check('input_pwl', e['pwl'], lambda: pwl(facts, e.get('pwl_source','vin')))
        if e.get('unity_feedback',True):
            check('unity_feedback', ['out', 'inn', 0], lambda: element(facts, 'vfb')[1:3]+[dc_value(facts, 'vfb')])
    if 'noise_measure_frequency_Hz' in e:
        def frequency():
            meas = command(facts, '.meas')
            if [s.lower() for s in meas[:4]] != ['noise', e.get('noise_measurement_name','en_1k'), 'find', 'v(inoise)']:
                raise ValueError('Wrong noise quantity')
            return number(meas[4].split('=', 1)[1])
        check('noise_frequency_Hz', e['noise_measure_frequency_Hz'], frequency, 'adapter_metric_definition')
    for key, expected in contract['metric'].items():
        check('metric_'+key, expected, lambda key=key: meta[key], 'plan_and_consumed_metric_definition')
    if fixture is not None:
        check('metric_fixture', contract['fixture'], lambda: fixture)
    if kind is not None:
        check('metric_dispatch_kind', contract['metric']['kind'], lambda: kind)
    semantics = e.get('metric_semantics', {})
    implemented = {'reference_time': 'end_of_input_transition',
                   'metric': 'last_entry_and_residence_until_end_of_observation', 'fraction_interval': [.1, .9]}
    for key, expected in semantics.items():
        check('postprocessor_'+key, expected, lambda key=key: implemented[key], 'implemented_postprocessor_semantics')
    code_hashes={p.name:__import__('hashlib').sha256(p.read_bytes()).hexdigest() for p in
                 [Path(__file__),Path(__file__).with_name('validation_02_spice_reader.py'),
                  Path(__file__).with_name('verify_02_metrics.py'),Path(__file__).with_name('tb_05_waveform_metrics.py')]}
    receipt = report('execution_contract', contract['plan_sha256'], checks,
                     evidence={'contract_version': VERSION, 'phase': phase, 'plan_sha256': contract['plan_sha256'],
                               'contract_sha256': digest(contract), 'deck_sha256': __import__('hashlib').sha256(deck.encode('utf-8')).hexdigest(),
                               'metric_definition_sha256': digest(contract['metric']), 'code_sha256':code_hashes,
                               'role': contract['role']}, limits=LIMITS)
    folder = receipt_dir or meta.get('execution_contract_receipt_dir')
    if folder:
        save_contract_receipt(folder,phase,receipt)
    if receipt['status'] != 'passed':
        raise ExecutionContractError(receipt)
    return receipt
