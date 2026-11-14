"""One-time migration of existing assistant-reviewed semantics to row annotations.

Not an AI extractor: no semantic inference or API calls occur in this utility.
"""
import argparse
from copy import deepcopy
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from opamp_pipeline.support.source_checks import fingerprint
from opamp_pipeline.pdf_03_render_pages import save_json


def migrate(base: dict, previous: dict) -> dict:
    if base['source_sha256']!=previous['source_sha256'] or base['target_product']!=previous['target_product']:
        raise ValueError('Different source document or target product')
    annotations=[];claimed=set()
    for old in previous['electrical_specs']:
        page=old['source']['pdf_page'];anchor=old['source']['value_row_y_points']
        matches=[r for r in base['electrical_specs'] if r['source']['pdf_page']==page
                 and r['source']['row_bbox_points'][1]<=anchor<r['source']['row_bbox_points'][3]]
        if len(matches)!=1 or matches[0]['id'] in claimed:raise ValueError('Ambiguous/duplicate legacy annotation mapping')
        row=matches[0];claimed.add(row['id'])
        patch={'row_id':row['id'],'fields':{k:deepcopy(old[k]) for k in ('symbol','name','unit','conditions','printed_notation','notes') if k in old},
               'interpreted_limits':{},'proposed_corrections':[]}
        for slot,cell in row['original_cell_evidence']['limit_cells'].items():
            value=old['limits'][slot]
            if cell['status']=='needs_interpretation' and isinstance(value,(dict,str)):
                patch['interpreted_limits'][slot]=deepcopy(value)
            elif value!=row['limits'][slot]:
                patch['proposed_corrections'].append({'field':'limits.'+slot,'proposed_value':value,
                    'reason':'Legacy assistant value differs from locked original-PDF cell; review required'})
        annotations.append(patch)
    return {'schema_version':'1.0','source_document_fingerprint':fingerprint(base),
            'authorship':{'mode':'migrated_existing_chat_assistant_semantics','external_llm_calls':0,
                         'previous_authorship':deepcopy(previous.get('authorship',{}))},
            'row_annotations':annotations,
            'document_annotations':{k:deepcopy(previous[k]) for k in ('condition_sets','operating_conditions','behavior_constraints','deferred_information','policy_notes') if k in previous}}


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--base',type=Path,required=True)
    ap.add_argument('--previous',type=Path,required=True);ap.add_argument('--output',type=Path,required=True)
    args=ap.parse_args()
    result=migrate(json.loads(args.base.read_text(encoding='utf-8')),json.loads(args.previous.read_text(encoding='utf-8')))
    save_json(args.output,result)
    print(json.dumps({'annotations':len(result['row_annotations']),
        'proposals':sum(len(r['proposed_corrections']) for r in result['row_annotations']),'external_llm_calls':0}))


if __name__=='__main__':main()
