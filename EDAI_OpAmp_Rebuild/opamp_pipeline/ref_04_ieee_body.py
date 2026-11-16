"""Official IEEE full-text endpoint only; abstract/login pages never count as body."""
import hashlib,re,urllib.request,urllib.parse,urllib.error
import xml.etree.ElementTree as ET

MAX_BYTES=8_000_000


def parse_body(xml,article_number):
    if '<!DOCTYPE' in xml.upper() or '<!ENTITY' in xml.upper():raise ValueError('External XML entities are not supported')
    root=ET.fromstring(xml)
    tag=lambda e:e.tag.rsplit('}',1)[-1].lower()
    if tag(root) not in {'response','article'}:raise ValueError('Not an IEEE/JATS article response')
    body=next((e for e in root.iter() if tag(e)=='body'),None)
    if body is None:raise ValueError('No article body; metadata/login/error is not full text')
    if not any(tag(e)=='sec' for e in body.iter()):raise ValueError('Article sections missing')
    blocks=[]
    def text(e):return ' '.join(' '.join(e.itertext()).split())
    def walk(e,section='Article body',section_id='body'):
        for child in e:
            kind=tag(child)
            if kind in {'abstract','ref-list','references'}:continue
            if kind=='sec':
                title=next((text(c) for c in child if tag(c)=='title'),section)
                walk(child,title,child.get('id',section_id))
            elif kind in {'p','disp-formula','table-wrap','fig'}:
                value=text(child)
                if value:
                    blocks.append({'id':f'{section_id}-b{len(blocks)+1}', 'section':section,
                        'section_id':section_id,'kind':kind,'text':value,
                        'figure_image_retrieved':False,'equation_interpretation_verified':False})
            elif kind not in {'title','label'}:walk(child,section,section_id)
    walk(body)
    paragraphs=[b for b in blocks if b['kind']=='p']
    if len(paragraphs)<2 or sum(len(b['text']) for b in paragraphs)<500:
        raise ValueError('Insufficient article body; not accepted as full-text evidence')
    return {'ok':True,'article_number':str(article_number),'full_text_retrieved':True,
            'evidence_scope':'article_body_text','source_url':f'https://ieeexplore.ieee.org/document/{article_number}',
            'source_xml':xml,'source_xml_sha256':hashlib.sha256(xml.encode('utf-8')).hexdigest(),
            'blocks':blocks,'body_characters':sum(len(b['text']) for b in blocks),
            'schematic_retrieved':False,'design_equations_verified':False}


def fetch_article_body(article_number,key):
    number=str(article_number)
    if not re.fullmatch(r'[0-9]{1,12}',number):return {'ok':False,'full_text_retrieved':False,'error':'Invalid article number'}
    if not key:return {'ok':False,'full_text_retrieved':False,'error':'Missing IEEE key'}
    url=f'https://ieeexploreapi.ieee.org/api/v1/search/document/{number}/fulltext?'+urllib.parse.urlencode({'apikey':key,'format':'xml'})
    req=urllib.request.Request(url,headers={'User-Agent':'EDAI-OpAmp-Rebuild/2.0','Accept':'application/xml'})
    try:
        with urllib.request.urlopen(req,timeout=25) as response:data=response.read(MAX_BYTES+1)
        if len(data)>MAX_BYTES:raise ValueError('Full-text response exceeds size limit')
        # Credentials are never persisted, even if an upstream payload echoes one.
        xml=data.decode('utf-8-sig').replace(key,'[redacted]')
        return parse_body(xml,number)
    except urllib.error.HTTPError as error:
        return {'ok':False,'article_number':number,'full_text_retrieved':False,
                'error':f'IEEE full-text HTTP {error.code}','access_denied':error.code in {401,403}}
    except Exception as error:
        return {'ok':False,'article_number':number,'full_text_retrieved':False,'error':f'IEEE full-text unavailable ({type(error).__name__})'}
