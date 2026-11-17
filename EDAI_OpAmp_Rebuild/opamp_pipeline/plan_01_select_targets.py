"""Select project targets without changing source data or temperature claims."""
from copy import deepcopy
from .hkg_query import specification_contexts
from .pdg_04_schedule import pdg_signature
from .support.source_checks import fingerprint


def source_specs(hkg):
    rows=[]
    for context in specification_contexts(hkg):
        row=deepcopy(context['specification']);links=context['linked_context']
        row['limits']={n['data']['slot']:deepcopy(n['data']['value']) for n in links['has_limit']}
        row['conditions']=deepcopy(links['has_condition_interpretation'][0]['data']['source_conditions'])
        row['verification']=deepcopy(links['has_verification'][0]['data'])
        row['hkg_node_id']='spec:'+row['id'];rows.append(row)
    return rows


def select_targets(hkg,pdg,policy):
    if policy.get('input_hkg_fingerprint')!=fingerprint(hkg) or policy.get('input_pdg_signature')!=pdg_signature(pdg):
        raise ValueError('Project target policy is stale')
    if policy.get('evaluation_temperature_C')!=25:raise ValueError('Current project scope is 25 C')
    rows=source_specs(hkg);known={r['id']:r for r in rows}
    decisions=policy.get('row_decisions',[]);mapping={d['row_id']:d for d in decisions}
    if len(mapping)!=len(decisions) or set(mapping)!=set(known):raise ValueError('Every source row needs exactly one explicit scope decision')
    selected={key for key,d in mapping.items() if d.get('action')=='include'}
    result=[]
    for row in rows:
        decision=mapping[row['id']]
        if decision.get('action') not in {'include','defer_temperature_coefficient','not_separate_temperature_variant',
                'defer_product_scope','defer_unimplemented_source','defer_source_ambiguity'} or not decision.get('reason'):
            raise ValueError('Invalid source-row scope decision')
        if decision['action'] in {'defer_product_scope','defer_unimplemented_source','defer_source_ambiguity'}:
            if not decision.get('source_evidence'):
                raise ValueError('Deferred source row needs explicit source evidence and remains unverified')
        if decision['action']=='not_separate_temperature_variant':
            primary=decision.get('primary_25c_row_id')
            if primary not in selected or known[primary]['symbol']!=row['symbol']:
                raise ValueError('Temperature variant must reference an included row of the same quantity')
        conditions=row['conditions'];common=next((n['data'] for n in hkg['nodes'] if n['type']=='ConditionSet' and n['label']==conditions.get('inherits')), {})
        temp=conditions.get('overrides',{}).get('ambient_temperature_C',common.get('ambient_temperature_C'))
        if decision['action']=='include':
            if isinstance(temp,dict):
                if not temp.get('min',float('inf'))<=25<=temp.get('max',float('-inf')):raise ValueError('Source range does not include evaluation temperature')
                if row['limits'].get('min') is None and row['limits'].get('max') is None:
                    raise ValueError('Range-only TYP cannot silently become a 25 C point target')
            elif temp!=25:raise ValueError('Unknown source temperature requires review')
        result.append({'row_id':row['id'],'source':row,'decision':deepcopy(decision),
            'required_in_project':decision['action']=='include','source_temperature_condition_C':deepcopy(temp),
            'evaluation_temperature_C':25,'source_temperature_rewritten':False,
            'temperature_variant_reference_is_not_full_range_compliance_proof':True})
    return {'stage':'plan_01_target_selection','input_hkg_fingerprint':fingerprint(hkg),
        'input_pdg_signature':pdg_signature(pdg),'target_product':hkg['target_product'],
        'items':result,'summary':{'source_rows':len(rows),'included':len(selected),
            'temperature_coefficients_deferred':sum(d['action']=='defer_temperature_coefficient' for d in decisions),
            'temperature_variants_not_separately_scheduled':sum(d['action']=='not_separate_temperature_variant' for d in decisions)},
        'explicit_source_deferrals':[deepcopy(d) for d in decisions if d['action'] in {
                'defer_product_scope','defer_unimplemented_source','defer_source_ambiguity'}],
        'origin':'explicit_project_engineering_policy','all_source_rows_retained':True}
