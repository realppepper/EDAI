"""
결과 화면(make_run_report.py)의 그림: 2단계 후보 회로도 모음, 3단계 후보 깔때기, 3~5단계 후보 x 스펙 표, 7단계 튜닝 그래프.
모두 실행 폴더에 이미 있는 결과(candidates.json, selection.json, tune.json)로 그린다. 그림은 결과 화면의 색 이름(--ok, --bad,
--accent, --line ...)만 써서 밝은·어두운 화면 모두에서 읽힌다.

후보 회로도는 2단계가 끝날 때 pipeline.step_candidates 가 draw_candidates 로 실행 폴더 candidates/ 에 SVG 로 그려 둔다
(후보 하나에 1~2초, netlistsvg 가 있는 WSL 에서만). 없으면 회로도 자리 없이 글만 보여 준다.
"""

import html
import json
import re
from pathlib import Path

GALLERY_FIRST = 6           # 후보 그림 모음에서 처음에 보여 줄 개수 (나머지는 '더보기')
GRID_FIRST = 10             # 후보 x 스펙 표에서 처음에 보여 줄 회로 수 (나머지는 '더보기')
CANDIDATE_DIR = "candidates"

CSS = """
.fig-note { color:var(--muted); font-size:12px; margin:4px 0 10px; }
/* 후보 그림 모음 */
.gallery { display:grid; grid-template-columns:repeat(auto-fill, minmax(150px, 1fr)); gap:10px; margin:10px 0; }
.cand { border:1px solid var(--line); border-radius:8px; background:var(--bg); padding:8px; display:flex; flex-direction:column;
        gap:6px; min-width:0; }
.cand.picked { border-color:var(--accent); box-shadow:0 0 0 1px var(--accent); }
.cand a.pic { display:block; aspect-ratio:4/3; background:#fff; border-radius:4px; overflow:hidden; }
.cand a.pic img { width:100%; height:100%; object-fit:contain; display:block; }
.cand .pic.none { display:grid; place-items:center; color:#888; font-size:11px; }
.cand .name { font-weight:600; font-size:13px; display:flex; justify-content:space-between; gap:6px; }
.cand .tags { display:flex; flex-wrap:nowrap; justify-content:flex-start; gap:4px; overflow:hidden; }
.tag { font-size:11px; border:1px solid var(--line); border-radius:999px; padding:0 7px; color:var(--muted); white-space:nowrap; }
.tag.new { color:var(--accent); border-color:var(--accent); }
.res { font-size:12px; } .res.ok { color:var(--ok); } .res.no { color:var(--muted); }
details.more > summary { margin:4px 0; font-size:13px; }
/* 깔때기 */
.funnel { display:grid; grid-template-columns:minmax(0, 15em) 1fr; gap:6px 12px; align-items:center; margin:10px 0 4px; font-size:13px; }
.funnel .lab { color:var(--fg); min-width:0; }
.funnel .lab small { color:var(--muted); display:block; font-size:11px; }
.funnel .track { display:flex; align-items:center; gap:8px; min-width:0; }
.funnel .bar { height:14px; border-radius:0 4px 4px 0; background:var(--accent); min-width:3px; }
.funnel .n { font-variant-numeric:tabular-nums; font-weight:600; white-space:nowrap; }
.funnel .n small { color:var(--muted); font-weight:400; margin-left:4px; }
@media (max-width:560px) { .funnel { grid-template-columns:1fr; } }
/* 후보 x 스펙 표 */
.gridwrap { overflow-x:auto; }
table.spec-grid { border-collapse:separate; border-spacing:0; font-size:12px; font-variant-numeric:tabular-nums; }
table.spec-grid th, table.spec-grid td { border-bottom:1px solid var(--line); padding:5px 8px; white-space:nowrap; }
table.spec-grid thead th { vertical-align:bottom; }
table.spec-grid thead small { display:block; font-weight:400; color:var(--muted); }
table.spec-grid tr.count td { color:var(--muted); font-size:11px; }
table.spec-grid td.v { text-align:right; }
table.spec-grid td.v.ok { color:var(--ok); }
table.spec-grid td.v.no { color:var(--bad); background:color-mix(in srgb, var(--bad) 9%, transparent); }
table.spec-grid td.v .mk { font-size:10px; margin-right:4px; }
table.spec-grid tr.picked th, table.spec-grid tr.picked td { box-shadow:inset 0 2px 0 var(--accent), inset 0 -2px 0 var(--accent); }
table.spec-grid th.row small { display:block; color:var(--muted); font-weight:400; }
.more-btn { font:inherit; font-size:13px; color:var(--accent); background:none; border:0; padding:4px 0; cursor:pointer; }
.more-btn:focus-visible { outline:2px solid var(--accent); outline-offset:2px; }
/* 튜닝 그래프: 한 줄에 2개, 커서를 대면 안내선과 말풍선 (SCRIPT) */
.multiples { display:grid; grid-template-columns:repeat(auto-fit, minmax(min(340px, 100%), 1fr)); gap:14px; margin:12px 0; }
.mini { position:relative; border:1px solid var(--line); border-radius:10px; background:var(--bg); padding:10px 12px 6px; min-width:0; }
.mini h4 { font-size:14px; margin:0 0 4px; font-weight:600; } .mini h4 small { color:var(--muted); font-weight:400; margin-left:4px; }
.mini svg { width:100%; height:auto; display:block; overflow:visible; cursor:crosshair; touch-action:pan-y; }
.mini .band { fill:var(--ok); opacity:.13; }
.mini .grid { stroke:var(--line); stroke-width:1; }
.mini .axis { fill:var(--muted); font-size:12px; font-variant-numeric:tabular-nums; }
.mini .line { fill:none; stroke:var(--accent); stroke-width:2.5; stroke-linejoin:round; stroke-linecap:round;
              stroke-dasharray:1; stroke-dashoffset:0; animation:draw .9s ease-out; }
@keyframes draw { from { stroke-dashoffset:1; } to { stroke-dashoffset:0; } }
.mini .dot { fill:var(--accent); stroke:var(--bg); stroke-width:1.5; transition:r .15s ease; }
.mini .best { fill:var(--ok); stroke:var(--bg); stroke-width:2; transition:r .15s ease; }
.mini circle.on { r:7.5; }
.mini .guide { stroke:var(--muted); stroke-width:1; stroke-dasharray:3 3; }
.mini .jump { stroke:var(--muted); stroke-dasharray:4 4; }
.mini .jlab { fill:var(--muted); font-size:11px; }
.mini .tip { position:absolute; pointer-events:none; transform:translate(-50%, calc(-100% - 12px)); white-space:nowrap;
             background:var(--fg); color:var(--bg); font-size:12px; line-height:1.45; padding:6px 10px; border-radius:6px;
             box-shadow:0 4px 14px rgba(0,0,0,.18); z-index:2; }
.mini .tip b { font-size:13px; } .mini .tip small { opacity:.8; display:block; }
@media (prefers-reduced-motion: reduce) { .mini .line { animation:none; } .mini circle { transition:none; } }
"""

esc = html.escape


# ---------------------------------------------------------------- 후보 회로도 (2단계)
def draw_candidates(run_dir: Path, log=print) -> int:
    """candidates.json 의 후보마다 회로도 SVG 를 run_dir/candidates/cNN.svg 로. 그린 개수 (못 그리면 0)."""
    import make_schematic_svg as ms
    cands = json.loads((run_dir / "candidates.json").read_text(encoding="utf-8"))["candidates"]
    out_dir = run_dir / CANDIDATE_DIR
    out_dir.mkdir(exist_ok=True)
    ms.WORK_DIR.mkdir(exist_ok=True)
    skin = ms.make_skin()
    made = 0
    try:
        for i, cand in enumerate(cands, 1):
            out = out_dir / f"c{i:02d}.svg"
            try:
                ms.render(ms.parse_rows(cand["table"]), {}, out, skin, png=False)
                made += 1
            except Exception as error:          # 한 후보를 못 그려도 나머지는 그린다
                log(f"  후보 {i} 회로도 실패: {str(error)[:80]}")
    finally:
        skin.unlink(missing_ok=True)
    return made


def _selection(run_dir: Path) -> dict:
    path = run_dir / "selection.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def candidate_results(run_dir: Path) -> dict:
    """후보 번호 -> 3단계 결과 {"passed", "judged", "form"} (동작한 모양 중 가장 많이 통과) 또는 {"reason"}."""
    sel = _selection(run_dir)
    out = {}
    for e in sel.get("entries") or []:
        n = e.get("from")
        for v in e.get("variants") or []:
            if v.get("valid"):
                best = out.get(n)
                if not best or "passed" not in best or v.get("passed", 0) > best["passed"]:
                    out[n] = {"passed": v.get("passed"), "judged": v.get("judged"), "form": e.get("form")}
        if n not in out:
            steps = e.get("steps") or {}
            reason = None if (steps.get("rules") or {}).get("ok", True) else "규칙 검사 탈락"
            forms = steps.get("forms") or []
            reason = reason or (forms[0].split(":", 1)[-1].strip() if forms else None) or \
                ((steps.get("sizing") or {}).get("reasons") or ["동작 안 함"])[0]
            out[n] = {"reason": reason}
    return out


def gallery_html(run_dir: Path) -> str:
    cands_file = run_dir / "candidates.json"
    if not cands_file.exists():
        return ""
    cands = json.loads(cands_file.read_text(encoding="utf-8"))["candidates"]
    results = candidate_results(run_dir)
    sel = _selection(run_dir)
    picked_entry = (sel.get("entries") or [None] * 10000)[sel.get("summary", {}).get("selected")] \
        if sel.get("summary", {}).get("selected") is not None and sel.get("entries") else None
    picked = (picked_entry or {}).get("from")
    order = sorted(range(1, len(cands) + 1),
                   key=lambda n: (n != picked, "passed" not in results.get(n, {}), -(results.get(n, {}).get("passed") or 0), n))

    def card(n):
        cand = cands[n - 1]
        svg = run_dir / CANDIDATE_DIR / f"c{n:02d}.svg"
        pic = (f"<a class='pic' href='{CANDIDATE_DIR}/c{n:02d}.svg' target='_blank' title='크게 보기'>"
               f"<img src='{CANDIDATE_DIR}/c{n:02d}.svg' alt='후보 {n} 회로도' loading='lazy'></a>"
               if svg.exists() else "<div class='pic none'>회로도 없음</div>")
        how = "빔 탐색" if cand.get("how") == "beam" else "무작위"
        tags = ["<span class='tag new'>새 구조</span>" if not cand.get("in_train") else "<span class='tag'>기존 구조</span>",
                f"<span class='tag'>{how}</span>"]          # 새 구조인지가 먼저, 한 줄에 왼쪽부터
        r = results.get(n, {})
        if "passed" in r:
            res = f"<div class='res ok'>✓ 동작 · {r['passed']}/{r['judged']} 통과</div>"
        elif cand.get("problems"):
            res = f"<div class='res no'>✕ 규칙 검사 탈락</div>"
        else:
            res = f"<div class='res no'>✕ {esc((r.get('reason') or '동작 안 함')[:28])}</div>"
        mark = "<span class='tag new'>채택</span>" if n == picked else ""
        return (f"<div class='cand{' picked' if n == picked else ''}'>{pic}"
                f"<div class='name'><span>후보 {n}</span>{mark}</div><div class='tags'>{''.join(tags)}</div>{res}</div>")

    first, rest = order[:GALLERY_FIRST], order[GALLERY_FIRST:]
    out = [f"<div class='gallery'>{''.join(card(n) for n in first)}</div>"]
    if rest:
        out.append(f"<details class='more'><summary>더보기 ({len(rest)}개)</summary>"
                   f"<div class='gallery'>{''.join(card(n) for n in rest)}</div></details>")
    out.append("<div class='fig-note'>동작한 후보가 먼저, 많이 통과한 순서. 회로도를 누르면 크게 볼 수 있어요.</div>")
    return "".join(out)


# ---------------------------------------------------------------- 깔때기 (2~5단계)
def funnel_html(run_dir: Path, status_steps: dict) -> str:
    sel = _selection(run_dir)
    cand_sum = status_steps.get("candidates") or {}
    if not sel or not cand_sum:
        return ""
    results = candidate_results(run_dir)
    working = [r for r in results.values() if "passed" in r]
    judged = max((r["judged"] for r in working), default=0)
    top = max((r["passed"] for r in working), default=0)
    stages = [("모델이 낸 서로 다른 후보", "2단계", cand_sum.get("total") or len(results)),
              ("규칙 검사 통과", "2단계", cand_sum.get("rule_ok")),
              ("크기 정하기 뒤 동작", "3단계", len(working)),
              (f"스펙 {judged}개 중 절반 이상 통과", "3단계", sum(r["passed"] * 2 >= judged for r in working)),
              (f"가장 많이 통과 ({top}/{judged})", "5단계", sum(r["passed"] == top for r in working))]
    stages = [s for s in stages if s[2] is not None]
    full = max(s[2] for s in stages) or 1
    rows, prev = [], None
    for k, (label, step, n) in enumerate(stages):
        share = f"<small>{100 * n / prev:.0f}%</small>" if prev else ""
        shade = 100 - k * 14                         # 단계마다 조금씩 옅게 (같은 색 한 가지)
        rows.append(f"<div class='lab'>{esc(label)}<small>{step}</small></div>"
                    f"<div class='track'><div class='bar' style='width:{max(1, 100 * n / full):.1f}%;"
                    f"background:color-mix(in srgb, var(--accent) {shade}%, var(--card))'></div>"
                    f"<span class='n'>{n}{share}</span></div>")
        prev = n or None
    return f"<div class='funnel'>{''.join(rows)}</div>"


# ---------------------------------------------------------------- 후보 x 스펙 표 (3~5단계)
def spec_grid_html(run_dir: Path) -> str:
    sel = _selection(run_dir)
    if not sel:
        return ""
    picked_index = sel.get("summary", {}).get("selected")
    best = {}
    for i, e in enumerate(sel.get("entries") or []):
        for v in e.get("variants") or []:
            if v.get("valid") and (i not in best or v.get("passed", 0) > best[i]["v"].get("passed", 0)):
                best[i] = {"e": e, "v": v}
    if not best:
        return ""
    columns = [(r["measure"], r.get("label") or r["measure"], r.get("unit") or "", r.get("target") or "")
               for r in next(iter(best.values()))["v"]["spec"]]
    groups = []                                      # 바이어스 정리 뒤 같은 회로가 된 후보는 한 줄로
    for i, b in sorted(best.items(), key=lambda kv: (-(kv[1]["v"].get("passed") or 0), kv[1]["e"].get("from") or 0)):
        rows = {r["measure"]: r for r in b["v"]["spec"]}
        sig = (b["e"].get("form"), tuple(round(rows[m]["value"], 3) if rows.get(m, {}).get("value") is not None else None
                                         for m, *_ in columns))
        same = next((g for g in groups if g["sig"] == sig), None)
        if same:
            same["from"].append(b["e"].get("from")); same["index"].append(i)
        else:
            groups.append({"sig": sig, "from": [b["e"].get("from")], "index": [i], "rows": rows, "v": b["v"], "e": b["e"]})
    counts = {m: sum(1 for g in groups if g["rows"].get(m, {}).get("status") == "PASS") for m, *_ in columns}
    head = "".join(f"<th>{esc(label)}<small>{esc(target)}</small></th>" for _, label, _, target in columns)
    count_row = "".join(f"<td class='v'>{counts[m]}/{len(groups)}</td>" for m, *_ in columns)
    body = []
    for g in groups:
        names = sorted(set(g["from"]))
        who = f"후보 {names[0]}" if len(names) == 1 else \
            f"후보 {', '.join(map(str, names[:3]))}{' …' if len(names) > 3 else ''} <small>{len(names)}개가 같은 회로</small>"
        if len(names) == 1:
            who += f"<small>{esc(g['e'].get('form') or '')} · 출력단 x{g['v'].get('output_scale', 0):g}</small>"
        cells = []
        for m, label, unit, _ in columns:
            r = g["rows"].get(m) or {}
            ok = r.get("status") == "PASS"
            val = r.get("value")
            txt = "—" if val is None else (f"{val:.0f}" if abs(val) >= 100 else f"{val:.3g}")
            cells.append(f"<td class='v {'ok' if ok else 'no'}' title='{esc(label)} {txt} {esc(unit)}'>"
                         f"<span class='mk' aria-hidden='true'>{'✓' if ok else '✕'}</span>{txt}</td>")
        picked = " class='picked'" if picked_index in g["index"] else ""
        body.append(f"<tr{picked}><th class='row'>{who}</th>{''.join(cells)}"
                    f"<td class='v'><b>{g['v'].get('passed')}/{g['v'].get('judged')}</b></td></tr>")
    first, rest = body[:GRID_FIRST], body[GRID_FIRST:]
    more = ""
    if rest:                                         # 10가지가 넘으면 나머지는 '더보기' 로 펼친다
        more = (f"<tbody class='grid-more' hidden>{''.join(rest)}</tbody>"
                f"<tbody><tr><td colspan='{len(columns) + 2}'><button type='button' class='more-btn' "
                f"onclick=\"const b=this.closest('table').querySelector('.grid-more');b.hidden=!b.hidden;"
                f"this.textContent=b.hidden?'더보기 ({len(rest)}가지)':'접기'\">더보기 ({len(rest)}가지)</button></td></tr></tbody>")
    return (f"<div class='gridwrap'><table class='spec-grid'><thead><tr><th>동작한 회로 {len(groups)}가지</th>{head}"
            f"<th>통과</th></tr></thead><tbody><tr class='count'><td>통과한 회로 수</td>{count_row}<td></td></tr>"
            f"{''.join(first)}</tbody>{more}</table></div>"
            "<div class='fig-note'>파란 테두리 줄이 채택된 후보예요 (5단계). 열마다 통과한 회로 수를 보면 다 같이 막힌 항목이 보여요.</div>")


# ---------------------------------------------------------------- 튜닝 그래프 (7단계)
def _bounds(target: str):
    """'≥ 83.52 dB', '≤ 250 µA' -> (하한, 상한)."""
    lo = re.search(r"≥\s*([-\d.]+)", target or "")
    hi = re.search(r"≤\s*([-\d.]+)", target or "")
    return (float(lo.group(1)) if lo else None, float(hi.group(1)) if hi else None)


def _nice_ticks(lo: float, hi: float, count: int = 3) -> list:
    """lo ~ hi 를 덮는 보기 좋은 눈금 (1, 2, 5 x 10^n 간격)."""
    import math
    span = (hi - lo) or abs(hi) or 1.0
    raw = span / count
    mag = 10 ** math.floor(math.log10(raw))
    step = next(m * mag for m in (1, 2, 5, 10) if m * mag >= raw)
    first = math.floor(lo / step) * step
    ticks = [first]
    while ticks[-1] < hi - 1e-9:
        ticks.append(ticks[-1] + step)
    return ticks


def _mini(title: str, unit: str, ys: list, band, best_k: int, jump_k, fmt, integer: bool = False,
          notes: list = None) -> str:
    """작은 선 그래프 하나. notes: 시도마다 말풍선에 붙일 글 (전류·배율·보상). 커서를 대면 SCRIPT 가 말풍선을 띄운다."""
    w, h, l, r, t, b = 420, 210, 46, 12, 14, 28
    pts = [(k, y) for k, y in enumerate(ys, 1) if y is not None]
    if not pts:
        return ""
    vals = [y for _, y in pts] + [v for v in band if v is not None]
    lo, hi = min(vals), max(vals)
    if min(y for _, y in pts) >= 0:
        lo = min(lo, 0) if integer else max(0.0, lo - (hi - lo) * 0.1)   # 음수가 될 수 없는 값은 0 아래로 안 내림
    ticks = _nice_ticks(lo, hi)
    lo, hi = ticks[0], ticks[-1]
    X = lambda k: l + (w - l - r) * (k - 1) / max(1, len(ys) - 1)
    Y = lambda y: t + (h - t - b) * (1 - (y - lo) / ((hi - lo) or 1))
    b_lo, b_hi = band

    def verdict(y):
        if b_lo is None and b_hi is None:
            return ""
        ok = (b_lo is None or y >= b_lo) and (b_hi is None or y <= b_hi)
        return " · 통과" if ok else " · 실패"

    data = [{"x": round(X(k), 1), "y": round(Y(y), 1), "k": k,
             "v": f"{fmt(y)} {unit}{verdict(y)}", "n": (notes or [""] * len(ys))[k - 1]} for k, y in pts]
    out = [f"<div class='mini'><h4>{esc(title)} <small>{esc(unit)}</small></h4>"
           f"<svg viewBox='0 0 {w} {h}' role='img' aria-label='{esc(title)}' "
           f"data-pts='{esc(json.dumps(data, ensure_ascii=False))}'>"]
    if b_lo is not None or b_hi is not None:      # 통과 구간을 옅게 칠한다
        top_y = Y(min(hi, b_hi)) if b_hi is not None else t
        bot_y = Y(max(lo, b_lo)) if b_lo is not None else h - b
        out.append(f"<rect class='band' x='{l}' y='{top_y:.1f}' width='{w - l - r}' height='{max(0, bot_y - top_y):.1f}'/>")
    for gy in ticks:
        out.append(f"<line class='grid' x1='{l}' x2='{w - r}' y1='{Y(gy):.1f}' y2='{Y(gy):.1f}'/>"
                   f"<text class='axis' x='{l - 6}' y='{Y(gy) + 4:.1f}' text-anchor='end'>{fmt(gy)}</text>")
    for k in sorted({1, len(ys), (len(ys) + 1) // 2}):
        out.append(f"<text class='axis' x='{X(k):.1f}' y='{h - 8}' text-anchor='middle'>{k}</text>")
    if jump_k:
        out.append(f"<line class='jump' x1='{X(jump_k):.1f}' x2='{X(jump_k):.1f}' y1='{t}' y2='{h - b}'/>"
                   f"<text class='jlab' x='{X(jump_k) + 4:.1f}' y='{t + 12}'>전류 건너뜀</text>")
    out.append(f"<line class='guide' x1='0' x2='0' y1='{t}' y2='{h - b}' visibility='hidden'/>")
    line_pts = " ".join(f"{X(k):.1f},{Y(y):.1f}" for k, y in pts)
    out.append(f"<polyline class='line' pathLength='1' points='{line_pts}'/>")
    for k, y in pts:
        cls = "best" if k == best_k else "dot"
        out.append(f"<circle class='{cls}' data-k='{k}' cx='{X(k):.1f}' cy='{Y(y):.1f}' r='{6 if k == best_k else 3.5}'/>")
    out.append("</svg><div class='tip' role='tooltip' hidden></div></div>")
    return "".join(out)


def tune_html(tune: dict) -> str:
    trials = tune.get("trials") or []
    if len(trials) < 2:
        return ""
    best = tune.get("best") or {}
    best_k = next((k for k, tr in enumerate(trials, 1) if tr["unit_current_ua"] == best.get("unit_current_ua")
                   and tr["scale"] == best.get("scale") and tr["cap_pf"] == best.get("cap_pf")), None)
    jump = tune.get("jump_ua")
    jump_k = next((k for k, tr in enumerate(trials, 1) if k > 1 and jump is not None
                   and abs(tr["unit_current_ua"] - jump) < 1e-9), None)
    spec = {r["measure"]: r for r in (tune.get("start") or {}).get("spec") or []}
    first_failed = trials[0].get("failed") or []
    shown = (first_failed + [m for m in ("idd", "pm", "avd", "ugbw") if m not in first_failed])[:3]
    notes = [f"전류 {tr['unit_current_ua']:.3g} µA · 출력단 x{tr['scale']:g} · 보상 {tr['cap_pf']:g} pF"
             + (" · 채택" if k == best_k else "") for k, tr in enumerate(trials, 1)]
    charts = [_mini("통과한 스펙 개수", f"{trials[0].get('judged')}개 중",
                    [tr.get("passed") if tr.get("valid") else None for tr in trials], (None, None), best_k, jump_k,
                    lambda v: f"{v:.0f}", integer=True, notes=notes)]
    for m in shown:
        row = spec.get(m) or {}
        ys = [(tr.get("values") or {}).get(m) for tr in trials]
        if all(y is None for y in ys):
            continue
        charts.append(_mini(row.get("label") or m, row.get("unit") or "", ys, _bounds(row.get("target")), best_k, jump_k,
                            lambda v: f"{v:.0f}" if abs(v) >= 10 else f"{v:.2g}", notes=notes))
    return (f"<div class='multiples'>{''.join(charts)}</div>"
            "<div class='fig-note'>가로축은 시도 순서, 초록 구간이 통과 범위, 큰 초록 점이 채택된 조합이에요. "
            "그래프에 커서를 대면 그 시도의 값과 조합이 나와요.</div>")


# 튜닝 그래프 말풍선: 커서와 가장 가까운 시도의 점을 키우고 안내선·값을 보여 준다 (결과 화면 끝에 한 번 넣음)
SCRIPT = """<script>
document.querySelectorAll('.mini svg[data-pts]').forEach(svg => {
  const pts = JSON.parse(svg.dataset.pts), box = svg.parentElement, tip = box.querySelector('.tip');
  const guide = svg.querySelector('.guide'), dots = svg.querySelectorAll('circle');
  function show(ev) {
    const m = svg.getScreenCTM(); if (!m) return;
    const x = (ev.clientX - m.e) / m.a;
    let p = pts[0];
    for (const q of pts) if (Math.abs(q.x - x) < Math.abs(p.x - x)) p = q;
    guide.setAttribute('x1', p.x); guide.setAttribute('x2', p.x); guide.setAttribute('visibility', 'visible');
    dots.forEach(d => d.classList.toggle('on', +d.dataset.k === p.k));
    tip.innerHTML = '<b>' + p.v + '</b><small>시도 ' + p.k + (p.n ? ' · ' + p.n : '') + '</small>';
    tip.hidden = false;
    const sx = svg.getBoundingClientRect(), bx = box.getBoundingClientRect();
    const left = sx.left - bx.left + p.x * m.a, top = sx.top - bx.top + p.y * m.d;
    const half = tip.offsetWidth / 2;
    tip.style.left = Math.min(Math.max(left, half + 4), bx.width - half - 4) + 'px';
    tip.style.top = top + 'px';
  }
  svg.addEventListener('pointermove', show);
  svg.addEventListener('pointerdown', show);
  svg.addEventListener('pointerleave', () => { tip.hidden = true; guide.setAttribute('visibility', 'hidden');
    dots.forEach(d => d.classList.remove('on')); });
});
</script>"""
