"""Final verification on the integrated document; row IDs persist end to end."""
from copy import deepcopy
import hashlib
from pathlib import Path
import pymupdf
from .spec_01_build_rows import native_view
from .support.source_checks import fingerprint, verify_sources
from .support.native_tables import NativeTableExtractor
from .support.content_audit import check_conditions
from .support.semantic_review import build_review_packet, attach_review
from .support.condition_annotations import validate_condition_annotations


def verify_integrated(base: dict, enriched: dict, source_pdf: str, semantic_review=None) -> tuple[dict,dict]:
    if enriched.get('base_document_fingerprint')!=fingerprint(base):raise ValueError('Enriched document/base mismatch')
    base_rows={r['id']:r for r in base['electrical_specs']}
    enriched_rows={r['id']:r for r in enriched['electrical_specs']}
    if len(enriched_rows)!=len(enriched['electrical_specs']) or set(base_rows)!=set(enriched_rows):
        raise ValueError('Canonical rows were added, removed or duplicated')
    for row_id,row in enriched_rows.items():
        original=base_rows[row_id]
        if row['target_product']!=original['target_product'] or row['category']!=original['category']:
            raise ValueError('Locked product/category was changed')
        if row['source']!=original['source'] or row['original_cell_evidence']!=original['original_cell_evidence']:
            raise ValueError('Locked source evidence was changed')
        for slot,cell in original['original_cell_evidence']['limit_cells'].items():
            if cell['status']!='needs_interpretation' and (isinstance(row['limits'][slot],bool) or row['limits'][slot]!=original['limits'][slot]):
                raise ValueError('A locked scalar/blank value was changed')
    source=Path(source_pdf);digest=hashlib.sha256(source.read_bytes()).hexdigest()
    native=native_view(base)
    pages={r['source']['pdf_page'] for r in native['rows']}
    with pymupdf.open(source) as doc:
        words={n:doc[n-1].get_text('words') for n in pages}
        page_texts={n:doc[n-1].get_text() for n in pages}
    # Re-read the PDF rather than trusting only the saved list. This shares the
    # original detector, so common-mode detection errors remain possible.
    fresh=NativeTableExtractor(str(source),base['target_product']).extract({
        'source_sha256':digest,'pages':[{'pdf_page':n,'roles':['target_specs']} for n in sorted(pages)]})
    fresh_ids={r['id'] for r in fresh['rows']}
    saved_ids={r['source']['native_row_id'] for r in base_rows.values()}
    report=verify_sources(enriched,native,words,digest)
    report['stage']='spec_03_verify_integrated_document'
    report['source_row_coverage']={
        'missing_from_document':sorted(fresh_ids-saved_ids),
        'not_found_on_reread':sorted(saved_ids-fresh_ids),
        'excluded_other_product_rows':fresh['excluded_rows'],
        'table_issues':fresh['table_issues'],
        'scope_pages':sorted(pages),'whole_document_complete':False,
        'limitations':'Fresh original PDF read using the same detector; not independent proof of all rows or non-table requirements.'}
    report['summary']['unannotated_rows']=len(enriched.get('unannotated_row_ids',[]))
    report['summary']['open_correction_proposals']=sum(len(r.get('correction_proposals',[])) for r in enriched_rows.values())
    for checked in report['rows']:
        row=enriched_rows[checked['candidate_id']]
        inherited=row.get('conditions',{}).get('inherits')
        if inherited and inherited not in enriched.get('condition_sets',{}):
            checked['issues'].append('Condition inheritance refers to a missing condition set')
            checked['status']='conflict'
        checked['condition_reference_check']='resolved' if not inherited or inherited in enriched.get('condition_sets',{}) else 'missing'
        checked['open_correction_proposals']=deepcopy(row.get('correction_proposals',[]))
        checked['condition_audit']=check_conditions(row,enriched.get('condition_sets',{}),page_texts[row['source']['pdf_page']],
            footnote_context='\n'.join(page_texts[n] for n in sorted(page_texts)))
        interpretation_issues=validate_condition_annotations(row.get('conditions',{}),enriched.get('condition_sets',{}))
        checked['condition_interpretation_check']={'issues':interpretation_issues,
            'status':'conflict' if interpretation_issues else 'annotation_references_consistent',
            'effective_conditions_generated':False}
        if interpretation_issues:
            checked['issues'].extend(interpretation_issues)
            checked['status']='conflict'
        if checked['condition_audit']['status']=='conflict':
            checked['issues'].append('Explicit source condition differs from the JSON; see condition_audit')
            checked['status']='conflict'
    report['summary']['conflict_rows']=sum(r['status']=='conflict' for r in report['rows'])
    report['summary']['source_rows_missing_from_document']=len(fresh_ids-saved_ids)
    report['summary']['condition_conflict_rows']=sum(r['condition_audit']['status']=='conflict' for r in report['rows'])
    report['summary']['condition_fields_explicitly_supported']=sum(f['status']=='explicit_quantity_supported' for r in report['rows'] for f in r['condition_audit']['fields'])
    report['summary']['condition_fields_pending_review']=sum(f['status']=='review_required' for r in report['rows'] for f in r['condition_audit']['fields'])
    attach_review(report,build_review_packet(enriched,source_pdf),semantic_review)
    result=deepcopy(enriched)
    result['stage']='spec_03_verified_document'
    result['verification_summary']=deepcopy(report['summary'])
    checks={r['candidate_id']:r for r in report['rows']}
    for row in result['electrical_specs']:
        row['verification']=deepcopy(checks[row['id']])
        row['ready_for_design']=False
    for key in ('operating_conditions','behavior_constraints'):
        for item in result.get(key,[]):item['verification_status']='assistant_only_pending_independent_review'
    result['ready_for_design']=False
    result['verification_status']='code_and_llm_review_completed_with_open_items' if semantic_review is not None else 'partial_numeric_support_semantic_and_coverage_review_pending'
    return result,report
