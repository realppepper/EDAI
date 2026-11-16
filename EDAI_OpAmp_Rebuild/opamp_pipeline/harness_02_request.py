"""Full-scope request/response contract for current-chat or a future API transport."""
import json,re,hashlib
from pathlib import Path
from .harness_01_fixed import load_harness,system_text,validate_candidate
from .loop_04_extended_policy import ledger
from .support.source_checks import fingerprint
from .support.execution_state import file_hash
from .harness_04_feedback import implemented_scope_case_ids,describe_case,scope_and_task_summary
from .ref_05_research import tool_contract,validate_usage
from . import ref_07_datasheet as datasheet_refs


def compact(value):
    if isinstance(value,dict):return {k:compact(v) for k,v in value.items() if v is not None and k not in {'actual_dut_binding','source_case_conditions'}}
    if isinstance(value,list):return [compact(v) for v in value]
    return value


def fixture_contracts(case):
    contracts=[]
    for part in case.get('parts',[]):
        if part.get('profile'):
            contracts.append({'variant':part.get('direction',part.get('variant')),'profile':part['profile']});continue
        p=part.get('job_path') or part.get('path')
        if p and Path(p).is_file():
            # Stored fixture data, never executable instructions to the designer.
            lines=[s for s in Path(p).read_text(encoding='ascii').splitlines() if s.strip() and not s.startswith('*')
                   and not re.match(r'^\.(include|nodeset|save|options)\b',s,re.I)]
            contracts.append({'variant':part.get('variant'),'read_only_testbench':'\n'.join(lines)})
    # Identical fixture strings are represented once within a case.
    return list({fingerprint(x):x for x in contracts}.values())


def make_request(plan,results,candidate_text,policy_path=None):
    policy,sha=load_harness(*([policy_path] if policy_path else []));validate_candidate(candidate_text)
    cases=ledger(results);goals=[];feedback=[]
    required=set(implemented_scope_case_ids(cases,policy))
    plan_ids={c['case_id'] for row in plan['measurements'] for c in row['cases']}
    if set(cases)!=plan_ids:raise ValueError('Plan and result coverage differ')
    for row in plan['measurements']:
        per_case=[]
        for source in row['cases']:
            recorded=cases[source['case_id']]
            if recorded['target']!=row['target'] or recorded['case']['fixture']!=source['fixture']:raise ValueError('Requirement or fixture changed')
            per_case.append({'case_id':source['case_id'],'fixture':compact(source['fixture']),
                             'required_for_implemented_scope':source['case_id'] in required})
        goals.append({'row_id':row['row_id'],'symbol':row['symbol'],'source_page':row['source']['source']['pdf_page'],
                      'target':row['target'],'method':row['method'],'resolved_conditions':compact(row['resolved_conditions']['values']),'cases':per_case})
    for key,record in cases.items():
        c=record['case'];f={'case_id':key,'symbol':record['symbol'],'status':c['status'],'tests':c.get('tests',[]),
                         'execution_error':c.get('error'),'gate_issues':c.get('gate_issues',[]),'reason':c.get('reason'),
                         'model_limitations':c.get('model_limitations',[]),'component_checks':c.get('component_checks',[])}
        f.update(describe_case(record,key in required))
        # Execution contracts matter even for passed cases: a revision must retain them.
        f['test_contracts']=fixture_contracts(c)
        feedback.append(compact(f))
    scope,tasks=scope_and_task_summary(cases,policy,feedback)
    request={'schema_version':2,'mode':'current_chat_designer','harness_id':policy['id'],'harness_sha256':sha,
             'system_instructions':system_text(policy),'requirements':goals,'feedback':feedback,
             'evaluation_scope':scope,'task_summary':tasks,
             'feedback_interpretation':{
                 'required_means':'A condition of current implemented-scope success, not a timing priority.',
                 'all_plan_cases_remain_tracked':True,
                 'tests_field':'Original reported tests are preserved. Use case_assessment.target_verdict_usable before interpreting them as compliance evidence.',
                 'diagnostic_evidence_is_not_a_confirmed_physical_cause':True},
             'candidate_netlist':candidate_text,'candidate_sha256':hashlib.sha256(candidate_text.encode('ascii')).hexdigest(),
             'coverage':results['case_status_counts'],'full_datasheet_success':False,
             'response_schema':{'request_id':'echo exactly','netlist':'complete ASCII frozen-model DUT',
                                'summary':'brief engineering justification','changes':['proposed changes'],
                                'hypotheses':[{'case_ids':['source case IDs'],'claim':'hypothesis, not established physical cause','probe':'what could test it'}],
                                'tradeoffs':['metrics that may get worse']},
             'external_llm_api_calls':0,'chat_token_usage':None,'harness2_enabled':False}
    request['netlist_hash_encoding']='ASCII, normalized text LF'
    request['optional_literature_research']=tool_contract()
    datasheet_refs.add_catalog(request)
    if results.get('operational_startup'):
        request['operational_startup']=results['operational_startup']
        request['feedback_interpretation']['startup_gate']='Required in addition to implemented datasheet cases. A failed or missing startup is not successful design completion; use measured evidence as a hypothesis, not a proven physical cause.'
    request['measurement_feedback_matches_current_candidate']=any(
        Path(p).suffix=='.inc' and Path(p).is_file() and file_hash(p)==sha and Path(p).read_text(encoding='ascii')==candidate_text
        for p,sha in results['input_signatures'].items())
    history=policy.get('iteration_history')
    if history is not None:
        if not isinstance(history,dict) or not isinstance(history.get('enabled'),bool):raise ValueError('Invalid iteration history policy')
        if history['enabled']:
            limit=history.get('max_transitions',3)
            if isinstance(limit,bool) or not isinstance(limit,int) or not 1<=limit<=10:raise ValueError('Invalid history bound')
            request['schema_version']=3
            request['iteration_history_configuration']={'enabled':True,'max_transitions':limit}
    request['request_id']=fingerprint(request)
    return request


def validate_response(request,response):
    validate_usage(request,response)
    datasheet_refs.validate_usage(request,response)
    if response.get('request_id')!=request['request_id']:raise ValueError('Response belongs to another request')
    if not isinstance(response.get('summary'),str) or not response['summary'].strip():raise ValueError('Engineering summary required')
    if not isinstance(response.get('changes'),list) or not response['changes']:raise ValueError('Changes required')
    allowed={f['case_id'] for f in request['feedback']}
    for h in response.get('hypotheses',[]):
        if not set(h.get('case_ids',[]))<=allowed:raise ValueError('Unknown evidence case ID')
    validate_candidate(response['netlist'])
    return True
