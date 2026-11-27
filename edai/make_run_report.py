"""
실행 폴더(runs/<...>/) -> report.html (결과 화면 한 장, 그림까지 파일 안에 넣음).
폴더만 받으면 더블클릭으로 열리고, 브라우저 인쇄로 PDF 저장도 된다. pipeline.py 가 단계마다 다시 쓴다.

사용법: python make_run_report.py runs/<실행 폴더>
"""

import base64
import html
import json
import re
import sys
from pathlib import Path

STATE_TEXT = {"wait": "대기", "run": "진행 중", "done": "완료", "fail": "실패"}
REFRESH_SECONDS = 15        # 진행 중일 때 화면을 다시 읽는 간격

CSS = """
:root { --bg:#fff; --fg:#1d2330; --muted:#6b7280; --line:#e3e6ec; --card:#f7f8fa; --ok:#1a7f37; --bad:#c62828;
        --run:#b26a00; --accent:#2856c7; }
@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) { --bg:#15181e; --fg:#e7e9ee; --muted:#9aa3b2;
        --line:#2c313b; --card:#1d2129; --ok:#4cc26b; --bad:#ef6b6b; --run:#e0a13c; --accent:#7aa2ff; } }
:root[data-theme="dark"] { --bg:#15181e; --fg:#e7e9ee; --muted:#9aa3b2;
        --line:#2c313b; --card:#1d2129; --ok:#4cc26b; --bad:#ef6b6b; --run:#e0a13c; --accent:#7aa2ff; }
* { box-sizing:border-box; }
body { margin:0; background:var(--bg); color:var(--fg); font:15px/1.6 "Malgun Gothic","Apple SD Gothic Neo",sans-serif; }
main { max-width:1040px; margin:0 auto; padding:24px 16px 64px; }
h1 { font-size:24px; margin:0 0 4px; } h2 { font-size:18px; margin:0; }
.sub { color:var(--muted); font-size:13px; }
.steps { display:flex; flex-wrap:wrap; gap:6px; margin:16px 0 24px; }
.chip { border:1px solid var(--line); border-radius:999px; padding:2px 10px; font-size:12px; }
.chip.done { color:var(--ok); border-color:var(--ok); } .chip.fail { color:var(--bad); border-color:var(--bad); }
.chip.run { color:var(--run); border-color:var(--run); }
section { border:1px solid var(--line); border-radius:10px; padding:16px; margin-bottom:16px; background:var(--card);
          break-inside:avoid; }
.head { display:flex; justify-content:space-between; align-items:baseline; gap:8px; margin-bottom:10px; }
.state { font-size:12px; } .state.done { color:var(--ok); } .state.fail { color:var(--bad); } .state.run { color:var(--run); }
table { border-collapse:collapse; width:100%; font-size:13px; margin:8px 0; }
th, td { border-bottom:1px solid var(--line); padding:5px 6px; text-align:left; vertical-align:top; }
th { color:var(--muted); font-weight:600; }
.pass { color:var(--ok); font-weight:600; } .failc { color:var(--bad); font-weight:600; }
.mono { font-family:Consolas,"D2Coding",monospace; font-size:12px; word-break:break-all; }
.err { color:var(--bad); white-space:pre-wrap; }
h3 { font-size:15px; margin:18px 0 6px; }
.warn { border:1px solid var(--bad); color:var(--bad); border-radius:6px; padding:8px 10px; margin-bottom:10px; font-size:13px; }
.pdg svg { width:100%; height:auto; background:#fff; border:1px solid var(--line); border-radius:6px; }
.chart { width:100%; height:auto; }
figure { margin:12px 0; } figure img { width:100%; height:auto; background:#fff; border:1px solid var(--line); border-radius:6px; }
figcaption { color:var(--muted); font-size:13px; margin-top:4px; }
details summary { cursor:pointer; color:var(--accent); }
pre { white-space:pre-wrap; font-size:12px; max-height:420px; overflow:auto; background:var(--bg); padding:8px;
      border:1px solid var(--line); border-radius:6px; }
@media print { section { background:none; } .noprint { display:none; } }
"""


def esc(x) -> str:
    return html.escape("" if x is None else str(x))


def num(x, digits=1) -> str:
    if x is None:
        return "—"
    if isinstance(x, (int, float)):
        return f"{x:.{digits}f}" if isinstance(x, float) else str(x)
    return esc(x)


def read(run_dir: Path, name: str):
    path = run_dir / name
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def run_info(run_dir: Path) -> dict:
    """모든 실행에 같은 형식: 제목 = 칩 이름, 언제 = 월/일 시:분, 메모 (input.json 에만 저장, UI 에서 고침)."""
    inp = read(run_dir, "input.json") or {}
    status = read(run_dir, "status.json") or {}
    m = re.match(r"\d{4}-(\d\d)-(\d\d) (\d\d):(\d\d)", status.get("started") or "")         or re.match(r"\d{4}(\d\d)(\d\d)_(\d\d)(\d\d)", run_dir.name)
    title = inp.get("title") or run_dir.name
    number = chip_number(run_dir, title)          # 같은 칩의 첫 실행은 번호 없이, 두 번째부터 (2) (3) …
    return {"title": title if number == 1 else f"{title} ({number})", "chip": title, "memo": inp.get("memo") or "",
            "when": f"{m.group(1)}/{m.group(2)} {m.group(3)}:{m.group(4)}" if m else ""}


def chip_number(run_dir: Path, title: str) -> int:
    """같은 칩 이름의 실행 중 몇 번째로 시작했나 (1부터). 옆 실행 폴더들(runs/)의 시작 시각 순서.
    새 실행은 항상 뒤 번호를 받으므로 이미 붙은 번호는 바뀌지 않는다."""
    same = []
    for d in Path(run_dir).resolve().parent.iterdir():
        inp, status = read(d, "input.json"), read(d, "status.json")
        if inp is not None and (inp.get("title") or d.name) == title:
            same.append(((status or {}).get("started") or "9999", d.name))
    order = sorted(same)
    return 1 + next((i for i, (_, name) in enumerate(order) if name == Path(run_dir).resolve().name), len(order))


def spec_table(rows: list) -> str:
    """판정 행 (measure, label, unit, value, target, status)."""
    out = ["<table><tr><th>항목</th><th>측정</th><th>목표</th><th>판정</th></tr>"]
    for r in rows or []:
        ok = r.get("status") == "PASS"
        out.append(f"<tr><td>{esc(r.get('label') or r.get('measure'))}</td><td>{num(r.get('value'))} {esc(r.get('unit'))}</td>"
                   f"<td>{esc(r.get('target'))}</td><td class='{'pass' if ok else 'failc'}'>{'통과' if ok else '실패'}</td></tr>")
    return "".join(out) + "</table>"


def evidence_cell(e: dict) -> str:
    """판정 항목이 나온 데이터시트 줄: 쪽(누르면 PDF 그 쪽이 열림), 원문 값(최소/보통/최대 단위), 근거 글."""
    if not e:
        return ""
    page = e.get("page")
    link = f"<a href='datasheet.pdf#page={esc(page)}' target='_blank'>{esc(page)}쪽</a>" if page else ""
    values = " / ".join("-" if e.get(k) is None else esc(e.get(k)) for k in ("min", "typ", "max"))
    quote = esc(str(e.get("evidence") or "")[:160])
    return f"{link} · 원문 {values} {esc(e.get('unit'))}<br><span class='sub'>{quote}</span>"


def body_extract(run_dir: Path, s: dict) -> str:
    spec = read(run_dir, "spec.json")
    out = [f"<p>부품 <b>{esc(s.get('part'))}</b> · 추출한 사양 {s.get('rows')}줄 · 핀 {s.get('pins')}개 · 판정 항목 {s.get('judged')}개</p>"]
    if spec:
        out.append("<table><tr><th>판정 항목</th><th>최소</th><th>보통</th><th>최대</th><th>단위</th><th>조건</th>"
                   "<th>데이터시트 근거</th></tr>")
        for it in spec["specs"]:
            out.append(f"<tr><td>{esc(it.get('label') or it['measure'])}</td><td>{num(it.get('min'))}</td><td>{num(it.get('typ'))}</td>"
                       f"<td>{num(it.get('max'))}</td><td>{esc(it.get('unit'))}</td><td>{esc(it.get('condition'))}</td>"
                       f"<td>{evidence_cell(it.get('extracted') or {})}</td></tr>")
        out.append("</table>")
    out.append(f"<p class='sub'>모델 입력 문장</p><p class='mono'>{esc(s.get('model_input'))}</p>")
    out.append(hkg_details(run_dir) + pdg_details(run_dir))
    return "".join(out)


def hkg_details(run_dir: Path) -> str:
    """HKG (데이터시트에서 뽑은 지식 그래프) 전체: 부품 정보, 핀, 전기적 사양, 기능 블록."""
    hkg = read(run_dir, "hkg.json")
    if not hkg:
        return ""
    ic = hkg.get("ic_device") or {}
    out = ["<h3>HKG (데이터시트 분석 전체)</h3>",
           f"<p>{esc(ic.get('name'))} · {esc(ic.get('category'))} · {esc(ic.get('package'))}<br>"
           f"<span class='sub'>{esc(ic.get('description'))}</span></p>"]
    pins = hkg.get("pins") or []
    out.append(f"<details open><summary>핀 {len(pins)}개</summary><table><tr><th>이름</th><th>번호</th><th>역할</th>"
               "<th>방향</th><th>설명</th><th>쪽</th></tr>" + "".join(
                   f"<tr><td>{esc(p.get('name'))}</td><td>{esc(', '.join(map(str, p.get('pin_numbers') or [p.get('pin_number') or ''])))}</td>"
                   f"<td>{esc(p.get('role'))}</td><td>{esc(p.get('direction'))}</td><td>{esc(p.get('description'))}</td>"
                   f"<td>{esc(p.get('page'))}</td></tr>" for p in pins) + "</table></details>")
    rows = hkg.get("electrical_parameters") or []
    out.append(f"<details><summary>전기적 사양 {len(rows)}줄 (표에서 뽑은 그대로)</summary><table><tr><th>기호</th><th>이름</th>"
               "<th>최소</th><th>보통</th><th>최대</th><th>단위</th><th>조건</th><th>쪽</th></tr>" + "".join(
                   f"<tr><td>{esc(r.get('symbol'))}</td><td>{esc(r.get('name'))}</td><td>{num(r.get('min'), 3)}</td>"
                   f"<td>{num(r.get('typ'), 3)}</td><td>{num(r.get('max'), 3)}</td><td>{esc(r.get('unit'))}</td>"
                   f"<td>{esc(r.get('test_conditions'))}</td><td>{esc(r.get('page'))}</td></tr>" for r in rows) + "</table></details>")
    blocks = hkg.get("functional_blocks") or []
    if blocks:
        out.append(f"<details><summary>기능 블록 {len(blocks)}개</summary><table><tr><th>이름</th><th>종류</th><th>설명</th>"
                   "<th>입력</th><th>출력</th></tr>" + "".join(
                       f"<tr><td>{esc(b.get('name'))}</td><td>{esc(b.get('type'))}</td><td>{esc(b.get('description'))}</td>"
                       f"<td>{esc(', '.join(map(str, b.get('input_ports') or [])))}</td>"
                       f"<td>{esc(', '.join(map(str, b.get('output_ports') or [])))}</td></tr>" for b in blocks) + "</table></details>")
    return "".join(out)


def pdg_details(run_dir: Path) -> str:
    """PDG (핀 사이 의존 관계와 전원 켜는 순서): 그림, 감사 점수, 순서, 연결."""
    pdg = read(run_dir, "pdg.json")
    if not pdg:
        return ""
    audit = pdg.get("audit") or {}
    score = audit.get("fidelity_score_pct")
    out = ["<h3>PDG (핀 의존 관계와 전원 순서)</h3>",
           f"<p>핀 {len(pdg['nodes'])}개 · 의존 관계 {len(pdg['edges'])}개 · 순서 단계 {len(pdg.get('levels') or [])}"
           + (f" · 추출 신뢰도 감사 <b>{num(score)}%</b> ({esc(audit.get('status'))})" if score is not None else "")
           + "</p>"]
    svg = run_dir / "pdg.svg"
    if svg.exists():
        out.append(f"<div class='pdg'>{svg.read_text(encoding='utf-8')}</div>")
    sched = pdg.get("schedule_us") or {}
    out.append("<details><summary>전원 켜는 순서와 의존 관계</summary><table><tr><th>핀</th><th>켜지는 시각 (µs)</th></tr>"
               + "".join(f"<tr><td>{esc(k)}</td><td>{num(v, 3)}</td></tr>" for k, v in sorted(sched.items(), key=lambda x: x[1]))
               + "</table><table><tr><th>앞</th><th>뒤</th><th>종류</th><th>지연 (µs)</th><th>조건</th></tr>" + "".join(
                   f"<tr><td>{esc(e.get('from'))}</td><td>{esc(e.get('to'))}</td><td>{esc(e.get('dependency_type'))}</td>"
                   f"<td>{num(e.get('delay_us'), 3)}</td><td>{esc(e.get('condition'))}</td></tr>" for e in pdg["edges"])
               + "</table></details>")
    return "".join(out)


def body_candidates(run_dir: Path, s: dict) -> str:
    return (f"<p>모델(FLAN-T5)이 만든 서로 다른 후보 <b>{s.get('total')}</b>개 → 규칙 검사 통과 <b>{s.get('rule_ok')}</b>개 "
            f"(그중 학습 데이터에 없던 구조 {s.get('new')}개)</p>")


def body_select(run_dir: Path, s: dict) -> str:
    out = (f"<p>후보 {s.get('evaluated')}개마다 바이어스를 실제 소자로 채우고 크기를 정해 측정 → 동작한 후보 <b>{s.get('working')}</b>개, "
           f"가장 많이 통과한 것 {esc(s.get('best_passed'))}</p>")
    if s.get("forms") is not None:              # 고쳐 보기 (--repair)
        forms = s.get("forms_working") or {}
        out += ("<p class='sub'>후보마다 모델 구조 그대로 말고도 정해진 변환을 한 모양을 같이 쟀어요: 자체 바이어스 회로를 검증된 "
                "바이어스로 바꾼 것(바이어스 정리), 입력쌍이 공통모드 범위를 못 덮으면 상보 뒤집기, 그래도 안 되면 쌓인 구조 규칙. "
                "동작한 모양: " + (", ".join(f"{esc(k)} {v}개" for k, v in forms.items()) or "없음") + "</p>")
    return out


def body_rank(run_dir: Path, s: dict) -> str:
    out = ["<p>순위 규칙 v4: 입력쌍이 공통모드 범위를 덮는 구조 → (목표 AVD 가 높으면) 이득 노드 2개 이상 → 통과 수 → 모자란 정도</p>",
           "<table><tr><th>순위</th><th>후보</th><th>통과</th><th>출력단 배율</th><th>이득 노드</th><th>입력쌍</th><th>AVD</th></tr>"]
    for i, r in enumerate(s.get("top") or [], 1):
        fixed_mark = " (LLM 이 고친 회로)" if r.get("how") == "llm_fix" else ""
        out.append(f"<tr><td>{i}</td><td>{r['index'] + 1}{fixed_mark}</td><td>{r['passed']}/{r['judged']}</td><td>x{num(r['scale'], 0)}</td>"
                   f"<td>{r['gain_nodes']}</td><td>{'맞음' if r['input_ok'] else '범위 못 덮음'}</td><td>{num(r['avd'])}</td></tr>")
    return "".join(out) + "</table>"


def body_rules(run_dir: Path, s: dict) -> str:
    final = read(run_dir, "final_rules.json") or read(run_dir, "final.json")   # 7단계가 final.json 을 바꾸므로 그 전 것
    if not final:
        return ""
    out = ["<table><tr><th>해 본 회로</th><th>출력단 배율</th><th>결과</th></tr>"]
    for t in final["tried"]:
        res = f"{t['passed']}/{t['judged']}" if t["valid"] else f"<span class='failc'>실패</span> {esc((t.get('reason') or '')[:60])}"
        mark = " ← 고름" if t["label"] == final["label"] and t["scale"] == final["output_scale"] else ""
        out.append(f"<tr><td>{esc(t['label'])}</td><td>x{num(t['scale'], 0)}</td><td>{res}<b>{mark}</b></td></tr>")
    out.append("</table><p class='sub'>고른 회로의 판정</p>" + spec_table(final["spec"]))
    return "".join(out)


def body_tune(run_dir: Path, s: dict) -> str:
    tune = read(run_dir, "tune.json")
    if not tune:
        return ""
    best = tune["best"]
    out = [f"<p>구조는 그대로 두고 전류원 전류, 출력단 배율, 보상 커패시터(출력 트랜지스터 게이트 "
           f"{esc(', '.join(tune.get('miller_nodes') or []) or '없음')} ↔ OUT)를 바꿔 가며 {len(tune['trials'])}번 쟀어요 "
           f"({esc(tune['stopped'])}, {tune['seconds']} s).</p>"]
    if tune.get("jump_ua") is not None:
        out.append(f"<p class='sub'>공급 전류가 목표를 넘어, 전류원 전류를 목표에 맞을 값({tune['jump_ua']:.3g} µA)으로 "
                   "건너뛴 점에서도 한 번 더 찾았어요.</p>")
    loads = tune.get("measure_loads") or {}
    if loads:
        out.append(f"<p class='sub'>측정 부하 (데이터시트 조건): 이득 RL {esc(loads.get('avd_rl'))}, "
                   f"대역폭·위상 여유 RL {esc(loads.get('ac_rl'))} · CL {esc(loads.get('ac_cl'))}</p>")
    if tune["improved"]:
        out.append(f"<p>통과 {tune['start']['passed']}/{tune['start']['judged']} → <b>{best['passed']}/{best['judged']}</b>: "
                   f"전류 {best['unit_current_ua']:.3g} µA, 출력단 x{num(best['scale'], 0)}, 보상 {num(best['cap_pf'], 1)} pF. "
                   "이 회로를 하네스로 넘겼어요.</p>")
    else:
        out.append("<p>더 나아진 조합이 없어 6단계 회로를 그대로 하네스로 넘겼어요.</p>")
    out.append("<table><tr><th>전류 (µA)</th><th>출력단 배율</th><th>보상 (pF)</th><th>결과</th><th>못 맞춘 항목</th><th>걸린 시간 (s)</th></tr>")
    for t in tune["trials"]:
        res = f"{t['passed']}/{t['judged']}" if t["valid"] else f"<span class='failc'>실패</span> {esc((t.get('reason') or '')[:60])}"
        out.append(f"<tr><td>{t['unit_current_ua']:.3g}</td><td>x{num(t['scale'], 0)}</td><td>{num(t['cap_pf'], 1)}</td>"
                   f"<td>{res}</td><td>{esc(', '.join(t.get('failed') or []))}</td><td>{num(t['seconds'], 0)}</td></tr>")
    out.append("</table>")
    if tune["improved"]:
        out.append("<p class='sub'>하네스로 넘긴 회로의 판정</p>" + spec_table(best["spec"]))
    return "".join(out)


# 하네스 채점 묶음 (run_harness.spec_counts) -> 결과 화면에 쓰는 설명. 이 줄들은 통과율 계산에서 빠진다
EXCLUDED_GROUPS = [
    ("not_testable", "시뮬레이션으로 확인할 수 없는 줄 (열 저항·ESD·절대 최대·권장 조건 등)"),
    ("supply", "전원 조건이 설계 전원(5 V, 4.5~5.5 V)과 다른 줄 (예: 2.7 V 표, ±15 V 표)"),
    ("no_method", "측정 방법이 없는 줄 (왜곡·잡음·임피던스 등)"),
    ("no_limit", "숫자 기준이 없는 줄"),
    ("sim_error", "시뮬레이션이 멈춰 못 잰 줄"),
]
JUDGED = ("PASS", "PASS_TYP", "FAIL", "FAIL_TYP")
STATUS_WORD = {"PASS": "통과", "PASS_TYP": "통과 (보통값 기준)", "FAIL": "실패", "FAIL_TYP": "실패 (보통값 기준)"}


def harness_counts(run_dir: Path) -> dict:
    """하네스 채점 개수. result.json 에 없으면(2026-11-27 전 실행) 채점 파일에서 센다."""
    result = read(run_dir, "harness/result.json") or {}
    if result.get("counts"):
        return result["counts"]
    if not (run_dir / "harness").is_dir():
        return {}
    from file_find import find_files
    from run_harness import spec_counts
    counts = spec_counts(run_dir / "harness")
    files = find_files(run_dir / "harness", "*_SPEC_EVALUATION.json")
    if counts and files:            # 통과·실패는 그때 하네스가 센 값 그대로 (그때는 다른 칩 줄·측정값 없는 왜곡 줄도 셈)
        summary = json.loads(files[0].read_text(encoding="utf-8"))
        counts.update(passed=summary.get("passed_specs", counts["passed"]), failed=summary.get("failed_specs", counts["failed"]),
                      old=True)
        counts["judged"] = counts["passed"] + counts["failed"]
    return counts


def harness_line(run_dir: Path) -> str:
    """실행 목록 한 줄에 붙는 하네스 결과 (예: '하네스 에이전트 22/30 통과 (73.3%)'). 결과가 없으면 빈 글."""
    c = harness_counts(run_dir)
    if not c:
        return ""
    if not c.get("judged"):
        return "하네스 에이전트 판정할 항목 없음"
    old = " (예전 채점)" if c.get("old") else ""
    return f"하네스 에이전트 {c['passed']}/{c['judged']} 통과 ({100 * c['passed'] / c['judged']:.1f}%){old}"


SI_PREFIXES = [(1e9, "G"), (1e6, "M"), (1e3, "k"), (1, ""), (1e-3, "m"), (1e-6, "µ"), (1e-9, "n"), (1e-12, "p"), (1e-15, "f")]
SI_UNITS = {"A", "V", "Hz", "F", "Ohm", "Ω", "s", "W", "V/s"}       # 접두어(µ, m, k ...)를 붙여 읽기 쉽게 쓰는 단위


def _value(x, unit) -> str:
    """하네스 값(SI 단위) -> '525.6 µA' 처럼. dB·° 같은 단위는 그대로."""
    if x is None:
        return "—"
    try:
        v = float(x)
    except (TypeError, ValueError):
        return esc(x)
    unit = unit or ""
    if unit in SI_UNITS and v != 0:
        scale, prefix = next(((s, p) for s, p in SI_PREFIXES if abs(v) >= s), SI_PREFIXES[-1])
        return f"{v / scale:.4g} {prefix}{unit}"
    return f"{v:.4g} {esc(unit)}".strip()


def body_harness(run_dir: Path, s: dict) -> str:
    result = read(run_dir, "harness/result.json") or {}
    c = harness_counts(run_dir)
    out = ["<p>하네스 에이전트(박준석 시스템의 채점기)가 최종 회로를 데이터시트의 모든 줄로 따로 채점합니다. "
           "회로는 바꾸지 않습니다. 앞 단계는 스펙 파일의 몇 항목만 재지만, 여기서는 데이터시트의 부하·전원 조건대로 전체를 잽니다.</p>"]
    if c.get("judged"):
        out.append(f"<p>판정 <b>{c['judged']}</b>개 중 <b>{c['passed']}</b>개 통과 "
                   f"(<b>{100 * c['passed'] / c['judged']:.1f}%</b>), 실패 {c['failed']}개. "
                   f"데이터시트 {c['total']}줄 중 아래 줄은 판정에서 뺐습니다 ({result.get('seconds')} s)</p>")
        if c.get("old"):
            out.append("<p class='sub'>2026-11-27 전 채점입니다. 그때는 같은 데이터시트의 다른 칩 줄, 공정 한계를 넘는 전원 조건 줄, "
                       "측정값이 없는 왜곡 줄도 판정에 넣어 지금 기준과 다릅니다.</p>")
    elif c:
        out.append(f"<p><b>판정할 항목이 없습니다.</b> 데이터시트 {c['total']}줄이 모두 아래 이유로 빠졌습니다.</p>")
    else:
        out.append(f"<p>통과율 <b>{num(result.get('pass_rate_percent'))}%</b></p>")
    if c:
        rows = [(label, c.get(key, 0)) for key, label in EXCLUDED_GROUPS if c.get(key)]
        if result.get("other_part_rows_dropped"):
            rows.append(("같은 데이터시트의 다른 칩 줄 (하네스에 넘기기 전에 뺌)", result["other_part_rows_dropped"]))
        if rows:
            out.append("<table><tr><th>판정에서 뺀 줄</th><th>개수</th></tr>" + "".join(
                f"<tr><td>{esc(label)}</td><td>{n}</td></tr>" for label, n in rows) + "</table>")
    out.append(harness_rows_html(run_dir))
    if result.get("note"):
        out.append(f"<p class='sub'>{esc(result['note'])}</p>")
    progress = harness_progress_html(run_dir)
    its = result.get("iterations") or []
    if (result.get("iterations_count") or 0) > 1:           # 하네스가 LLM 으로 회로를 고치던 때(2026-11-23 전) 실행
        if progress:
            out.append(progress)
        elif its:
            out.append("<table><tr><th>반복</th><th>통과율</th></tr>" + "".join(
                f"<tr><td>{esc(it.get('iteration', i + 1))}</td><td>{num(it.get('pass_rate_percent'))}%</td></tr>"
                for i, it in enumerate(its)) + "</table>")
    if result.get("final_netlist"):
        out.append(f"<details><summary>최종 넷리스트</summary><pre>{esc(result['final_netlist'][:20000])}</pre></details>")
    return "".join(out)


def harness_rows_html(run_dir: Path) -> str:
    """판정한 줄 표 (실패 먼저) + 판정에서 뺀 줄 접기."""
    from file_find import find_files
    files = find_files(run_dir / "harness", "*_SPEC_EVALUATION.json") if (run_dir / "harness").is_dir() else []
    if not files:
        return ""
    rows = json.loads(files[0].read_text(encoding="utf-8")).get("spec_evaluations") or []
    judged = sorted((r for r in rows if r.get("status") in JUDGED), key=lambda r: r["status"].startswith("PASS"))
    def target(r):
        parts = [f"{k} {_value(r.get(f'{k}_target'), r.get('unit'))}" for k in ("min", "typ", "max")
                 if r.get(f"{k}_target") is not None]
        return " · ".join(parts) or "—"
    out = []
    if judged:
        out.append("<table><tr><th>결과</th><th>항목</th><th>측정값</th><th>데이터시트 기준</th><th>조건</th></tr>" + "".join(
            f"<tr><td class='{'pass' if r['status'].startswith('PASS') else 'failc'}'>{STATUS_WORD[r['status']]}</td>"
            f"<td>{esc(r.get('symbol'))} {esc(r.get('name'))}</td><td>{_value(r.get('measured'), r.get('unit'))}</td>"
            f"<td>{target(r)}</td><td>{esc(r.get('conditions'))}</td></tr>" for r in judged) + "</table>")
    others = [r for r in rows if r.get("status") not in JUDGED]
    if others:
        out.append(f"<details><summary>판정에서 뺀 줄 {len(others)}개</summary><table><tr><th>이유</th><th>항목</th><th>조건</th></tr>"
                   + "".join(f"<tr><td>{esc(r.get('status'))}</td><td>{esc(r.get('symbol'))} {esc(r.get('name'))}</td>"
                             f"<td>{esc(r.get('conditions'))}</td></tr>" for r in others) + "</table></details>")
    return "".join(out)


HARNESS_PATTERNS = [   # 하네스 진행 기록에서 통과율이 나오는 줄
    ("round", re.compile(r"=== \[Outer Loop (\d+)/(\d+)\]")),
    ("llm", re.compile(r"Step (\d+) Complete \(Synthesis (\d+)/(\d+)\): Pass Rate = ([\d.]+)% \((\d+)/(\d+) specs\)")),
    ("blueprint", re.compile(r"Blueprint Adaptation candidate passed with ([\d.]+)%")),
    ("compose", re.compile(r"Compose: Base=([\d.]+)% .*Probe A=([\d.]+)% .*Probe B=([\d.]+)%")),
]


def harness_events(run_dir: Path) -> list:
    """log.txt 의 마지막 하네스 실행에서 단계별 통과율. LLM 이 직접 만든 회로 턴은 라운드마다 한 줄로 묶는다."""
    log_file = run_dir / "log.txt"
    if not log_file.exists():
        return []
    lines = log_file.read_text(encoding="utf-8").splitlines()
    starts = [i for i, line in enumerate(lines) if re.search(r"== \d+\. 하네스", line)]   # 단계 번호가 바뀌어도 찾게
    if not starts:
        return []
    events, round_no, llm = [], 0, None

    def flush():
        nonlocal llm
        if llm:
            events.append({"time": llm["time"], "round": round_no, "what": f"LLM 이 직접 만든 회로 ({llm['turns']}턴)",
                           "rate": llm["best"], "detail": f"측정까지 간 회로 {llm['measured']}개"})
            llm = None

    for line in lines[starts[-1]:]:
        time_text = line[1:9] if line.startswith("[") else ""
        for kind, pattern in HARNESS_PATTERNS:
            m = pattern.search(line)
            if not m:
                continue
            if kind == "round":
                flush()
                round_no = int(m.group(1))
            elif kind == "llm":
                llm = llm or {"time": time_text, "turns": 0, "best": 0.0, "measured": 0}
                llm["turns"] += 1
                llm["best"] = max(llm["best"], float(m.group(4)))
                llm["measured"] += int(m.group(6)) > 0
            elif kind == "blueprint":
                flush()
                events.append({"time": time_text, "round": round_no, "what": "우리 회로를 바탕으로 고친 회로",
                               "rate": float(m.group(1)), "detail": ""})
            else:
                flush()
                events.append({"time": time_text, "round": round_no, "what": "고치는 방법 두 가지 시험 (A, B)",
                               "rate": max(float(m.group(2)), float(m.group(3))),
                               "detail": f"기준 {m.group(1)}% · A {m.group(2)}% · B {m.group(3)}%"})
            break
    flush()
    best = 0.0
    for e in events:
        best = max(best, e["rate"])
        e["best"] = best
    return events


def harness_progress_html(run_dir: Path) -> str:
    events = harness_events(run_dir)
    if not events:
        return ""
    w, h, pad = 600, 150, 28
    xs = [pad + i * (w - 2 * pad) / max(1, len(events) - 1) for i in range(len(events))]

    def y(v):
        return h - pad - v / 100 * (h - 2 * pad)

    best_line = " ".join(f"{x:.1f},{y(e['best']):.1f}" for x, e in zip(xs, events))
    dots = "".join(f"<circle cx='{x:.1f}' cy='{y(e['rate']):.1f}' r='4' fill='var(--accent)'>"
                   f"<title>{esc(e['what'])}: {e['rate']}%</title></circle>" for x, e in zip(xs, events))
    grid = "".join(f"<line x1='{pad}' x2='{w - pad}' y1='{y(v):.1f}' y2='{y(v):.1f}' stroke='var(--line)'/>"
                   f"<text x='0' y='{y(v) + 4:.1f}' font-size='10' fill='var(--muted)'>{v}%</text>" for v in (0, 50, 100))
    chart = (f"<svg class='chart' viewBox='0 0 {w} {h}' role='img' aria-label='하네스 통과율 변화'>{grid}"
             f"<polyline points='{best_line}' fill='none' stroke='var(--ok)' stroke-width='2'/>{dots}</svg>"
             "<p class='sub'>점 = 그 단계 회로의 통과율, 초록 선 = 그때까지 최고</p>")
    table = ("<table><tr><th>시각</th><th>라운드</th><th>한 일</th><th>통과율</th><th>그때까지 최고</th><th>비고</th></tr>" + "".join(
        f"<tr><td>{esc(e['time'])}</td><td>{e['round']}</td><td>{esc(e['what'])}</td><td>{num(e['rate'])}%</td>"
        f"<td>{num(e['best'])}%</td><td>{esc(e['detail'])}</td></tr>" for e in events) + "</table>")
    return chart + table


def figure(run_dir: Path, stem: str, caption: str) -> str:
    png = run_dir / "schematic" / f"{stem}.png"
    if not png.exists():
        return ""
    data = base64.b64encode(png.read_bytes()).decode()
    svg_link = f" · <a href='schematic/{stem}.svg'>SVG</a> · <a href='schematic/{stem}.png'>PNG</a>"
    return f"<figure><img src='data:image/png;base64,{data}' alt='{esc(caption)}'><figcaption>{esc(caption)}{svg_link}</figcaption></figure>"


def body_schematic(run_dir: Path, s: dict) -> str:
    return (figure(run_dir, "after_harness", "하네스 후 최종 회로")
            + figure(run_dir, "before_harness", "하네스 전 우리 회로 (모델 구조 + 규칙 + 바이어스 + 크기)"))


def body_fix(run_dir: Path, s: dict) -> str:
    """LLM 이 실패한 구조를 어떻게 진단하고 고쳤는지 (structure_doctor.py 기록)."""
    doctor = read(run_dir, "doctor.json") or {}
    if not doctor.get("needed", s.get("needed")):
        return (f"<p>스펙을 절반 이상 통과하는 후보가 있어서 고치기는 필요 없었어요 "
                f"(동작한 후보 {doctor.get('working_before', s.get('working_before'))}개).</p>")
    fixed = doctor.get("fixed") or []
    how = {"rule_fix": "규칙으로", "llm_fix": "LLM 이"}
    used = ", ".join(f"{m.split('/')[-1]} {n}번" for m, n in ((doctor.get("llm") or {}).get("used") or {}).items())
    out = [f"<p>동작한 후보가 없어서 고쳐 봤어요. 규칙 자동 적용 <b>{len(doctor.get('rules_tried') or [])}번</b>, "
           f"LLM 호출 <b>{doctor.get('llm_calls', 0)}번</b>{f' ({esc(used)})' if used else ''}, "
           f"고쳐서 동작한 회로 <b>{len(fixed)}개</b>"
           + (" (" + ", ".join(f"{how.get(f.get('how'), '')} {f['passed']}/{f['judged']}" for f in fixed) + ")" if fixed else "")
           + ".</p>",
           "<p class='sub'>먼저 쌓인 규칙(조건 → 블록 변환)을 LLM 없이 적용하고, 그래도 안 되면 LLM 이 구조를 블록(입력단, 출력단, "
           "보상, 자체 바이어스)으로 나눠 보고 블록을 바꾸거나 새로 조합해요. 고친 회로는 시뮬레이션으로 다시 확인하고, LLM 이 고친 "
           "방법은 규칙으로 남겨 다음 칩에 먼저 써요. LLM 에 보낸 내용과 받은 답 원문은 실행 폴더의 doctor/ 에 있어요.</p>"]
    if doctor.get("rules_tried"):
        out.append("<h3>규칙 자동 적용</h3><table><tr><th>후보</th><th>규칙</th><th>내용</th><th>변환</th><th>결과</th></tr>")
        for r in doctor["rules_tried"]:
            ok = (r.get("result") or "").startswith("동작함")
            out.append(f"<tr><td>{r['candidate']}</td><td>{esc(r['rule'])} ({esc(r.get('status'))})</td>"
                       f"<td>{esc(r.get('text'))}</td><td class='mono'>{esc(r.get('then'))}</td>"
                       f"<td class='{'pass' if ok else 'failc'}'>{esc(r.get('result'))}</td></tr>")
        out.append("</table>")
    if doctor.get("attempts"):
        out.append("<h3>LLM 고치기</h3><table><tr><th>호출</th><th>후보</th><th>실패 이유</th><th>LLM 진단</th>"
                   "<th>고른 방법</th><th>결과</th></tr>")
        for a in doctor["attempts"]:
            params = json.dumps(a.get("params") or {}, ensure_ascii=False)
            ok = (a.get("result") or "").startswith("동작함")
            out.append(f"<tr><td>{a['call']}</td><td>{a['candidate']}</td><td>{esc((a.get('failure') or '')[:60])}</td>"
                       f"<td>{esc(a.get('diagnosis'))}<br><span class='sub'>{esc(a.get('why'))}</span></td>"
                       f"<td class='mono'>{esc(a.get('action'))} {esc(params if params != '{}' else '')}</td>"
                       f"<td class='{'pass' if ok else 'failc'}'>{esc(a.get('result'))}</td></tr>")
        out.append("</table>")
    if doctor.get("rules_written") or doctor.get("rule_changes"):
        out.append("<h3>규칙 모음에 남긴 것</h3><ul>")
        out += [f"<li>{'새 규칙' if w.get('new') else '같은 규칙에 통한 기록 추가'}: {esc(w.get('text'))}"
                f"<br><span class='mono sub'>{esc(w.get('rule_text'))}</span></li>" for w in doctor.get("rules_written") or []]
        out += [f"<li>상태 바뀜: {esc(c)}</li>" for c in doctor.get("rule_changes") or []]
        out.append("</ul>")
    return "".join(out)


BODIES = {"extract": body_extract, "candidates": body_candidates, "select": body_select, "fix": body_fix, "rank": body_rank,
          "rules": body_rules, "tune": body_tune, "harness": body_harness, "schematic": body_schematic}


def render(run_dir: Path) -> str:
    status = read(run_dir, "status.json") or {"steps": []}
    from pipeline import STEPS                   # 화면에는 지금 코드의 단계 이름을 쓴다
    titles = dict(STEPS)
    for s in status["steps"]:
        s["title"] = titles.get(s["key"], s["title"])
    running = status.get("state") == "running"
    chips = "".join(f"<span class='chip {s['state']}'>{esc(s['title'])}</span>" for s in status["steps"])
    parts = []
    for s in status["steps"]:
        if s["state"] == "wait":
            continue
        took = f" · {s['seconds']} s" if s.get("seconds") is not None else ""
        body = ""
        if s["state"] == "fail":
            body = f"<p class='err'>{esc(s.get('error'))}</p>"
        elif s["state"] == "done":
            try:
                body = BODIES[s["key"]](run_dir, s.get("summary") or {})
            except Exception as error:
                body = f"<p class='err'>화면 만들기 실패: {esc(error)}</p>"
        else:
            body = "<p class='sub'>진행 중…</p>" + (harness_progress_html(run_dir) if s["key"] == "harness" else "")
        if s.get("warnings"):
            body = ("<div class='warn'><b>프로그램 오류로 보임</b> (회로 문제가 아니라 코드를 고쳐야 할 수 있어요)<br>"
                    + "<br>".join(esc(w) for w in s["warnings"]) + "</div>") + body
        parts.append(f"<section><div class='head'><h2>{esc(s['title'])}</h2>"
                     f"<span class='state {s['state']}'>{STATE_TEXT[s['state']]}{took}</span></div>{body}</section>")
    log = (run_dir / "log.txt").read_text(encoding="utf-8")[-30000:] if (run_dir / "log.txt").exists() else ""
    log = log.replace(" (박준석 시스템)", "")       # 예전 단계 이름이 남은 기록
    refresh = f"<meta http-equiv='refresh' content='{REFRESH_SECONDS}'>" if running else ""
    info = run_info(run_dir)
    times = " · ".join(esc(x) for x in (info["when"], info["memo"]) if x)
    times += f" · 끝 {esc(status.get('finished'))}" if status.get("finished") else ""
    inp = read(run_dir, "input.json") or {}
    if (run_dir / "datasheet.pdf").exists():      # 같은 폴더의 파일이라 폴더만 받아도 열린다
        pdf_name = esc(inp.get("pdf_name") or "datasheet.pdf")
        times += f" · <a href='datasheet.pdf' download='{pdf_name}'>데이터시트 PDF 받기</a>"
    return f"""<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">{refresh}
<title>EDAI 설계 결과 - {esc(info['title'])}</title><style>{CSS}</style></head>
<body><main><h1>{esc(info['title'])}</h1><div class="sub">{times} · 실행 폴더 {esc(run_dir.name)}</div>
{f"<p class='sub'>{esc(status['note'])}</p>" if status.get("note") else ""}<div class="steps">{chips}</div>{''.join(parts)}
<details class="noprint"><summary>진행 기록 (log.txt)</summary><pre>{esc(log)}</pre></details>
</main></body></html>"""


def write(run_dir: Path) -> Path:
    out = Path(run_dir) / "report.html"
    out.write_text(render(Path(run_dir)), encoding="utf-8")
    return out


if __name__ == "__main__":
    print(write(Path(sys.argv[1])))
