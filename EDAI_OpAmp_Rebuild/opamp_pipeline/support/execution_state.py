"""Publish completed generations; a file's existence alone is never readiness."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import uuid
from ..pdf_03_render_pages import save_json
from .source_checks import fingerprint


def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class PipelineExecution:
    def __init__(self, output_dir, inputs=()):
        self.output=Path(output_dir);self.inputs=[Path(p).resolve() for p in inputs if p is not None]
        self.state={'run_id':uuid.uuid4().hex,'stage':'started','completed':False,'ready_for_design':False}

    def __enter__(self):
        self.update()
        try:
            self.state['inputs']=[{'path':str(p),'sha256':file_hash(p)} for p in self.inputs]
            self.update()
        except Exception:
            self.update(stage='failed',completed=False)
            raise
        return self

    def update(self, **values):
        self.state.update(values);save_json(self.output/'STATUS.json',self.state)

    def provenance(self):
        return {'run_id':self.state['run_id'],'inputs':deepcopy(self.state.get('inputs',[]))}

    def track_input(self,path):
        path=Path(path).resolve()
        if str(path) not in {item['path'] for item in self.state.get('inputs',[])}:
            self.inputs.append(path)
            self.state.setdefault('inputs',[]).append({'path':str(path),'sha256':file_hash(path)})
            self.update()

    def complete(self, final_path, **values):
        for source in self.state.get('inputs',[]):
            if file_hash(source['path'])!=source['sha256']:
                raise ValueError('Pipeline input changed during execution')
        document=json.loads(Path(final_path).read_text(encoding='utf-8'))
        provenance=document.get('_graph_execution',document.get('_execution',{}))
        if provenance.get('run_id')!=self.state['run_id']:
            raise ValueError('Final artifact belongs to another execution')
        self.update(completed=True,final_path=str(Path(final_path).resolve()),
                    final_document_fingerprint=fingerprint(document),**values)

    def __exit__(self, kind, value, traceback):
        if kind is not None:self.update(stage='failed',completed=False,error_type=kind.__name__)
        return False


def spec_core(document):
    core=deepcopy(document)
    for field in ('characteristic_graphs','graph_reference_summary','evaluation_scope',
                  'linked_spec_document_fingerprint','_graph_execution'):
        core.pop(field,None)
    for row in core.get('electrical_specs',[]):
        for field in ('related_graph_ids','evaluation_temperature_scope'):row.pop(field,None)
    return core


def require_current_spec(run_dir, requested_path):
    out=Path(run_dir)/'spec_pipeline'
    status=json.loads((out/'STATUS.json').read_text(encoding='utf-8'))
    if status.get('completed') is not True or not status.get('run_id'):
        raise ValueError('Specification generation is not complete; old final files cannot be consumed')
    canonical_path=out/'spec_03_result.json'
    canonical=json.loads(canonical_path.read_text(encoding='utf-8'))
    if canonical.get('_execution',{}).get('run_id')!=status['run_id']:
        raise ValueError('Specification result belongs to an old generation')
    if fingerprint(canonical)!=status.get('final_document_fingerprint'):
        raise ValueError('Specification final content differs from completed generation')
    for name,key in [('spec_01_rows.json','base_fingerprint'),('spec_02_enriched_rows.json','enriched_document_fingerprint')]:
        content=json.loads((out/name).read_text(encoding='utf-8'))
        if fingerprint(content)!=status.get(key):raise ValueError('Specification intermediate input is stale')
    for item in status.get('inputs',[]):
        if file_hash(item['path'])!=item['sha256']:raise ValueError('Specification source input changed after completion')
    requested=json.loads(Path(requested_path).read_text(encoding='utf-8'))
    if fingerprint(spec_core(requested))!=fingerprint(canonical):
        raise ValueError('Requested specification is not the current completed result')
    return requested


def require_current_references(run_dir):
    out=Path(run_dir)/'chart_pipeline'
    path=out/'spec_with_chart_references.json'
    document=require_current_spec(run_dir,path)
    status=json.loads((out/'STATUS.json').read_text(encoding='utf-8'))
    if status.get('completed') is not True or status.get('linked_spec_complete') is not True:
        raise ValueError('Graph reference generation is not complete')
    if document.get('_graph_execution',{}).get('run_id')!=status.get('run_id'):
        raise ValueError('Graph references belong to an old generation')
    if fingerprint(document)!=status.get('final_document_fingerprint'):
        raise ValueError('Graph reference content differs from completed generation')
    if document.get('linked_spec_document_fingerprint')!=fingerprint(spec_core(document)):
        raise ValueError('Graph references are linked to an old specification')
    for item in status.get('inputs',[]):
        if file_hash(item['path'])!=item['sha256']:raise ValueError('Graph input changed after completion')
    return document


def require_current_hkg(run_dir):
    out=Path(run_dir)/'hkg_pipeline'
    status=json.loads((out/'STATUS.json').read_text(encoding='utf-8'))
    document=json.loads((out/'hkg_01_graph.json').read_text(encoding='utf-8'))
    if status.get('completed') is not True or document.get('_execution',{}).get('run_id')!=status.get('run_id'):
        raise ValueError('HKG is incomplete or belongs to an old generation')
    if fingerprint(document)!=status.get('final_document_fingerprint'):
        raise ValueError('HKG differs from its completed generation')
    for item in status.get('inputs',[]):
        if file_hash(item['path'])!=item['sha256']:raise ValueError('HKG input changed after completion')
    spec=require_current_spec(run_dir,Path(run_dir)/'spec_pipeline/spec_03_result.json')
    if document.get('input_document_fingerprint')!=fingerprint(spec):
        source=require_current_references(run_dir)
        if document.get('input_document_fingerprint')!=fingerprint(source):raise ValueError('HKG source document is stale')
    return document


def require_current_pdg(run_dir):
    out=Path(run_dir)/'pdg_pipeline'
    status=json.loads((out/'STATUS.json').read_text(encoding='utf-8'))
    document=json.loads((out/'pdg_01_graph.json').read_text(encoding='utf-8'))
    if status.get('completed') is not True or document.get('_execution',{}).get('run_id')!=status.get('run_id'):
        raise ValueError('PDG is incomplete or belongs to an old generation')
    if fingerprint(document)!=status.get('final_document_fingerprint'):raise ValueError('PDG content changed after completion')
    for item in status.get('inputs',[]):
        if file_hash(item['path'])!=item['sha256']:raise ValueError('PDG input changed after completion')
    hkg=require_current_hkg(run_dir)
    if document.get('input_hkg_fingerprint')!=fingerprint(hkg):raise ValueError('PDG references an old HKG')
    return document
