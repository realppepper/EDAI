"""Channel completeness and provenance audit, inspired by legacy PDG checks."""
from collections import Counter,deque


def audit_pdg(graph):
    nodes={n['id']:n for n in graph['nodes']};keys={n['source_key']:n for n in graph['nodes']}
    errors=[];warnings=[];adj={key:[] for key in nodes};degree=Counter();indegree=Counter()
    edges=graph['edges'];relations={(e['source'],e['relation'],e['target']) for e in edges}
    for edge in edges:
        if edge['source'] not in nodes or edge['target'] not in nodes:
            errors.append({'kind':'dangling_edge','edge_id':edge['id']});continue
        adj[edge['source']].append(edge['target']);indegree[edge['target']]+=1
        degree[edge['source']]+=1;degree[edge['target']]+=1
        if edge.get('basis') not in {'datasheet_statement','engineering_interpretation'}:
            errors.append({'kind':'missing_assertion_origin','edge_id':edge['id']})
        if not edge.get('evidence'):errors.append({'kind':'missing_evidence','edge_id':edge['id']})
    queue=deque(key for key in nodes if not indegree[key]);visited=[]
    while queue:
        key=queue.popleft();visited.append(key)
        for target in adj[key]:
            indegree[target]-=1
            if not indegree[target]:queue.append(target)
    if len(visited)!=len(nodes):errors.append({'kind':'cycle','action':'Reject; never delete source edges to force a DAG'})
    channels=[n for n in nodes.values() if n['type']=='Channel']
    ports=[n for n in nodes.values() if n['type']=='Port']
    supplies=[n for n in ports if n['data']['role']=='supply']
    if not channels or not ports:errors.append({'kind':'missing_channel_or_interface'})
    channel_checks=[];expected_paths=0;present_paths=0
    def reachable(source,target):
        pending=[source];seen=set()
        while pending:
            key=pending.pop()
            if key==target:return True
            if key not in seen:seen.add(key);pending.extend(adj[key])
        return False
    for channel in channels:
        data=channel['data'];output=keys.get(data.get('output_port'))
        expected_inputs=data.get('input_ports',[])
        if not output or not expected_inputs:
            errors.append({'kind':'incomplete_channel','channel':channel['source_key']});continue
        missing=[]
        if (channel['id'],'produces_output',output['id']) not in relations:
            errors.append({'kind':'missing_channel_output','channel':channel['source_key']})
        for name in expected_inputs:
            expected_paths+=1;node=keys.get(name)
            if node and (node['id'],'signal_dependency',output['id']) in relations:present_paths+=1
            else:missing.append(name);errors.append({'kind':'missing_signal_path','channel':channel['source_key'],'input':name,'output':output['source_key']})
        assigned={n['source_key'] for n in ports if n['data'].get('channel_key')==channel['source_key'] and n['data']['role']=='input'}
        if assigned!=set(expected_inputs):errors.append({'kind':'channel_input_binding_mismatch','channel':channel['source_key']})
        if output['data'].get('channel_key')!=channel['source_key']:
            errors.append({'kind':'channel_output_binding_mismatch','channel':channel['source_key']})
        constraints=[n for n in nodes.values() if n['type']=='ValidityConstraint' and n['data'].get('channel_key')==channel['source_key']]
        for constraint in constraints:
            if (constraint['id'],'validity_dependency',output['id']) not in relations:
                errors.append({'kind':'missing_validity_path','channel':channel['source_key'],'constraint':constraint['source_key']})
        if not constraints:warnings.append({'kind':'no_validity_constraint_declared','channel':channel['source_key']})
        unreachable=[s['source_key'] for s in supplies if not reachable(s['id'],output['id'])]
        for supply in unreachable:errors.append({'kind':'unreachable_supply','channel':channel['source_key'],'supply':supply})
        channel_checks.append({'channel':channel['source_key'],'inputs':expected_inputs,'output':output['source_key'],
                               'missing_signal_paths':missing,'unreachable_supply_ports':unreachable})
    for edge in edges:
        if edge['relation']=='signal_dependency' and edge['source'] in nodes and edge['target'] in nodes:
            source=nodes[edge['source']];target=nodes[edge['target']]
            a=source['data'].get('channel_key');b=target['data'].get('channel_key')
            if a and b and a!=b:errors.append({'kind':'cross_channel_signal','edge_id':edge['id'],'source_channel':a,'target_channel':b})
            elif not a or not b:warnings.append({'kind':'unbound_signal_channel','edge_id':edge['id']})
        if edge['relation']=='validity_dependency' and edge['source'] in nodes and edge['target'] in nodes:
            if nodes[edge['source']]['data'].get('channel_key')!=nodes[edge['target']]['data'].get('channel_key'):
                errors.append({'kind':'cross_channel_validity','edge_id':edge['id']})
    for node in ports:
        if not degree[node['id']]:errors.append({'kind':'isolated_port','port':node['source_key']})
    details=[{'edge_id':e['id'],'source':nodes[e['source']]['label'] if e['source'] in nodes else e['source'],
        'target':nodes[e['target']]['label'] if e['target'] in nodes else e['target'],
        'relation':e['relation'],'assertion_origin':e.get('basis'),'evidence':e.get('evidence',[]),
        'delay_s':e.get('minimum_delay_s'),'delay_origin':'not_specified' if e.get('minimum_delay_s') is None else 'unsupported'} for e in edges]
    return {'status':'functional_checks_passed' if not errors else 'failed','errors':errors,'warnings':warnings,
        'channel_checks':channel_checks,'summary':{'channels':len(channels),'expected_signal_paths':expected_paths,
            'present_signal_paths':present_paths,'cross_channel_errors':sum(e['kind']=='cross_channel_signal' for e in errors),
            'unreachable_supply_errors':sum(e['kind']=='unreachable_supply' for e in errors),
            'origin_counts':dict(Counter(e.get('basis','missing') for e in edges)),
            'unknown_delays':sum(e.get('minimum_delay_s') is None for e in edges)},
        'edge_provenance':details,'semantic_accuracy_score':None,
        'scope':'Coverage and provenance structure, not a percentage estimate of physical correctness or executable timing.'}
