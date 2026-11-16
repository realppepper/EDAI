"""Observed adjacent-candidate history; never infer physical causes or edit rules."""
import difflib,json,math
from copy import deepcopy
from pathlib import Path
from .harness_01_fixed import validate_candidate
from .harness_04_feedback import describe_case
from .loop_04_extended_policy import ledger
from .support.execution_state import file_hash


def _verified_json(path,expected):
    if not expected or file_hash(path)!=expected:
        raise ValueError('History artifact hash missing or changed: '+str(path))
    return json.loads(Path(path).read_text(encoding='utf-8'))


def _snapshot(record):
    path=Path(record['candidate_path'])
    if file_hash(path)!=record.get('candidate_sha256'):
        raise ValueError('History candidate changed')
    text=path.read_text(encoding='ascii');validate_candidate(text)
    result=None;cases=None
    if record.get('ledger_path'):
        result=_verified_json(record['ledger_path'],record.get('ledger_sha256'))
        bound=any(Path(p).suffix.lower()=='.inc' and sha==record['candidate_sha256']
                  and Path(p).is_file() and file_hash(p)==sha
                  for p,sha in result.get('input_signatures',{}).items())
        if not bound:raise ValueError('History measurements are not bound to their candidate')
        cases=ledger(result)
    declared=[]
    if record.get('response_path'):
        response=_verified_json(record['response_path'],record.get('response_sha256'))
        declared_netlist=response.get('netlist')
        if not isinstance(declared_netlist,str) or declared_netlist.replace('\r\n','\n').replace('\r','\n')!=text:
            raise ValueError('History response and candidate differ')
        declared=deepcopy(response.get('changes',[]))
    return {'record':record,'text':text,'cases':cases,'declared_changes':declared}


def _public(snapshot):
    record=snapshot['record']
    return {'candidate_index':record['index'],'candidate_path':record['candidate_path'],
            'candidate_sha256':record['candidate_sha256'],
            'ledger_path':record.get('ledger_path'),'ledger_sha256':record.get('ledger_sha256'),
            'measurement_completed':snapshot['cases'] is not None,
            'execution_error':record.get('execution_error')}


def _number(value):
    return isinstance(value,(int,float)) and not isinstance(value,bool) and math.isfinite(value)


def _case_changes(before,after,required):
    if set(before)!=set(after):raise ValueError('History case coverage changed')
    changes=[];regressions=[];new_passes=[]
    for key,left in before.items():
        right=after[key]
        if (left['row_id']!=right['row_id'] or left['kind']!=right['kind'] or left['symbol']!=right['symbol']
                or left['target']!=right['target'] or left['case']['fixture']!=right['case']['fixture']):
            raise ValueError('History targets or fixtures changed')
        a,b=left['case'],right['case']
        va=describe_case(left,key in required)['case_assessment']
        vb=describe_case(right,key in required)['case_assessment']
        comparable=va['target_verdict_usable'] and vb['target_verdict_usable']
        layout_changed=False
        numeric=[]
        if comparable:
            ta,tb=a.get('tests',[]),b.get('tests',[])
            definition=lambda tests:[{k:v for k,v in t.items() if k not in {'value','passed'}} for t in tests]
            da,db=definition(ta),definition(tb)
            if da!=db:
                # Complete DC coverage can be reported as two center-out parts
                # or one ascending sweep. Do not zip or invent aggregate deltas.
                layout_changed=(len(da)!=len(db) and bool(da) and bool(db)
                                and all(d in db for d in da) and all(d in da for d in db))
                if not layout_changed:raise ValueError('History measurement definitions changed')
                comparable=False
            for index,(x,y) in enumerate(zip(ta,tb) if comparable else []):
                if x.get('value')==y.get('value'):continue
                item={'test_index':index,'metric':y.get('metric'),'variant':y.get('variant'),
                      'operator':y.get('operator'),'limit':y.get('limit'),'unit':y.get('unit'),
                      'before_value':x.get('value'),'after_value':y.get('value')}
                if _number(x.get('value')) and _number(y.get('value')):
                    delta=y['value']-x['value']
                    if not math.isfinite(delta):raise ValueError('Nonfinite history delta')
                    item['after_minus_before']=delta
                numeric.append(item)
        status_changed=a['status']!=b['status']
        if a['status']=='passed_sampled_model_case' and b['status']!='passed_sampled_model_case':regressions.append(key)
        if a['status']!='passed_sampled_model_case' and b['status']=='passed_sampled_model_case':new_passes.append(key)
        if status_changed or numeric or layout_changed:
            changes.append({'case_id':key,'symbol':right['symbol'],
                'before_status':a['status'],'after_status':b['status'],
                'before_category':va['category'],'after_category':vb['category'],
                'numeric_comparison_valid':comparable,
                'measurement_layout_changed':layout_changed,
                'comparison_note':('Equivalent metric definitions have different part counts; status retained, no numeric delta inferred.' if layout_changed
                                   else 'Same case, target and fixture; observation only.' if comparable
                                   else 'Measurement prerequisite/execution/model limitation: no numeric improvement inferred.'),
                'test_changes':numeric})
    return changes,regressions,new_passes


def build_iteration_history(records,required_case_ids,max_transitions=3):
    if isinstance(max_transitions,bool) or not isinstance(max_transitions,int) or not 1<=max_transitions<=10:
        raise ValueError('History bound must be an integer from1 to10')
    if not records:raise ValueError('History requires the current candidate')
    indexes=[r['index'] for r in records]
    if any(b<=a for a,b in zip(indexes,indexes[1:])):raise ValueError('History candidate order changed')
    selected=records[-(max_transitions+1):]
    snapshots=[_snapshot(record) for record in selected]
    required=set(required_case_ids)
    for snapshot in snapshots:
        if snapshot['cases'] is not None and not required<=set(snapshot['cases']):
            raise ValueError('History required cases missing')
    transitions=[]
    for before,after in zip(snapshots,snapshots[1:]):
        diff='\n'.join(difflib.unified_diff(before['text'].splitlines(),after['text'].splitlines(),
                     fromfile=f"candidate_{before['record']['index']}",tofile=f"candidate_{after['record']['index']}",lineterm=''))
        comparable=before['cases'] is not None and after['cases'] is not None
        changes,regressions,passes=_case_changes(before['cases'],after['cases'],required) if comparable else ([],[],[])
        transitions.append({'before':_public(before),'after':_public(after),
            'actual_netlist_diff':diff[:16000],'diff_truncated':len(diff)>16000,
            'full_diff_available_from_candidate_paths':True,
            'llm_declared_changes_unverified':after['declared_changes'],
            'both_candidate_measurements_completed':comparable,
            'case_changes':changes,'previously_passed_now_not_passed_case_ids':regressions,
            'newly_passed_case_ids':passes,'physical_causes_confirmed':False})
    return {'schema_version':1,'source':'current_session_candidates_only',
        'interpretation':'Observed joint changes are not physical causal proof. Invalid measurements are not improvement evidence. No external successful design or automatic rule changes are added.',
        'total_session_candidates':len(records),'included_candidate_count':len(selected),
        'older_candidates_omitted':len(records)-len(selected),'max_transitions':max_transitions,
        'current_candidate_index':records[-1]['index'],'current_candidate_sha256':records[-1]['candidate_sha256'],
        'transitions':transitions}
