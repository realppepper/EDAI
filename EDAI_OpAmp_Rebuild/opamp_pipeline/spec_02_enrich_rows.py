"""Apply semantic-only AI annotations to the SAME immutable-source row set."""
from copy import deepcopy
import json
from pathlib import Path
from typing import Protocol
from .support.source_checks import fingerprint


class SemanticEnricher(Protocol):
    def annotate(self, packet: dict) -> dict: ...


class ManualAnnotations:
    """Current chat-assistant annotations. An API implementation can replace this."""
    def __init__(self,path: str):self.path=Path(path)
    def annotate(self,packet: dict) -> dict:
        return json.loads(self.path.read_text(encoding='utf-8'))


def apply_enrichment(document: dict, annotations: dict) -> dict:
    if annotations.get('source_document_fingerprint')!=fingerprint(document):
        raise ValueError('Annotations are stale for this row set')
    patches=annotations.get('row_annotations',[])
    if not isinstance(patches,list):raise ValueError('row_annotations must be a list')
    if len({p['row_id'] for p in patches})!=len(patches):raise ValueError('Duplicate row annotations')
    row_ids={r['id'] for r in document['electrical_specs']}
    if {p['row_id'] for p in patches}-row_ids:raise ValueError('Unknown row_id in annotations')
    result=deepcopy(document);rows={r['id']:r for r in result['electrical_specs']}
    allowed={'symbol','name','unit','conditions','printed_notation','notes'}
    for patch in patches:
        if set(patch)-{'row_id','fields','interpreted_limits','proposed_corrections'}:
            raise ValueError('Unexpected annotation keys')
        row=rows[patch['row_id']]
        fields=patch.get('fields',{})
        if not isinstance(fields,dict):raise ValueError('Annotation fields must be an object')
        if set(fields)-allowed:raise ValueError('AI attempted to edit locked/unknown fields')
        for key in ('symbol','name','unit'):
            if key in fields and not isinstance(fields[key],str):raise ValueError(f'{key} must be text')
        for key in ('conditions','printed_notation'):
            if key in fields and not isinstance(fields[key],dict):raise ValueError(f'{key} must be an object')
        if not isinstance(patch.get('interpreted_limits',{}),dict):raise ValueError('interpreted_limits must be an object')
        if not isinstance(patch.get('proposed_corrections',[]),list):raise ValueError('proposed_corrections must be a list')
        for key,value in fields.items():
            row[key]=deepcopy(value)
            row['field_provenance'][key]='assistant_semantic_candidate_pending_verification'
        for slot,value in patch.get('interpreted_limits',{}).items():
            if slot not in ('min','typ','max') or row['original_cell_evidence']['limit_cells'][slot]['status']!='needs_interpretation':
                raise ValueError('Scalar/blank code limits cannot be overwritten')
            if not isinstance(value,(dict,str)):raise ValueError('Keep expression/composite form; do not invent a scalar')
            row['limits'][slot]=deepcopy(value)
            row['field_provenance']['limits.'+slot]='assistant_interpretation_pending_verification'
        row['correction_proposals']=deepcopy(patch.get('proposed_corrections',[]))
        row['semantic_status']='enriched_pending_verification'
    metadata=annotations.get('document_annotations',{})
    if not isinstance(metadata,dict):raise ValueError('document_annotations must be an object')
    allowed_meta={'condition_sets','operating_conditions','behavior_constraints','deferred_information','policy_notes'}
    if set(metadata)-allowed_meta:raise ValueError('Unexpected document annotations')
    if 'condition_sets' in metadata and not isinstance(metadata['condition_sets'],dict):raise ValueError('condition_sets must be an object')
    for key,value in metadata.items():result[key]=deepcopy(value)
    result['stage']='spec_02_enrich_rows'
    result['base_document_fingerprint']=fingerprint(document)
    result['enrichment_provenance']=deepcopy(annotations.get('authorship',{}))
    result['unannotated_row_ids']=sorted(row_ids-{p['row_id'] for p in patches})
    return result
