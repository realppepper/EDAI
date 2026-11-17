"""Validate designer-selected sizing variables/ranges without executing designer code."""
from pathlib import Path
import math
import re
from .optuna_01_parameters import _line_indices,validate_space
from .validation_02_spice_reader import number
from .support.execution_state import file_hash

SCREENING=['iq','gbw','pm','sr']


def designer_policy(trials=4,rounds=1):
    if any(isinstance(n,bool) or not isinstance(n,int) for n in (trials,rounds)) or not 2<=trials<=20 or not 1<=rounds<=20:
        raise ValueError('Designer sizing requires2..20 total trials and1..20 rounds')
    return {'mode':'designer_proposal','trials':trials,'trial_cap':trials,'max_rounds':rounds,
            'screening_kinds':list(SCREENING),'max_parameters':6,'config_path':None,'seed':17}


def proposal_contract(state,reason):
    policy=state['optuna'];current=state['candidates'][-1]
    return {'enabled':reason in {'numeric_repair_eligible','startup_repair_eligible'},'routing_reason':reason,
            'candidate_file_sha256':current['candidate_sha256'],'max_total_trials':policy.get('trial_cap',policy['trials']),
            'max_parameter_groups':policy.get('max_parameters',6),'screening_kinds':list(policy['screening_kinds']),
            'objective':'minimize_worst_case_quiescent_power_mW',
            'rules':['Select explicit R/C values or MOS W/L, grouped where matching must be retained.',
                     'Use SI units: Ohm,F,m. Finite positive bounds must include the current value; baseline counts as one trial.',
                     'Do not edit topology, model cards, source targets or testbench definitions.',
                     'Give hypotheses, evidence case IDs and risks; the host validates syntax, not circuit insight.',
                     'Startup repair may cite OPERATIONAL-STARTUP. Invalid or incomplete measurements are not physical failures.',
                     'Partial screens are followed by bounded full implemented-scope validation; unscreened failures remain required.',
                     'A circuit revision remains available if numeric sizing is inappropriate.'],
            'response_schema':{'action':'propose_sizing','request_id':'echo request_id','request_sha256':'SHA256 of this request file',
                'based_on_candidate_sha256':'echo candidate_file_sha256',
                'sizing_proposal':{'reason':'engineering hypothesis','evidence_case_ids':['actual failed case IDs'],
                    'risks':['possible tradeoffs'],'trials':'integer2..max_total_trials',
                    'parameters':[{'name':'stable_identifier','elements':['CCOMP'],'field':'value or W or L',
                                   'low':'positive SI number','high':'positive SI number','log':True,'reason':'why this group and range'}]}}}


def _current_value(text,spec):
    lines,indices=_line_indices(text)
    if not isinstance(spec['elements'],list) or not spec['elements'] or any(not isinstance(e,str) for e in spec['elements']):raise ValueError('Element groups must be nonempty string lists')
    first=spec['elements'][0].upper()
    if first not in indices:raise ValueError('Unknown proposed element: '+first)
    line=lines[indices[first]];field=spec['field']
    if field=='value':
        tokens=line.split()
        if first[0] not in 'RC' or len(tokens)!=4:raise ValueError('Only plain resistor/capacitor scalar values are supported')
        return number(tokens[3])
    if field not in {'W','L'} or not first.startswith('M'):raise ValueError('Only MOS W/L or R/C values can be proposed')
    hits=re.findall(r'\b'+field+r'\s*=\s*([^\s]+)',line,re.I)
    if len(hits)!=1:raise ValueError('Need one explicit current MOS dimension')
    return number(hits[0])


def validate_proposal(request,response,text,policy,request_sha256):
    contract=request.get('numeric_sizing_proposal',{})
    if not contract.get('enabled'):raise ValueError('No eligible numeric sizing proposal was requested')
    if response.get('action')!='propose_sizing' or response.get('request_id')!=request['request_id'] or response.get('request_sha256')!=request_sha256:
        raise ValueError('Sizing response is not bound to the pending request')
    if response.get('based_on_candidate_sha256')!=contract['candidate_file_sha256']:raise ValueError('Sizing response belongs to another candidate')
    if any(k in response for k in ('netlist','candidate_file','config_path','command')):raise ValueError('A sizing proposal must not contain circuit edits, paths or commands')
    proposal=response.get('sizing_proposal')
    if not isinstance(proposal,dict) or set(proposal)-{'reason','evidence_case_ids','risks','trials','parameters'}:raise ValueError('Unknown sizing proposal fields')
    if not isinstance(proposal.get('reason'),str) or not proposal['reason'].strip():raise ValueError('Sizing rationale required')
    if not isinstance(proposal.get('risks'),list) or not proposal['risks'] or any(not isinstance(x,str) or not x.strip() for x in proposal['risks']):raise ValueError('Sizing tradeoffs required')
    evidence=proposal.get('evidence_case_ids');known={x['case_id'] for x in request['feedback']}
    failed={x['case_id'] for x in request['feedback'] if x['status']=='failed_in_model'}
    if contract.get('routing_reason')=='startup_repair_eligible' and request.get('operational_startup',{}).get('passed') is False:
        known.add('OPERATIONAL-STARTUP');failed.add('OPERATIONAL-STARTUP')
    if not isinstance(evidence,list) or not evidence or any(not isinstance(x,str) for x in evidence) or not set(evidence)<=known or not set(evidence)&failed:raise ValueError('Sizing evidence must reference a measured failed case')
    trials=proposal.get('trials')
    if isinstance(trials,bool) or not isinstance(trials,int) or not 2<=trials<=policy.get('trial_cap',policy['trials']):raise ValueError('Sizing proposal exceeds host trial budget')
    specs=proposal.get('parameters')
    if not isinstance(specs,list) or not 1<=len(specs)<=policy.get('max_parameters',6):raise ValueError('Invalid parameter-group count')
    converted=[]
    for spec in specs:
        if not isinstance(spec,dict) or set(spec)-{'name','elements','field','low','high','log','reason','baseline'}:raise ValueError('Unknown parameter fields')
        if not {'name','elements','field','low','high','reason'}<=set(spec):raise ValueError('Missing required parameter fields')
        if not isinstance(spec.get('name'),str) or not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{0,63}',spec['name']):raise ValueError('Invalid parameter identifier')
        if not isinstance(spec.get('reason'),str) or not spec['reason'].strip():raise ValueError('Explain each parameter group and range')
        if type(spec.get('log',False)) is not bool:raise ValueError('log must be boolean')
        baseline=float(format(_current_value(text,spec),'.15g'))
        if 'baseline' in spec and (isinstance(spec['baseline'],bool) or not isinstance(spec['baseline'],(int,float)) or not math.isclose(spec['baseline'],baseline,rel_tol=1e-10,abs_tol=1e-20)):
            raise ValueError('Proposed current value differs from actual DUT')
        converted.append({**spec,'baseline':baseline})
    config={'schema_version':'opamp-sizing/1','description':'Host-validated designer proposal; ranges/selection are hypotheses.',
            'seed':policy.get('seed',17),'screening_kinds':list(policy['screening_kinds']),
            'objective':'minimize_worst_case_quiescent_power_mW','parameters':converted}
    validate_space(text,config)
    from .ref_05_research import validate_usage
    from . import ref_07_datasheet
    validate_usage(request,response);ref_07_datasheet.validate_usage(request,response)
    return config,trials


def accept(session,state,response_path,response,config,trials):
    from . import harness_03_loop as fixed
    from .ref_05_research import record_usage
    from . import ref_07_datasheet
    session=Path(session);current=state['candidates'][-1];pending=state['pending_request'];request=fixed.read(pending['path'])
    folder=session/'sizing_proposals'/f"proposal_{len(state.get('sizing_proposals',[])):03d}"
    folder.mkdir(parents=True,exist_ok=False)
    (folder/'REQUEST.json').write_bytes(Path(pending['path']).read_bytes())
    (folder/'RESPONSE.json').write_bytes(Path(response_path).read_bytes())
    fixed.write_json(folder/'CONFIG.json',config)
    record={'candidate_sha256':current['candidate_sha256'],'request_path':str(folder/'REQUEST.json'),
            'request_sha256':file_hash(folder/'REQUEST.json'),'response_path':str(folder/'RESPONSE.json'),
            'response_sha256':file_hash(folder/'RESPONSE.json'),'submitted_response_sha256':file_hash(response_path),
            'config_path':str(folder/'CONFIG.json'),'config_sha256':file_hash(folder/'CONFIG.json'),
            'reason':response['sizing_proposal']['reason'],'evidence_case_ids':response['sizing_proposal']['evidence_case_ids'],
            'risks':response['sizing_proposal']['risks'],'trials':trials}
    state.setdefault('sizing_proposals',[]).append(record)
    state['optuna'].update(config_path=record['config_path'],config_sha256=record['config_sha256'],
                           proposal_for_candidate=current['candidate_sha256'],trials=trials)
    record_usage(state,request,response);ref_07_datasheet.record_usage(state,request,response)
    state.update(status='awaiting_optuna_execution',pending_request=None)
    fixed.save(session,state)
    return state
