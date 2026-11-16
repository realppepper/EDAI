"""Explicit need -> IEEE search -> selected body read -> bound design handoff."""
import argparse,json
from pathlib import Path
from opamp_pipeline.ref_05_research import search,read_selected,make_supplement
from opamp_pipeline.ref_06_attach import attach


def main():
    p=argparse.ArgumentParser();p.add_argument('action',choices=['search','read','attach'])
    p.add_argument('--research-dir',type=Path,required=True);p.add_argument('--request',type=Path);p.add_argument('--decision',type=Path)
    p.add_argument('--article-number');p.add_argument('--env-file',type=Path)
    p.add_argument('--mcp-deps',type=Path,default=Path('C:/Projects/AnalogVerifier_upstream_20261111/.integration_deps'))
    p.add_argument('--session',type=Path);p.add_argument('--kind',choices=['fixed','initial'],default='fixed');a=p.parse_args()
    if a.action=='search':
        if not a.request or not a.decision:p.error('Request and need decision required')
        s=search(a.request,a.decision,a.research_dir,a.mcp_deps,a.env_file)
        print(json.dumps({'status':s['status'],'search_calls':s['external_search_calls'],
            'papers':[{'article_number':r['article_number'],'title':r['title'],'access_type':r['access_type']} for r in s.get('search',{}).get('papers',[])]},ensure_ascii=False))
    elif a.action=='read':
        if not a.article_number:p.error('Select an article from this search')
        s=read_selected(a.research_dir,a.article_number,a.mcp_deps,a.env_file)
        supplement=make_supplement(a.research_dir)
        print(json.dumps({'status':s['status'],'article_number':a.article_number,'body_retrieved':s['reading'][a.article_number]['full_text_retrieved'],
            'excerpt_characters':supplement['body_excerpt_characters'],'error':s['reading'][a.article_number]['error']},ensure_ascii=False))
    else:
        if not a.session:p.error('Session required')
        make_supplement(a.research_dir)
        s=attach(a.session,a.research_dir/'SUPPLEMENT.json',a.kind)
        print(json.dumps({'status':s['status'],'pending_request':s['pending_request'],'design_or_simulation_started':False},ensure_ascii=False))


if __name__=='__main__':main()
