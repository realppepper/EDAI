"""Bounded edits of explicit scalar values; never change topology or model cards."""
from copy import deepcopy
import math
import re
from .validation_02_spice_reader import number


def _line_indices(text):
    lines=text.splitlines();indices={};inside=False;count=0
    for index,line in enumerate(lines):
        tokens=line.split()
        if not tokens or tokens[0].startswith('*'):continue
        if tokens[0].lower()=='.subckt':
            count+=1;inside=True;continue
        if tokens[0].lower()=='.ends':inside=False;continue
        if not inside:continue
        key=tokens[0].upper()
        if key in indices:raise ValueError('Duplicate DUT element: '+key)
        indices[key]=index
    if count!=1:raise ValueError('Sizing adapter requires exactly one DUT subcircuit')
    return lines,indices


def validate_space(text,config):
    if config.get('schema_version')!='opamp-sizing/1':raise ValueError('Unknown sizing config version')
    if config.get('objective')!='minimize_worst_case_quiescent_power_mW':raise ValueError('Unsupported objective')
    params=config.get('parameters',[])
    if not params:raise ValueError('Empty search space')
    lines,indices=_line_indices(text);names=set();bindings=set()
    for spec in params:
        if spec['name'] in names:raise ValueError('Duplicate parameter name')
        names.add(spec['name'])
        values=[spec['low'],spec['high'],spec['baseline']]
        if any(isinstance(x,bool) or not isinstance(x,(int,float)) or not math.isfinite(x) for x in values):raise ValueError('Nonfinite parameter range')
        if not 0<spec['low']<spec['high'] or not spec['low']<=spec['baseline']<=spec['high']:raise ValueError('Invalid positive sizing range')
        if not spec['elements'] or len(set(spec['elements']))!=len(spec['elements']):raise ValueError('Empty/duplicate element group')
        for element in spec['elements']:
            element=element.upper();binding=(element,spec['field'].upper())
            if binding in bindings:raise ValueError('Overlapping parameter bindings')
            bindings.add(binding)
            if element not in indices:raise ValueError('Unknown parameter element: '+element)
            line=lines[indices[element]]
            if spec['field']=='value':
                tokens=line.split()
                if element[0] not in 'RC' or len(tokens)!=4:raise ValueError('Only plain resistor/capacitor scalar values are supported')
                actual=number(tokens[3])
            elif spec['field'].upper() in {'W','L'}:
                if not element.startswith('M'):raise ValueError('W/L edits require MOS devices')
                matches=re.findall(r'\b'+re.escape(spec['field'])+r'\s*=\s*([^\s]+)',line,re.I)
                if len(matches)!=1:raise ValueError('Expected one explicit MOS dimension')
                actual=number(matches[0])
            else:raise ValueError('Unsupported sizing field')
            if not math.isclose(actual,spec['baseline'],rel_tol=1e-10,abs_tol=1e-20):raise ValueError('Baseline config differs from DUT: '+element)
    return {spec['name']:spec['baseline'] for spec in params}


def apply_parameters(text,config,values):
    validate_space(text,config)
    if set(values)!={p['name'] for p in config['parameters']}:raise ValueError('Missing or extra candidate parameters')
    lines,indices=_line_indices(text)
    for spec in config['parameters']:
        value=values[spec['name']]
        if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or not spec['low']<=value<=spec['high']:raise ValueError('Candidate outside search bounds')
        for name in spec['elements']:
            i=indices[name.upper()]
            if spec['field']=='value':
                tokens=lines[i].split();tokens[3]=format(value,'.15g');lines[i]=' '.join(tokens)
            else:
                pattern=r'(\b'+re.escape(spec['field'])+r'\s*=\s*)[^\s]+'
                lines[i]=re.sub(pattern,lambda m:m[1]+format(value,'.15g'),lines[i],count=1,flags=re.I)
    return '\n'.join(lines)+'\n'


def physical_score(cases):
    """Feasibility comes from native verdicts, never a substituted missing metric."""
    failed=[];powers=[]
    for case in cases:
        if case['status']!='passed_sampled_model_case':failed.append(case['case_id'])
        if case['kind']=='iq':
            for part in case['parts']:
                value=part['value']
                if not isinstance(value,(int,float)) or isinstance(value,bool) or not math.isfinite(value) or value<=0:
                    raise ValueError('Undefined/nonpositive quiescent current')
                powers.append(value*case['supply_V']*1000)
    if not powers:raise ValueError('No measured quiescent power objective')
    return {'feasible_for_screening':not failed,'failed_screening_case_ids':failed,
            'objective_power_mW':max(powers)}


def normalized_constraints(cases):
    """Signed, dimensionless distance for every measured acceptance rule.

    Positive means violated; zero/negative means satisfied. Missing measurements
    or invalid prerequisites are not substituted with an invented distance.
    """
    constraints={};details=[]
    if not cases:raise ValueError('No measured cases for normalized constraints')
    for case in cases:
        if case['status'] not in {'passed_sampled_model_case','failed_in_model'}:
            raise ValueError('Model/execution/adapter limitations cannot be ranked as measured specification distances')
        if case.get('gate_issues') or any(p.get('gate_issues') for p in case.get('parts',[])):
            raise ValueError('Measurement prerequisites are invalid; no physical violation score assigned')
        tests=case.get('tests',[])
        if not tests:raise ValueError('No acceptance rules for a measured case')
        if (case['status']=='passed_sampled_model_case')!=all(t.get('passed') is True for t in tests):
            raise ValueError('Measured case status disagrees with its acceptance rules')
        for index,test in enumerate(tests):
            value,limit=test.get('value'),test.get('limit')
            if any(isinstance(x,bool) or not isinstance(x,(int,float)) or not math.isfinite(x) for x in (value,limit)):
                raise ValueError('Nonfinite or missing measured value/limit')
            scale=test.get('normalization_scale',abs(limit))
            if isinstance(scale,bool) or not isinstance(scale,(int,float)) or not math.isfinite(scale) or scale<=0:
                raise ValueError('Zero-limit criteria require an explicit positive normalization scale')
            operator=test.get('operator')
            if operator=='>=':distance=(limit-value)/scale
            elif operator=='<=':distance=(value-limit)/scale
            elif operator=='==':distance=abs(value-limit)/scale
            else:raise ValueError('Unsupported acceptance operator for normalized constraints')
            if not math.isfinite(distance):raise ValueError('Constraint distance overflow')
            if (distance<=0)!=test.get('passed'):raise ValueError('Numeric rule and reported verdict disagree')
            key=f"{case['case_id']}:{index}:{test['metric']}:{operator}"
            if key in constraints:raise ValueError('Duplicate measured constraint identifier')
            constraints[key]=distance
            details.append({'id':key,'case_id':case['case_id'],'metric':test['metric'],
                            'operator':operator,'measured':value,'limit':limit,'scale':scale,
                            'signed_normalized_distance':distance,'violation_fraction':max(0,distance)})
    violations=[d['violation_fraction'] for d in details]
    return {'policy':'signed_normalized_per_test_v1','constraints':constraints,'details':details,
            'total_normalized_violation':sum(violations),'worst_normalized_violation':max(violations)}
