"""Return a spec with its linked context without flattening its conditions."""
from copy import deepcopy


def specification_contexts(graph,symbol=None,row_id=None):
    nodes={n['id']:n for n in graph['nodes']};outgoing={key:[] for key in nodes}
    for edge in graph['edges']:
        if edge['source'] not in nodes or edge['target'] not in nodes:raise ValueError('Dangling graph edge')
        outgoing[edge['source']].append(edge)
    result=[]
    for node in graph['nodes']:
        if node['type']!='Specification':continue
        data=node['data']
        if symbol is not None and data.get('symbol')!=symbol:continue  # En and en differ.
        if row_id is not None and data.get('id')!=row_id:continue
        context={'specification':deepcopy(data),'linked_context':{}}
        for edge in outgoing[node['id']]:
            context['linked_context'].setdefault(edge['relation'],[]).append(deepcopy(nodes[edge['target']]))
        context['related_graphs']=[{'id':n['data']['id'],'metadata':deepcopy(n['data'].get('reviewed_metadata',{})),
            'numeric_verification':deepcopy(n['data'].get('numeric_data',{})),
            'same_test_conditions':'not_asserted'} for n in graph['nodes'] if n['type']=='CharacteristicGraph'
            and data['id'] in n['data'].get('related_spec_ids',[])]
        context['effective_conditions_generated']=False
        result.append(context)
    return result
