"""Check PDG structure, graph provenance and no inferred activation timetable."""
from .pdg_01_build import build_pdg
from .support.source_checks import fingerprint


def validate_pdg(graph,hkg,packet,annotations):
    expected=build_pdg(hkg,packet,annotations)
    core={k:v for k,v in graph.items() if k!='_execution'}
    if core!=expected:raise ValueError('PDG differs from the reviewed source annotations')
    lookup={n['id']:n for n in graph['nodes']}
    if len(lookup)!=len(graph['nodes']):raise ValueError('Duplicate PDG node IDs')
    if len({e['id'] for e in graph['edges']})!=len(graph['edges']):raise ValueError('Duplicate PDG edges')
    adjacency={key:[] for key in lookup}
    for edge in graph['edges']:
        if edge['source'] not in lookup or edge['target'] not in lookup:raise ValueError('Dangling PDG dependency')
        adjacency[edge['source']].append(edge['target'])
    active=set();visited=set()
    def visit(key):
        if key in active:raise ValueError('Cyclic PDG dependency requires a different graph model')
        if key in visited:return
        active.add(key)
        for target in adjacency[key]:visit(target)
        active.remove(key);visited.add(key)
    for key in lookup:visit(key)
    if graph['input_hkg_fingerprint']!=fingerprint(hkg):raise ValueError('PDG HKG reference is stale')
    return {'status':'source_annotations_and_graph_integrity_passed','nodes':len(lookup),'edges':len(graph['edges']),
            'hkg_references_preserved':True,'explicit_wait_times_added':0,'test_schedule_created':False,
            'scope':'Checks annotation provenance, quoted source existence, identity, graph integrity and absence of fabricated timing; not independent semantic certification.'}
