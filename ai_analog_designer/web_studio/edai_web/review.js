'use strict';
let reviewData = null;
window.confirmationId = null;
window.invalidateReview = () => {
  window.confirmationId = null;
  const c = $('#review-consent');
  if (c) c.checked = false;
  const st = $('#review-state');
  if (st) st.textContent = '자료 또는 목표가 변경되었습니다. 확인 정보를 다시 저장하세요.';
};

const keys = ['name','value','unit','kind','condition','source','page','quote'];
const labels = {name:'항목명', value:'값', unit:'단위', kind:'구분', condition:'측정 조건', source:'파일명', page:'페이지', quote:'원문 근거'};

function addField(field = {}) {
  const row = document.createElement('div');
  row.className = 'review-field';
  row.dataset.evidence = field.evidence_status || 'user_entered';
  row.innerHTML = '<div class="field-grid">' + keys.map(k => `<label>${labels[k]}<input data-field="${k}" value="${esc(field[k]??'')}"></label>`).join('') + '</div>'
    + `<p class="note">${field.evidence_status==='text_match'?'원문 인용 일치 · 값·단위·조건 확인':'사용자 원문 대조 필요'}</p><button type="button" class="text-button">항목 삭제</button>`;
  row.querySelector('button').onclick = () => { row.remove(); window.invalidateReview(); };
  row.addEventListener('input', () => { row.dataset.evidence = 'user_edited'; window.invalidateReview(); });
  $('#review-fields').append(row);
}

async function extractFiles(useAI) {
  try {
    error('');
    const files = Array.from($('#source-files').files);
    if (!files.length) throw Error('PDF 또는 자료 파일을 선택해 주세요.');
    aiBusy = true; lock(true);
    $('#extract-local').disabled = true; $('#extract-ai').disabled = true;
    $('#ai-status').textContent = useAI ? 'AI가 항목과 출처를 추출하고 있습니다…' : '로컬에서 페이지 텍스트를 추출하고 있습니다…';
    const result = await api('/api/extract', {files: await Promise.all(files.map(encodeFile)), use_ai: useAI, instruction: $('#instruction').value.trim()});
    reviewData = result; window.confirmationId = null;
    $('#review-panel').hidden = false;
    $('#review-fields').innerHTML = '';
    result.fields.forEach(addField);
    if (!result.fields.length) addField();
    $('#review-pages').innerHTML = result.pages.map(p => `<h3>${esc(p.source)} · ${p.page}쪽</h3><pre>${esc(p.text||'(텍스트 없음)')}</pre>`).join('');
    $('#review-warning').textContent = (result.warnings || []).join(' / ');
    $('#review-state').textContent = '추출 완료. 원문과 목표를 검토한 뒤 확인 정보를 저장하세요.';
    $('#review-consent').checked = false;
    $('#ai-status').textContent = useAI ? `AI 추출 완료 · ${result.fields.length}개 항목` : '로컬 텍스트 추출 완료';
  } catch (e) { error(e.message); }
  finally {
    aiBusy = false; lock(job?.state === 'running');
    $('#extract-local').disabled = false; $('#extract-ai').disabled = false;
  }
}

$('#extract-local').onclick = () => extractFiles(false);
$('#extract-ai').onclick = () => extractFiles(true);
$('#field-add').onclick = () => { addField(); window.invalidateReview(); };
$('#source-files').addEventListener('change', () => { reviewData = null; $('#review-panel').hidden = true; window.invalidateReview(); });
$('#instruction').addEventListener('input', window.invalidateReview);

$('#confirm-review').onclick = async () => {
  try {
    if (!reviewData) throw Error('자료를 먼저 추출하세요.');
    const fields = $$('#review-fields .review-field').map(row => ({
      ...Object.fromEntries(Array.from(row.querySelectorAll('[data-field]')).map(e => [e.dataset.field, e.value.trim()])),
      evidence_status: row.dataset.evidence
    })).filter(r => r.name);
    const data = await api('/api/confirm', {review_id: reviewData.review_id, fields, goals: $('#instruction').value.trim(), confirmed: $('#review-consent').checked});
    window.confirmationId = data.confirmation_id;
    $('#review-state').textContent = '확인 정보 저장 완료. 베이스 회로 초안을 생성하거나 실행하세요.';
    error('');
  } catch (e) { error(e.message); }
};

$('#config-save').onclick = async () => {
  try {
    await api('/api/settings', {simulator: $('#config-engine').value, simulator_path: $('#config-path').value, model: $('#config-model').value});
    error(''); await refreshStatus();
  } catch (e) { error(e.message); }
};

api('/api/settings').then(c => {
  $('#config-engine').value = c.simulator || 'ltspice';
  $('#config-path').value = c.simulator_path || '';
  $('#config-model').value = c.model || '';
}).catch(() => {});

window.renderComparison = () => {
  const first = job?.runs?.[0], current = job?.runs?.find(r => r.iteration === selected);
  if (!first || !current) { $('#before-after').innerHTML = ''; return; }
  const names = [...new Set(job.settings.goals.map(g => g.measure))];
  $('#before-after').innerHTML = '<table><thead><tr><th>지표</th><th>초기</th><th>선택 #' + selected + '</th></tr></thead><tbody>'
    + names.map(n => `<tr><td>${esc(n)} (${esc(job.settings.goals.find(g=>g.measure===n)?.unit||'')})</td><td>${fmt(first.metrics[n])}</td><td>${fmt(current.metrics[n])}</td></tr>`).join('')
    + '</tbody></table>';
};
