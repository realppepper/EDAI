"""Build a source-reviewed port dependency graph, never a fabricated schedule."""
from copy import deepcopy
import hashlib
from pathlib import Path
import pymupdf
from .support.source_checks import fingerprint
from .support.semantic_review import quote_key


RELATIONS={'contributes_to_supply','powers_channel','produces_output','signal_dependency','validity_dependency'}
NODE_TYPES={'Port','Channel','SupplyState','ValidityConstraint'}


def build_pdg_packet(hkg,source_pdf,page_plan):
    if hashlib.sha256(Path(source_pdf).read_bytes()).hexdigest()!=hkg['source_sha256']:
        raise ValueError('PDG source PDF changed')
    if page_plan['source_sha256']!=hkg['source_sha256']:raise ValueError('PDG page plan/source mismatch')
    roles={'pin_interface','behavior_and_structure_reference','operating_and_safety_conditions',
           'application_reference','measurement_definitions'}
    selected=[p['pdf_page'] for p in page_plan['pages'] if roles & set(p['roles'])]
    with pymupdf.open(source_pdf) as pdf:
        pages={str(n):{'text':pdf[n-1].get_text()} for n in selected}
    return {'source_sha256':hkg['source_sha256'],'target_product':hkg['target_product'],
        'hkg_fingerprint':fingerprint(hkg),'source_pages':pages,
        'hkg_reference_index':[{'id':n['id'],'type':n['type'],'label':n['label']} for n in hkg['nodes']],
        'instructions':'Return logical ports, channels and source-grounded functional/validity dependencies. Cite source page and exact text. Distinguish explicitly stated facts from engineering interpretation. Preserve package columns as references, not a selected package for a new IC. Do not invent controls, port order or numerical startup delay. A device allowing inputs before supply must not acquire a mandatory supply-before-input edge. Any future test schedule is a separate engineering policy.'}


def validate_annotations(packet,annotations):
    if annotations.get('packet_fingerprint')!=fingerprint(packet):raise ValueError('PDG annotations are stale')
    if not annotations.get('reviewer',{}).get('method'):raise ValueError('PDG reviewer provenance missing')
    nodes=annotations.get('nodes',[]);known={n['key']:n for n in nodes}
    if not nodes or len(known)!=len(nodes):raise ValueError('Empty or duplicate PDG nodes')
    hkg_ids={n['id'] for n in packet['hkg_reference_index']}
    def evidence(item):
        cites=item.get('evidence',[])
        if not cites:raise ValueError('PDG source evidence required')
        for cite in cites:
            page=packet['source_pages'].get(str(cite.get('pdf_page')));quote=cite.get('quote','')
            if not isinstance(quote,str) or not page or len(quote_key(quote))<5 or quote_key(quote) not in quote_key(page['text']):
                raise ValueError('PDG quote is absent from the original source')
    profiles=annotations.get('package_profiles',{})
    for node in nodes:
        if node['type'] not in NODE_TYPES:raise ValueError('Unsupported PDG node type')
        if not set(node.get('hkg_refs',[])) <= hkg_ids:raise ValueError('Unknown HKG reference')
        evidence(node)
        if node['type']=='Port':
            if node['data'].get('role') not in {'supply','input','output','control'}:raise ValueError('Unknown port role')
            for profile,number in node['data'].get('reference_pin_numbers',{}).items():
                if profile not in profiles or isinstance(number,bool) or not isinstance(number,int) or not 1<=number<=profiles[profile]['pin_count']:
                    raise ValueError('Invalid package-table pin reference')
            channel=node['data'].get('channel_key')
            if channel is not None and (channel not in known or known[channel]['type']!='Channel'):
                raise ValueError('Port refers to an unknown channel')
        elif node['type']=='Channel':
            for port in node['data'].get('input_ports',[]):
                if port not in known or known[port]['type']!='Port' or known[port]['data'].get('role')!='input':
                    raise ValueError('Invalid channel input port')
            port=node['data'].get('output_port')
            if port not in known or known[port]['type']!='Port' or known[port]['data'].get('role')!='output':
                raise ValueError('Invalid channel output port')
    for profile in profiles:
        numbers=[n['data']['reference_pin_numbers'][profile] for n in nodes if n['type']=='Port' and profile in n['data'].get('reference_pin_numbers',{})]
        if len(numbers)!=len(set(numbers)):raise ValueError('Two logical ports occupy the same package-table pin')
    seen=set()
    for edge in annotations.get('dependencies',[]):
        if edge['source'] not in known or edge['target'] not in known or edge['source']==edge['target']:
            raise ValueError('Invalid PDG dependency endpoint')
        if edge['relation'] not in RELATIONS:raise ValueError('Unsupported/implicit sequencing relation')
        source=known[edge['source']];target=known[edge['target']]
        expected={'contributes_to_supply':('Port','SupplyState'),'powers_channel':('SupplyState','Channel'),
            'produces_output':('Channel','Port'),'signal_dependency':('Port','Port'),'validity_dependency':('ValidityConstraint','Port')}
        if (source['type'],target['type'])!=expected[edge['relation']]:raise ValueError('PDG relation/node types do not agree')
        if edge['relation']=='contributes_to_supply' and source['data'].get('role')!='supply':raise ValueError('Supply dependency needs a supply port')
        if edge['relation'] in {'produces_output','signal_dependency','validity_dependency'} and target['data'].get('role')!='output':raise ValueError('Signal/validity dependencies must target an output')
        if edge['relation']=='signal_dependency' and source['data'].get('role') not in {'input','control'}:raise ValueError('Signal dependency needs an input/control port')
        identity=(edge['source'],edge['relation'],edge['target'])
        if identity in seen:raise ValueError('Duplicate PDG dependency')
        seen.add(identity);evidence(edge)
        if edge.get('minimum_delay_s') is not None:raise ValueError('No numeric delay is supported without explicit timing extraction')
        if edge.get('imposes_temporal_order') is not False:raise ValueError('Functional dependencies must not become timing constraints')
        if edge.get('basis') not in {'datasheet_statement','engineering_interpretation'}:
            raise ValueError('Dependency basis must distinguish source statements and interpretations')
    for item in annotations.get('ordering_exceptions',[]):evidence(item)
    if annotations.get('timing_constraints'):
        raise ValueError('Explicit timing constraints require a separate reviewed timing extraction adapter')


def build_pdg(hkg,packet,annotations):
    if packet['hkg_fingerprint']!=fingerprint(hkg):raise ValueError('PDG input HKG changed')
    if packet['source_sha256']!=hkg['source_sha256'] or packet['target_product']!=hkg['target_product']:
        raise ValueError('PDG packet/source identity mismatch')
    validate_annotations(packet,annotations)
    namespace=hkg['source_sha256'][:20]
    ids={n['key']:'PDG:'+namespace+':'+n['key'] for n in annotations['nodes']}
    nodes=[{'id':ids[n['key']],'source_key':n['key'],'type':n['type'],'label':n['label'],
            'data':deepcopy(n['data']),'evidence':deepcopy(n['evidence']),'hkg_refs':deepcopy(n.get('hkg_refs',[]))}
           for n in annotations['nodes']]
    edges=[]
    for edge in annotations['dependencies']:
        item=deepcopy(edge);item['source']=ids[edge['source']];item['target']=ids[edge['target']]
        item['id']='PDG-EDGE-'+fingerprint([item['source'],item['relation'],item['target']])[:24]
        edges.append(item)
    return {'schema_version':'1.0','kind':'PDG','source_sha256':hkg['source_sha256'],
        'target_product':hkg['target_product'],'input_hkg_fingerprint':fingerprint(hkg),
        'annotation_fingerprint':fingerprint(annotations),'nodes':nodes,'edges':edges,
        'package_profiles':deepcopy(annotations.get('package_profiles',{})),
        'reviewer':deepcopy(annotations['reviewer']),
        'ordering_exceptions':deepcopy(annotations.get('ordering_exceptions',[])),
        'timing_constraints':[],'open_timing_questions':deepcopy(annotations.get('open_timing_questions',[])),
        'evaluation_scope':deepcopy(annotations.get('evaluation_scope',{})),
        'ready_for_test_execution':False,'test_plan_generated':False,'testbench_generated':False,
        'summary':{'ports':sum(n['type']=='Port' for n in nodes),'channels':sum(n['type']=='Channel' for n in nodes),
            'nodes':len(nodes),'dependencies':len(edges),'explicit_timing_constraints':0},
        'limitations':'Source-reviewed functional and validity dependencies, not a total pin activation sequence. No startup or settling wait has been inferred from unrelated performance specs. Port maps describe the source datasheet, not a chosen interface/package of the new design.'}
