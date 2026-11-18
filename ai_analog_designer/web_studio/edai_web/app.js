'use strict';
const $ = s => document.querySelector(s);
const $$ = s => Array.from(document.querySelectorAll(s));
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const fmt = n => n === null || n === undefined ? '—' : Number(n).toLocaleString('en-US', {maximumSignificantDigits: 5, useGrouping: false});

let settings = null, status = null, job = null, selected = 0, followBest = true, poller = null, aiBusy = false;

function error(message) {
  const el = $('#error');
  el.textContent = message || '';
  el.hidden = !message;
  if (message) el.scrollIntoView({behavior: 'smooth', block: 'nearest'});
}

async function api(path, data) {
  const opts = data === undefined ? {} : {
    method: 'POST',
    headers: {'Content-Type': 'application/json', 'X-EDAI-Token': window.EDAI_TOKEN || ''},
    body: JSON.stringify(data)
  };
  const r = await fetch(path, opts);
  const j = await r.json();
  if (!r.ok) throw Error(j.error || '요청 실패');
  return j;
}

function tab(name) {
  $$('[data-tab]').forEach(b => b.classList.toggle('active', b.dataset.tab === name));
  $('#tab-net').hidden = name !== 'net';
  $('#tab-ai').hidden = name !== 'ai';
  $('#tab-topo').hidden = name !== 'topo';
}
$$('[data-tab]').forEach(b => b.addEventListener('click', () => tab(b.dataset.tab)));

function paramRow(p = {name:'RNEW', min:1000, max:10000, initial:5000, step:1000}) {
  return '<tr>' + ['name','min','max','initial','step'].map(k =>
    `<td><input aria-label="변수 ${k}" data-key="${k}" type="${k==='name'?'text':'number'}" step="any" value="${esc(p[k])}"></td>`
  ).join('') + '<td><button data-remove aria-label="변수 삭제">×</button></td></tr>';
}

function goalRow(g = {measure:'gain', op:'>=', value:10, unit:'V/V'}) {
  return `<tr>
    <td><input data-key="measure" aria-label="측정명" value="${esc(g.measure)}"></td>
    <td><select data-key="op" aria-label="조건 방향">
      <option ${g.op==='>='?'selected':''} value=">=">≥</option>
      <option ${g.op==='<='?'selected':''} value="<=">≤</option>
    </select></td>
    <td><input data-key="value" type="number" step="any" aria-label="목표값" value="${esc(g.value)}"></td>
    <td><input data-key="unit" aria-label="단위" value="${esc(g.unit)}"></td>
    <td><button data-remove aria-label="조건 삭제">×</button></td>
  </tr>`;
}

function loadProject(p) {
  settings = p.settings;
  $('#netlist').value = p.netlist || '';
  if (settings) {
    $('#params').innerHTML = (settings.parameters || []).map(paramRow).join('');
    $('#goals').innerHTML = (settings.goals || []).map(goalRow).join('');
    $('#objective').value = settings.objective?.measure || '';
    $('#sense').value = settings.objective?.sense || 'min';
    $('#method').value = settings.method || 'feedback';
    $('#max-runs').value = settings.max_runs || 32;
  }
}

function readSettings() {
  function rows(id, numeric) {
    return $$(id + ' tr').map(tr => Object.fromEntries(Array.from(tr.querySelectorAll('[data-key]')).map(e => {
      if (numeric.includes(e.dataset.key) && !e.value.trim()) throw Error('빈 숫자 입력란을 채워 주세요.');
      return [e.dataset.key, numeric.includes(e.dataset.key) ? Number(e.value) : e.value.trim()];
    })));
  }
  return {
    title: settings?.title || '사용자 회로',
    parameters: rows('#params', ['min','max','initial','step']),
    goals: rows('#goals', ['value']),
    objective: {measure: $('#objective').value.trim(), sense: $('#sense').value},
    method: $('#method').value,
    max_runs: Number($('#max-runs').value),
    timeout_s: 20
  };
}

document.addEventListener('click', e => {
  if (e.target.closest('[data-remove]')) e.target.closest('tr').remove();
});
$('#add-param').onclick = () => { if ($$('#params tr').length < 6) $('#params').insertAdjacentHTML('beforeend', paramRow()); };
$('#add-goal').onclick = () => { if ($$('#goals tr').length < 12) $('#goals').insertAdjacentHTML('beforeend', goalRow()); };

$('#example').onclick = async () => {
  try { window.invalidateReview?.(); loadProject(await api('/api/example')); error(''); tab('net'); window.renderSchematicPreview?.(); }
  catch (e) { error(e.message); }
};
const opampExBtn = $('#load-opamp-example');
if (opampExBtn) {
  opampExBtn.onclick = async () => {
    try { window.invalidateReview?.(); loadProject(await api('/api/example?name=opamp')); error(''); tab('net'); window.renderSchematicPreview?.(); }
    catch (e) { error(e.message); }
  };
}

$('#net-file').onchange = async e => {
  const f = e.target.files[0];
  if (!f) return;
  if (f.size > 100000) return error('넷리스트는 100 KB 이하로 넣어 주세요.');
  window.invalidateReview?.();
  $('#netlist').value = await f.text();
  error('넷리스트를 가져왔습니다. 변수/목표를 확인하고 실행하세요.');
  window.renderSchematicPreview?.();
};

$('#source-files').onchange = () => {
  $('#file-list').textContent = Array.from($('#source-files').files).map(f => `${f.name} (${Math.ceil(f.size/1024)} KB)`).join(' · ');
};

function lock(on) {
  $$('.input-column input,.input-column select,.input-column textarea,.input-column button,#example').forEach(e => e.disabled = on);
  $('#cancel').disabled = job?.state !== 'running';
  $('#run').disabled = on || !status?.ready;
  $('#generate').disabled = on || !status?.ai_ready || aiBusy;
  $('#refine').disabled = on || !status?.ai_ready || !job?.runs?.length || aiBusy;
}

async function refreshStatus() {
  status = await api('/api/edai/status');
  $('#engine-status').textContent = status.ready ? `${status.simulator} 준비됨` : 'SPICE 설정 필요';
  $('#engine-status').className = 'badge ' + (status.ready ? '' : 'warn');
  const aiBadge = $('#ai-provider-badge');
  if (aiBadge) aiBadge.textContent = status.ai_ready ? `${status.llm_provider} · ${status.ai_model}` : 'LLM 키 미설정';
  $('#ai-status').textContent = status.ai_ready ? `AI 연결 설정됨 · ${status.llm_provider}/${status.ai_model}` : 'LLM API 키 미설정 · 로컬 추출·토폴로지/gm-ID·SPICE 스윕은 사용 가능';
  const routingInfo = $('#llm-routing-info');
  if (routingInfo) {
    routingInfo.textContent = `Provider: ${status.llm_provider || 'none'} | Extract: ${status.extract_model || '—'} | Synth: ${status.synth_model || '—'} | IEEE MCP: ${status.ieee_mcp_ready ? 'configured' : 'direct/OpenAlex'}`;
  }
  if (!status.ready) error(status.error);
  lock(false);
}

$('#run').onclick = async () => {
  try {
    error('');
    const s = readSettings();
    const r = await api('/api/run', {netlist: $('#netlist').value, settings: s, confirmation_id: window.confirmationId || null});
    job = {id: r.id, state: 'running', runs: [], settings: s, best_iteration: null};
    selected = 0; followBest = true;
    lock(true); render();
    clearTimeout(poller); poll();
  } catch (e) { error(e.message); lock(false); }
};

$('#cancel').onclick = async () => {
  if (!job) return;
  try { await api('/api/cancel', {id: job.id}); $('#run-status').textContent = '중지 요청 중…'; }
  catch (e) { error(e.message); }
};

async function poll() {
  try {
    job = await api('/api/jobs/' + job.id);
    if (followBest) selected = job.best_iteration ?? Math.max(0, job.runs.length - 1);
    render();
    if (job.state === 'running') poller = setTimeout(poll, 600);
    else { lock(false); if (job.error) error(job.error); }
  } catch (e) { error(e.message + ' · 서버 상태를 확인해 주세요.'); lock(false); }
}

function render() {
  const runs = job?.runs || [], best = job?.best_iteration;
  $('#count').textContent = runs.length;
  $('#feasible').textContent = runs.filter(r => r.feasible).length;
  $('#best').textContent = best === null || best === undefined ? '—' : '#' + String(best).padStart(2, '0');
  $('#run-status').textContent = {
    running: 'SPICE 스윕 실행 중 · 후보를 시뮬레이션하고 있습니다.',
    completed: '실행 완료 · 선택 후보와 로그를 확인하세요.',
    cancelled: '사용자 요청으로 중지했습니다.',
    failed: '실행을 완료하지 못했습니다.'
  }[job?.state] || '실행 대기';

  const b = runs.find(r => r.iteration === best);
  $('#selection-note').textContent = !b ? '유효한 측정 결과를 기다리고 있습니다.'
    : b.feasible ? '현재 선택 후보가 설정한 모든 목표를 만족합니다.'
    : '아직 모든 목표를 만족하는 후보가 없습니다. 목표 위반이 가장 작은 유효 후보를 표시합니다.';
  if (job && job.state !== 'running' && !b) $('#selection-note').textContent = '유효한 후보가 없습니다. 측정 실패 또는 실행 로그를 확인하세요.';

  const dl = $('#download');
  const available = job && job.state !== 'running';
  dl.classList.toggle('disabled', !available);
  dl.setAttribute('aria-disabled', String(!available));
  if (available) dl.href = `/api/jobs/${job.id}/download`;
  else dl.removeAttribute('href');

  $('#history').innerHTML = runs.slice().reverse().map(r =>
    `<tr class="${r.iteration===selected?'selected':''}">
      <td>#${String(r.iteration).padStart(2,'0')}${r.iteration===best?'<small>현재 최선</small>':''}</td>
      <td>${Object.entries(r.parameters).map(([k,v])=>`${esc(k)} ${fmt(v)}`).join('<br>')}</td>
      <td class="${r.feasible?'good':'bad'}">${r.valid?`${r.checks.filter(c=>c.passed).length}/${r.checks.length}`:'측정 실패'}</td>
      <td>${r.elapsed_s} s</td>
      <td><button data-select="${r.iteration}">보기</button></td>
    </tr>`
  ).join('');

  $$('[data-select]').forEach(btn => btn.onclick = () => { followBest = false; selected = Number(btn.dataset.select); render(); });
  const names = [...new Set((job?.settings?.goals || []).map(g => g.measure))];
  const prev = $('#trend-metric').value;
  $('#trend-metric').innerHTML = names.map(n => `<option>${esc(n)}</option>`).join('');
  if (names.includes(prev)) $('#trend-metric').value = prev;
  renderTrend(); renderSelected(); window.renderComparison?.();
}

function svgChart(series, options = {}) {
  const W = 680, H = 230, L = 61, R = 19, T = 20, B = 38;
  const pts = series.flatMap(s => s.points).filter(p => p.every(Number.isFinite));
  if (!pts.length) return '<p class="empty">표시할 유효한 수치가 없습니다.</p>';
  let xmin = Math.min(...pts.map(p => p[0])), xmax = Math.max(...pts.map(p => p[0]));
  let ymin = Math.min(...pts.map(p => p[1])), ymax = Math.max(...pts.map(p => p[1]));
  const targets = options.targets || [];
  targets.forEach(t => { ymin = Math.min(ymin, t); ymax = Math.max(ymax, t); });
  const pad = (ymax - ymin) * 0.13 || Math.max(Math.abs(ymax) * 0.1, 1);
  ymin -= pad; ymax += pad;
  if (xmax === xmin) xmax = xmin + 1;
  const x = v => L + (v - xmin) / (xmax - xmin) * (W - L - R);
  const y = v => H - B - (v - ymin) / (ymax - ymin) * (H - T - B);
  let grid = '', labels = '';
  for (let i = 0; i <= 4; i++) {
    const xx = xmin + (xmax - xmin) * i / 4, yy = ymin + (ymax - ymin) * i / 4;
    grid += `<line x1="${L}" y1="${y(yy)}" x2="${W-R}" y2="${y(yy)}" stroke="#e5ecdf"/>`;
    labels += `<text x="${L-8}" y="${y(yy)+4}" text-anchor="end">${yy.toPrecision(3)}</text><text x="${x(xx)}" y="${H-15}" text-anchor="middle">${xx.toPrecision(3)}</text>`;
  }
  const lines = series.map(s =>
    `<path d="${s.points.filter(p => p.every(Number.isFinite)).map((p,i)=>(i?'L':'M')+x(p[0]).toFixed(2)+','+y(p[1]).toFixed(2)).join(' ')}" fill="none" stroke="${s.color}" stroke-width="${s.width||2}"/>`
    + (s.dots ? s.points.filter(p => p.every(Number.isFinite)).map(p => `<circle cx="${x(p[0])}" cy="${y(p[1])}" r="3" fill="${s.color}"/>`).join('') : '')
  ).join('');
  return `<svg role="img" aria-label="${esc(options.title||'측정값 그래프')}" viewBox="0 0 ${W} ${H}">${grid}${targets.map(t=>`<line x1="${L}" x2="${W-R}" y1="${y(t)}" y2="${y(t)}" stroke="#cb965a" stroke-dasharray="5 5"/>`).join('')}${lines}<g font-size="11" fill="#73856a">${labels}<text x="${W-R}" y="${H-1}" text-anchor="end">${esc(options.xlabel||'후보 번호')}</text></g></svg>`;
}

function renderTrend() {
  const name = $('#trend-metric').value, runs = job?.runs || [];
  let incumbent = null; const best = [];
  for (const r of runs) {
    if (r.new_best) incumbent = r;
    if (incumbent && Number.isFinite(incumbent.metrics[name])) best.push([r.iteration, incumbent.metrics[name]]);
  }
  $('#trend').innerHTML = svgChart([
    {points: runs.filter(r => r.valid && Number.isFinite(r.metrics[name])).map(r => [r.iteration, r.metrics[name]]), color: '#c2cbb8', dots: true},
    {points: best, color: '#35764f', width: 2.6}
  ], {title: `${name} 실제 측정값 변화`, targets: (job?.settings?.goals || []).filter(g => g.measure === name).map(g => g.value)});
}

function renderSelected() {
  const r = job?.runs?.find(x => x.iteration === selected);
  if (!r) {
    $('#checks').textContent = '아직 선택할 결과가 없습니다.';
    $('#feedback').hidden = true;
    $('#wave').innerHTML = '<p class="empty">시뮬레이션 대기</p>';
    $('#log').textContent = '실행 대기';
    return;
  }
  $('#selected-label').textContent = '#' + String(r.iteration).padStart(2, '0');
  $('#checks').className = 'checks';
  $('#checks').innerHTML = r.checks.map(c =>
    `<div class="check ${c.passed?'ok':''}"><span>${esc(c.measure)} <small>(${esc(c.unit||'')})</small><br>목표 ${esc(c.op)} ${c.value}</span><strong>${fmt(c.actual)} ${c.passed?'✓':'· 미충족'}</strong></div>`
  ).join('');
  $('#feedback').hidden = false;
  $('#feedback').textContent = `${r.reason} / ${r.feedback}`;
  $('#log').textContent = r.log_tail;
  const old = $('#wave-signal').value;
  const signals = r.waveform?.variables?.slice(1) || [];
  $('#wave-signal').innerHTML = signals.map(v => `<option>${esc(v)}</option>`).join('');
  if (signals.includes(old)) $('#wave-signal').value = old;
  else if (signals.includes('v(out)')) $('#wave-signal').value = 'v(out)';
  renderWave(); window.renderComparison?.();
}

function renderWave() {
  const r = job?.runs?.find(x => x.iteration === selected), w = r?.waveform;
  if (!w) { $('#wave').innerHTML = '<p class="empty">표시할 실수형 raw 파형이 없습니다.</p>'; return; }
  const name = $('#wave-signal').value, index = w.variables.indexOf(name), isTime = w.variables[0].toLowerCase() === 'time';
  const first = job?.runs?.[0]?.waveform, initialIndex = first?.variables.indexOf(name);
  const initialSeries = first && initialIndex > 0 && selected !== 0 ? [{points: first.points.map(p => [p[0]*(isTime?1000:1), p[initialIndex]]), color: '#a8b3aa'}] : [];
  $('#wave').innerHTML = svgChart([...initialSeries, {points: w.points.map(p => [p[0]*(isTime?1000:1), p[index]]), color: '#37774e'}], {title: `${name} SPICE 파형`, xlabel: isTime ? '시간 (ms)' : w.variables[0]});
}

$('#trend-metric').onchange = renderTrend;
$('#wave-signal').onchange = renderWave;

function encodeFile(f) {
  return new Promise((resolve, reject) => {
    const r = new FileReader();
    r.onerror = () => reject(Error('파일 읽기 실패'));
    r.onload = () => resolve({name: f.name, base64: String(r.result).split(',')[1]});
    r.readAsDataURL(f);
  });
}

async function askAI(refine = false) {
  try {
    error('');
    const instruction = $('#instruction').value.trim() || (refine ? '측정 결과와 목표를 비교하여 회로 또는 파라미터 탐색 범위를 개선해 주세요.' : '');
    if (!instruction) throw Error('설계 요청과 목표를 입력해 주세요.');
    const files = Array.from($('#source-files').files);
    if (files.length > 4 || files.reduce((s, f) => s + f.size, 0) > 10000000) throw Error('최대 4개, 총 10 MB까지 넣어 주세요.');
    aiBusy = true; lock(true);
    $('#ai-status').textContent = 'LLM이 베이스 회로 초안을 생성하고 있습니다…';
    if (files.length && !window.confirmationId) throw Error('자료 추출 후 출처·목표 확인을 먼저 완료해 주세요.');
    const data = {
      instruction,
      files: await Promise.all(files.map(encodeFile)),
      confirmation_id: window.confirmationId || null,
      ieee_context: window.selectedIeeeContext || ''
    };
    if (refine) {
      const best = job.runs.find(r => r.iteration === job.best_iteration);
      let previousNet = job.netlist;
      if (best) for (const [name, value] of Object.entries(best.parameters)) {
        previousNet = previousNet.replace(new RegExp(`(^\\s*\\.param\\s+${name}\\s*=\\s*)[^\\n;]+`, 'gmi'), (_, prefix) => prefix + value);
      }
      data.previous = {netlist: previousNet, settings: job.settings, result: best ? {parameters: best.parameters, metrics: best.metrics, feedback: best.feedback} : {}};
    }
    const result = await api('/api/generate_base', data);
    $('#ai-result').innerHTML = `<h3>${esc(result.needs_clarification ? '추가 정보가 필요합니다' : '베이스 회로 초안 생성 완료')}</h3><p>${esc(result.summary)}</p>`;
    if (!result.needs_clarification) {
      loadProject(result);
      tab('net');
      window.renderSchematicPreview?.();
    }
    $('#ai-status').textContent = `베이스 초안 수신 · ${result.model || 'LLM'}`;
  } catch (e) {
    error(e.message);
    $('#ai-status').textContent = '베이스 초안 요청을 완료하지 못했습니다.';
  } finally { aiBusy = false; lock(job?.state === 'running'); }
}

$('#generate').onclick = () => askAI(false);
$('#refine').onclick = () => askAI(true);

window.addEventListener('DOMContentLoaded', async () => {
  try {
    loadProject(await api('/api/example'));
    await refreshStatus();
    window.renderSchematicPreview?.();
  } catch (e) { error(e.message); }
});
