"""Create one canonical row set from original-PDF evidence, before AI enrichment."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
from .support.native_tables import NativeTableExtractor
from .support.source_checks import fingerprint


def stable_row_id(source_hash: str, source: dict) -> str:
    identity=[source_hash,source['pdf_page'],[round(x,3) for x in source['row_bbox_points']]]
    digest=hashlib.sha256(json.dumps(identity,separators=(',',':')).encode()).hexdigest()
    return 'ROW-'+digest[:20]


def native_view(document: dict) -> dict:
    """A view of locked evidence inside the same rows, not a second extraction."""
    return {'source_sha256':document['source_sha256'],'target_product':document['target_product'],
            'rows':[deepcopy(r['original_cell_evidence']) for r in document['electrical_specs']],
            'excluded_rows':deepcopy(document['coverage']['excluded_rows']),
            'table_issues':deepcopy(document['coverage']['table_issues'])}


def build_rows(run_dir: str) -> dict:
    root=Path(run_dir)
    read=lambda name:json.loads((root/name).read_text(encoding='utf-8'))
    inventory=read('01_pdf_inventory.json');plan=read('02_page_plan.json');checks=read('05_layout_checks.json')
    if len({inventory['sha256'],plan['source_sha256'],checks['source_sha256']})!=1:
        raise ValueError('Inventory, plan and layout checks refer to different PDFs')
    selected=[p for p in plan['pages'] if set(p['roles']) & {'target_specs','specs_product_scope_review'}]
    if not selected:raise ValueError('No electrical specification page candidates')
    if set(checks['blocked_pages']) & {p['pdf_page'] for p in selected}:
        raise ValueError('Resolve blocked electrical-page parsing first')
    native=NativeTableExtractor(inventory['source_pdf'],plan['target_product']).extract(
        {'source_sha256':inventory['sha256'],'pages':selected})
    rows=[]
    for evidence in native['rows']:
        source=deepcopy(evidence['source'])
        source['native_row_id']=evidence['id']
        source['value_row_y_points']=(source['row_bbox_points'][1]+source['row_bbox_points'][3])/2
        row={'id':stable_row_id(inventory['sha256'],source),'symbol':None,'name':None,
             'category':'electrical_characteristic','target_product':plan['target_product'],
             'limits':deepcopy(evidence['limits']),'unit':evidence['raw_unit'],
             'printed_notation':{slot:cell['raw'] for slot,cell in evidence['limit_cells'].items() if cell['raw'].startswith('±')},
             'conditions':{},'source':source,'original_cell_evidence':deepcopy(evidence),
             'semantic_status':'awaiting_enrichment','correction_proposals':[],
             'field_provenance':{'limits':'original_pdf_code','source':'original_pdf_code','unit':'original_pdf_raw_text'}}
        rows.append(row)
    if not rows or len({r['id'] for r in rows})!=len(rows):raise ValueError('Empty or duplicate canonical rows')
    return {'schema_version':'1.0','pipeline':'code_rows_then_semantic_enrichment_then_verification',
            'source_sha256':inventory['sha256'],'source_filename':Path(inventory['source_pdf']).name,
            'target_product':plan['target_product'],'electrical_specs':rows,'ready_for_design':False,
            'stage':'spec_01_build_rows','coverage':{'electrical_pages':[p['pdf_page'] for p in selected],
                'excluded_rows':native['excluded_rows'],'table_issues':native['table_issues'],
                'whole_document_requirements_complete':False},
            'limitations':['Scalar/blank limits and original evidence are locked. Semantic interpretation is pending.']}


def build_enrichment_packet(document: dict, run_dir: str) -> dict:
    root=Path(run_dir)
    plan=json.loads((root/'02_page_plan.json').read_text(encoding='utf-8'))
    context_roles={'operating_and_safety_conditions','behavior_and_structure_reference'}
    page_numbers=set(document['coverage']['electrical_pages']) | {p['pdf_page'] for p in plan['pages'] if set(p['roles']) & context_roles}
    pages={}
    for number in sorted(page_numbers):
        path=root/'pages'/f'page_{number:04d}.json'
        if path.exists():
            data=json.loads(path.read_text(encoding='utf-8'))
            pages[str(number)]={'text':data.get('document_text',''),'parse_status':data['status']}
    return {'source_document_fingerprint':fingerprint(document),'source_sha256':document['source_sha256'],
            'target_product':document['target_product'],
            'instructions':'Return annotations by existing row_id only. Do not change scalar/blank limits or source. Propose corrections separately. Interpret unresolved cells and condition inheritance with provenance.',
            'rows':[{'row_id':r['id'],'pdf_page':r['source']['pdf_page'],
                     'parameter_and_condition_cells':[{"text":c['text']} for c in r['original_cell_evidence']['raw_parameter_and_conditions']],
                     'limit_cells':{k:{'raw':c['raw'],'code_value':c['value'],'status':c['status']} for k,c in r['original_cell_evidence']['limit_cells'].items()},
                     'raw_unit':r['original_cell_evidence']['raw_unit']} for r in document['electrical_specs']],
            'shared_page_context':pages,
            'scope':'Context shared once per page; full-document word coordinates are not transmitted'}
