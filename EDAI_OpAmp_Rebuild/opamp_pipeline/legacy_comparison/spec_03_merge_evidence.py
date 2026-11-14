"""Combine semantic candidates and original-cell evidence without silent conflicts."""
from copy import deepcopy
from ..support.source_checks import fingerprint


def merge_evidence(candidate: dict, native: dict, verification: dict) -> dict:
    expected=verification['input_fingerprints']
    if fingerprint(candidate)!=expected['candidate'] or fingerprint(native)!=expected['native']:
        raise ValueError('Verification report is stale for these input JSONs')
    checks={r['candidate_id']:r for r in verification['rows']}
    native_rows={r['id']:r for r in native['rows']}
    result=deepcopy(candidate)
    result['schema_version']='0.2'
    result['authorship']={'mode':'hybrid_candidate_and_original_cell_evidence','semantic_source':candidate.get('authorship'),
                         'cell_source':native.get('authorship'),'external_llm_calls_this_merge':0}
    result['verification_status']='partial_numeric_support_semantic_review_pending'
    result['verification_summary']=deepcopy(verification['summary'])
    result['verification_input_fingerprints']=deepcopy(expected)
    result['ready_for_design']=False
    result.pop('format_checks',None)
    for spec in result['electrical_specs']:
        report=deepcopy(checks[spec['id']])
        source=native_rows.get(report.get('native_row_id'))
        spec['verification']=report
        spec['field_provenance']={'name':'assistant_candidate_pending_semantic_review',
            'conditions':'assistant_candidate_pending_semantic_review',
            'limits':'per_slot_checks_against_original_pdf', 'unit':'unit_check_against_native_cell_text'}
        spec['candidate_limits_before_merge']=deepcopy(spec['limits'])
        if source:
            spec['original_cell_evidence']=deepcopy(source)
        # Adopt a code-derived scalar only when both the original cell and the
        # candidate agree. Conflicting numbers remain explicitly unresolved.
        if report.get('issues') or not source:
            spec['limits']={'min':None,'typ':None,'max':None}
        for slot, check in report.get('limit_checks',{}).items():
            if report.get('issues') or not source:
                continue
            if check['status']=='numeric_match':
                spec['limits'][slot]=check['source_value']
            elif check['status']=='conflict':
                spec['limits'][slot]=None
        spec['review_status']=report['status']
    for key in ('operating_conditions','behavior_constraints'):
        for item in result.get(key,[]):
            item['verification_status']='assistant_only_pending_independent_review'
    result['coverage_review']={'missing_candidate_native_ids':verification['missing_candidate_native_ids'],
        'unmapped_native_rows':[deepcopy(native_rows[k]) for k in verification['missing_candidate_native_ids']],
        'native_table_issues':verification.get('native_table_issues',[]),
        'deferred_information':deepcopy(candidate.get('deferred_information',[])),
        'scope':'Detected electrical table rows only; whole-document requirements coverage is not certified'}
    return result
