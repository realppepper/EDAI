"""Collect typical-characteristic chart evidence without adopting target values."""
import hashlib
import json
from pathlib import Path
import re
import pymupdf
from .support.source_checks import fingerprint
from .support.parse_identity import parse_image_issues


def caption_candidates(page):
    lines = []
    for block in page.get_text('dict')['blocks']:
        for line in block.get('lines', []):
            text = ''.join(s['text'] for s in line['spans'])
            lines.append({'text': text, 'bbox': list(line['bbox'])})
    captions = []
    for line in lines:
        match = re.match(r'Figure\s+(\d+-\d+)\.\s*(.*)', line['text'])
        if not match:
            continue
        title = match.group(2)
        box = line['bbox'][:]
        # A wrapped caption can be in a separate PDF text block.
        continuation = [x for x in lines if 0 <= x['bbox'][1]-box[3] <= 6
            and abs((x['bbox'][0]+x['bbox'][2])/2-(box[0]+box[2])/2) < 90
            and not x['text'].startswith('Figure')]
        if continuation:
            item = min(continuation, key=lambda x: x['bbox'][1])
            title += ' ' + item['text']; box[3] = item['bbox'][3]
        captions.append({'figure_number': match.group(1), 'title': title,
                         'bbox_points': box, 'source_text': line['text']})
    return captions


def match_caption(box, captions, page_rect):
    x = (box[0]+box[2])/2*page_rect.width
    bottom = box[3]*page_rect.height
    candidates = [c for c in captions if c['bbox_points'][1] >= bottom-8
        and c['bbox_points'][1]-bottom < page_rect.height*0.16
        and abs((c['bbox_points'][0]+c['bbox_points'][2])/2-x) < page_rect.width*0.22]
    return min(candidates, key=lambda c: c['bbox_points'][1]-bottom) if candidates else None


def collect_charts(run_dir):
    root = Path(run_dir)
    read = lambda name: json.loads((root/name).read_text(encoding='utf-8'))
    inventory=read('01_pdf_inventory.json'); plan=read('02_page_plan.json'); manifest=read('03_render_manifest.json')
    digest=hashlib.sha256(Path(inventory['source_pdf']).read_bytes()).hexdigest()
    if {inventory['sha256'],plan['source_sha256'],manifest['source_sha256']} != {digest}:
        raise ValueError('Chart source identity mismatch')
    images={p['pdf_page']:p for p in manifest['images']}
    selected=[p['pdf_page'] for p in plan['pages'] if 'target_typical_reference' in p['roles']]
    graphs=[]; missing=[]; page_coverage=[]
    with pymupdf.open(inventory['source_pdf']) as pdf:
        for number in selected:
            path=root/'pages'/f'page_{number:04d}.json'
            if not path.exists(): missing.append(number); continue
            parsed=json.loads(path.read_text(encoding='utf-8'))
            if parsed.get('status')!='ok' or parsed.get('source_sha256')!=digest or parsed.get('pdf_page')!=number:
                raise ValueError('Chart parse source/status mismatch')
            img=images[number]
            if parse_image_issues(parsed,img,digest):
                raise ValueError('Chart parse/render provenance mismatch')
            if hashlib.sha256(Path(img['image_path']).read_bytes()).hexdigest()!=img['image_sha256']:
                raise ValueError('Chart source image changed')
            page=pdf[number-1]; captions=caption_candidates(page); assigned=[]
            text=page.get_text()
            section=re.search(r'This typical characteristics section.*?\(unless otherwise noted\)\.',text,re.S)
            for index,block in enumerate(parsed['blocks']):
                if block['type']!='chart': continue
                coords=block.get('coordinates_normalized',[])
                xs=[c['value'] for c in coords if c['axis']=='x']; ys=[c['value'] for c in coords if c['axis']=='y']
                box=[min(xs),min(ys),max(xs),max(ys)] if len(xs)>=2 and len(ys)>=2 and page.rotation==0 else None
                caption=match_caption(box,captions,page.rect) if box else None
                if caption:assigned.append(caption['figure_number'])
                raw=block['text']; title=re.search(r'^title:\s*(.*)',raw,re.M)
                axes=dict(re.findall(r'^axis\[([^]]+)\]:\s*(.*)',raw,re.M))
                legend=re.search(r'^legend\[[^]]+\]:\s*items=(.*)',raw,re.M)
                identity=[digest,number,index,fingerprint(block)]
                graph={'id':'GRAPH-'+fingerprint(identity)[:20], 'source':{
                    'pdf_page':number,'parse_block_index':index,'bbox_normalized':box,
                    'page_image_path':img['image_path'],'page_image_sha256':img['image_sha256'],
                    'parse_block_fingerprint':fingerprint(block),'caption_candidate':caption},
                    'parsed_metadata':{'title':title.group(1) if title else None,'axes':axes,
                        'legend':legend.group(1).split(';') if legend else [],
                        'notes':re.findall(r'^note:\s*(.*)',raw,re.M)},
                    'raw_chart_text':raw,
                    'original_section_conditions_text':section.group(0) if section else None,
                    'review_status':'pending','reference_only':True,
                    'numeric_data':{'status':'unverified_parser_estimates','approved_for_design':False},
                    'acceptance_criterion':False}
                graphs.append(graph)
            page_coverage.append({'pdf_page':number,'source_caption_numbers':[c['figure_number'] for c in captions],
                'unmatched_source_figures':[c['figure_number'] for c in captions if c['figure_number'] not in assigned],
                'duplicate_caption_assignments':sorted({n for n in assigned if assigned.count(n)>1})})
    return {'stage':'chart_01_collect','source_sha256':digest,'target_product':plan['target_product'],
        'graphs':graphs,'coverage':{'selected_pages':selected,'missing_parse_pages':missing,'pages':page_coverage},
        'scope':'Typical-characteristic pages selected by page plan. Circuit diagrams and other images are not reconstructed.'}


def build_chart_review_packet(document):
    return {'document_fingerprint':fingerprint(document),'source_sha256':document['source_sha256'],
        'target_product':document['target_product'],'graphs':document['graphs'],
        'instructions':'Inspect original page images. Review figure/title, axes/scales/rail-relative units, legend, common and local conditions. Preserve temperature provenance. Keep typical graphs reference-only. Numeric estimates need separate point verification. Correct parser metadata through reviewed_metadata with explanation; never silently change raw evidence.'}
