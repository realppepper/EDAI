'use strict';
window.selectedIeeeContext = '';
let currentPdgSchedule = {};
let lastSizedNetlist = '';
let autoPoller = null;
let lastAutoNetlist = '';

// 1. Sample IC Datasheets (/api/samples) & PDG Extraction (/api/extract_pdg)
async function loadSampleDatasheets() {
  try {
    const res = await api('/api/samples');
    const sel = $('#sample-select');
    if (!sel || !res.samples) return;
    sel.innerHTML = '<option value="">-- 샘플 IC 데이터시트 선택 --</option>' +
      res.samples.map(s => `<option value="${esc(s.path)}">${esc(s.part_name)} (${esc(s.filename)})</option>`).join('');
  } catch (_) {}
}

function updatePdgTimeline(tUs) {
  const tv = $('#pdg-time-val');
  if (tv) tv.textContent = `${Number(tUs).toFixed(1)} us`;
  const tbody = $('#pdg-table-body');
  if (!tbody) return;
  Array.from(tbody.querySelectorAll('tr')).forEach(tr => {
    const delay = parseFloat(tr.dataset.delay || '0');
    const st = tr.querySelector('.pdg-pin-state');
    if (st) {
      const active = Number(tUs) >= delay;
      st.textContent = active ? 'Active' : 'Waiting';
      st.className = 'pdg-pin-state ' + (active ? 'good' : 'bad');
    }
  });
}

const btnPdg = $('#btn-extract-pdg');
if (btnPdg) {
  btnPdg.onclick = async () => {
    const pdfPath = $('#sample-select')?.value;
    if (!pdfPath) return error('먼저 샘플 IC 데이터시트를 선택해 주세요.');
    try {
      error('');
      btnPdg.disabled = true; btnPdg.textContent = 'PDG 추출 중…';
      const data = await api('/api/extract_pdg?pdf_path=' + encodeURIComponent(pdfPath));
      $('#pdg-box').hidden = false;
      $('#pdg-title').textContent = `${data.ic_name || 'DUT'} · Port Dependency Graph`;
      $('#pdg-svg-box').innerHTML = data.svg || '<p class="empty">SVG 없음</p>';
      currentPdgSchedule = data.schedule || {};
      const maxDelay = Math.max(10, ...Object.values(currentPdgSchedule).map(Number));
      const slider = $('#pdg-slider');
      slider.max = String(Math.ceil(maxDelay));
      slider.value = '0';
      $('#pdg-table-body').innerHTML = (data.pins || []).map(p => {
        const d = currentPdgSchedule[p.name] ?? 0;
        return `<tr data-delay="${d}"><td><b>${esc(p.name)}</b></td><td>${esc(p.role||'SIGNAL')}</td><td>${d} us</td><td class="pdg-pin-state">Waiting</td></tr>`;
      }).join('');
      updatePdgTimeline(0);
    } catch (e) { error(e.message); }
    finally { btnPdg.disabled = false; btnPdg.textContent = 'PDG 추출·시각화'; }
  };
}
if ($('#pdg-slider')) {
  $('#pdg-slider').oninput = e => updatePdgTimeline(e.target.value);
}

// 2. Schematic SVG Preview & NetlistValidator Guardrails
window.renderSchematicPreview = async (structureTable = '') => {
  const box = $('#schematic-svg-container');
  const badge = $('#schematic-renderer-badge');
  if (!box) return;
  try {
    const payload = structureTable ? {structure_table: structureTable} : {netlist: $('#netlist').value};
    const res = await api('/api/schematic_svg', payload);
    box.innerHTML = res.svg || '<p class="empty">회로도를 그릴 소자가 없습니다.</p>';
    if (badge) badge.textContent = `${res.renderer || 'svg'} (${res.device_count || 0} 소자)`;
  } catch (e) {
    box.innerHTML = `<p class="empty">${esc(e.message)}</p>`;
  }
};

if ($('#btn-render-svg')) {
  $('#btn-render-svg').onclick = () => window.renderSchematicPreview();
}

if ($('#btn-validate-guardrail')) {
  $('#btn-validate-guardrail').onclick = async () => {
    const out = $('#guardrail-result');
    try {
      error('');
      const res = await api('/api/validate_netlist', {netlist: $('#netlist').value});
      out.hidden = false;
      out.innerHTML = res.is_valid
        ? `<strong class="good">✓ NetlistValidator 물리 규칙 통과</strong> (소자 ${res.element_count || 0}개, 트랜지스터 ${res.transistor_count || 0}개)`
        : `<strong class="bad">✗ 가드레일 오류 (${(res.errors||[]).length}건)</strong><ul>${(res.errors||[]).map(x=>`<li>${esc(x)}</li>`).join('')}</ul>`;
    } catch (e) { error(e.message); }
  };
}

// 3. IEEE MCP Literature Search
if ($('#btn-ieee-search')) {
  $('#btn-ieee-search').onclick = async () => {
    const q = $('#ieee-query').value.trim();
    if (!q) return error('IEEE 검색어를 입력해 주세요.');
    try {
      error('');
      $('#btn-ieee-search').disabled = true;
      const res = await api('/api/ieee/search', {query: q, max_results: 4});
      const papers = res.papers || [];
      if (!papers.length) {
        $('#ieee-results').innerHTML = '<p class="note">검색 결과가 없습니다.</p>';
        return;
      }
      window.selectedIeeeContext = papers.map(p => `[${p.year||''}] ${p.title} (${p.doi||''}): ${(p.abstract||'').slice(0,300)}`).join('\n');
      $('#ieee-results').innerHTML = papers.map(p =>
        `<div class="ieee-item">
          <h4>${esc(p.title)} <small>(${esc(p.venue||'IEEE')} ${esc(p.year||'')})</small></h4>
          <p>${esc((p.abstract||'').slice(0,280))}...</p>
          ${p.url ? `<a href="${esc(p.url)}" target="_blank" rel="noopener">DOI / 원문 ↗</a>` : ''}
        </div>`
      ).join('');
    } catch (e) { error(e.message); }
    finally { $('#btn-ieee-search').disabled = false; }
  };
}

// 4. Topology Exploration & gm/ID Sizing (jiyun)
if ($('#btn-topo-explore')) {
  $('#btn-topo-explore').onclick = async () => {
    try {
      error('');
      $('#btn-topo-explore').disabled = true;
      const res = await api('/api/topology/candidates', {
        prompt_hint: $('#topo-hint').value.trim(),
        max_candidates: 6,
        auto_size_preview: false
      });
      const cands = res.candidates || [];
      const container = $('#topo-candidates');
      if (!cands.length) {
        container.innerHTML = '<p class="note">후보가 없습니다.</p>';
        return;
      }
      container.innerHTML = cands.map((c, idx) =>
        `<div class="cand-item" data-idx="${idx}">
          <div class="cand-meta"><strong>${esc(c.name)}</strong><span>${esc(c.source)} · ${c.transistor_count||'?'} MOS · ${c.ok?'규칙 통과':'문제 있음'}</span></div>
          <p class="note" style="margin:0 0 8px">${esc(c.description)}</p>
          <button type="button" class="secondary pick-cand" data-table="${esc(c.table)}">이 구조 선택 → gm/ID 사이징</button>
        </div>`
      ).join('');
      $$('.pick-cand').forEach(btn => {
        btn.onclick = () => {
          $$('.cand-item').forEach(el => el.classList.remove('active'));
          btn.closest('.cand-item').classList.add('active');
          $('#topo-table-input').value = btn.dataset.table;
          window.renderSchematicPreview(btn.dataset.table);
        };
      });
    } catch (e) { error(e.message); }
    finally { $('#btn-topo-explore').disabled = false; }
  };
}

if ($('#btn-run-gmid')) {
  $('#btn-run-gmid').onclick = async () => {
    const tbl = $('#topo-table-input').value.trim();
    if (!tbl) return error('먼저 토폴로지 후보를 선택하거나 구조 표를 입력해 주세요.');
    try {
      error('');
      $('#btn-run-gmid').disabled = true;
      const res = await api('/api/topology/auto_size', {
        structure_table: tbl,
        unit_current_ua: Number($('#gmid-current').value || 20),
        output_scale: Number($('#gmid-scale').value || 1),
        simulator: 'auto'
      });
      lastSizedNetlist = res.subckt_ltspice || res.subckt_ngspice || '';
      $('#btn-apply-gmid').disabled = !lastSizedNetlist;
      $('#gmid-result').innerHTML = `<strong>${res.ok?'✓ 사이징 완료':'✗ 사이징 주의'}</strong> (${esc(res.mode)}) · ${esc(res.reason||'')}<br>검증기: ${res.validator?.is_valid ? '물리 규칙 통과' : esc((res.validator?.errors||[]).join(', '))}`;
      if (res.schematic_svg) {
        $('#schematic-svg-container').innerHTML = res.schematic_svg;
        $('#schematic-renderer-badge').textContent = res.schematic_renderer || 'svg';
      } else {
        window.renderSchematicPreview(tbl);
      }
    } catch (e) { error(e.message); }
    finally { $('#btn-run-gmid').disabled = false; }
  };
}

if ($('#btn-apply-gmid')) {
  $('#btn-apply-gmid').onclick = () => {
    if (!lastSizedNetlist) return;
    $('#netlist').value = lastSizedNetlist;
    tab('net');
    window.renderSchematicPreview();
  };
}

// 5. Autonomous Hermes x Harness2 Closed-Loop (/api/generate + /api/status)
function updateAutonomousPhases(activePhase, failed) {
  for (let p = 1; p <= 6; p++) {
    const el = $(`#auto-phase-${p}`);
    if (!el) continue;
    el.className = 'phase-box ' + (p < activePhase ? 'done' : p === activePhase ? (failed ? 'err' : 'active') : '');
  }
}

if ($('#btn-run-autonomous')) {
  $('#btn-run-autonomous').onclick = async () => {
    const pdfPath = $('#sample-select')?.value || null;
    const prompt = $('#instruction')?.value.trim() || '';
    if (!pdfPath && !prompt) {
      return error('자율 폐루프를 실행하려면 샘플 PDF를 선택하거나 설계 요청을 입력해 주세요.');
    }
    try {
      error('');
      $('#autonomous-monitor').hidden = false;
      $('#auto-result-actions').hidden = true;
      $('#btn-run-autonomous').disabled = true;
      updateAutonomousPhases(1, false);
      const res = await api('/api/generate', {
        pdf_path: pdfPath,
        user_prompt: prompt,
        max_iterations: Number($('#hermes-max-iters').value || 20)
      });
      const taskId = res.task_id;
      clearInterval(autoPoller);
      autoPoller = setInterval(async () => {
        try {
          const st = await api('/api/status?task_id=' + encodeURIComponent(taskId));
          const isErr = st.status === 'failed';
          updateAutonomousPhases(st.current_phase || 1, isErr);
          const logs = st.logs || [];
          $('#auto-log-count').textContent = logs.length;
          $('#auto-logs').textContent = logs.join('\n') || '실행 중...';
          $('#run-status').textContent = `Hermes 자율 루프 · Phase ${st.current_phase}: ${st.phase_title}`;
          if (st.status !== 'running') {
            clearInterval(autoPoller);
            $('#btn-run-autonomous').disabled = false;
            if (isErr) { error(st.error || '자율 실행 실패'); return; }
            const sum = st.result_summary || {};
            lastAutoNetlist = sum.netlist_code || '';
            $('#auto-result-actions').hidden = false;
            if (st.dashboard_url) $('#auto-dashboard-link').href = st.dashboard_url;
            $('#selection-note').textContent = `Hermes 자율 완료 · ${sum.subckt_name || 'DUT'} 통과율 ${(sum.pass_rate_percent || 0).toFixed(1)}%`;
            if (lastAutoNetlist) window.renderSchematicPreview();
          }
        } catch (err) {
          clearInterval(autoPoller);
          $('#btn-run-autonomous').disabled = false;
          error(err.message);
        }
      }, 1200);
    } catch (e) {
      $('#btn-run-autonomous').disabled = false;
      error(e.message);
    }
  };
}

if ($('#btn-apply-auto-netlist')) {
  $('#btn-apply-auto-netlist').onclick = () => {
    if (!lastAutoNetlist) return;
    $('#netlist').value = lastAutoNetlist;
    tab('net');
    window.renderSchematicPreview();
  };
}

window.addEventListener('DOMContentLoaded', loadSampleDatasheets);
