"""Compare the full source-case ledger without erasing unknowns or regressions."""
import math

PASS='passed_sampled_model_case'


def ledger(document):
    cases={}
    for row_id,row in document['rows'].items():
        for case in row['cases']:
            key=case['case_id']
            if key in cases:raise ValueError('Duplicate source case')
            cases[key]={'row_id':row_id,'symbol':row['symbol'],'kind':row['kind'],'target':row['target'],'case':case}
    if len(cases)!=document['source_cases_required']:raise ValueError('Incomplete source-case coverage')
    return cases


def compare_extended(baseline,candidate,priority_case_ids=None):
    old=ledger(baseline);new=ledger(candidate)
    if set(old)!=set(new):raise ValueError('A source case disappeared or was added without a new policy')
    if baseline.get('source_rows_required')!=candidate.get('source_rows_required'):raise ValueError('Source row count changed')
    selected=set(priority_case_ids) if priority_case_ids is not None else None
    if selected is not None and len(selected)!=len(priority_case_ids):raise ValueError('Duplicate priority case identifiers')
    if selected is not None and (not selected or not selected<=set(old)):raise ValueError('Priority case identifiers outside source ledger')
    priorities=[];regressions=[];improvements=[];numeric_changes=[];unknown=[]
    for key,before in old.items():
        after=new[key]
        if before['row_id']!=after['row_id'] or before['target']!=after['target'] or before['case']['fixture']!=after['case']['fixture']:
            raise ValueError('Source requirement or fixture changed')
        a,b=before['case'],after['case']
        if a['status'].startswith('unverified') and b['status']==PASS:
            raise ValueError('Unverified case needs a separate model/adapter qualification before promotion')
        if b.get('tests') and a.get('tests'):
            definitions=lambda tests:[{k:v for k,v in t.items() if k not in {'value','passed'}} for t in tests]
            if definitions(a['tests'])!=definitions(b['tests']):raise ValueError('Case-level acceptance rules changed')
        record={'case_id':key,'row_id':before['row_id'],'symbol':before['symbol'],'supply_V':a['supply_V'],
                'before_status':a['status'],'after_status':b['status']}
        if a['status']==PASS and b['status']!=PASS:regressions.append(record)
        if a['status']!=PASS and b['status']==PASS:improvements.append(record)
        if b['status'].startswith('unverified'):unknown.append(record)
        priority=(key in selected) if selected is not None else (before['kind']=='psrr' or before['kind']=='iq' and a['supply_V']==36)
        if priority:
            priorities.append({**record,'passed':b['status']==PASS,'before_tests':a.get('tests',[]),'after_tests':b.get('tests',[])})
        for i,(left,right) in enumerate(zip(a.get('parts',[]),b.get('parts',[]))):
            v0,v1=left.get('value'),right.get('value')
            if all(isinstance(v,(int,float)) and not isinstance(v,bool) and math.isfinite(v) for v in (v0,v1)):
                numeric_changes.append({**record,'part_index':i,'variant':right.get('variant'),'before':v0,'after':v1})
    if len(priorities)!=(len(selected) if selected is not None else 4):raise ValueError('Priority coverage mismatch')
    achieved=all(p['passed'] for p in priorities)
    return {'priority_goals_passed':achieved,'priority_checks':priorities,'new_regressions':regressions,
        'newly_passing_cases':improvements,'numeric_changes':numeric_changes,'unverified_cases':unknown,
        'adoptable_without_losing_previous_passes':achieved and not regressions,
        'whole_datasheet_success':False,'all_source_cases_preserved':True,
        'summary':{'source_cases':len(old),'priority_passed':sum(p['passed'] for p in priorities),
                   'new_regressions':len(regressions),'newly_passing':len(improvements),'unverified':len(unknown)}}
