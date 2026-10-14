"""
EDAI 화면 부품 모음 (NiceGUI).

화면(ui_app.py)은 이 파일의 부품을 조립해서 만든다. 모양과 동작의 원칙:
    밝은 복숭아색 바탕에 옅은 모눈, 크림색 둥근 카드, 굵고 진한 글자, 왼쪽 정렬.
    단계는 옆으로 넘기고(페이지처럼), 단계 안의 내용은 차례로 나타나며 아래로 따라 내려간다.
    제목은 명사형으로 끝낸다. 상태는 색만으로 전하지 않고 글자를 항상 같이 쓴다.

구성
    install_theme()        색·글꼴·움직임 규칙과 넘기기 동작을 페이지에 넣는다
    deck()                 맨 위 흐름 표시 + 옆으로 넘기는 단계 틀. with 안에서 panel() 을 그린다
    panel()                단계 하나 (머리말: 단계 이름, 제목, 결론 한 문장)
    scene()                단계 안에서 한 번에 나타나는 묶음. 차례로 나타나고 화면이 따라 내려간다
    io_cards()             "넣은 것 -> 한 일 -> 나온 것" 세 칸
    card()                 크림색 카드
    sub_title()            카드 안의 소제목
    goal_row()             쉬운 말 이름 + 원래 용어 + 값 + 표시 한 줄
    small_row()            접어 둔 자세한 목록의 한 줄
    more()                 접어 둔 자세한 내용
    figures(), figure()    큰 숫자
    meter()                통과 비율 선
    chip()                 작은 표시의 HTML
    response_chart()       선 그래프 (주파수 응답, 시간 응답)
    count_chart()          회차별 통과 수 그래프
    state_panel()          비어 있음 / 오류 안내

조작 (install_theme 이 넣는 스크립트가 처리)
    좌우 화살표: 이전·다음 단계        맨 위 단계 이름: 그 단계로 이동
    스페이스: 자동 재생 멈춤·계속       Enter: 지금 단계를 한꺼번에 펼치기
    주소 끝의 #2 같은 번호: 그 단계에서 시작        ?static=1: 모든 단계를 세로로 펼쳐 보기

사용 예시
    import ui_components as kit

    @ui.page("/example")
    def example():
        kit.install_theme()
        with kit.deck(["스펙 읽기", "구조 고르기"]):
            with kit.panel(0, "1단계 · 스펙 읽기", "데이터시트에서 설계 목표 추출", "25개 항목 중 15개가 설계 목표입니다."):
                with kit.scene():
                    kit.io_cards({"head": "데이터시트 PDF"}, {"head": "표 읽기"}, {"head": "설계 목표", "number": 15, "unit": "개"})
"""

from contextlib import contextmanager

from nicegui import ui

# ---- 그래프 색. 계열색은 1, 2, 3번 순서로만 쓴다 ----
SERIES_COLORS = ["#2a78d6", "#eb6834", "#1baf7a"]
CHART_INK, CHART_MUTED, CHART_GRID, CHART_AXIS = "#33271f", "#8a7868", "rgba(51,39,31,.10)", "rgba(51,39,31,.35)"
PASS_COLOR, FAIL_COLOR = "#2f7a55", "#c24f36"
TABLE_VIEW_POINTS = 8
# 장면이 나타난 뒤 다음 장면까지 기다리는 시간(초): 글자 수에 따라 정한다
HOLD_MIN_S, HOLD_MAX_S, READ_CHARS_PER_S = 5.0, 16.0, 9.0
# 가로축 눈금 글자: 큰 수는 k, M, G 로 줄여 서로 겹치지 않게 한다
AXIS_FORMATTER = ("v => Math.abs(v) >= 1e9 ? v / 1e9 + 'G' : Math.abs(v) >= 1e6 ? v / 1e6 + 'M' "
                  ": Math.abs(v) >= 1e3 ? v / 1e3 + 'k' : +v.toPrecision(3)")
PRETENDARD_CSS = "https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/variable/pretendardvariable-dynamic-subset.min.css"

THEME_CSS = """
:root { --bg: #f9e2c3; --cream: #fdf8ea; --ink: #33271f; --ink-2: #6a584b; --ink-3: #9a8878; --line: rgba(51,39,31,.16);
        --accent: #3a66b8; --pass: #2f7a55; --fail: #c24f36; --warn: #9a6216;
        --sans: "Pretendard Variable", "Pretendard", -apple-system, "Segoe UI", "Malgun Gothic", sans-serif;
        --mono: "JetBrains Mono", Consolas, "Pretendard Variable", "Malgun Gothic", monospace; }
html, body { height: 100%; }
body, .q-page, .nicegui-content { background: var(--bg) !important; color: var(--ink); font-family: var(--sans); }
.nicegui-content { padding: 0 !important; display: block !important; }
body { overflow: hidden; word-break: keep-all; overflow-wrap: anywhere; }
.dk-grid { position: fixed; inset: 0; z-index: 0; pointer-events: none;
  background-image: linear-gradient(rgba(51,39,31,.055) 1px, transparent 1px), linear-gradient(90deg, rgba(51,39,31,.055) 1px, transparent 1px);
  background-size: 32px 32px; animation: dkDrift 40s linear infinite; }

/* 맨 위 흐름 표시 */
.dk-bar { position: fixed; top: 14px; left: 50%; transform: translateX(-50%); z-index: 30; width: min(1080px, calc(100% - 40px));
          display: flex; align-items: center; gap: 6px; padding: 10px 14px 10px 20px; border-radius: 999px;
          background: rgba(253,248,234,.94); backdrop-filter: blur(10px); box-shadow: 0 6px 24px -14px rgba(51,39,31,.45); flex-wrap: wrap; }
.dk-bar .brand { font-weight: 700; font-size: 18px; margin-right: 10px; }
.dk-step { display: flex; align-items: center; gap: 8px; padding: 8px 15px; border-radius: 999px; font-size: 15px; font-weight: 600;
           color: var(--ink-3); background: transparent; border: none; cursor: pointer; font-family: var(--sans);
           transition: background .3s, color .3s; }
.dk-step b { width: 22px; height: 22px; border-radius: 50%; border: 1.5px solid currentColor; display: inline-flex; align-items: center;
             justify-content: center; font-size: 12px; }
.dk-step:hover { color: var(--ink); background: rgba(51,39,31,.06); }
.dk-step.done { color: var(--ink-2); }
.dk-step.now { background: var(--ink); color: var(--cream); animation: dkPulse 2.4s ease-in-out infinite; }
.dk-bar .arrow { color: var(--ink-3); font-size: 13px; }
.dk-bar .space { flex: 1; }
.dk-status { font-size: 13px; color: var(--ink-2); padding: 7px 14px; border-radius: 999px; border: 1px solid var(--line);
             background: transparent; cursor: pointer; font-family: var(--sans); white-space: nowrap; }
.dk-status:hover { background: rgba(51,39,31,.06); }

/* 옆으로 넘기는 틀 */
.dk-view { position: fixed; inset: 0; overflow: clip; z-index: 1; }
.dk-track { display: flex; height: 100%; transition: transform .9s cubic-bezier(.7,0,.2,1); will-change: transform; }
.dk-panel { flex: 0 0 100vw; width: 100vw; height: 100%; overflow-y: auto; scroll-behavior: smooth; padding: 120px 0 140px; outline: none !important; }
.dk-wrap { max-width: 1080px; margin: 0 auto; padding: 0 28px; }
.dk-arrow { position: fixed; top: 50%; z-index: 25; width: 54px; height: 54px; margin-top: -27px; border-radius: 50%;
            border: 1px solid var(--line); background: rgba(253,248,234,.94); color: var(--ink); font-size: 22px; cursor: pointer;
            display: flex; align-items: center; justify-content: center; transition: transform .25s, background .25s, opacity .3s;
            box-shadow: 0 6px 20px -12px rgba(51,39,31,.5); }
.dk-arrow:hover { background: var(--ink); color: var(--cream); transform: scale(1.06); }
.dk-arrow.prev { left: 22px; } .dk-arrow.next { right: 22px; }
.dk-arrow[disabled] { opacity: 0; pointer-events: none; }
.dk-arrow.next.ready { width: auto; padding: 0 22px; border-radius: 999px; background: var(--ink); color: var(--cream);
                       font-size: 16px; font-weight: 600; gap: 10px; animation: dkPulse 1.8s ease-in-out infinite; }
.dk-arrow.next .label { display: none; font-family: var(--sans); }
.dk-arrow.next.ready .label { display: inline; }

/* 단계 머리말 */
.dk-eyebrow { font-size: 15px; font-weight: 700; color: var(--accent); margin-bottom: 8px; }
.dk-title { font-size: 40px; font-weight: 700; letter-spacing: -.025em; line-height: 1.2; margin: 0 0 14px; }
.dk-lede { font-size: 19px; line-height: 1.6; color: var(--ink-2); max-width: 860px; margin-bottom: 30px; text-wrap: pretty; }
.dk-lede strong { color: var(--ink); font-weight: 700; }

/* 장면: 차례로 나타난다 */
.dk-scene { opacity: 0; transform: translateY(30px); transition: opacity .9s ease, transform .9s cubic-bezier(.2,.7,.2,1);
            scroll-margin-top: 110px; margin-bottom: 22px; }
.dk-scene.on { opacity: 1; transform: none; }

/* 넣은 것 -> 한 일 -> 나온 것 */
.dk-io { display: grid; grid-template-columns: 1fr auto 1fr auto 1fr; gap: 14px; align-items: stretch; }
.dk-card { background: var(--cream); border-radius: 24px; padding: 24px 26px; min-width: 0; }
.dk-card .tag { font-size: 13px; font-weight: 700; color: var(--ink-3); margin-bottom: 10px; }
.dk-card .head { font-size: 21px; font-weight: 700; margin-bottom: 8px; letter-spacing: -.01em; }
.dk-card p, .dk-text { font-size: 16px; line-height: 1.65; color: var(--ink-2); margin: 0; }
.dk-card .num { font-size: 52px; font-weight: 700; letter-spacing: -.03em; line-height: 1.05; font-variant-numeric: tabular-nums; }
.dk-card .num small { font-size: 19px; font-weight: 600; color: var(--ink-2); margin-left: 4px; }
.dk-io-arrow { align-self: center; font-size: 26px; color: var(--ink-3); }
.dk-doc { margin-top: 14px; border-radius: 12px; border: 1px solid var(--line); overflow: hidden; background: #fff; }
.dk-doc img { display: block; width: 100%; }
.dk-legend { display: flex; gap: 14px; font-size: 13px; color: var(--ink-2); margin-top: 8px; flex-wrap: wrap; }
.dk-legend i { display: inline-block; width: 12px; height: 12px; border-radius: 3px; margin-right: 6px; vertical-align: -1px; }
.dk-cols { display: grid; gap: 18px; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); }
.dk-card.chosen { box-shadow: inset 0 0 0 2px var(--accent), 0 18px 40px -28px rgba(58,102,184,.7); }
.dk-card.rejected { opacity: .78; }

.dk-sub { font-size: 17px; font-weight: 700; margin: 0 0 12px; }
.dk-row { display: flex; align-items: baseline; gap: 14px; padding: 15px 2px; border-top: 1px solid var(--line); flex-wrap: wrap; }
.dk-row .plain { font-size: 18px; font-weight: 600; }
.dk-row .term { font-size: 14px; color: var(--ink-3); flex: 1; min-width: 6rem; }
.dk-row .value { font-family: var(--mono); font-size: 17px; font-weight: 600; white-space: nowrap; font-variant-numeric: tabular-nums; }
.dk-row .goal { font-family: var(--mono); font-size: 14px; color: var(--ink-3); white-space: nowrap; }
.dk-row.fail .value { color: var(--fail); }
.dk-row .was { font-family: var(--mono); font-size: 15px; color: var(--ink-3); text-decoration: line-through; white-space: nowrap; }
.dk-row.changed .value { color: var(--accent); }
.dk-chip { display: inline-block; font-size: 12.5px; font-weight: 700; padding: 3px 11px; border-radius: 999px; border: 1px solid var(--line);
           color: var(--ink-2); white-space: nowrap; }
.dk-chip.warn { color: var(--warn); border-color: rgba(154,98,22,.45); }
.dk-chip.pass { color: var(--pass); border-color: rgba(47,122,85,.5); }
.dk-chip.fail { color: var(--fail); border-color: rgba(194,79,54,.55); }
.dk-chip.solid { color: var(--cream); background: var(--ink); border-color: var(--ink); }
.dk-more { margin-top: 12px; }
.dk-more .q-item { padding-left: 0; font-size: 16px; font-weight: 600; color: var(--accent); }
.dk-more .q-item__section--side { color: var(--accent); }
.dk-small { display: flex; gap: 12px; padding: 9px 0; border-top: 1px solid var(--line); font-size: 15px; flex-wrap: wrap; align-items: baseline; }
.dk-small .n { font-weight: 600; min-width: 13rem; }
.dk-small .c { color: var(--ink-2); flex: 1; }
.dk-small .g { font-family: var(--mono); white-space: nowrap; }
.dk-quote { font-size: 16px; line-height: 1.65; color: var(--ink-2); border-left: 3px solid var(--line); padding: 2px 0 2px 14px; margin: 6px 0 12px; }

.dk-figs { display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); gap: 0 26px; }
.dk-fig { border-top: 2px solid var(--ink); padding: 14px 0 6px; }
.dk-fig .label { font-size: 16px; font-weight: 700; min-height: 3em; }
.dk-fig .term { font-size: 13px; color: var(--ink-3); margin-bottom: 4px; }
.dk-fig .num { font-size: 44px; font-weight: 700; letter-spacing: -.03em; line-height: 1.15; font-variant-numeric: tabular-nums; }
.dk-fig .unit { font-size: 17px; font-weight: 600; color: var(--ink-2); margin-left: 5px; }
.dk-fig .note { font-size: 14px; color: var(--ink-2); margin-top: 2px; }

.dk-meter { height: 6px; width: 100%; background: rgba(51,39,31,.12); border-radius: 6px; overflow: hidden; margin: 12px 0 8px; }
.dk-meter > i { display: block; height: 100%; background: var(--pass); border-radius: 6px; transform-origin: left; transform: scaleX(0);
                transition: transform 1.2s cubic-bezier(.2,.7,.2,1) .3s; }
.dk-meter.partial > i { background: var(--warn); }
.dk-scene.on .dk-meter > i { transform: scaleX(1); }
.dk-chart .q-table__card, .dk-chart .q-table { background: transparent !important; color: var(--ink-2); box-shadow: none; }

/* 전체 보기: 모든 단계를 세로로 펼친다 */
body.dk-static { overflow: auto; }
.dk-static .dk-view { position: static; overflow: visible; }
.dk-static .dk-track { display: block; transform: none !important; height: auto; }
.dk-static .dk-panel { width: auto; height: auto; overflow: visible; padding: 110px 0 30px; }
.dk-static .dk-scene { opacity: 1; transform: none; }
.dk-static .dk-arrow { display: none; }

@keyframes dkPulse { 0%, 100% { box-shadow: 0 0 0 0 rgba(51,39,31,.30); } 50% { box-shadow: 0 0 0 10px rgba(51,39,31,0); } }
@keyframes dkDrift { from { background-position: 0 0; } to { background-position: 32px 32px; } }
:focus-visible { outline: 2px solid var(--accent); outline-offset: 3px; }
@media (prefers-reduced-motion: reduce) {
  .dk-grid, .dk-step.now, .dk-arrow.next.ready { animation: none !important; }
  .dk-track, .dk-scene, .dk-meter > i { transition: none !important; }
  .dk-panel { scroll-behavior: auto; }
}
@media (max-width: 860px) {
  .dk-io { grid-template-columns: 1fr; } .dk-io-arrow { transform: rotate(90deg); justify-self: center; }
  .dk-title { font-size: 30px; } .dk-arrow { top: auto; bottom: 18px; } .dk-step span { display: none; }
}
"""

# 단계 넘기기와 장면 재생. 화면 내용은 처음에 한 번 다 그려 두고, 보이는 순서만 여기서 조절한다.
DECK_SCRIPT = """
<script>
(function () {
  var cur = 0, auto = true, timer = null, panels = [], track, steps, nextBtn, prevBtn, statusBtn;
  var isStatic = /[?&]static=1/.test(location.search);
  var reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  function countUp(el) {
    if (reduce || el.dataset.done) return;
    el.dataset.done = '1';
    var end = parseFloat(el.dataset.count), start = performance.now(), whole = Number.isInteger(end);
    function frame() {
      var p = Math.max(0, Math.min(1, (performance.now() - start) / 1200)), eased = 1 - Math.pow(1 - p, 3);
      el.textContent = p < 1 ? (whole ? Math.round(end * eased) : Number((end * eased).toPrecision(4))).toString() : el.dataset.final;
      if (p < 1) requestAnimationFrame(frame);
    }
    requestAnimationFrame(frame);
  }
  function show(scene) { scene.classList.add('on'); scene.querySelectorAll('[data-count]').forEach(countUp); }
  function scenes(n) { return Array.prototype.slice.call(panels[n].querySelectorAll('.dk-scene')); }
  function finish(n) { panels[n].dataset.seen = '1'; if (n === cur && n < panels.length - 1) nextBtn.classList.add('ready'); }
  function revealAll(n) { scenes(n).forEach(show); finish(n); }
  function playFrom(n) {
    clearTimeout(timer);
    if (n !== cur) return;
    var list = scenes(n), i = list.findIndex(function (s) { return !s.classList.contains('on'); });
    if (i < 0) { finish(n); return; }
    show(list[i]);
    if (i > 0) scrollToScene(panels[n], list[i]);
    var hold = parseFloat(list[i].dataset.hold || '6') * 1000;
    if (auto) timer = setTimeout(function () { playFrom(n); }, hold);
  }
  // 단계 안에서만 아래로 내린다 (scrollIntoView 는 옆으로 넘기는 틀까지 움직일 수 있어 쓰지 않는다)
  function scrollToScene(panel, scene) {
    // 새 장면의 아래 끝이 보일 만큼만 내린다. 장면이 화면보다 길면 장면의 위 끝을 맞춘다
    var box = scene.getBoundingClientRect(), frame = panel.getBoundingClientRect();
    var toTop = panel.scrollTop + box.top - frame.top - 100;
    var toBottom = panel.scrollTop + box.bottom - frame.bottom + 70;
    var top = Math.min(toTop, toBottom);
    if (top > panel.scrollTop) panel.scrollTo({ top: top, behavior: reduce ? 'auto' : 'smooth' });
  }
  function setStatus() { statusBtn.textContent = auto ? '자동 재생 중 · Space 로 멈춤' : '멈춤 · Space 로 계속'; }
  function go(n) {
    n = Math.max(0, Math.min(panels.length - 1, n));
    clearTimeout(timer);
    cur = n;
    track.style.transform = 'translateX(' + (-n * 100) + 'vw)';
    steps.forEach(function (s, i) { s.classList.toggle('now', i === n); s.classList.toggle('done', i < n);
                                    s.setAttribute('aria-current', i === n ? 'step' : 'false'); });
    prevBtn.disabled = n === 0; nextBtn.disabled = n === panels.length - 1;
    nextBtn.classList.remove('ready');
    history.replaceState(null, '', location.pathname + location.search + '#' + (n + 1));
    panels[n].focus({ preventScroll: true });
    if (panels[n].dataset.seen) { revealAll(n); } else { panels[n].scrollTop = 0; setTimeout(function () { playFrom(n); }, 700); }
  }
  function init() {
    var deck = document.querySelector('.dk-view');
    if (!deck || deck.dataset.ready) return;
    panels = Array.prototype.slice.call(document.querySelectorAll('.dk-panel'));
    steps = Array.prototype.slice.call(document.querySelectorAll('.dk-step'));
    if (!panels.length || steps.length !== panels.length) return;
    deck.dataset.ready = '1';
    track = document.querySelector('.dk-track');
    nextBtn = document.querySelector('.dk-arrow.next'); prevBtn = document.querySelector('.dk-arrow.prev');
    statusBtn = document.querySelector('.dk-status');
    if (isStatic) {
      document.body.classList.add('dk-static');
      document.querySelectorAll('.dk-scene').forEach(show);
      statusBtn.textContent = '단계별로 보기'; statusBtn.onclick = function () { location.href = location.pathname; };
      steps.forEach(function (s, i) { s.onclick = function () { panels[i].scrollIntoView({ behavior: 'smooth' }); }; });
      return;
    }
    steps.forEach(function (s, i) { s.onclick = function () { go(i); }; });
    nextBtn.onclick = function () { go(cur + 1); }; prevBtn.onclick = function () { go(cur - 1); };
    statusBtn.onclick = toggle;
    document.addEventListener('keydown', function (e) {
      if (e.target && /INPUT|TEXTAREA/.test(e.target.tagName)) return;
      if (e.key === 'ArrowRight' || e.key === 'PageDown') { e.preventDefault(); go(cur + 1); }
      else if (e.key === 'ArrowLeft' || e.key === 'PageUp') { e.preventDefault(); go(cur - 1); }
      else if (e.key === ' ') { e.preventDefault(); toggle(); }
      else if (e.key === 'Enter') { e.preventDefault(); clearTimeout(timer); revealAll(cur); }
    });
    setStatus();
    var start = parseInt(location.hash.slice(1), 10);
    go(isNaN(start) ? 0 : start - 1);
  }
  function toggle() { auto = !auto; setStatus(); if (auto) playFrom(cur); else clearTimeout(timer); }
  new MutationObserver(init).observe(document.documentElement, { childList: true, subtree: true });
  document.addEventListener('DOMContentLoaded', init);
})();
</script>
"""


def install_theme() -> None:
    """색·글꼴·움직임 규칙과 넘기기 동작을 페이지에 넣는다."""
    ui.add_head_html(f'<link rel="stylesheet" href="{PRETENDARD_CSS}">')  # 인터넷이 없으면 시스템 글꼴로 보인다
    ui.add_css(THEME_CSS)
    ui.add_head_html(DECK_SCRIPT)


def escape(text) -> str:
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def html(markup: str, classes: str = ""):
    """직접 쓴 HTML 조각. 바깥에서 온 글자는 반드시 escape() 를 거쳐 넣는다."""
    return ui.html(markup, sanitize=False).classes(classes)


def _text_length(element) -> int:
    """요소 안에 들어 있는 글자 수 (장면을 읽는 데 걸리는 시간을 정하는 데 쓴다)."""
    total = 0
    for child in element.descendants():
        content = getattr(child, "content", "") or getattr(child, "text", "") or ""
        inside, count = False, 0
        for char in str(content):
            if char == "<":
                inside = True
            elif char == ">":
                inside = False
            elif not inside and not char.isspace():
                count += 1
        total += count
    return total


@contextmanager
def deck(step_names: list, brand: str = "edai"):
    """맨 위 흐름 표시와 옆으로 넘기는 틀. with 안에서 panel() 을 단계 수만큼 그린다."""
    ui.element("div").classes("dk-grid").props("aria-hidden=true")
    steps = "".join(
        f'<button class="dk-step" type="button"><b>{index + 1}</b><span>{escape(name)}</span></button>'
        + ('<span class="arrow" aria-hidden="true">→</span>' if index < len(step_names) - 1 else "")
        for index, name in enumerate(step_names))
    html(f'<span class="brand">{escape(brand)}</span>{steps}<span class="space"></span>'
         f'<button class="dk-status" type="button">자동 재생 중</button>'
         f'<a class="dk-status" href="?static=1">전체 보기</a>', "dk-bar").props('role="navigation" aria-label="단계 이동"')
    html('<button class="dk-arrow prev" type="button" aria-label="이전 단계">←</button>'
         '<button class="dk-arrow next" type="button" aria-label="다음 단계"><span class="label">다음 단계</span>→</button>')
    with ui.element("div").classes("dk-view"):
        with ui.element("div").classes("dk-track") as track:
            yield track


@contextmanager
def panel(index: int, eyebrow: str, title: str, lede_html: str):
    """단계 하나. 머리말(단계 이름, 제목, 결론 한 문장)이 첫 장면이 된다. lede_html 은 <strong> 을 쓸 수 있다."""
    with ui.element("section").classes("dk-panel").props(f'tabindex="-1" aria-label="{title}" id="step-{index + 1}"'):
        with ui.element("div").classes("dk-wrap"):
            with scene():
                html(escape(eyebrow), "dk-eyebrow")
                html(escape(title), "dk-title").props("role=heading aria-level=1")
                html(lede_html, "dk-lede")
            yield


@contextmanager
def scene(anchor: str = "", hold: float = 0.0):
    """한 번에 나타나는 묶음. hold(초)를 주지 않으면 안에 든 글자 수로 읽는 시간을 정한다."""
    with ui.element("div").classes("dk-scene") as element:
        if anchor:
            element.props(f'id="{anchor}"')
        yield element
    seconds = hold or max(HOLD_MIN_S, min(HOLD_MAX_S, _text_length(element) / READ_CHARS_PER_S))
    element.props(f'data-hold="{seconds:.1f}"')


def card(classes: str = ""):
    """크림색 카드. with 로 열어 안에 내용을 그린다."""
    return ui.element("div").classes(f"dk-card {classes}")


def columns():
    """화면 폭에 맞춰 나란히 놓는 칸. with 로 연다."""
    return ui.element("div").classes("dk-cols")


def io_cards(given: dict, work: dict, result: dict) -> None:
    """'넣은 것 -> 한 일 -> 나온 것' 세 칸.

    각 칸은 dict: head(제목), body(설명 HTML), number·unit(큰 숫자), extra(추가 HTML). 없는 것은 생략한다.
    """
    with ui.element("div").classes("dk-io"):
        for index, (tag, box) in enumerate((("넣은 것", given), ("한 일", work), ("나온 것", result))):
            if index:
                html("→", "dk-io-arrow").props("aria-hidden=true")
            with card():
                html(tag, "tag")
                html(escape(box.get("head", "")), "head")
                if "number" in box:
                    html(f'<div class="num"><span data-count="{box["number"]}" data-final="{box["number"]}">{box["number"]}</span>'
                         f'<small>{escape(box.get("unit", ""))}</small></div>')
                if box.get("body"):
                    html(f'<p>{box["body"]}</p>').style("margin-top:6px")
                if box.get("extra"):
                    html(box["extra"])


def sub_title(text: str):
    return html(escape(text), "dk-sub")


def chip(text: str, tone: str = "") -> str:
    """작은 표시의 HTML. tone: warn, pass, fail, solid."""
    return f'<span class="dk-chip {tone}">{escape(text)}</span>'


def goal_row(plain: str, term: str = "", value: str = "", goal: str = "", chips: str = "", state: str = "",
             was: str = "") -> None:
    """한 줄: 쉬운 말 이름, 원래 용어, (이전 값), 값, 목표, 표시. state 는 'fail' 또는 'changed'."""
    html(f'<span class="plain">{escape(plain)}</span><span class="term">{escape(term)}</span>'
         + (f'<span class="was">{escape(was)}</span>' if was else "")
         + (f'<span class="value">{escape(value)}</span>' if value else "")
         + (f'<span class="goal">{escape(goal)}</span>' if goal else "") + chips,
         f"dk-row {state}").props("role=row")


def small_row(name: str, note: str = "", value: str = "") -> None:
    """접어 둔 자세한 목록의 한 줄."""
    html(f'<span class="n">{escape(name)}</span><span class="c">{escape(note)}</span>'
         f'<span class="g">{escape(value)}</span>', "dk-small")


def more(title: str):
    """접어 둔 자세한 내용. 누르면 펼쳐진다. with 로 연다."""
    return ui.expansion(title).classes("dk-more w-full")


def figures():
    """큰 숫자를 나란히 놓는 칸. with 로 열어 figure() 를 그린다."""
    return ui.element("div").classes("dk-figs")


def figure(label: str, value: float, unit: str = "", term: str = "", note: str = "", digits: int = 4) -> None:
    """큰 숫자 하나. 장면이 나타날 때 숫자가 올라간다. figures() 안에서 쓴다."""
    final = f"{value:.{digits}g}"
    with ui.element("div").classes("dk-fig"):
        html(escape(label), "label")
        if term:
            html(escape(term), "term")
        html(f'<span class="num" data-count="{value}" data-final="{final}" '
             f'aria-label="{escape(label)} {final} {escape(unit)}">{final}</span><span class="unit">{escape(unit)}</span>')
        if note:
            html(escape(note), "note")


def meter(passed: int, total: int) -> None:
    """통과 비율 선. 장면이 나타날 때 차오른다."""
    ratio = passed / total if total else 0
    partial = " partial" if passed < total else ""
    html(f'<div class="dk-meter{partial}" role="img" aria-label="{total}개 중 {passed}개 통과">'
         f'<i style="width:{ratio * 100:.1f}%"></i></div>')


def state_panel(kind: str, title: str, detail: str = "") -> None:
    """비어 있음(empty) / 오류(error) 안내."""
    tone, text = ("", "비어 있음") if kind == "empty" else ("fail", "오류")
    with ui.element("div").style("max-width:720px;margin:140px auto;padding:0 24px;position:relative;z-index:1") \
            .props(f'role="{"status" if kind == "empty" else "alert"}"'):
        with card():
            html(chip(text, tone))
            html(escape(title), "head").style("margin-top:12px")
            if detail:
                html(f"<p>{escape(detail)}</p>").style("word-break:break-all")


def _chart_base(height: str, options: dict, label: str):
    return ui.echart(options).style(f"width:100%;height:{height}").props(f'role=img aria-label="{label}"')


def response_chart(title: str, series: list, x_label: str, y_label: str, x_log: bool = False,
                   limits: tuple = (), height: str = "320px") -> None:
    """선 그래프 (주파수 응답, 시간 응답). 선이 왼쪽부터 그려지며 나타난다.

    series: [{"name": 이름, "x": [...], "y": [...]}] - 순서대로 계열색 1, 2, 3번 (최대 3개)
    limits: [{"label": 글자, "value": 값, "axis": "x" 또는 "y"}] - 기준선 (점선)
    y축은 하나만 쓴다. 단위가 다른 두 값(이득과 위상 등)은 그래프를 나눠 그린다.
    """
    with card("dk-chart"):
        sub_title(title)
        if not series or not any(len(s["x"]) for s in series):
            html("<p>그릴 파형이 없습니다. 시뮬레이션을 먼저 실행하세요.</p>")
            return
        mark_lines = [
            {("xAxis" if limit["axis"] == "x" else "yAxis"): limit["value"], "name": limit["label"],
             "label": {"formatter": limit["label"], "color": CHART_MUTED, "position": "insideEndTop", "fontSize": 12}}
            for limit in limits
        ]
        options = {
            "aria": {"enabled": True},
            "backgroundColor": "transparent",
            "animationDuration": 1800,
            "animationEasing": "cubicOut",
            "color": SERIES_COLORS,
            "textStyle": {"color": CHART_INK, "fontFamily": "Pretendard Variable, Segoe UI, sans-serif"},
            "grid": {"left": 56, "right": 22, "top": 42, "bottom": 50},
            "tooltip": {"trigger": "axis", "backgroundColor": "#fdf8ea", "borderColor": CHART_AXIS,
                        "textStyle": {"color": CHART_INK, "fontSize": 14},
                        "axisPointer": {"type": "cross", "lineStyle": {"color": CHART_AXIS},
                                        "label": {"backgroundColor": "#33271f"}},
                        ":valueFormatter": "v => (v === undefined || v === null) ? '-' : Number(v).toPrecision(4)"},
            "legend": {"show": len(series) > 1, "top": 0, "right": 4, "icon": "roundRect", "itemWidth": 16,
                       "itemHeight": 4, "textStyle": {"color": CHART_INK, "fontSize": 13}},
            "xAxis": {"type": "log" if x_log else "value", "name": x_label, "nameLocation": "middle", "nameGap": 32,
                      "nameTextStyle": {"color": CHART_MUTED, "fontSize": 13},
                      "axisLine": {"lineStyle": {"color": CHART_AXIS}}, "axisTick": {"show": False},
                      "axisLabel": {"color": CHART_MUTED, "fontSize": 12, ":formatter": AXIS_FORMATTER},
                      "splitLine": {"lineStyle": {"color": CHART_GRID}}, "min": "dataMin", "max": "dataMax"},
            "yAxis": {"type": "value", "name": y_label, "nameTextStyle": {"color": CHART_MUTED, "fontSize": 13},
                      "axisLabel": {"color": CHART_MUTED, "fontSize": 12},
                      "splitLine": {"lineStyle": {"color": CHART_GRID}}, "scale": True},
            "series": [
                {"name": s["name"], "type": "line", "showSymbol": False, "lineStyle": {"width": 2.5},
                 "emphasis": {"focus": "series"},
                 "data": [[float(x), float(y)] for x, y in zip(s["x"], s["y"])],
                 **({"markLine": {"silent": True, "symbol": "none",
                                  "lineStyle": {"type": "dashed", "color": CHART_MUTED, "width": 1},
                                  "data": mark_lines}} if index == 0 and mark_lines else {})}
                for index, s in enumerate(series[:len(SERIES_COLORS)])
            ],
        }
        _chart_base(height, options, f"{title}: {', '.join(s['name'] for s in series)}")
        with more("표로 보기"):
            for s in series:
                step_size = max(1, len(s["x"]) // TABLE_VIEW_POINTS)
                rows = [{"x": f"{float(x):.4g}", "y": f"{float(y):.4g}"}
                        for x, y in zip(s["x"][::step_size], s["y"][::step_size])]
                ui.table(columns=[{"name": "x", "label": x_label, "field": "x", "align": "right"},
                                  {"name": "y", "label": y_label, "field": "y", "align": "right"}],
                         rows=rows, title=s["name"]).props("dense flat").classes("w-full")


def count_chart(title: str, labels: list, values: list, total: int, anchors: list = ()) -> None:
    """회차별 통과 수 막대그래프. 모두 통과한 회차는 초록, 아니면 주황. 막대를 누르면 해당 회차로 내려간다."""
    with card("dk-chart"):
        sub_title(title)
        options = {
            "aria": {"enabled": True},
            "backgroundColor": "transparent",
            "animationDuration": 1400,
            "animationEasing": "cubicOut",
            "textStyle": {"color": CHART_INK, "fontFamily": "Pretendard Variable, Segoe UI, sans-serif"},
            "grid": {"left": 44, "right": 20, "top": 30, "bottom": 34},
            "tooltip": {"trigger": "axis", "backgroundColor": "#fdf8ea", "borderColor": CHART_AXIS,
                        "textStyle": {"color": CHART_INK, "fontSize": 14}},
            "xAxis": {"type": "category", "data": labels, "axisLine": {"lineStyle": {"color": CHART_AXIS}},
                      "axisTick": {"show": False}, "axisLabel": {"color": CHART_INK, "fontSize": 14, "fontWeight": 600}},
            "yAxis": {"type": "value", "min": 0, "max": total + 3, "interval": 3, "splitLine": {"lineStyle": {"color": CHART_GRID}},
                      "axisLabel": {"color": CHART_MUTED, "fontSize": 12}},
            "series": [{
                "name": "통과한 목표 수", "type": "bar", "barWidth": "38%",
                "itemStyle": {"borderRadius": [8, 8, 0, 0]},
                "label": {"show": True, "position": "insideTop", "distance": 12, "color": "#fff", "fontSize": 17, "fontWeight": 700,
                          "formatter": "{c} / " + str(total)},
                "data": [{"value": value, "itemStyle": {"color": PASS_COLOR if value >= total else "#d99a3f"}}
                         for value in values],
                "markLine": {"silent": True, "symbol": "none",
                             "lineStyle": {"type": "dashed", "color": CHART_MUTED, "width": 1},
                             "label": {"formatter": "모두 통과", "color": CHART_MUTED, "position": "insideEndTop"},
                             "data": [{"yAxis": total}]},
            }],
        }

        def jump(event) -> None:
            index = getattr(event, "data_index", None)
            if anchors and index is not None and index < len(anchors):
                ui.run_javascript(
                    f"(function(){{var s=document.getElementById('{anchors[index]}');if(!s)return;"
                    "var p=s.closest('.dk-panel');if(document.body.classList.contains('dk-static'))"
                    "{s.scrollIntoView({behavior:'smooth'});return;}"
                    "p.scrollTo({top:p.scrollTop+s.getBoundingClientRect().top-p.getBoundingClientRect().top-100,"
                    "behavior:'smooth'});}})()")

        ui.echart(options, on_point_click=jump).style("width:100%;height:260px") \
            .props(f'role=img aria-label="{title}: {", ".join(f"{a} {b}개" for a, b in zip(labels, values))}"')
