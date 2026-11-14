"""Standalone local PDG inspector with provenance, audit and policy views."""
from collections import defaultdict,deque
import html
import json


def diagram_svg(graph):
    nodes={n['id']:n for n in graph['nodes']};adj=defaultdict(list);incoming={key:0 for key in nodes};rank={key:0 for key in nodes}
    for e in graph['edges']:adj[e['source']].append(e['target']);incoming[e['target']]+=1
    queue=deque(k for k,v in incoming.items() if not v)
    while queue:
        key=queue.popleft()
        for target in adj[key]:
            rank[target]=max(rank[target],rank[key]+1);incoming[target]-=1
            if not incoming[target]:queue.append(target)
    levels=defaultdict(list)
    for key in nodes:levels[rank[key]].append(key)
    height=max(420,max(map(len,levels.values()),default=1)*105+70);width=max(940,(max(levels,default=0)+1)*290+50)
    positions={}
    for level,keys in levels.items():
        for index,key in enumerate(keys):positions[key]=(25+level*290,35+(index+.5)*(height-70)/len(keys))
    out=[f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" role="img" aria-label="PDG 기능 의존관계. 배치는 시간 순서가 아닙니다.">',
        '<style>.node rect{fill:#f6f9fd;stroke:#c5d4e4}.node text{font:14px sans-serif;fill:#203147}.node .sub{font-size:11px;fill:#61748b}</style>',
        '<defs><marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path d="M0 0 L10 5 L0 10 Z" fill="#72849a"/></marker></defs>']
    for edge in graph['edges']:
        x,y=positions[edge['source']];tx,ty=positions[edge['target']];x+=225
        color='#258669' if edge['basis']=='datasheet_statement' else '#b67b2d'
        out.append(f'<path class="edge" data-edge="{html.escape(edge["id"],quote=True)}" data-origin="{edge["basis"]}" d="M{x} {y} C{x+65} {y} {tx-65} {ty} {tx} {ty}" fill="none" stroke="{color}" stroke-width="2" tabindex="0" role="button"><title>{html.escape(edge["relation"])}</title></path><polygon points="{tx},{ty} {tx-8},{ty-4} {tx-8},{ty+4}" fill="{color}" style="pointer-events:none"/>')
    for key,node in nodes.items():
        x,y=positions[key];label=node['label'];short=label if len(label)<29 else label[:26]+'…'
        sub=node['data'].get('role',node['type'])
        out.append(f'<g class="node" data-node="{html.escape(key,quote=True)}" tabindex="0" role="button" aria-label="{html.escape(label,quote=True)}"><title>{html.escape(label)}</title><rect x="{x}" y="{y-30}" width="225" height="60" rx="9" fill="#f6f9fd" stroke="#c5d4e4"/><text x="{x+12}" y="{y-4}" fill="#203147" font-family="Arial" font-size="14">{html.escape(short)}</text><text class="sub" x="{x+12}" y="{y+17}" fill="#61748b" font-family="Arial" font-size="11">{html.escape(sub)}</text></g>')
    out.append('</svg>');return '\n'.join(out)


def render_pdg_inspector(graph,audit,schedule,templates):
    payload=json.dumps({'graph':graph,'audit':audit,'schedule':schedule,'templates':templates},ensure_ascii=False).replace('<','\\u003c')
    title=html.escape(graph['target_product'])
    shell='''<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>PDG 검토</title>
<style>
*{box-sizing:border-box}body{margin:0;background:#f3f6fa;color:#203147;font:15px system-ui,sans-serif}main{max-width:1500px;margin:auto;padding:28px}h1{margin:0 0 8px}h2{font-size:18px}.muted{color:#61748b}.cards{display:flex;gap:12px;flex-wrap:wrap;margin:22px 0}.card{background:white;border:1px solid #dbe3ec;border-radius:12px;padding:16px;flex:1;min-width:145px}.value{font-size:25px;font-weight:700}.layout{display:grid;grid-template-columns:minmax(0,1fr) 350px;gap:18px}.panel{background:white;border:1px solid #dbe3ec;border-radius:12px;padding:18px}.diagram{overflow:auto;max-height:680px}.diagram svg{min-width:940px;width:100%}.node{cursor:pointer}.node rect{fill:#f6f9fd;stroke:#c5d4e4}.node:hover rect,.node:focus rect{stroke:#266da9;stroke-width:2}.node text{font:14px system-ui;fill:#203147}.node .sub{font-size:11px;fill:#61748b}.edge{cursor:pointer}.edge:hover,.edge:focus{stroke-width:5}pre{white-space:pre-wrap;word-break:break-word;font:12px ui-monospace,monospace;background:#f5f7fa;padding:12px;border-radius:8px}select{padding:8px;border:1px solid #bbcbdc;border-radius:6px}blockquote{margin:10px 0;padding:10px;background:#f6f9fd;border-left:3px solid #a6bdd4}summary{cursor:pointer}section{margin-top:20px}.legend{display:flex;align-items:center;gap:12px;flex-wrap:wrap}.green{color:#258669}.orange{color:#a26c22}li{margin:7px 0}table{border-collapse:collapse;width:100%}td,th{padding:9px;border-bottom:1px solid #e3e9f0;text-align:left}@media(max-width:950px){.layout{grid-template-columns:1fr}main{padding:14px}}
</style></head><body><main><h1>__TITLE__ · PDG 검토</h1><div class="muted">기능 의존관계와 검사 실행 정책을 구분합니다. 그래프의 왼쪽→오른쪽 배치는 핀 인가 순서를 뜻하지 않습니다.</div>
<div class="cards"><div class="card">논리 포트<div class="value" id="ports"></div></div><div class="card">채널<div class="value" id="channels"></div></div><div class="card">신호 경로<div class="value" id="paths"></div></div><div class="card">연결 검사<div class="value" id="errors"></div></div></div>
<div class="layout"><div class="panel"><div class="legend"><span class="green">● 원문 명시 관계</span><span class="orange">● 공학적 해석 관계</span><label>표시 <select id="origin"><option value="all">전체</option><option value="datasheet_statement">원문 명시</option><option value="engineering_interpretation">공학적 해석</option></select></label></div><div class="diagram">__SVG__</div></div>
<aside class="panel"><h2 id="detail-title">노드 또는 연결을 선택하세요</h2><div id="detail"></div></aside></div>
<section class="panel"><h2>검사별 실행 방식</h2><label>분석 <select id="analysis"><option value="op">DC 동작점</option><option value="dc">DC 스윕</option><option value="noise">잡음 분석</option><option value="ac">AC 주파수 응답</option><option value="tran">과도응답</option></select></label><ol id="operations"></ol><p id="schedule-status"></p><p class="muted">실제 회로·검사 항목·조건 유효성 판정은 아직 연결되지 않았습니다. 여기서 회로 시뮬레이션을 실행하지 않습니다.</p><details><summary>정책 입력과 생성 결과</summary><pre id="policy"></pre></details></section>
<section class="panel"><h2>확인 사항</h2><ul id="findings"></ul></section></main>
<script id="pdg-data" type="application/json">__DATA__</script><script>
const d=JSON.parse(document.getElementById('pdg-data').textContent),g=d.graph;
const $=id=>document.getElementById(id),nodes=new Map(g.nodes.map(n=>[n.id,n])),edges=new Map(g.edges.map(e=>[e.id,e]));
$('ports').textContent=g.summary.ports;$('channels').textContent=g.summary.channels;$('paths').textContent=d.audit.summary.present_signal_paths+' / '+d.audit.summary.expected_signal_paths;$('errors').textContent=d.audit.errors.length+'개 오류';
function add(parent,tag,text){const el=document.createElement(tag);el.textContent=text;parent.appendChild(el);return el;}
function show(kind,id){const n=kind==='node'?nodes.get(id):edges.get(id),box=$('detail');box.replaceChildren();$('detail-title').textContent=kind==='node'?n.label:nodes.get(n.source).label+' → '+nodes.get(n.target).label;
if(kind==='edge'){add(box,'p','출처: '+(n.basis==='datasheet_statement'?'원문 명시':'공학적 해석'));add(box,'p','수치 지연: '+(n.minimum_delay_s===null?'미정':n.minimum_delay_s+' s'));add(box,'p','시간 순서 강제: 없음');}
for(const e of n.evidence||[])add(box,'blockquote','PDF '+e.pdf_page+'쪽 · '+e.quote);
const details=add(box,'details','');add(details,'summary','연결 정보 자세히');add(details,'pre',JSON.stringify(n,null,2));}
for(const el of document.querySelectorAll('[data-node],[data-edge]')){const click=()=>show(el.dataset.node?'node':'edge',el.dataset.node||el.dataset.edge);el.addEventListener('click',click);el.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();click();}});}
$('origin').addEventListener('change',()=>{for(const path of document.querySelectorAll('.edge'))path.style.opacity=$('origin').value==='all'||path.dataset.origin===$('origin').value?'1':'.1';});
const labels={configure_bias_and_dc_sweep:'DC 바이어스·스윕 구성',solve_operating_points_across_sweep:'스윕별 동작점 계산',collect_dc_sweep_results:'DC 스윕 결과 수집',configure_bias_and_noise_models:'바이어스·잡음 모델 구성',run_noise_spectrum:'잡음 스펙트럼 분석',collect_noise_results:'잡음 결과 수집',configure_supplies_inputs_loads:'전원·입력·부하 구성',solve_dc_operating_point:'DC 동작점 계산',check_operating_point:'동작점 유효성 확인',configure_dc_bias_and_ac_sources:'DC 바이어스·AC 소스 구성',run_ac_sweep:'AC 주파수 스윕',collect_ac_results:'AC 측정 결과 수집',configure_transient_sources_and_initialization:'과도응답 소스·초기화 구성',run_transient_with_policy:'명시한 정책으로 과도응답 실행',check_pre_measurement_conditions:'측정 전 조건 유효성 확인',collect_transient_results:'과도응답 결과 수집'};
const sequence={dc:['configure_bias_and_dc_sweep','solve_operating_points_across_sweep','check_operating_point','collect_dc_sweep_results'],noise:['configure_bias_and_noise_models','solve_dc_operating_point','check_operating_point','run_noise_spectrum','collect_noise_results'],op:['configure_supplies_inputs_loads','solve_dc_operating_point','check_operating_point'],ac:['configure_dc_bias_and_ac_sources','solve_dc_operating_point','check_operating_point','run_ac_sweep','collect_ac_results'],tran:['configure_transient_sources_and_initialization','run_transient_with_policy','check_pre_measurement_conditions','collect_transient_results']};
function policy(){const a=$('analysis').value;$('operations').replaceChildren();for(const step of sequence[a])add($('operations'),'li',labels[step]);$('schedule-status').textContent=d.schedule.policy_applied&&d.schedule.analysis===a?'명시된 정책의 실행 순서를 생성했습니다. 실제 회로 실행 전 검사가 남아 있습니다.':'실행 정책 입력 대기 · 임의의 대기 시간을 채우지 않습니다.';$('policy').textContent=JSON.stringify(d.schedule.policy_applied&&d.schedule.analysis===a?d.schedule:d.templates[a],null,2);}
$('analysis').addEventListener('change',policy);policy();for(const item of g.ordering_exceptions)add($('findings'),'li',item.statement);for(const item of g.open_timing_questions)add($('findings'),'li',item);for(const item of d.audit.errors)add($('findings'),'li','오류: '+JSON.stringify(item));
</script></body></html>'''
    return shell.replace('__TITLE__',title).replace('__SVG__',diagram_svg(graph)).replace('__DATA__',payload)
