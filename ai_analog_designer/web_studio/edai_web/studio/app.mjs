import './pdf-compat.mjs';
import {DEFAULT_SPEC,BASE,CASES,LIMITS,validateSpec,evaluate,optimize,response,bode,extractTargets,chunkText,rankChunks} from './model.mjs';
const $=s=>document.querySelector(s),$$=s=>Array.from(document.querySelectorAll(s));
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const fmt=(n,d=1)=>Number(n).toFixed(d);
const icons={
sliders:'<path d="M4 7h16M4 17h16"/><circle cx="8" cy="7" r="3"/><circle cx="16" cy="17" r="3"/>',
layers:'<path d="m12 3 9 5-9 5-9-5 9-5Zm-9 10 9 5 9-5M3 18l9 5 9-5"/>',
grid:'<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/>',
file:'<path d="M14 3H5v18h14V8l-5-5Zm0 0v5h5M8 12h8M8 16h8"/>',
chart:'<path d="M3 3v18h18M6 15l4-7 4 5 6-9"/>',
help:'<circle cx="12" cy="12" r="9"/><path d="M9 9a3 3 0 0 1 6 0c0 2-3 2-3 5M12 17v.1"/>',
refresh:'<path d="M20 10a8 8 0 1 0-2 8M20 4v6h-6"/>',
play:'<path d="m8 4 12 8-12 8V4Z"/>',
link:'<path d="m10 14 4-4M9 16l-2 2a4 4 0 0 1-6-6l4-4a4 4 0 0 1 6 0M15 8l2-2a4 4 0 0 1 6 6l-4 4a4 4 0 0 1-6 0" transform="translate(0 -1)"/>',
plus:'<path d="M12 4v16M4 12h16"/>',
upload:'<path d="M12 16V3m-5 5 5-5 5 5M4 16v5h16v-5"/>',
download:'<path d="M12 3v13m-5-5 5 5 5-5M4 17v4h16v-4"/>',
search:'<circle cx="10" cy="10" r="6"/><path d="m15 15 6 6"/>',
code:'<path d="m8 6-6 6 6 6M16 6l6 6-6 6M14 3l-4 18"/>',
circuit:'<path d="M5 3v18l15-9L5 3ZM1 8h4M1 16h4M20 12h3M8 8h4M10 6v4M8 16h4"/>'
};
function icon(name){return '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'+(icons[name]||icons.file)+'</svg>';}
function hydrateIcons(root=document){root.querySelectorAll('[data-icon]').forEach(e=>e.innerHTML=icon(e.dataset.icon));}
const state={spec:{...DEFAULT_SPEC},baseline:evaluate(BASE,DEFAULT_SPEC),selected:evaluate(BASE,DEFAULT_SPEC),run:null,step:0,completed:0,manual:false,running:false,chart:'step',docs:[],chunks:[],caseFilter:'all',dirty:false};
let toastTimer,runTimer,pdfModule;
function toast(text){$('#toast').textContent=text;$('#toast').classList.add('show');clearTimeout(toastTimer);toastTimer=setTimeout(()=>$('#toast').classList.remove('show'),3800);}
function modal(title,html){$('#modal-title').textContent=title;$('#modal-body').innerHTML=html;hydrateIcons($('#modal-body'));$('#modal').showModal();}
$('#modal-close').addEventListener('click',()=>$('#modal').close());
$('#modal').addEventListener('click',e=>{if(e.target===$('#modal')){const r=$('#modal').getBoundingClientRect();if(e.clientX<r.left||e.clientX>r.right||e.clientY<r.top||e.clientY>r.bottom)$('#modal').close();}});
function showView(name){if(!['workspace','sources','cases','report'].includes(name))name='workspace';$$('.view').forEach(e=>e.classList.toggle('active',e.id==='view-'+name));$$('.nav-item').forEach(e=>{e.classList.toggle('active',e.dataset.view===name);e.setAttribute('aria-current',e.dataset.view===name?'page':'false');});$('#breadcrumb-current').textContent={workspace:'설계 워크스페이스',sources:'자료 & 근거',cases:'Test Case 라이브러리',report:'결과 리포트'}[name];if(name==='report')renderReport();if(name==='sources')renderSources();if(name==='cases')renderCases();history.replaceState(null,'','#'+name);window.scrollTo({top:0,behavior:'instant'});}
document.addEventListener('click',e=>{const el=e.target.closest('[data-view]');if(el){e.preventDefault();showView(el.dataset.view);}});
$('.brand').addEventListener('click',e=>{e.preventDefault();showView('workspace');});
const labels={gain:'폐루프 이득',pm:'위상마진',overshoot:'오버슈트',settling:'정착시간',power:'소비전력',bw:'대역폭',vdd:'전원',load:'부하'};
const units={gain:'V/V',pm:'°',overshoot:'%',settling:'μs',power:'mW',bw:'MHz',vdd:'V',load:'pF'};
const digits={pm:1,overshoot:1,settling:2,power:2,bw:3,gain:1};
function setForm(spec){for(const k of Object.keys(LIMITS))$('#spec-'+k).value=spec[k];$('#spec-priority').value=spec.priority;state.dirty=false;}
function readForm(){const obj=Object.fromEntries(new FormData($('#spec-form')));return validateSpec(obj);}
function lockForm(locked){$$('#spec-form input,#spec-form select,#spec-form button,#apply-manual,#reset-demo').forEach(e=>e.disabled=locked);}
function renderMetrics(){
 const cur=state.selected,s=state.spec,base=state.baseline;
 $('#metrics').innerHTML=['pm','overshoot','settling','power'].map(k=>{
 const pass=cur.pass[k],diff=cur[k]-base[k],better=k==='pm'?diff>0:diff<0;
 let delta=Math.abs(diff)<0.005?'초기 설계':(diff>0?'↑ ':'↓ ')+fmt(Math.abs(diff),k==='power'||k==='settling'?2:1)+units[k];
 return '<div class="metric '+(pass?'ok':'')+'"><div class="metric-top">'+labels[k]+'<small>'+(pass?'충족':'미달')+'</small></div><div class="metric-value">'+fmt(cur[k],k==='settling'||k==='power'?2:1)+'<span>'+units[k]+'</span></div><div class="metric-bottom"><span>목표 '+(k==='pm'?'≥ ':'≤ ')+s[k]+'</span><span class="metric-trend" style="color:'+(better?'#739365':Math.abs(diff)<.005?'#a1aa97':'#b58964')+'">'+delta+'</span></div></div>';
 }).join('');
 const badge=$('#pass-badge');badge.textContent=cur.passed+' / 5 목표 충족';badge.classList.toggle('pass',cur.feasible);
 const name=state.manual?'직접 조정한 설계':state.step===0?'초기 설계 분석':state.step===4?'선택 설계 분석':'중간 설계 · STEP '+state.step;
 $('#analysis-title').textContent=name;$('#analysis-sub').textContent=state.dirty?'목표 변경됨 · 실행해 적용':'Cc '+cur.cc+' pF / Ibias '+cur.ibias+' μA';
 $('#cc-value').textContent=cur.cc+' pF';$('#bias-value').textContent=cur.ibias+' μA';
 $('#cc-slider').value=cur.cc;$('#cc-output').textContent=cur.cc+' pF';$('#ibias-slider').value=cur.ibias;$('#ibias-output').textContent=cur.ibias+' μA';
 $('#flow-state').textContent=state.running?'후보 비교 중':cur.feasible?'선택 조건 충족':state.run?'조건별 결과 확인':'초기 설계 진단';
}
function pathPoints(points,x,y){return points.map((p,i)=>(i?'L':'M')+fmt(x(p[0]),2)+','+fmt(y(p[1]),2)).join(' ');}
function stepSvg(){
 const m=state.selected,b=state.baseline,W=760,H=255,l=49,r=18,top=21,bot=38;
 const maxT=Math.max(8,Math.min(150,Math.max(m.settling,b.settling)*1.7));
 const maxY=Math.ceil((1+Math.max(m.overshoot,b.overshoot)/100+.1)*10)/10;
 const x=t=>l+t/maxT*(W-l-r),y=v=>H-bot-v/maxY*(H-top-bot);
 let grid='',ticks='';
 for(let i=0;i<=4;i++){const t=maxT*i/4;grid+='<line x1="'+x(t)+'" y1="'+top+'" x2="'+x(t)+'" y2="'+(H-bot)+'" stroke="#f0f3eb"/>';ticks+='<text x="'+x(t)+'" y="'+(H-18)+'" text-anchor="middle">'+fmt(t,1)+'</text>';}
 for(let v=0;v<=maxY;v+=.5){grid+='<line x1="'+l+'" y1="'+y(v)+'" x2="'+(W-r)+'" y2="'+y(v)+'" stroke="#eaf0e2" stroke-dasharray="3 4"/>';ticks+='<text x="'+(l-10)+'" y="'+(y(v)+3)+'" text-anchor="end">'+fmt(v,1)+'</text>';}
 const pts=Array.from({length:460},(_,i)=>i*maxT/459);
 const before=pathPoints(pts.map(t=>[t,response(t,b)]),x,y),after=pathPoints(pts.map(t=>[t,response(t,m)]),x,y),marker=x(m.settling);
 return '<svg viewBox="0 0 '+W+' '+H+'" xmlns="http://www.w3.org/2000/svg"><title>정규화된 계단 응답. 초기 오버슈트 '+fmt(b.overshoot)+'%, 선택 '+fmt(m.overshoot)+'%. 시간 단위 마이크로초.</title><defs><clipPath id="step-clip"><rect x="'+l+'" y="'+top+'" width="'+(W-l-r)+'" height="'+(H-top-bot)+'"/></clipPath></defs><g fill="#9aab8a" font-size="9" font-family="inherit"><text x="'+l+'" y="10">정규화 출력 (최종값 = 1)</text><text x="'+(W-r)+'" y="'+(H-1)+'" text-anchor="end">시간 (μs)</text>'+ticks+'</g><rect x="'+l+'" y="'+y(1.02)+'" width="'+(W-l-r)+'" height="'+(y(.98)-y(1.02))+'" fill="#dbe9cd" opacity=".8"/>'+grid+'<line x1="'+l+'" y1="'+y(1)+'" x2="'+(W-r)+'" y2="'+y(1)+'" stroke="#b4c4a7" stroke-dasharray="4 4"/><g clip-path="url(#step-clip)"><path d="'+before+'" fill="none" stroke="#bdc9b5" stroke-width="2" stroke-dasharray="5 5"/><path d="'+after+'" fill="none" stroke="#477853" stroke-width="2.6" stroke-linecap="round"/><line x1="'+marker+'" y1="'+(top+18)+'" x2="'+marker+'" y2="'+(H-bot)+'" stroke="#d6b98f" stroke-dasharray="3 4"/></g><rect x="'+Math.max(l,Math.min(W-132,marker-46))+'" y="'+top+'" width="98" height="19" rx="4" fill="#fbf3e5"/><text x="'+(Math.max(l,Math.min(W-132,marker-46))+49)+'" y="'+(top+13)+'" fill="#b49369" text-anchor="middle" font-size="9">정착 '+fmt(m.settling,2)+' μs</text></svg>';
}
function bodeSvg(){
 const m=state.selected,b=state.baseline,W=760,H=285,l=48,r=21;
 const x=f=>l+(Math.log10(f)-3)/5*(W-l-r),yd=db=>20+(60-db)/120*100,yp=phase=>167+(-phase-90)/90*73;
 let grid='',txt='';
 [1e3,1e4,1e5,1e6,1e7,1e8].forEach((f,i)=>{grid+='<line x1="'+x(f)+'" y1="19" x2="'+x(f)+'" y2="245" stroke="#eef2e8"/>';txt+='<text x="'+x(f)+'" y="263" text-anchor="middle">'+['1k','10k','100k','1M','10M','100M'][i]+'</text>';});
 [60,30,0,-30,-60].forEach(d=>{grid+='<line x1="'+l+'" x2="'+(W-r)+'" y1="'+yd(d)+'" y2="'+yd(d)+'" stroke="'+(d===0?'#c1ceaf':'#edf2e5')+'" stroke-dasharray="3 4"/>';txt+='<text x="'+(l-8)+'" y="'+(yd(d)+3)+'" text-anchor="end">'+d+'</text>';});
 [-90,-135,-180].forEach(p=>{grid+='<line x1="'+l+'" x2="'+(W-r)+'" y1="'+yp(p)+'" y2="'+yp(p)+'" stroke="#edf2e5" stroke-dasharray="3 4"/>';txt+='<text x="'+(l-8)+'" y="'+(yp(p)+3)+'" text-anchor="end">'+p+'°</text>';});
 const fs=Array.from({length:240},(_,i)=>Math.pow(10,3+i/239*5));
 let paths='';for(const [v,color,dash]of [[b,'#bcc9af','5 5'],[m,'#477853','']]){
 const values=fs.map(f=>[f,bode(f,v)]);
 paths+='<path d="'+pathPoints(values.map(p=>[p[0],p[1].db]),x,yd)+'" fill="none" stroke="'+color+'" stroke-width="2.2" stroke-dasharray="'+dash+'" clip-path="url(#bode-clip)"/><path d="'+pathPoints(values.map(p=>[p[0],p[1].phase]),x,yp)+'" fill="none" stroke="'+color+'" stroke-width="2.2" stroke-dasharray="'+dash+'"/>';
 }
 const cross=x(m.fc*1e6),phase=yp(-180+m.pm);
 return '<svg viewBox="0 0 '+W+' '+H+'" xmlns="http://www.w3.org/2000/svg"><title>예시 루프 전달함수의 이득 및 위상. 0 dB 교차점의 위상마진 '+fmt(m.pm)+'도.</title><defs><clipPath id="bode-clip"><rect x="'+l+'" y="20" width="'+(W-l-r)+'" height="100"/></clipPath></defs>'+grid+'<g fill="#98a989" font-size="9"><text x="'+l+'" y="11">루프 이득 (dB)</text><text x="'+l+'" y="155">루프 위상 (°)</text><text x="'+(W-r)+'" y="282" text-anchor="end">주파수 (Hz, 로그 축)</text>'+txt+'</g>'+paths+'<line x1="'+cross+'" y1="20" x2="'+cross+'" y2="240" stroke="#d1b286" stroke-dasharray="3 4"/><line x1="'+cross+'" y1="'+phase+'" x2="'+cross+'" y2="240" stroke="#cba374" stroke-width="3"/><circle cx="'+cross+'" cy="'+yd(0)+'" r="3.5" fill="#477853"/><text x="'+(Math.min(cross+9,W-99))+'" y="226" fill="#b09062" font-size="10">PM '+fmt(m.pm)+'°</text></svg>';
}
function renderChart(){
 $('#response-chart').innerHTML=state.chart==='step'?stepSvg():bodeSvg();
 $('#response-chart').setAttribute('aria-label',state.chart==='step'?'정규화 스텝 응답 전후 비교':'루프 이득 및 위상 Bode plot 비교');
 $('#legend-target').style.display=state.chart==='step'?'flex':'none';
 const m=state.selected,s=state.spec;
 $('#chart-insight').innerHTML=state.chart==='step'?'대역폭 <strong>'+fmt(m.bw,3)+' MHz</strong> · 목표 ≥ '+s.bw+' MHz <strong>'+(m.pass.bw?'충족':'미달')+'</strong>':'0 dB 교차 <strong>'+fmt(m.fc,3)+' MHz</strong> · PM = 180° + ∠L(jωc)';
}
$$('[data-chart]').forEach(el=>el.addEventListener('click',()=>{state.chart=el.dataset.chart;$$('[data-chart]').forEach(e=>e.classList.toggle('active',e===el));renderChart();}));
function renderIterations(){
 $('#iteration-track').innerHTML=[0,1,2,3,4].map(i=>{const m=state.run?.states[i];const ready=i===0||Boolean(m&&i<=state.completed);let c=i===state.step&&!state.manual?'current':'';if(i===4&&ready&&i!==state.step)c='selected';
 return '<button class="iteration '+c+'" data-step="'+i+'" '+(!ready?'disabled':'')+' aria-label="'+(i===0?'초기':i===4?'선택':'중간 '+i)+' 설계 보기" aria-pressed="'+(i===state.step&&!state.manual)+'"><span class="step-node">'+(i===4&&ready?'✓':String(i).padStart(2,'0'))+'</span><strong>'+['초기 설계','안정성 조정','전력 균형','조건 점검','선택 설계'][i]+'</strong><small>'+(ready?fmt((m||state.baseline).pm)+'° PM':'계산 대기')+'</small></button>';
 }).join('');
 $$('#iteration-track [data-step]').forEach(e=>e.addEventListener('click',()=>{if(state.running)return;state.step=Number(e.dataset.step);state.selected=state.run?state.run.states[state.step]:state.baseline;state.manual=false;renderWorkspace();}));
 const m=state.selected,b=state.baseline;
 let message='현재 <strong>'+m.passed+'개 목표</strong>를 충족합니다. 최적화를 실행해 변경할 설계값과 이유를 확인하세요.';
 if(state.manual)message='직접 조정한 Cc <strong>'+m.cc+' pF</strong> / Ibias <strong>'+m.ibias+' μA</strong>의 결과입니다.';
 else if(state.run){message='Cc <strong>'+b.cc+' → '+m.cc+' pF</strong> · Ibias <strong>'+b.ibias+' → '+m.ibias+' μA</strong>. '+(m.feasible?'선택 조건을 모두 충족합니다.':'미충족 조건 '+(5-m.passed)+'개를 확인하세요.');}
 if(state.run&&state.run.feasibleCount===0)message+='<br><strong>탐색 범위 안에서 모든 목표를 만족하는 후보가 없습니다.</strong> 미충족 조건 또는 탐색 범위를 조정해 주세요.';
 $('#iteration-insight').innerHTML='<span class="insight-icon">'+(m.feasible?'✓':'↗')+'</span><span>'+message+'</span>';
 $('#round-pill').textContent=state.manual?'MANUAL':state.running?'CALCULATING':state.run?'STEP '+state.step+' / 4':'INITIAL';
 $('#iteration-description').textContent=state.run?'285개 조합 · 조건 충족 '+state.run.feasibleCount+'개 · 단계를 눌러 비교하세요.':'최적화를 실행하면 단계별 설계와 근거가 연결됩니다.';
}
function renderDiagnosis(){
 const m=state.selected,s=state.spec;let list=[];
 if(!m.pass.pm||!m.pass.overshoot)list.push({ok:false,title:'안정성 보강이 필요해요',body:'PM '+fmt(m.pm)+'°, 오버슈트 '+fmt(m.overshoot)+'%. 이 예시 모델에서는 Cc를 늘리면 감쇠가 커지지만 속도가 낮아질 수 있습니다.',q:'compensation'});
 else list.push({ok:true,title:'설정한 안정성 목표를 충족했어요',body:'위상마진과 오버슈트가 목표 범위입니다. 실제 회로에서는 공정·전압·온도와 부하를 바꿔 다시 검증해야 합니다.',q:'phase'});
 if(!m.pass.power)list.push({ok:false,title:'전력 예산을 초과했어요',body:fmt(m.power,2)+' mW / 목표 '+s.power+' mW. Ibias를 낮출 때 속도 조건도 함께 확인하세요.',q:'power'});
 else if(!m.pass.bw||!m.pass.settling)list.push({ok:false,title:'속도 조건을 다시 확인하세요',body:'대역폭 '+fmt(m.bw,3)+' MHz, 정착시간 '+fmt(m.settling,2)+' μs. Cc와 Ibias의 균형을 다시 탐색해 보세요.',q:'bandwidth'});
 else list.push({ok:true,title:'전력과 응답 속도도 함께 확인했어요',body:'전력 '+fmt(m.power,2)+' mW, 대역폭 '+fmt(m.bw,3)+' MHz. 이는 선언한 예시 모델의 범위에서만 유효합니다.',q:'power'});
 $('#diagnosis').innerHTML=list.map(d=>'<div class="diagnosis-item '+(d.ok?'ok':'')+'"><span class="diagnosis-icon">'+(d.ok?'✓':'↗')+'</span><div><strong>'+d.title+'</strong><p>'+d.body+'</p><button class="text-link" data-evidence-query="'+d.q+'">관련 예시 근거 보기 ↗</button></div></div>').join('');
 $$('#diagnosis [data-evidence-query]').forEach(e=>e.addEventListener('click',()=>{showView('sources');$('#evidence-search').value=e.dataset.evidenceQuery;renderEvidence();}));
}
function renderSchematic(){
 const m=state.selected;
 $('#schematic').innerHTML='<svg viewBox="0 0 340 125" xmlns="http://www.w3.org/2000/svg"><title>입력, 차동 증폭단, 이득단, 출력, 피드백의 기능 블록 개념도.</title><g fill="none" stroke="#9daf8f" stroke-width="1.5"><path d="M10 66h43m54 0h24m75 0h37m64 0h23M300 67v40H68V88"/><rect x="53" y="46" width="55" height="42" rx="5"/><rect x="131" y="46" width="75" height="42" rx="5"/><rect x="244" y="46" width="63" height="42" rx="5"/><path d="M159 46V24h35m9 0h24v42M194 17v14m9-14v14M21 63v6M18 66h6M65 77h8"/></g><g fill="#839873" font-size="10" text-anchor="middle"><text x="80" y="72">차동 입력</text><text x="169" y="72">전압 이득</text><text x="275" y="72">출력</text><text x="18" y="52">Vin</text><text x="322" y="52">Vout</text><text x="179" y="122">저항 피드백 · G = '+state.spec.gain+' V/V</text></g><rect x="164" y="0" width="72" height="16" rx="4" fill="#f8eddd"/><text x="200" y="11" text-anchor="middle" font-size="9" fill="#b18b58">Cc '+m.cc+' pF</text><circle cx="226" cy="66" r="2.5" fill="#8b9f7b"/></svg>';
}
function renderWorkspace(){renderMetrics();renderChart();renderIterations();renderDiagnosis();renderSchematic();}
$('#spec-form').addEventListener('input',()=>{state.dirty=true;$('#analysis-sub').textContent='목표 변경됨 · 실행해 적용';$('#spec-error').textContent='';});
$('#spec-form').addEventListener('submit',e=>{
 e.preventDefault();if(state.running)return;
 let s;try{s=readForm();}catch(err){$('#spec-error').textContent=err.message;return;}
 state.spec=s;state.baseline=evaluate(BASE,s);state.run=optimize(s);state.completed=0;state.step=0;state.selected=state.baseline;state.manual=false;state.dirty=false;state.running=true;lockForm(true);
 $('#optimize-button').innerHTML='<span class="spin">'+icon('refresh')+'</span>설계 경로 계산 중';renderWorkspace();
 const delay=matchMedia('(prefers-reduced-motion: reduce)').matches?20:550;
 function advance(){state.completed++;state.step=state.completed;state.selected=state.run.states[state.step];renderWorkspace();if(state.completed<4)runTimer=setTimeout(advance,delay);else{state.running=false;lockForm(false);$('#optimize-button').innerHTML=icon('play')+'최적화 다시 실행<span class="button-arrow">→</span>';renderWorkspace();toast(state.run.feasibleCount?'조건을 만족하는 '+state.run.feasibleCount+'개 후보 중 선택했어요.':'탐색 범위 안에서 모든 목표를 만족하는 후보가 없어요.');}}
 runTimer=setTimeout(advance,delay);
});
$('#cc-slider').addEventListener('input',e=>$('#cc-output').textContent=e.target.value+' pF');
$('#ibias-slider').addEventListener('input',e=>$('#ibias-output').textContent=e.target.value+' μA');
$('#apply-manual').addEventListener('click',()=>{
 if(state.running)return;
 let s;try{s=readForm();}catch(err){$('#spec-error').textContent=err.message;return;}
 const p={cc:Number($('#cc-slider').value),ibias:Number($('#ibias-slider').value)};
 if(JSON.stringify(s)!==JSON.stringify(state.spec)){state.run=null;state.completed=0;state.step=0;}
 state.spec=s;state.baseline=evaluate(BASE,s);state.selected=evaluate(p,s);state.manual=true;state.dirty=false;renderWorkspace();toast('직접 조정한 값으로 다시 계산했어요.');
});
$('#reset-demo').addEventListener('click',()=>{clearTimeout(runTimer);state.running=false;state.spec={...DEFAULT_SPEC};state.baseline=evaluate(BASE,state.spec);state.selected=state.baseline;state.run=null;state.step=0;state.completed=0;state.manual=false;setForm(state.spec);$('#spec-error').textContent='';lockForm(false);$('#optimize-button').innerHTML=icon('play')+'최적화 실행<span class="button-arrow">→</span>';renderWorkspace();toast('예시 목표와 초기 설계값을 불러왔어요.');});
function addDoc(doc){state.docs.push(doc);for(const page of doc.pages){const chunks=chunkText(page.text);chunks.forEach((text,i)=>state.chunks.push({id:doc.id+'-'+page.page+'-'+i,docId:doc.id,name:doc.name,page:page.page,text,demo:doc.demo}));}}
function renderSources(){
 $('#source-count').textContent=state.docs.length;$('#document-total').textContent=state.docs.length+'개 문서';
 const chunkCount=state.chunks.length;$('#flow-source').textContent=state.docs.length+'개 문서 · '+chunkCount+'개 텍스트 조각';
 $('#upload-summary').textContent=state.docs.length+'개 자료 연결됨 · 브라우저 세션에만 보관';
 $('#document-list').innerHTML=state.docs.length?state.docs.map(d=>'<div class="document-card"><span class="file-icon">'+esc(d.type)+'</span><div><strong>'+esc(d.name)+'</strong><small>'+(d.demo?'예시 자료':'사용자 자료')+' · '+d.pages.length+' '+(d.type==='PDF'?'쪽':'단위')+' · '+(d.note?esc(d.note):'텍스트 준비됨')+'</small></div><span class="doc-actions"><button data-doc-open="'+esc(d.id)+'">원문</button>'+(!d.demo?'<button data-doc-remove="'+esc(d.id)+'" aria-label="'+esc(d.name)+' 삭제">✕</button>':'')+'</span></div>').join(''):'<div class="empty-state">자료를 추가해 주세요.</div>';
 $$('[data-doc-open]').forEach(e=>e.addEventListener('click',()=>openDoc(e.dataset.docOpen)));
 $$('[data-doc-remove]').forEach(e=>e.addEventListener('click',()=>{const d=state.docs.find(x=>x.id===e.dataset.docRemove);if(d?.url)URL.revokeObjectURL(d.url);state.docs=state.docs.filter(x=>x.id!==e.dataset.docRemove);state.chunks=state.chunks.filter(x=>x.docId!==e.dataset.docRemove);renderSources();toast('자료를 제거했어요.');}));
 renderTargets();renderEvidence();
}
function openDoc(id,page=1){
 const d=state.docs.find(x=>x.id===id);if(!d)return;
 const p=d.pages.find(x=>x.page===page)||d.pages[0];
 modal(d.name+' · '+(d.type==='PDF'?'p.':'단위 ')+p.page,'<p class="small">'+(d.demo?'이 문서는 직접 만든 가상의 예시 자료입니다.':'문서에서 추출한 원문입니다. 표 구조와 단위는 원본에서 다시 확인하세요.')+'</p>'+(d.url?'<p><a href="'+esc(d.url)+'#page='+p.page+'" target="_blank" rel="noopener noreferrer">원본 파일 열기 ↗</a></p>':'')+'<pre>'+esc(p.text||'(선택 가능한 텍스트 없음)')+'</pre>'+(d.pages.length>1?'<label>페이지 <select id="source-page">'+d.pages.map(v=>'<option value="'+v.page+'" '+(v.page===p.page?'selected':'')+'>'+v.page+'</option>').join('')+'</select></label>':''));
 $('#source-page')?.addEventListener('change',e=>{const n=Number(e.target.value);$('#modal').close();openDoc(id,n);});
}
function renderTargets(){
 const ds=state.docs.map(d=>({doc:d,targets:extractTargets(d.pages.map(p=>p.text).join('\n'))})).filter(x=>Object.keys(x.targets).length);
 $('#extracted-targets').innerHTML=ds.length?ds.map(x=>'<div class="target-card"><strong>'+esc(x.doc.name)+'</strong><div class="target-fields">'+Object.entries(x.targets).map(([k,v])=>'<span>'+labels[k]+' '+v+' '+units[k]+'</span>').join('')+'</div><button class="button secondary" data-target-doc="'+esc(x.doc.id)+'">이 목표를 입력란에 적용 →</button></div>').join(''):'<div class="empty-state">명시적인 목표 키가 없습니다.<br>설계 입력에서 스펙을 직접 입력하세요.</div>';
 $$('[data-target-doc]').forEach(e=>e.addEventListener('click',()=>{if(state.running){toast('계산이 끝나면 목표를 적용해 주세요.');return;}const row=ds.find(x=>x.doc.id===e.dataset.targetDoc);for(const[k,v]of Object.entries(row.targets))$('#spec-'+k).value=v;state.dirty=true;$('#analysis-sub').textContent='자료에서 목표 적용됨 · 실행해 반영';showView('workspace');toast('목표 입력란에 적용했어요. 최적화 실행을 눌러 주세요.');}));
}
function renderEvidence(){
 const q=$('#evidence-search').value.trim(),all=rankChunks(state.chunks,q),show=all.slice(0,8);
 $('#evidence-stats').textContent=state.docs.length+'개 문서 · '+state.chunks.length+'개 텍스트 조각 · 검색 결과 '+all.length+'개'+(all.length>8?' (상위 8개 표시)':'');
 $('#evidence-list').innerHTML=show.length?show.map((c,i)=>'<article class="evidence-card"><h3><span class="label-light">'+(c.demo?'DEMO':'DOC')+'</span> '+esc(c.name)+'</h3><p>'+esc(c.text.slice(0,325))+(c.text.length>325?'…':'')+'</p><div class="source-loc"><span>p./단위 '+c.page+' · 근거 '+(i+1)+(q?' · 일치 단어 '+c.rank+'개':'')+'</span><button data-chunk="'+esc(c.id)+'">원문 확인 ↗</button></div></article>').join(''):'<div class="empty-state"><strong>일치하는 근거가 없어요.</strong>다른 키워드로 검색하거나 자료를 추가해 주세요.<br>의미 검색·RAG는 아직 연결되지 않았습니다.</div>';
 $$('[data-chunk]').forEach(e=>e.addEventListener('click',()=>{const c=state.chunks.find(x=>x.id===e.dataset.chunk);if(c)openDoc(c.docId,c.page);}));
}
$('#evidence-search').addEventListener('input',renderEvidence);
$$('[data-query]').forEach(e=>e.addEventListener('click',()=>{$('#evidence-search').value=e.dataset.query;renderEvidence();}));
async function getPDF(){if(!pdfModule){pdfModule=await import('./vendor/pdf.mjs');pdfModule.GlobalWorkerOptions.workerSrc=new URL('./vendor/pdf.worker.compat.mjs',import.meta.url).href;}return pdfModule;}
async function acceptFiles(list){
 const files=Array.from(list);if(!files.length)return;
 if(files.length>12){toast('한 번에 최대 12개 파일을 추가해 주세요.');return;}
 const status=$('#upload-status');$('#file-input').disabled=true;
 const messages=[];
 for(const file of files){
  status.textContent=file.name+' 텍스트 읽는 중…';
  if(file.size>10*1024*1024){messages.push(file.name+': 10 MB 초과');continue;}
  if(state.docs.some(d=>d.fingerprint===file.name+'|'+file.size+'|'+file.lastModified)){messages.push(file.name+': 이미 추가됨');continue;}
  if(state.docs.length>=30){messages.push('최대 30개 문서까지 처리할 수 있습니다.');break;}
  try{
   const type=file.name.split('.').pop().toLowerCase();
   if(!['pdf','txt','json'].includes(type))throw Error('PDF, TXT, JSON 형식만 지원합니다.');
   const doc={id:'user-'+Date.now()+'-'+Math.random().toString(36).slice(2,7),name:file.name,type:type.toUpperCase(),pages:[],demo:false,fingerprint:file.name+'|'+file.size+'|'+file.lastModified};
   if(type==='pdf'){
    const pdfjs=await getPDF();let pdf;
    try{
     const task=pdfjs.getDocument({data:new Uint8Array(await file.arrayBuffer()),isEvalSupported:false,useSystemFonts:true});
     task.onPassword=()=>task.destroy();pdf=await task.promise;
     const max=Math.min(pdf.numPages,80);
     for(let p=1;p<=max;p++){status.textContent=file.name+' · '+p+' / '+max+'쪽 분석 중';const pg=await pdf.getPage(p);const tc=await pg.getTextContent();const text=tc.items.map(i=>i.str+(i.hasEOL?'\n':' ')).join('');doc.pages.push({page:p,text});pg.cleanup();}
     if(pdf.numPages>80)doc.note='전체 '+pdf.numPages+'쪽 중 앞 80쪽만 분석';
     const total=doc.pages.reduce((n,p)=>n+p.text.trim().length,0);
     if(total<30)doc.note='텍스트 부족 · 스캔 PDF는 OCR 필요';
    }finally{if(pdf)await pdf.destroy();}
    doc.url=URL.createObjectURL(file);
   }else{
    const text=await file.text();let content=text;
    let records=null;
    if(type==='json'){
     const data=JSON.parse(text);content=JSON.stringify(data,null,2);
     if(content.length>300000)throw Error('텍스트가 너무 많습니다. 30만 자 이하로 나누어 추가해 주세요.');
     if(Array.isArray(data.records)){
      if(data.records.length>1000)throw Error('한 JSON에 최대 1,000개 레코드까지 지원합니다.');
      records=data.records;content=JSON.stringify({...data,records:undefined},null,2);
      doc.note=records.length+'개 레코드 · 개별 근거로 색인';
     }
     if(data.targets)content+='\n'+Object.entries(data.targets).map(([k,v])=>k+'='+v).join('\n');
    }
    if(content.length>300000)throw Error('텍스트가 너무 많습니다. 30만 자 이하로 나누어 추가해 주세요.');
    doc.pages=[{page:1,text:content},...(records||[]).map((r,i)=>({page:i+2,text:JSON.stringify(r,null,2)}))];
   }
   addDoc(doc);messages.push(file.name+': '+(doc.note||'추가 완료'));
  }catch(err){messages.push(file.name+': '+(err.name==='PasswordException'?'암호 PDF는 지원하지 않습니다.':err.message||'파일을 읽지 못했습니다.'));}
 }
 status.textContent=messages.join('\n');status.style.whiteSpace='pre-line';$('#file-input').disabled=false;$('#file-input').value='';renderSources();
}
$('#file-input').addEventListener('change',e=>acceptFiles(e.target.files));
const dz=$('#dropzone');['dragenter','dragover'].forEach(t=>dz.addEventListener(t,e=>{e.preventDefault();dz.classList.add('drag');}));['dragleave','drop'].forEach(t=>dz.addEventListener(t,e=>{e.preventDefault();dz.classList.remove('drag');}));dz.addEventListener('drop',e=>{if(!$('#file-input').disabled)acceptFiles(e.dataTransfer.files);});
function renderCases(){
 const q=$('#case-search').value.toLowerCase().trim();
 const rows=CASES.filter(c=>(!q||(c.id+' '+c.name+' '+c.ko).toLowerCase().includes(q))&&(state.caseFilter==='all'||state.caseFilter==='ready'&&c.available||state.caseFilter==='differential'&&c.group==='차동 증폭기'));
 $('#case-grid').innerHTML=rows.length?rows.map(c=>'<article class="case-card '+(c.available?'ready':'')+'"><div class="case-card-top">CASE '+String(c.id).padStart(2,'0')+'<span>'+(c.available?'해석 모델 연결됨':'참고 목록')+'</span></div><h3>'+c.ko+'</h3><p>'+c.name+'</p><button class="text-link" data-case="'+c.id+'">'+(c.available?'이 회로로 시작하기 →':'회로 범위 확인 ↗')+'</button></article>').join(''):'<div class="empty-state">일치하는 회로가 없어요.</div>';
 $$('[data-case]').forEach(e=>e.addEventListener('click',()=>{const c=CASES.find(c=>c.id===Number(e.dataset.case));if(c.available){showView('workspace');toast('Case 13의 예시 해석 모델이 선택되어 있어요.');}else modal('Case '+c.id+' · '+c.ko,'<p>'+esc(c.name)+'</p><p>첨부 이미지에 포함된 회로 후보입니다. 현재는 목록과 분류만 정리되어 있고, 이 회로의 토폴로지·소자 모델·SPICE 실행은 구현되어 있지 않습니다.</p><p>팀원의 넷리스트, 시뮬레이션 결과와 측정 조건을 연결한 뒤 이 화면을 확장할 수 있습니다.</p>'+(c.id===14?'<p><strong>래치 비교기는 Op-Amp와 평가 항목이 다릅니다.</strong> 위상마진 대신 결정 지연, 오프셋, 에너지 등 목적에 맞는 지표를 별도로 정의해야 합니다.</p>':''));}));
}
$('#case-search').addEventListener('input',renderCases);$$('[data-case-filter]').forEach(e=>e.addEventListener('click',()=>{state.caseFilter=e.dataset.caseFilter;$$('[data-case-filter]').forEach(b=>b.classList.toggle('active',b===e));renderCases();}));
$('#reference-open').addEventListener('click',()=>modal('첨부한 테스트 회로 목록','<img src="assets/test-cases-reference.png" alt="사용자가 제공한 15개 테스트 회로 목록"><p>첨부 목록의 이름을 그대로 보존했습니다. 13번을 데모의 개념적 출발점으로 선택했습니다.</p>'));
function makeReportData(){
 return {schema_version:'edai-demo-1.0',generated_at:new Date().toISOString(),project:'EDAI Circuit Studio',case_id:13,provenance:{kind:'synthetic_analytical_model',is_spice_result:false,is_vlm_result:false,is_transistor_design:false,trace_kind:'interpolated_design_path',note:'Synthetic second-order model with invented Cc/Ibias mapping. Middle steps are explanatory interpolation, not optimization iteration logs.'},targets:{...state.spec},initial:state.baseline,selected:state.selected,selection:state.manual?'manual':state.step===0?'initial':state.step===4?'grid_selected':'intermediate',search:state.run?{candidate_count:285,feasible_count:state.run.feasibleCount,best:state.run.best}:null,design_path:state.run?.states||[state.baseline],documents:state.docs.map(d=>({name:d.name,is_demo:d.demo,page_count:d.pages.length,note:d.note||null})),not_validated:['transistor sizing','PVT corners','mismatch','noise','slew rate','output swing','real power','SPICE execution','VLM inference']};
}
function reportMarkup(){
 const m=state.selected,b=state.baseline,s=state.spec;
 const title=state.manual?'직접 조정한 설계':state.step===0?'초기 설계':state.step===4?'탐색 후 선택 설계':'중간 설계 '+state.step;
 const desc=m.feasible?'선택한 5개 성능 조건을 모두 충족했습니다.':'5개 성능 조건 중 '+(5-m.passed)+'개가 미충족입니다.';
 return '<div class="report-eyebrow">EDAI / MODEL REVIEW / CASE 13</div><h2>'+title+' 검토</h2><p>'+desc+' 아래 값은 가상의 파라미터 매핑을 사용하는 2차 해석 모델로 계산했습니다.</p><div class="report-summary"><span><strong>'+m.passed+' / 5</strong>목표 조건 충족</span><span><strong>'+fmt(m.pm)+'°</strong>위상마진</span><span><strong>'+fmt(m.power,2)+'</strong>전력 예시 · mW</span></div><h3>목표와 결과 비교</h3><table class="report-table"><thead><tr><th>지표</th><th>목표</th><th>초기</th><th>선택</th><th>판정</th></tr></thead><tbody>'+['pm','overshoot','settling','power','bw'].map(k=>'<tr><td>'+labels[k]+'<br><small>'+units[k]+'</small></td><td>'+(k==='pm'||k==='bw'?'≥ ':'≤ ')+s[k]+'</td><td>'+fmt(b[k],digits[k])+'</td><td>'+fmt(m[k],digits[k])+'</td><td class="'+(m.pass[k]?'good':'bad')+'">'+(m.pass[k]?'충족':'미달')+'</td></tr>').join('')+'</tbody></table><h3>변경한 설계값</h3><p>보상 커패시터 Cc: <strong>'+b.cc+' → '+m.cc+' pF</strong><br>바이어스 전류 Ibias: <strong>'+b.ibias+' → '+m.ibias+' μA</strong><br>폐루프 이득 '+s.gain+' V/V · 전원 '+s.vdd+' V · 부하 '+s.load+' pF</p><h3>선택 방법</h3><p>'+(state.run?'Cc 2–16 pF (1 pF 간격), Ibias 60–240 μA (10 μA 간격), 총 285개 조합을 비교했습니다. 목표 위반을 먼저 최소화하고 '+{balanced:'균형',stability:'안정성',speed:'속도',power:'저전력'}[s.priority]+' 우선순위로 선택했습니다. 조건을 만족한 후보는 '+state.run.feasibleCount+'개입니다.':'현재는 초기값 또는 수동 조정값입니다. 전체 조합 최적화는 아직 실행하지 않았습니다.')+'</p><h3>자료와 근거</h3><ul class="report-notes">'+state.docs.map(d=>'<li>'+esc(d.name)+' ('+(d.demo?'가상 예시':'사용자 업로드')+', '+d.pages.length+'쪽/단위)</li>').join('')+'</ul><h3>해석 범위와 남은 검증</h3><ul class="report-notes"><li>실제 CMOS 소자 사이징, SPICE 실행, VLM 추론 결과가 아닙니다.</li><li>전력은 전류 가정으로 만든 예시 값이며, 전달함수 자체의 소비전력이 아닙니다.</li><li>과도 응답과 Bode plot은 같은 2차 모델에서 계산했습니다. 정착시간은 ±2% 조건으로 수치 추정합니다.</li><li>중간 단계는 선택 설계까지 보간한 설명용 설계 경로입니다.</li><li>PVT, 노이즈, 슬루율, 출력 스윙과 실제 회로 구현을 추가 검증해야 합니다.</li></ul>';
}
function renderReport(){$('#report-content').innerHTML=reportMarkup();}
function download(name,text,type='text/plain;charset=utf-8'){const u=URL.createObjectURL(new Blob([text],{type}));const a=document.createElement('a');a.href=u;a.download=name;document.body.appendChild(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(u),10000);}
function exportWave(){const a=state.baseline,b=state.selected,end=Math.max(8,Math.max(a.settling,b.settling)*1.7);const rows=['# EDAI synthetic analytical model - not SPICE measurements','time_us,initial_normalized,selected_normalized'];for(let i=0;i<=1000;i++){const t=end*i/1000;rows.push([fmt(t,6),fmt(response(t,a),8),fmt(response(t,b),8)].join(','));}download('EDAI_waveform_demo.csv',rows.join('\n'),'text/csv;charset=utf-8');toast('비교 파형을 저장했어요.');}
$('#wave-export').addEventListener('click',exportWave);$('#report-wave-export').addEventListener('click',exportWave);
$('#json-export').addEventListener('click',()=>{download('EDAI_design_result_demo.json',JSON.stringify(makeReportData(),null,2),'application/json');toast('결과 JSON을 저장했어요.');});
$('#report-download').addEventListener('click',()=>{const html='<!doctype html><html lang="ko"><meta charset="utf-8"><title>EDAI 예시 설계 리포트</title><style>body{font-family:Arial,"Malgun Gothic",sans-serif;max-width:900px;margin:50px auto;padding:0 30px;color:#28412f;font-size:14px;line-height:1.8}table{border-collapse:collapse;width:100%}th,td{padding:10px;text-align:left;border-bottom:1px solid #dbe4d7}th{background:#f1f6ec}h2{font-size:25px}h3{margin-top:28px}.report-summary{display:flex;justify-content:space-around;padding:20px;background:#f1f6ec}.report-summary strong{display:block;font-size:28px}.good{color:#477c38}.bad{color:#b36b44}.report-eyebrow{letter-spacing:2px;font-size:11px}.report-notes{font-size:12px}.report-summary span{font-size:12px}@media print{body{margin:15px;font-size:11px}h3{break-after:avoid}tr{break-inside:avoid}}</style><body><p><strong>해석 모델 데모 · 실제 SPICE / VLM 결과 아님</strong></p>'+reportMarkup()+'<p>생성: '+new Date().toLocaleString('ko-KR')+'</p></body></html>';download('EDAI_design_report_demo.html',html,'text/html;charset=utf-8');toast('리포트를 저장했어요. 브라우저에서 열어 PDF로 인쇄할 수도 있어요.');});
function netlist(){
 const m=state.selected,s=state.spec,T=Math.max(10,Math.max(m.settling,state.baseline.settling)*2);
 return ['* EDAI SYNTHETIC DEMO - equivalent RLC transfer-function model','* NOT a CMOS transistor circuit. NOT yet executed in LTspice.','* H(s)=G*wn^2/(s^2+2*zeta*wn*s+wn^2).','* Cc='+m.cc+' pF, Ibias='+m.ibias+' uA are UX parameters.','* Their invented mapping is precomputed below. Editing this comment does nothing.','* Supply, loading, current, slew rate and real power are NOT modeled here.','.param G='+s.gain+' WN='+fmt(m.wn*1e6,6)+' ZETA='+fmt(m.zeta,10)+' LEQ=1u','VIN in 0 PULSE(0 10m 0 1n 1n 1m 2m) AC 1','EGAIN drive 0 in 0 {G}','RDAMP drive damp {2*ZETA*WN*LEQ}','LEQUIV damp out {LEQ}','CEQUIV out 0 {1/(WN*WN*LEQ)}','.tran 0 '+fmt(T,3)+'u 0 2n','.ac dec 100 1k 100Meg','* Plot V(out) for transient and V(out)/V(in) for CLOSED-LOOP AC.','* Dashboard Bode plots LOOP L(s), not this closed-loop H(s).','* Open-loop equivalent: L(s)=wn^2/[s*(s+2*zeta*wn)].','.end',''].join('\n');
}
$('#netlist-export').addEventListener('click',()=>{download('EDAI_equivalent_model_demo.cir',netlist());toast('동등 전달함수 예제를 저장했어요. LTspice 실행은 아직 검증하지 않았어요.');});
$('#netlist-preview').addEventListener('click',()=>modal('설계 모델 · 현재 선택값','<p>현재 화면의 파형은 2차 전달함수로 계산합니다. 아래 파일은 같은 전달함수를 RLC 회로로 나타낸 예시이며, 실제 CMOS 넷리스트가 아닙니다.</p><pre>'+esc(netlist())+'</pre><p>LTspice 실행 검증은 다음 단계입니다. 화면의 Bode plot은 루프 L(s), .cir의 AC 해석은 폐루프 H(s)이므로 서로 다른 그래프입니다.</p>'));
const guideHtml='<p><strong>먼저 예시만으로 전체 흐름을 경험해 보세요.</strong></p><ol><li><strong>설계 워크스페이스 → 최적화 실행</strong><br>초기값에서 선택 설계로 변화하는 과정을 확인합니다.</li><li><strong>개선 과정의 00–04를 클릭</strong><br>각 단계의 파형·성능·변경한 값을 비교합니다. Bode plot으로도 전환할 수 있습니다.</li><li><strong>자료 & 근거 → 예시 PDF 다운로드</strong><br>PDF를 업로드해 페이지별 텍스트 읽기를 확인합니다. 명시적인 목표 키가 있으면 입력란에 적용할 수 있습니다.</li><li><strong>목표 스펙이나 우선순위를 바꾸고 다시 실행</strong><br>엄격한 목표를 입력하면 조건을 충족하는 후보가 없을 수도 있습니다.</li><li><strong>결과 리포트</strong><br>리포트 HTML, 메트릭 JSON, 비교 파형 CSV와 동등 전달함수 .cir를 저장합니다.</li></ol><p>업로드 자료는 브라우저 메모리에서만 처리합니다. 새로고침하면 초기화됩니다. 실제 AI 분석 및 SPICE 실행은 미연결 상태입니다.</p>';
function guide(){modal('3분 시연 가이드',guideHtml);}
$('#guide-open').addEventListener('click',guide);$('#help-open').addEventListener('click',guide);
$('#model-open').addEventListener('click',()=>modal('예시 모델의 범위','<p>이 화면은 <strong>Case 13에서 착안한 UX 프로토타입</strong>입니다. 실제 다단 CMOS 회로를 해석하거나 최적화했다는 뜻은 아닙니다.</p><h3>파형과 안정성 계산</h3><pre>H(s) = ωn² / (s² + 2ζωn s + ωn²)\nL(s) = ωn² / [s(s + 2ζωn)]\nζ = clamp((0.18 + 0.06 Cc) √(100/Ibias) √(20/CL), 0.12, 1.4)\nfn [MHz] = 0.55 √(Ibias/100) √(10/G) √(20/CL) / √(1+Cc/4)\nP [mW] = VDD × (0.15 + 0.005 Ibias)\nCc, CL: pF / Ibias: μA</pre><p>Cc·Ibias와 전달함수의 연결 및 전력식은 시연을 위해 임의로 정의했습니다. 부품 데이터시트나 CMOS 소자 모델에서 유도한 식이 아닙니다. 폐루프 이득은 이상적 목표값으로 고정되어 별도 통과 지표에 포함하지 않습니다.</p><h3>실제 동작하는 부분</h3><p>목표 입력, 285개 조합 비교, 스텝 응답·Bode 계산, 2% 정착시간 수치 추정, PDF 텍스트 추출, 키워드 검색, 결과 내보내기입니다.</p><h3>아직 연결하지 않은 부분</h3><p>VLM·LLM 호출, RAG 의미 검색, 스캔 PDF OCR, 실제 트랜지스터 사이징, SPICE 실행과 PVT 검증입니다.</p><h3>일반 원리 참고</h3><p>부하와 안정성의 관계: <a href="https://www.analog.com/en/resources/analog-dialogue/articles/ask-the-applications-engineer-25.html" target="_blank" rel="noopener noreferrer">Analog Devices · Op Amps Driving Capacitive Loads</a>. 이 외부 자료는 예시 숫자의 출처가 아닙니다.</p>'));
$('#integration-open').addEventListener('click',()=>modal('팀원의 결과와 연결하는 구조','<ol><li><strong>자료 입력</strong><br>PDF와 회로 DB → 페이지·표 추출 → 검색 가능한 근거 저장소</li><li><strong>설계 엔진</strong><br>목표 스펙 + 검색 근거 → LLM의 후보 넷리스트 생성</li><li><strong>검증</strong><br>LTspice/ngspice 실행 → 원시 파형에서 수치 계산 → 조건 판정</li><li><strong>시각 진단</strong><br>VLM이 그래프의 형태를 보조 분석하고, 정량 판정은 원시 데이터와 연결</li><li><strong>현재 만든 UI</strong><br>실제 iteration별 메트릭·파형·변경값·근거를 받아 개선 과정을 표시</li></ol><p>현재 화면은 5번의 기능을 먼저 구현했습니다. 1번은 로컬 텍스트 추출·키워드 검색까지 구현되어 있고, 2–4번은 예시 모델로 대체되어 있습니다.</p><p><a href="samples/integration_contract.json" download>실제 결과용 JSON 형식 다운로드</a>를 팀원과 합의하면 다음 연결 작업을 시작할 수 있습니다. 이 형식의 실제 결과를 화면에 반영하는 어댑터는 다음 구현 단계입니다.</p>'));
async function init(){
 hydrateIcons();setForm(DEFAULT_SPEC);renderWorkspace();renderCases();showView(location.hash.slice(1)||'workspace');
 try{const r=await fetch('samples/demo_evidence.json');if(!r.ok)throw Error('예시 자료를 불러오지 못했습니다.');const data=await r.json();for(const d of data.documents)addDoc(d);renderSources();}
 catch(err){$('#upload-status').textContent=err.message;$('#source-count').textContent='0';renderSources();}
}
init();
