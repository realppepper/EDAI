"""Lossless, typed property graph from reviewed spec candidates; no inference."""
from collections import Counter
from copy import deepcopy
from .support.source_checks import fingerprint


class GraphBuilder:
    def __init__(self, document, page_count=None):
        self.document=document;self.page_count=page_count;self.nodes={};self.edges={}
        self.prefix=document['source_sha256'][:20]

    def node(self, node_id, kind, label, data):
        item={'id':node_id,'type':kind,'label':label,'data':deepcopy(data)}
        if node_id in self.nodes and self.nodes[node_id]!=item:
            raise ValueError('Conflicting duplicate HKG node: '+node_id)
        self.nodes[node_id]=item
        return node_id

    def edge(self, source, relation, target, **data):
        identity=[source,relation,target,data]
        edge_id='EDGE-'+fingerprint(identity)[:24]
        self.edges[edge_id]={'id':edge_id,'source':source,'relation':relation,'target':target,'data':deepcopy(data)}

    def page(self, number):
        if isinstance(number,bool) or not isinstance(number,int) or number<1 or (self.page_count and number>self.page_count):
            raise ValueError('Invalid source page in HKG')
        key=f'page:{self.prefix}:{number}'
        self.node(key,'SourcePage',f'PDF {number}',{'pdf_page':number,'source_sha256':self.document['source_sha256']})
        self.edge(key,'part_of','document:'+self.prefix)
        return key

    def source_edges(self, node_id, pages):
        for number in sorted(set(pages)):
            self.edge(node_id,'supported_by',self.page(number))

    def build(self):
        d=self.document
        doc=self.node('document:'+self.prefix,'Datasheet',d.get('source_filename','PDF'),{
            'source_sha256':d['source_sha256'],'source_filename':d.get('source_filename'),
            'coverage':d.get('coverage',{}),'limitations':d.get('limitations',[]),
            'whole_document_requirements_complete':d.get('coverage',{}).get('whole_document_requirements_complete',False)})
        product=self.node('product:'+self.prefix+':'+fingerprint(d['target_product'])[:12],
            'Product',d['target_product'],{'name':d['target_product']})
        self.edge(product,'documented_by',doc)
        for key,value in d.get('condition_sets',{}).items():
            node=self.node('conditions:'+self.prefix+':'+key,'ConditionSet',key,value)
            self.source_edges(node,value.get('source_pages',[]))
        rows=d.get('electrical_specs',[])
        if len({r['id'] for r in rows})!=len(rows):raise ValueError('Duplicate source specification IDs')
        spec_ids={r['id']:'spec:'+r['id'] for r in rows}
        graph_rows=d.get('characteristic_graphs',[])
        if len({g['id'] for g in graph_rows})!=len(graph_rows):raise ValueError('Duplicate source graph IDs')
        for row in rows:
            key=spec_ids[row['id']]
            excluded={'limits','conditions','verification','related_graph_ids','original_cell_evidence'}
            attrs={k:deepcopy(v) for k,v in row.items() if k not in excluded}
            attrs['adopted_as_design_target']=False
            attrs['original_cell_evidence']=deepcopy(row.get('original_cell_evidence',{}))
            self.node(key,'Specification',f"{row.get('symbol')} — {row.get('name')}",attrs)
            self.edge(product,'has_specification',key)
            self.source_edges(key,[row['source']['pdf_page']])
            for slot,value in row['limits'].items():
                if slot not in {'min','typ','max'}:raise ValueError('Unknown source limit slot')
                limit=self.node('limit:'+row['id']+':'+slot,'SpecLimit',slot.upper(),{
                    'slot':slot,'value':value,'unit':row.get('unit'),
                    'printed_notation':row.get('printed_notation',{}).get(slot),
                    'original_cell':row.get('original_cell_evidence',{}).get('limit_cells',{}).get(slot),
                    'acceptance_criterion':False})
                self.edge(key,'has_limit',limit)
            conditions=row.get('conditions',{})
            inherited=conditions.get('inherits')
            if inherited:
                if inherited not in d.get('condition_sets',{}):raise ValueError('Unknown inherited condition set')
                self.edge(key,'inherits_conditions','conditions:'+self.prefix+':'+inherited)
            local=self.node('local:'+row['id'],'LocalConditions','행별 조건',{'overrides':conditions.get('overrides',{})})
            self.edge(key,'has_local_conditions',local)
            interpretation=self.node('interpretation:'+row['id'],'ConditionInterpretation','조건 적용 해석',{
                'source_conditions':conditions,'effective_conditions_generated':False})
            self.edge(key,'has_condition_interpretation',interpretation)
            for inherited_field,local_field in conditions.get('inheritance_replacements',{}).items():
                self.edge(local,'supersedes_condition','conditions:'+self.prefix+':'+str(inherited),
                          inherited_field=inherited_field,local_field=local_field)
            verification=self.node('verification:'+row['id'],'Verification','검토 상태',row.get('verification',{}))
            self.edge(key,'has_verification',verification)
        for graph in graph_rows:
            if graph.get('acceptance_criterion') is not False or graph.get('numeric_data',{}).get('approved_for_design') is not False:
                raise ValueError('Characteristic graph must remain a non-target reference')
            key='graph:'+graph['id'];meta=graph.get('reviewed_metadata',{})
            self.node(key,'CharacteristicGraph',meta.get('figure_number',graph['id'])+' '+meta.get('title',''),graph)
            self.edge(product,'has_reference_graph',key,acceptance_criterion=False)
            self.source_edges(key,[graph['source']['pdf_page']])
            for row_id in graph.get('related_spec_ids',[]):
                if row_id not in spec_ids:raise ValueError('Graph references unknown specification')
                self.edge(key,'related_characteristic',spec_ids[row_id],same_test_conditions='not_asserted',acceptance_criterion=False)
        for collection,kind in [('operating_conditions','OperatingCondition'),('behavior_constraints','BehaviorConstraint')]:
            for item in d.get(collection,[]):
                key=f"{kind}:{self.prefix}:{item['id']}"
                self.node(key,kind,item.get('parameter',item.get('statement',item['id'])),item)
                self.edge(product,'has_context',key,verification_status=item.get('verification_status','pending'))
                self.source_edges(key,[item['source_page']])
        for index,item in enumerate(d.get('deferred_information',[])):
            key=f'deferred:{self.prefix}:{index}'
            self.node(key,'DeferredInformation',item.get('type','미구조화 정보'),item)
            self.edge(product,'has_deferred_information',key)
            self.source_edges(key,item.get('source_pages',[]))
        scope=self.node('scope:'+self.prefix,'EvaluationScope','현재 평가 범위',d.get('evaluation_scope',{}))
        self.edge(product,'has_evaluation_scope',scope)
        result={'schema_version':'1.0','kind':'HKG','stage':'hkg_01_build',
            'source_sha256':d['source_sha256'],'target_product':d['target_product'],
            'input_document_fingerprint':fingerprint(d),'nodes':list(self.nodes.values()),'edges':list(self.edges.values()),
            'ready_for_design':False,'generated_pdg':False,'generated_test_plan':False,
            'verification_policy':'Preserve source review states. Graph construction neither re-verifies claims nor adopts design targets.',
            'summary':{'nodes':len(self.nodes),'edges':len(self.edges),'node_types':dict(Counter(n['type'] for n in self.nodes.values())),
                       'edge_relations':dict(Counter(e['relation'] for e in self.edges.values()))}}
        return result


def build_hkg(document,page_count=None):
    return GraphBuilder(document,page_count).build()
