"""MCP search with explicit trigger, content-addressed cache, safe failures."""
import asyncio,html,json,re,site,sys
from datetime import datetime,timezone,timedelta
from pathlib import Path
from .support.source_checks import fingerprint


def plain(text):return ' '.join(html.unescape(re.sub('<[^>]*>',' ',str(text or ''))).split())


def normalize_paper(p):
    doi=plain(p.get('doi'));number=str(p.get('article_number',''))
    return {'id':'IEEE-'+fingerprint([doi,number,p.get('title')])[:16],
            'title':plain(p.get('title')),'abstract':plain(p.get('abstract')),
            'doi':doi,'article_number':number,'year':p.get('publication_year'),
            'venue':plain(p.get('publication_title')),
            'url':('https://doi.org/'+doi if doi else 'https://ieeexplore.ieee.org/document/'+number),
            'evidence_scope':'metadata_and_abstract_only','full_text_retrieved':False,
            'design_equations_verified':False,'schematic_retrieved':False}


async def _call(query,limit,deps,env_file):
    site.addsitedir(str(deps));sys.path.insert(0,str(deps))
    from mcp import ClientSession,StdioServerParameters
    from mcp.client.stdio import stdio_client
    import os
    env=os.environ.copy();env['PYTHONIOENCODING']='utf-8'
    server=StdioServerParameters(command=sys.executable,
        args=[str(Path(__file__).with_name('ref_01_ieee_server.py')),'--deps',str(deps),'--env-file',str(env_file)],env=env)
    async with stdio_client(server) as (read,write):
        async with ClientSession(read,write,read_timeout_seconds=timedelta(seconds=35)) as session:
            await session.initialize()
            if 'search_papers' not in [t.name for t in (await session.list_tools()).tools]:
                return {'ok':False,'papers':[],'error':'MCP search tool missing'}
            result=await session.call_tool('search_papers',{'query':query,'max_results':limit})
            if result.isError:return {'ok':False,'papers':[],'error':'MCP tool returned error'}
            data=getattr(result,'structuredContent',None)
            if not isinstance(data,dict):data=json.loads(next(c.text for c in result.content if getattr(c,'type',None)=='text'))
            return data


def _invoke(query,limit,deps,env_file):
    return asyncio.run(asyncio.wait_for(_call(query,limit,deps,env_file),timeout=42))


def retrieve(query,limit,cache_dir,deps,env_file,refresh=False):
    if not query.strip() or not 1<=limit<=10:raise ValueError('Invalid IEEE query/limit')
    identity={'query':query,'limit':limit,'source':'ieee_xplore','adapter_schema':1}
    cache=Path(cache_dir)/(fingerprint(identity)+'.json');cache.parent.mkdir(parents=True,exist_ok=True)
    if cache.exists() and not refresh:
        try:
            cached=json.loads(cache.read_text(encoding='utf-8'))
            body={k:v for k,v in cached.items() if k!='content_fingerprint'}
            if body.get('identity')==identity and cached.get('content_fingerprint')==fingerprint(body) and body.get('ok'):
                return {**cached,'cache_hit':True,'external_search_calls':0}
        except (ValueError,TypeError,AttributeError):pass
    try:data=_invoke(query,limit,deps,env_file)
    except Exception as error:data={'ok':False,'papers':[],'error':f'IEEE MCP call failed ({type(error).__name__})'}
    result={'identity':identity,'retrieved_utc':datetime.now(timezone.utc).isoformat(),
            'transport':'mcp_stdio','ok':data.get('ok') is True,
            'papers':[normalize_paper(p) for p in data.get('papers',[])],
            'total_records':data.get('total_records'),'error':data.get('error')}
    result['content_fingerprint']=fingerprint(result)
    if result['ok']:
        tmp=cache.with_suffix('.tmp');tmp.write_text(json.dumps(result,indent=2,ensure_ascii=False),encoding='utf-8');tmp.replace(cache)
    return {**result,'cache_hit':False,'external_search_calls':1}
