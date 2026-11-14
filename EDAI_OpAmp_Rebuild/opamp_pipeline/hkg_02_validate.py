"""Graph integrity and source round-trip verification, not new circuit judgement."""
from .support.source_checks import fingerprint


def validate_hkg(graph, document):
    if graph.get('source_sha256')!=document['source_sha256'] or graph.get('target_product')!=document['target_product']:
        raise ValueError('HKG/source identity mismatch')
    if graph.get('input_document_fingerprint')!=fingerprint(document):raise ValueError('HKG input is stale')
    nodes=graph['nodes'];edges=graph['edges'];lookup={n['id']:n for n in nodes}
    if len(lookup)!=len(nodes) or len({e['id'] for e in edges})!=len(edges):raise ValueError('Duplicate graph IDs')
    if any(e['source'] not in lookup or e['target'] not in lookup for e in edges):raise ValueError('Dangling HKG edge')
    if len({fingerprint([e['source'],e['relation'],e['target'],e['data']]) for e in edges})!=len(edges):raise ValueError('Duplicate HKG relations')
    source_specs={r['id']:r for r in document['electrical_specs']}
    graph_specs={n['data']['id']:n for n in nodes if n['type']=='Specification'}
    if set(source_specs)!=set(graph_specs):raise ValueError('Missing or extra HKG specifications')
    outgoing={key:[] for key in lookup}
    for edge in edges:outgoing[edge['source']].append(edge)
    def targets(key,relation):return [lookup[e['target']] for e in outgoing[key] if e['relation']==relation]
    docs=[n for n in nodes if n['type']=='Datasheet'];products=[n for n in nodes if n['type']=='Product']
    if len(docs)!=1 or len(products)!=1 or products[0]['data'].get('name')!=document['target_product']:
        raise ValueError('HKG document/product identity differs from source')
    if docs[0]['data'].get('coverage')!=document.get('coverage',{}):raise ValueError('HKG lost coverage limitations')
    for row_id,row in source_specs.items():
        key=graph_specs[row_id]['id'];node=lookup[key]
        for field in ('symbol','name','unit','source','notes','evaluation_temperature_scope','original_cell_evidence'):
            if field in row and node['data'].get(field)!=row[field]:raise ValueError('HKG altered source specification metadata')
        limits=targets(key,'has_limit')
        if {n['data']['slot']:n['data']['value'] for n in limits}!=row['limits'] or len(limits)!=len(row['limits']):
            raise ValueError('HKG lost or changed original limit values')
        for limit in limits:
            slot=limit['data']['slot']
            if limit['data'].get('unit')!=row.get('unit') or limit['data'].get('printed_notation')!=row.get('printed_notation',{}).get(slot):
                raise ValueError('HKG altered limit unit or printed notation')
            if limit['data'].get('acceptance_criterion') is not False:raise ValueError('HKG promoted a limit to an adopted target')
        interpretations=targets(key,'has_condition_interpretation')
        if len(interpretations)!=1 or interpretations[0]['data']['source_conditions']!=row.get('conditions',{}):
            raise ValueError('HKG changed source conditions')
        local=targets(key,'has_local_conditions')
        if len(local)!=1 or local[0]['data']!={'overrides':row.get('conditions',{}).get('overrides',{})}:
            raise ValueError('HKG changed local condition overrides')
        reviews=targets(key,'has_verification')
        if len(reviews)!=1 or reviews[0]['data']!=row.get('verification',{}):raise ValueError('HKG lost review status')
        inherited=targets(key,'inherits_conditions');source_set=row.get('conditions',{}).get('inherits')
        if source_set:
            if len(inherited)!=1 or inherited[0]['data']!=document['condition_sets'][source_set]:raise ValueError('HKG inherited conditions differ from source')
        elif inherited:raise ValueError('HKG invented inherited conditions')
        pages=targets(key,'supported_by')
        if len(pages)!=1 or pages[0]['data']['pdf_page']!=row['source']['pdf_page']:raise ValueError('HKG source page mismatch')
    source_graphs={g['id']:g for g in document.get('characteristic_graphs',[])}
    graph_nodes={n['data']['id']:n for n in nodes if n['type']=='CharacteristicGraph'}
    if set(source_graphs)!=set(graph_nodes):raise ValueError('Missing or extra reference graphs')
    for gid,original in source_graphs.items():
        node=graph_nodes[gid]
        if node['data']!=original:raise ValueError('HKG altered reference graph data or verification state')
        linked=targets(node['id'],'related_characteristic')
        if {n['data']['id'] for n in linked}!=set(original.get('related_spec_ids',[])):
            raise ValueError('HKG reference/spec linkage differs from input')
        for edge in outgoing[node['id']]:
            if edge['relation']=='related_characteristic' and edge['data']!={'same_test_conditions':'not_asserted','acceptance_criterion':False}:
                raise ValueError('HKG reference relation must not assert matching test conditions')
    for collection,kind in [('operating_conditions','OperatingCondition'),('behavior_constraints','BehaviorConstraint')]:
        expected={item['id']:item for item in document.get(collection,[])}
        actual={n['data']['id']:n['data'] for n in nodes if n['type']==kind}
        if actual!=expected:raise ValueError('HKG lost context data or pending verification states')
    if [n['data'] for n in nodes if n['type']=='DeferredInformation']!=document.get('deferred_information',[]):
        raise ValueError('HKG lost deferred extraction information')
    if graph.get('ready_for_design') is not False or graph.get('generated_pdg') or graph.get('generated_test_plan'):
        raise ValueError('HKG must not imply downstream completion')
    return {'status':'graph_integrity_and_source_preservation_passed','specifications':len(source_specs),
        'reference_graphs':len(source_graphs),'nodes':len(nodes),'edges':len(edges),
        'new_semantic_verification_performed':False,'design_targets_adopted':False}
