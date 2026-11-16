"""Select existing datasheet references only after a concrete design need."""
import argparse,json
from pathlib import Path
from opamp_pipeline import ref_07_datasheet as refs


def main():
    p=argparse.ArgumentParser();p.add_argument('action',choices=['prepare','attach','catalog'])
    p.add_argument('--request',type=Path);p.add_argument('--decision',type=Path)
    p.add_argument('--supplement',type=Path);p.add_argument('--session',type=Path);p.add_argument('--document',type=Path)
    p.add_argument('--kind',choices=['fixed','initial'],default='fixed');a=p.parse_args()
    if a.action=='prepare':
        if not a.request or not a.decision or not a.supplement:p.error('Current request, need decision and output supplement required')
        s=refs.prepare(a.request,a.decision,a.supplement)
        result={'status':s['status'],'selected_pages':[r['pdf_page'] for r in s['references']],
            'text_characters':s['text_characters'],'external_calls':s['external_calls']}
    elif a.action=='attach':
        if not a.session:p.error('Session required')
        if not a.supplement:p.error('Supplement required')
        s=refs.attach(a.session,a.supplement,a.kind)
        result={'status':s['status'],'pending_request':s['pending_request']}
    else:
        if not a.session or not a.document:p.error('Session and original parsed document required')
        s=refs.connect_catalog(a.session,a.document,a.kind)
        result={'status':s['status'],'pending_request':s['pending_request'],'content_included':False}
    print(json.dumps(result,ensure_ascii=False))


if __name__=='__main__':main()
