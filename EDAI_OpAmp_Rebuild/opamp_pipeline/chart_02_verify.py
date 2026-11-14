"""Attach visual review with explicit temperature scope and source safeguards."""
from copy import deepcopy
import re
from .chart_01_collect import build_chart_review_packet
from .support.source_checks import fingerprint
from .support.graph_conditions import graph_condition_annotations
from .support.execution_state import spec_core


def apply_chart_review(candidates, review=None, temperature_C=25):
    if temperature_C != 25:raise ValueError('Current evaluation scope is fixed at 25 C')
    if review is not None and review.get('packet_fingerprint') != fingerprint(build_chart_review_packet(candidates)):
        raise ValueError('Chart review is stale or belongs to another source')
    patches=review.get('graph_reviews',[]) if review else []
    if review is not None and not review.get('reviewer',{}).get('method'):
        raise ValueError('Chart reviewer provenance required')
    known={g['id'] for g in candidates['graphs']}; mapping={}
    for patch in patches:
        key=patch.get('graph_id')
        if key not in known or key in mapping:raise ValueError('Unknown or duplicate chart review')
        mapping[key]=patch
    result=deepcopy(candidates); result['stage']='chart_02_reviewed_references'
    result['evaluation_scope']={'ambient_temperature_C':temperature_C,'source_conditions_preserved':True,
        'graphs_are_acceptance_criteria':False,'all_numeric_points_verified':False}
    result['reviewer']=deepcopy(review.get('reviewer')) if review else None
    for graph in result['graphs']:
        patch=mapping.get(graph['id'])
        if not patch:continue
        metadata=patch.get('reviewed_metadata',{})
        caption=graph['source']['caption_candidate']
        if not caption or metadata.get('figure_number')!=caption['figure_number']:
            raise ValueError('Visual figure identity must agree with original caption')
        if metadata.get('title') != caption['title']:
            raise ValueError('Reviewed title must preserve original caption text')
        if not metadata.get('axes') or not metadata.get('title') or not patch.get('explanation'):
            raise ValueError('Chart review requires axes, title and explanation')
        if not isinstance(patch.get('image_inspected'),bool) or not patch['image_inspected']:
            raise ValueError('Visual review must explicitly confirm image inspection')
        if patch.get('numeric_review',{}).get('status') not in {'not_verified','rejected','spot_checked_only'}:
            raise ValueError('Full digitization certification is not supported by this adapter')
        temperature=metadata.get('temperature',{})
        kind=temperature.get('kind')
        if kind not in {'fixed','sweep','series','distribution'}:raise ValueError('Temperature provenance required')
        if kind=='fixed' and temperature.get('value_C')==temperature_C:
            applicability='reference_at_evaluation_temperature'
        elif kind=='series' and temperature_C in temperature.get('values_C',[]):
            applicability='selected_temperature_trace_only'
            if not any(t.get('temperature_C')==temperature_C for t in metadata.get('traces',[])):
                raise ValueError('Mixed-temperature graph needs an identified evaluation-temperature trace')
        else:applicability='deferred_temperature_sweep_or_statistics' if kind in {'sweep','distribution'} else 'outside_temperature_scope'
        graph['reviewed_metadata']=deepcopy(metadata)
        graph['condition_annotations']=graph_condition_annotations(metadata)
        graph['visual_review']=deepcopy(patch)
        graph['review_status']='metadata_visually_reviewed'
        graph['numeric_data']={**deepcopy(patch['numeric_review']),'approved_for_design':False,
                              'all_points_verified':False}
        graph['evaluation_applicability']={'status':applicability,'temperature_C':temperature_C,
            'acceptance_criterion':False,'reason':patch.get('scope_reason','Typical reference, not a guaranteed bound.')}
        parsed_number=re.search(r'Figure\s+(\d+-\d+)',graph['parsed_metadata'].get('title') or '')
        graph['parser_caption_check']='matched' if parsed_number and parsed_number.group(1)==caption['figure_number'] else 'corrected_by_source_position_and_visual_review'
    result['summary']={'chart_count':len(result['graphs']),
        'visually_reviewed_metadata_count':sum(g['review_status']=='metadata_visually_reviewed' for g in result['graphs']),
        'caption_corrections':sum(g.get('parser_caption_check')=='corrected_by_source_position_and_visual_review' for g in result['graphs']),
        'reference_at_25C_count':sum(g.get('evaluation_applicability',{}).get('status')=='reference_at_evaluation_temperature' for g in result['graphs']),
        'selected_25C_trace_count':sum(g.get('evaluation_applicability',{}).get('status')=='selected_temperature_trace_only' for g in result['graphs']),
        'temperature_or_statistics_deferred_count':sum(g.get('evaluation_applicability',{}).get('status')=='deferred_temperature_sweep_or_statistics' for g in result['graphs']),
        'all_points_verified_count':0}
    return result


def link_to_specs(specs, references):
    if specs['source_sha256']!=references['source_sha256'] or specs['target_product']!=references['target_product']:
        raise ValueError('Graph/spec document source mismatch')
    result=deepcopy(specs)
    result.pop('_graph_execution',None)
    result['ready_for_design']=False
    result['linked_spec_document_fingerprint']=fingerprint(spec_core(result))
    result['characteristic_graphs']=deepcopy(references['graphs'])
    result['graph_reference_summary']=deepcopy(references['summary'])
    result['evaluation_scope']=deepcopy(references['evaluation_scope'])
    known={r['id'] for r in result['electrical_specs']}
    by_symbol={}
    for row in result['electrical_specs']:
        by_symbol.setdefault(row['symbol'],[]).append(row)
        row['related_graph_ids']=[]
    for row in result['electrical_specs']:
        conditions=row.get('conditions',{})
        common=result.get('condition_sets',{}).get(conditions.get('inherits'),{})
        temperature=conditions.get('overrides',{}).get('ambient_temperature_C',common.get('ambient_temperature_C'))
        if '/dT' in (row.get('symbol') or ''):
            status='deferred_temperature_coefficient'
        elif isinstance(temperature,dict) and temperature.get('min',float('inf'))<=25<=temperature.get('max',float('-inf')):
            status='range_contains_25C_bound_candidate_only'
        elif temperature==25:
            status='specified_at_25C_candidate'
        else:status='temperature_scope_review_required'
        row['evaluation_temperature_scope']={
            'evaluation_temperature_C':25,'original_temperature_condition_C':deepcopy(temperature),
            'status':status,'temperature_condition_rewritten':False,
            'range_value_is_not_a_separate_25C_measurement':isinstance(temperature,dict),
            'adopted_as_design_target':False}
    for graph in result['characteristic_graphs']:
        graph['related_spec_ids']=[]
        # Related concept only: does not imply identical fixture or guaranteed value.
        for symbol in graph.get('reviewed_metadata',{}).get('related_symbols',[]):
            for row in by_symbol.get(symbol,[]):
                if row['id'] not in graph['related_spec_ids']:graph['related_spec_ids'].append(row['id'])
                if graph['id'] not in row['related_graph_ids']:row['related_graph_ids'].append(graph['id'])
        assert set(graph['related_spec_ids']) <= known
        graph['link_meaning']='Related characteristic only; compare source conditions before use.'
    result['ready_for_design']=False
    return result
