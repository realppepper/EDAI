// EDAI demonstration model. All parameter mappings below are invented for UX study.
// It is NOT a transistor model, SPICE result, component rating or VLM inference.
export const DEFAULT_SPEC = Object.freeze({gain:10,pm:60,overshoot:10,settling:6,power:3,bw:0.15,vdd:3.3,load:20,priority:'balanced'});
export const BASE = Object.freeze({cc:2,ibias:220});
export const LIMITS={gain:[2,100],pm:[20,85],overshoot:[1,70],settling:[0.2,50],power:[0.2,10],bw:[0.01,3],vdd:[1.8,5],load:[5,100]};
export const CASES=[
 ['NMOS-input cascode amplifier','NMOS 입력 캐스코드 증폭기','단일 증폭단'],
 ['CMOS differential amplifier with common-mode rejection','공통 모드 제거 CMOS 차동 증폭기','차동 증폭기'],
 ['CMOS differential pair with active load','능동 부하 CMOS 차동쌍','차동 증폭기'],
 ['NMOS cross-coupled cascode amplifier','교차 결합 NMOS 캐스코드 증폭기','단일 증폭단'],
 ['Differential pair with source degeneration','소스 저항을 둔 차동쌍','차동 증폭기'],
 ['CMOS differential amplifier with source degeneration','소스 저항을 둔 CMOS 차동 증폭기','차동 증폭기'],
 ['CMOS differential amplifier with current-source load','전류원 부하 CMOS 차동 증폭기','차동 증폭기'],
 ['Differential pair with active load','능동 부하 차동쌍','차동 증폭기'],
 ['CMOS differential amplifier with resistive feedback','저항 피드백 CMOS 차동 증폭기','피드백'],
 ['Feedback-enhanced NMOS cascode amplifier','피드백 강화 NMOS 캐스코드 증폭기','피드백'],
 ['Two-stage cascaded differential amplifier','2단 종속 연결 차동 증폭기','다단 증폭기'],
 ['Differential pair with active load and cascode configuration','능동 부하·캐스코드 구성 차동쌍','차동 증폭기'],
 ['Multistage CMOS operational amplifier','다단 CMOS 연산증폭기','Op-Amp'],
 ['Dynamic Latch Comparator','동적 래치 비교기','비교기'],
 ['Differential pair with active load and cascode structure','능동 부하·캐스코드 구조 차동쌍','차동 증폭기']
].map((c,i)=>({id:i+1,name:c[0],ko:c[1],group:c[2],available:i===12}));
export function validateSpec(input){
 const out={...DEFAULT_SPEC};
 for(const [k,[min,max]] of Object.entries(LIMITS)){
   if(input[k]===undefined||input[k]===null||input[k]==='')throw Error(k+' 값을 입력해 주세요.');
   const n=Number(input[k]);if(!Number.isFinite(n)||n<min||n>max)throw Error(k+' 허용 범위: '+min+'–'+max);
   out[k]=n;
 }
 out.priority=['balanced','stability','speed','power'].includes(input.priority)?input.priority:'balanced';
 return out;
}
export function response(t,m){
 if(t<=0)return 0;
 const u=m.wn*t,z=m.zeta;
 if(Math.abs(z-1)<0.0001)return 1-Math.exp(-u)*(1+u);
 if(z<1){const d=Math.sqrt(1-z*z);return 1-Math.exp(-z*u)*(Math.cos(d*u)+z/d*Math.sin(d*u));}
 const d=Math.sqrt(z*z-1),r1=-z+d,r2=-z-d;
 return 1+(r2*Math.exp(r1*u)-r1*Math.exp(r2*u))/(r1-r2);
}
export function evaluate(params,spec){
 const cc=Number(params.cc),ibias=Number(params.ibias);
 const zeta=Math.max(0.12,Math.min(1.4,(0.18+0.06*cc)*Math.sqrt(100/ibias)*Math.sqrt(20/spec.load)));
 const fn=0.55*Math.sqrt(ibias/100)*Math.sqrt(10/spec.gain)/Math.sqrt(1+cc/4)*Math.sqrt(20/spec.load);
 const wn=2*Math.PI*fn;
 const cross=Math.sqrt(Math.sqrt(1+4*Math.pow(zeta,4))-2*zeta*zeta);
 const pm=Math.atan2(2*zeta,cross)*180/Math.PI;
 const bw=fn*Math.sqrt(1-2*zeta*zeta+Math.sqrt(2-4*zeta*zeta+4*Math.pow(zeta,4)));
 const overshoot=zeta>=1?0:100*Math.exp(-Math.PI*zeta/Math.sqrt(1-zeta*zeta));
 const power=spec.vdd*(0.15+0.005*ibias);
 const m={cc,ibias,zeta,fn,wn,pm,bw,overshoot,power,fc:fn*cross,gain:spec.gain};
 const end=20/(Math.min(zeta,1)*wn),dt=end/2400;let last=0;
 for(let i=0;i<=2400;i++)if(Math.abs(response(i*dt,m)-1)>0.02)last=i;
 m.settling=(last+1)*dt;
 m.pass={pm:pm>=spec.pm,overshoot:overshoot<=spec.overshoot,settling:m.settling<=spec.settling,power:power<=spec.power,bw:bw>=spec.bw};
 m.passed=Object.values(m.pass).filter(Boolean).length;
 m.feasible=m.passed===5;
 return m;
}
export function violation(m,s){
 return Math.max(0,(s.pm-m.pm)/s.pm)+Math.max(0,(m.overshoot-s.overshoot)/s.overshoot)+Math.max(0,(m.settling-s.settling)/s.settling)+Math.max(0,(m.power-s.power)/s.power)+Math.max(0,(s.bw-m.bw)/s.bw);
}
export function score(m,s){
 const w={balanced:[0.36,0.30,0.20,0.14],stability:[0.12,0.12,0.08,0.68],speed:[0.10,0.55,0.30,0.05],power:[0.82,0.08,0.05,0.05]}[s.priority]||[0.36,0.30,0.20,0.14];
 const preference=w[0]*m.power/s.power+w[1]*m.settling/s.settling+w[2]*s.bw/m.bw+w[3]*(90-m.pm)/90;
 return preference;
}
export function optimize(spec,baseline=BASE){
 const candidates=[];
 for(let cc=2;cc<=16;cc++)for(let ibias=60;ibias<=240;ibias+=10)candidates.push(evaluate({cc,ibias},spec));
 candidates.sort((a,b)=>violation(a,spec)-violation(b,spec)||score(a,spec)-score(b,spec));
 const best=candidates[0],states=[evaluate(baseline,spec)];
 for(let i=1;i<=4;i++){
  const alpha=i/4;
  const p={cc:Math.round((baseline.cc+(best.cc-baseline.cc)*alpha)*10)/10,ibias:Math.round(baseline.ibias+(best.ibias-baseline.ibias)*alpha)};
  states.push(evaluate(p,spec));
 }
 return {states,best,candidates,feasibleCount:candidates.filter(m=>m.feasible).length};
}
export function bode(f,m){
 const w=2*Math.PI*f/1e6; // input Hz; model angular frequency in rad/us
 return {db:20*Math.log10(m.wn*m.wn/(w*Math.sqrt(w*w+4*m.zeta*m.zeta*m.wn*m.wn))),phase:-90-Math.atan(w/(2*m.zeta*m.wn))*180/Math.PI};
}
export function extractTargets(text){
 const aliases={gain:['gain_vv'],pm:['phase_margin_min_deg'],overshoot:['overshoot_max_pct'],settling:['settling_max_us'],power:['power_max_mw'],bw:['bandwidth_min_mhz'],vdd:['supply_v'],load:['load_pf']};
 const out={};
 for(const [k,names]of Object.entries(aliases))for(const name of names){
 const match=text.match(new RegExp('(?:^|[^a-zA-Z0-9_])'+name+'\\s*[:=]\\s*([0-9]+(?:\\.[0-9]+)?)','i'));
 if(match){const n=Number(match[1]),[min,max]=LIMITS[k];if(n>=min&&n<=max)out[k]=n;}
 }
 return out;
}
export function chunkText(text,size=900){
 const cleaned=String(text).replace(/\s+/g,' ').trim();const chunks=[];
 for(let i=0;i<cleaned.length;i+=size-100)chunks.push(cleaned.slice(i,i+size));
 return chunks;
}
export function rankChunks(chunks,q){
 const terms=String(q).toLowerCase().split(/\s+/).filter(Boolean);
 return chunks.map(c=>({...c,rank:terms.reduce((a,t)=>a+(c.text.toLowerCase().includes(t)?1:0),0)})).filter(c=>!terms.length||c.rank>0).sort((a,b)=>b.rank-a.rank);
}
