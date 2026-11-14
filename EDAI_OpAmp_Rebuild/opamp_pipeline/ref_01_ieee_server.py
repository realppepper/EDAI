"""Read-only IEEE metadata MCP. Adapted from teammate's local IEEE adapter.

No LLM imports, no full-text claim, no credential URLs in returned errors.
"""
import argparse,json,os,site,sys,urllib.request,urllib.parse,urllib.error
from pathlib import Path


def load_key(env_file=None):
    names=('IEEE_API_KEY','IEEE_XPLORE_API_KEY')
    for name in names:
        if os.environ.get(name):return os.environ[name]
    if env_file and Path(env_file).is_file():
        for line in Path(env_file).read_text(encoding='utf-8-sig').splitlines():
            name,sep,value=line.strip().partition('=')
            if sep and name.strip() in names:
                value=value.strip().strip('\"\'')
                if value:return value
    return None


def search_metadata(query,max_results,key):
    if not key:return {'ok':False,'papers':[],'error':'Missing IEEE key'}
    if not query.strip():return {'ok':False,'papers':[],'error':'Empty query'}
    params={'querytext':query,'max_records':min(10,max(1,max_results)),'apikey':key,'format':'json'}
    url='https://ieeexploreapi.ieee.org/api/v1/search/articles?'+urllib.parse.urlencode(params)
    req=urllib.request.Request(url,headers={'User-Agent':'EDAI-OpAmp-Rebuild/1.0','Accept':'application/json'})
    try:
        with urllib.request.urlopen(req,timeout=25) as response:data=json.load(response)
    except urllib.error.HTTPError as error:
        return {'ok':False,'papers':[],'error':f'IEEE HTTP {error.code}'}
    except Exception as error:
        return {'ok':False,'papers':[],'error':f'IEEE request failed ({type(error).__name__})'}
    if not isinstance(data,dict) or data.get('error') or data.get('errors'):
        return {'ok':False,'papers':[],'error':'IEEE API response error'}
    papers=[]
    for p in data.get('articles',[]):
        papers.append({name:p.get(name,'') for name in ('title','abstract','doi','article_number','publication_year','publication_title','html_url')})
    return {'ok':True,'source':'ieee_xplore','papers':papers,'total_records':data.get('total_records',len(papers)),
            'retrieval_scope':'metadata_and_abstracts_only','full_text_retrieved':False}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--deps',required=True);parser.add_argument('--env-file')
    args=parser.parse_args();site.addsitedir(args.deps);sys.path.insert(0,args.deps)
    from mcp.server.fastmcp import FastMCP
    server=FastMCP('EDAI IEEE metadata');key=load_key(args.env_file)
    @server.tool()
    def search_papers(query:str,max_results:int=3)->dict:
        """Search IEEE titles/abstracts; does NOT retrieve full-text PDFs or schematics."""
        return search_metadata(query,max_results,key)
    server.run(transport='stdio')

if __name__=='__main__':main()
