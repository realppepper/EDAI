"""Compare candidate JSON and native-cell evidence with fresh original PDF words.

Numeric/source checks are distinct from unverified semantic conditions and
document completeness. Agreement between two extractors is not ground truth.
"""
from collections import defaultdict
from decimal import Decimal
import hashlib
import json
import re


def fingerprint(data: dict) -> str:
    return hashlib.sha256(json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def normalized_unit(unit: str) -> str:
    text = re.sub(r'\s+', '', unit).replace('µ', 'u').replace('μ', 'u').replace('Ω', 'Ohm').replace('℃', 'degC').replace('°C', 'degC')
    return {'°': 'deg', 'percent': '%', 'uVPP': 'uVpp', 'nV/√Hz': 'nV/sqrt(Hz)'}.get(text, text)


def _cell_text(words: list, bbox: list) -> str:
    x0,y0,x1,y1 = bbox
    selected = sorted([w for w in words if x0 <= (w[0]+w[2])/2 <= x1 and y0 <= (w[1]+w[3])/2 <= y1], key=lambda w:(round(w[1],1),w[0]))
    return ' '.join(w[4] for w in selected).strip()


def _same_number(a, b) -> bool:
    if isinstance(a, bool) or isinstance(b, bool): return False
    try: return Decimal(str(a)) == Decimal(str(b))
    except Exception: return False


def _source_scalar(raw: str):
    token = raw.strip().replace('−','-').replace('–','-').removeprefix('±').strip()
    if re.fullmatch(r'[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?',token):
        return Decimal(token)
    return None


def verify_sources(candidate: dict, native: dict, original_words: dict, source_sha256: str) -> dict:
    if candidate.get('source_sha256') != source_sha256 or native.get('source_sha256') != source_sha256:
        raise ValueError('Candidate/native evidence/original PDF hashes differ')
    if candidate.get('target_product') != native.get('target_product'):
        raise ValueError('Target products differ')
    specs, rows = candidate['electrical_specs'], native['rows']
    if len({r['id'] for r in specs}) != len(specs) or len({r['id'] for r in rows}) != len(rows):
        raise ValueError('Duplicate candidate/native row IDs')
    mappings, claimed = {}, defaultdict(list)
    for spec in specs:
        source = spec.get('source', {})
        anchor = source.get('value_row_y_points')
        matches = [r for r in rows if (not source.get('native_row_id') or r['id']==source['native_row_id'])
                   and r['source']['pdf_page'] == source.get('pdf_page')
                   and isinstance(anchor,(int,float)) and r['source']['row_bbox_points'][1] <= anchor < r['source']['row_bbox_points'][3]]
        mappings[spec['id']] = matches
        if len(matches) == 1: claimed[matches[0]['id']].append(spec['id'])
    result_rows = []
    for spec in specs:
        matches = mappings[spec['id']]
        entry = {'candidate_id':spec['id'], 'native_row_id':None, 'issues':[], 'limit_checks':{},
                 'conditions_check':'semantic_review_required', 'parameter_meaning_check':'semantic_review_required',
                 'ready_for_design':False}
        if len(matches) != 1:
            entry['issues'].append('Source row mapping is missing or ambiguous; never match by numeric value alone')
            entry['status']='conflict'
            result_rows.append(entry)
            continue
        row = matches[0]
        entry['native_row_id'] = row['id']
        if len(claimed[row['id']]) != 1:
            entry['issues'].append('Multiple candidate rows claim the same original row')
        words = original_words[row['source']['pdf_page']]
        for slot in ('min','typ','max'):
            evidence = row['limit_cells'][slot]
            raw = _cell_text(words, evidence['bbox_points'])
            header = _cell_text(words, evidence['header_bbox_points']).upper()
            given = spec['limits'][slot]
            check = {'source_raw':raw, 'candidate_value':given, 'source_value':None}
            box, hbox = evidence['bbox_points'], evidence['header_bbox_points']
            aligned = abs(box[0]-hbox[0]) < 0.01 and abs(box[2]-hbox[2]) < 0.01
            if header != slot.upper() or raw != evidence['raw'] or not aligned:
                check['status']='conflict'
                check['reason']='Stored cell/header evidence differs from fresh original PDF words'
            elif not raw:
                check['status']='blank_match' if given is None and evidence.get('value') is None else 'conflict'
                check['reason']='Original cell is blank'
            else:
                scalar = _source_scalar(raw)
                if scalar is None:
                    check['status']='needs_interpretation'
                    check['reason']='Formula/composite raw value retained; not independently interpreted'
                elif not _same_number(evidence.get('value'),scalar):
                    check['status']='conflict'
                    check['reason']='Stored numeric value differs from fresh original cell'
                else:
                    check['source_value']=float(scalar)
                    check['status']='numeric_match' if _same_number(given,scalar) else 'conflict'
                    check['source_notation']='plus_minus' if raw.strip().startswith('±') else 'signed_scalar'
                    if check['source_notation']=='plus_minus' and not str(spec.get('printed_notation',{}).get(slot,'')).startswith('±'):
                        check['status']='conflict'
                        check['reason']='Plus/minus notation missing from candidate'
            entry['limit_checks'][slot]=check
        raw_unit, unit = row.get('raw_unit',''), spec.get('unit','')
        unit_box=row.get('unit_cell_evidence',{}).get('bbox_points')
        fresh_unit=_cell_text(words,unit_box) if unit_box else None
        if fresh_unit is not None and fresh_unit != raw_unit:
            entry['unit_check']={'status':'conflict','reason':'Stored unit differs from original PDF cell','source_unit':fresh_unit,'candidate_unit':unit}
        elif normalized_unit(raw_unit)==normalized_unit(unit) and raw_unit and fresh_unit is not None:
            entry['unit_check']={'status':'text_alias_match','source_unit':raw_unit,'candidate_unit':unit}
        elif unit=='composite' or '/√/' in raw_unit or not raw_unit or fresh_unit is None:
            entry['unit_check']={'status':'review_required','source_unit':raw_unit,'candidate_unit':unit}
        else:
            entry['unit_check']={'status':'conflict','source_unit':raw_unit,'candidate_unit':unit}
        conflict = bool(entry['issues']) or any(c['status']=='conflict' for c in entry['limit_checks'].values()) or entry['unit_check']['status']=='conflict'
        entry['numeric_status']='conflict' if conflict else 'review_required' if any(c['status']=='needs_interpretation' for c in entry['limit_checks'].values()) else 'scalar_columns_supported'
        entry['status']='conflict' if conflict else 'semantic_review_required'
        entry['native_condition_evidence']=row.get('raw_parameter_and_conditions',[])
        result_rows.append(entry)
    missing = [r['id'] for r in rows if r['id'] not in claimed]
    summary={'candidate_rows':len(specs),'native_rows':len(rows),
             'uniquely_mapped_rows':sum(r['native_row_id'] is not None and len(claimed[r['native_row_id']])==1 for r in result_rows),
             'scalar_supported_rows':sum(r.get('numeric_status')=='scalar_columns_supported' for r in result_rows),
             'non_scalar_review_rows':sum(r.get('numeric_status')=='review_required' for r in result_rows),
             'conflict_rows':sum(r['status']=='conflict' for r in result_rows), 'missing_candidate_rows':len(missing),
             'unit_supported_rows':sum(r.get('unit_check',{}).get('status')=='text_alias_match' for r in result_rows),
             'unit_review_rows':sum(r.get('unit_check',{}).get('status')=='review_required' for r in result_rows),
             'conditions_semantically_verified_rows':0,'ready_for_design_rows':0}
    return {'stage':'spec_02_verify_sources','source_sha256':source_sha256,
            'input_fingerprints':{'candidate':fingerprint(candidate),'native':fingerprint(native)},
            'summary':summary,'rows':result_rows,'missing_candidate_native_ids':missing,
            'excluded_native_rows':native.get('excluded_rows',[]),'native_table_issues':native.get('table_issues',[]),
            'source_accuracy_verified':False,'external_llm_calls':0,
            'limitations':['Conditions, units with malformed text, formulas and semantic identity still need review.',
                           'Coverage is checked against detected native table rows, not independently against every row in every PDF page.',
                           'Original numeric words use the same PDF text engine as extraction; graphical/source-text errors can be shared.']}
