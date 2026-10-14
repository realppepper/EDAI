"""
EDAI 화면 (NiceGUI, 한 페이지).
데이터시트 스펙 -> 구조 선택 -> 크기 결정(LLM 선택, SymPy 계산, 시뮬레이션 판정) -> 검증 결과를 네 단계로 보여준다.
단계 안에서는 내용이 차례로 나타나며 아래로 내려가고, 단계 사이는 옆으로 넘긴다.

시뮬레이션을 다시 돌리지 않고 sim_out 에 남은 기록을 읽어 그린다. 기록은 아래로 만든다:
    ~/.venvs/edai/bin/python run_sim.py opamp_a opamp_b --select    # 구조 후보 판정과 선택
    ~/.venvs/edai/bin/python llm_design.py                           # LLM 설계 루프

실행: ~/.venvs/edai/bin/python ui_demo.py
    http://localhost:8080            자동으로 재생 (Space 멈춤, 좌우 화살표로 단계 이동, Enter 로 한꺼번에 펼치기)
    http://localhost:8080/#3         3단계부터 보기
    http://localhost:8080/?static=1  모든 단계를 세로로 펼쳐 보기
화면 부품은 ui_components.py 에 있다. 회로 종류에 묶인 글자는 여기 두지 않고 스펙 파일(plain, headline)과
sizing.CHOICE_RANGES(label, unit)에서 읽는다.
"""

import json

from nicegui import app, ui

import run_sim
import sizing
import ui_components as kit

app.add_static_files("/assets", str(run_sim.HERE / "assets"))

SELECTION_FILE = run_sim.OUT_DIR / "selection.json"
DESIGN_LOG_FILE = run_sim.OUT_DIR / "design_log.json"
FINAL_DESIGN = "opamp_llm"
RECORD_HINT = "run_sim.py opamp_a opamp_b --select 와 llm_design.py 를 먼저 실행하세요."
DATASHEET_IMAGE = "/assets/datasheet_table.png"
MICRO, MEGA = 1e6, 1e-6
JUDGED = (run_sim.STATUS_PASS, run_sim.STATUS_FAIL)
STEP_NAMES = ["스펙 읽기", "구조 고르기", "크기 정하기", "검증 결과"]
TESTBENCH_ANALYSES = ("dc", "ac", "slew", "settle", "drive")
# 식으로 계산한 값과 시뮬레이션 측정값을 비교할 항목: (키, 표시 배율, 단위)
PREDICTED_METRICS = (("avd", 1, "dB"), ("ugbw", MEGA, "MHz"), ("sr", MEGA, "V/µs"), ("idd", MICRO, "µA"))
UNIT_TEXT = {"uA": "µA", "um": "µm"}


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def count_transistors(name: str) -> int:
    path = run_sim.HERE / f"{name}.cir"
    if not path.exists():
        return 0
    return sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.upper().startswith("XM"))


def load_records() -> dict:
    """화면에 필요한 기록을 모두 읽는다. 핵심 기록이 없으면 빈 dict."""
    selection, log = read_json(SELECTION_FILE), read_json(DESIGN_LOG_FILE)
    if selection is None or log is None or not log["iterations"]:
        return {}
    spec = run_sim.load_spec(run_sim.HERE / log["spec_file"])
    candidates = [c["design"] for c in selection["candidates"]]
    # 화면에서는 파일 이름 대신 "후보 1, 후보 2, 최종 설계" 로 부른다
    names = {design: f"후보 {index + 1}" for index, design in enumerate(candidates)}
    names[FINAL_DESIGN] = "최종 설계"
    return {
        "spec": spec,
        "selection": selection,
        "log": log,
        "names": names,
        "plain": {item["measure"]: item.get("plain", item["label"]) for item in spec["specs"]},
        "plain_by_label": {item["label"]: item.get("plain", item["label"]) for item in spec["specs"]},
        "headline": [item["measure"] for item in spec["specs"] if item.get("headline")],
        "curves": {design: read_json(run_sim.OUT_DIR / f"{design}_curves.json") or {} for design in names},
        "transistors": {design: count_transistors(design) for design in names},
    }


def value_text(value, unit: str) -> str:
    return "-" if value is None else f"{value:.4g} {unit}"


def choice_text(key: str, value) -> str:
    unit = sizing.CHOICE_RANGES[key].get("unit", "")
    return f"{value:g} {UNIT_TEXT.get(unit, unit)}"


@ui.page("/")
def main_page():
    kit.install_theme()
    try:
        records = load_records()
    except Exception as error:  # 기록 파일이 깨졌을 때도 화면은 열려야 한다
        kit.state_panel("error", "기록을 읽지 못했습니다", str(error))
        return
    if not records:
        kit.state_panel("empty", "기록이 없습니다", RECORD_HINT)
        return
    with kit.deck(STEP_NAMES):
        render_spec_step(records)
        render_structure_step(records)
        render_sizing_step(records)
        render_result_step(records)


# ---------------------------------------------------------------- 1단계: 스펙 읽기
def render_spec_step(records: dict) -> None:
    spec, plain = records["spec"], records["plain"]
    rows = records["log"]["iterations"][-1]["rows"]
    judged = [r for r in rows if r["status"] in JUDGED]
    excluded = [r for r in rows if r["status"] == run_sim.STATUS_EXCLUDED]
    team = sum(r["basis"] == run_sim.BASIS_TEAM for r in judged)
    lede = (f"데이터시트 표에서 <strong>{len(rows)}개 항목</strong>을 찾았고, 그중 시뮬레이션으로 확인할 수 있는 "
            f"<strong>{len(judged)}개</strong>를 설계 목표로 삼았습니다.")
    with kit.panel(0, "1단계 · 스펙 읽기", "데이터시트에서 설계 목표 추출", lede):
        with kit.scene():
            kit.io_cards(
                {"head": "데이터시트 PDF", "body": kit.escape(spec["source"]),
                 "extra": f'<div class="dk-doc"><img src="{DATASHEET_IMAGE}" alt="데이터시트의 특성 표. 읽어 낸 줄이 색으로 표시되어 있다"></div>'
                          '<div class="dk-legend"><span><i style="background:rgba(64,112,196,.35)"></i>설계 목표로 읽은 줄</span>'
                          '<span><i style="background:rgba(140,128,115,.35)"></i>측정에서 제외한 줄</span></div>'},
                {"head": "표 읽기와 항목 분류",
                 "body": "항목마다 이름, 조건, 최소·대표·최대 값을 읽습니다.<br><br>대표값만 있는 항목에는 팀 기준"
                         "(대표값의 80% 이상 또는 120% 이하)을 적용하고, 시뮬레이션으로 잴 수 없는 항목은 이유와 함께 따로 둡니다.<br><br>"
                         "지금은 표의 값을 사람이 옮겨 적었습니다."},
                {"head": "설계 목표", "number": len(judged), "unit": "개",
                 "body": f"데이터시트 값 그대로 {len(judged) - team}개<br>팀 기준 적용 {team}개<br>측정에서 제외 {len(excluded)}개"},
            )
        with kit.scene():
            with kit.card():
                by_measure = {r["measure"]: r for r in judged}
                headline = [by_measure[m] for m in records["headline"] if m in by_measure]
                kit.sub_title(f"대표 목표 {len(headline)}가지")
                for r in headline:
                    kit.goal_row(plain[r["measure"]], r["label"], run_sim.target_text(r),
                                 chips=kit.chip(r["basis"], "warn" if r["basis"] == run_sim.BASIS_TEAM else ""))
                with kit.more(f"설계 목표 {len(judged)}개 전체 보기"):
                    kit.html(kit.escape(spec["conditions"]), "dk-text").style("margin-bottom:8px")
                    for r in judged:
                        kit.small_row(r["label"], r.get("condition") or "", run_sim.target_text(r))
                with kit.more(f"측정에서 제외한 {len(excluded)}개와 이유").style("margin-top:0"):
                    for r in excluded:
                        kit.small_row(r["label"], r.get("margin") or "")


# ---------------------------------------------------------------- 2단계: 구조 고르기
def render_structure_step(records: dict) -> None:
    selection, names = records["selection"], records["names"]
    candidates = selection["candidates"]
    chosen = next(c for c in candidates if c["design"] == selection["selected"])
    lede = (f"후보 구조 {len(candidates)}개를 같은 조건으로 측정했고, 설계 목표 {chosen['judged']}개 중 "
            f"<strong>{chosen['passed']}개를 통과한 {names[chosen['design']]}</strong>를 골랐습니다.")
    with kit.panel(1, "2단계 · 구조 고르기", "후보 구조 비교와 선정", lede):
        with kit.scene():
            kit.io_cards(
                {"head": f"후보 구조 {len(candidates)}개", "body": "같은 설계 목표를 놓고 서로 다른 방식으로 만든 회로입니다."},
                {"head": "같은 조건의 측정과 판정",
                 "body": f"후보마다 같은 테스트벤치 {len(TESTBENCH_ANALYSES)}종으로 시뮬레이션하고, 1단계에서 정한 목표로 통과 여부를 판정합니다."},
                {"head": f"{names[chosen['design']]} 선정", "number": chosen["passed"], "unit": f"/ {chosen['judged']} 통과"},
            )
        with kit.scene():
            with kit.columns():
                for candidate in candidates:
                    is_chosen = candidate["design"] == selection["selected"]
                    with kit.card("chosen" if is_chosen else "rejected"):
                        kit.html(kit.chip("선정", "solid") if is_chosen else kit.chip("탈락", "fail"))
                        kit.html(kit.escape(names[candidate["design"]]), "head").style("margin-top:12px")
                        kit.html(f'<div class="num">{candidate["passed"]}<small>/ {candidate["judged"]} 통과</small></div>')
                        kit.meter(candidate["passed"], candidate["judged"])
                        kit.html(f'<p>{kit.escape(candidate["structure"])}</p>')
                        kit.html(f'<p>트랜지스터 {records["transistors"].get(candidate["design"], 0)}개 · '
                                 f'{kit.escape(candidate["design"])}.cir</p>').style("margin-top:6px;font-size:14px")
        with kit.scene():
            with kit.card():
                kit.sub_title("선정 근거")
                for candidate in candidates:
                    name = names[candidate["design"]]
                    if not candidate["failed_items"]:
                        kit.goal_row(name, "판정한 목표를 모두 통과", chips=kit.chip("모두 통과", "pass"))
                        continue
                    kit.goal_row(name, f"{len(candidate['failed_items'])}개 목표에 미달",
                                 chips=kit.chip("미달", "fail"))
                    for item in candidate["failed_items"]:
                        kit.goal_row(records["plain_by_label"].get(item["label"], item["label"]), item["label"],
                                     value_text(item["value"], item["unit"]), f'목표 {item["target"]}', state="fail")


# ---------------------------------------------------------------- 3단계: 크기 정하기
def render_sizing_step(records: dict) -> None:
    log, plain = records["log"], records["plain"]
    iterations = log["iterations"]
    total = iterations[-1]["judged"]
    if log["final"]:
        lede = (f"고른 구조의 소자 크기를 정했습니다. 시뮬레이션 결과를 보고 값을 고쳐 가며 "
                f"<strong>{log['final']}번째 시도에서 목표 {total}개를 모두 통과</strong>했습니다.")
    else:
        lede = f"{len(iterations)}번 시도했지만 아직 목표 {total}개를 모두 통과하지 못했습니다."
    with kit.panel(2, "3단계 · 크기 정하기", "소자 크기 결정과 반복 개선", lede):
        with kit.scene():
            kit.io_cards(
                {"head": "고른 구조와 설계 목표", "body": kit.escape(log["structure"])},
                {"head": "선택, 계산, 판정의 반복",
                 "body": f"LLM 이 {len(sizing.CHOICE_RANGES)}가지 값을 고르고 이유를 답합니다.<br>"
                         "SymPy 가 식으로 소자 크기를 계산합니다.<br>시뮬레이션이 목표 통과 여부를 판정하고, 미달 항목을 LLM 에 돌려줍니다."},
                {"head": "모든 목표 통과까지", "number": len(iterations), "unit": "회"},
            )
        with kit.scene():
            kit.count_chart("시도마다 통과한 목표 수", [f"{r['iteration']}회차" for r in iterations],
                            [r["passed"] for r in iterations], total,
                            anchors=[f"iteration-{r['iteration']}" for r in iterations])
            with kit.card().style("margin-top:18px"):
                with kit.more("계산에 쓰는 식 (SymPy)").style("margin-top:0"):
                    for record in log["equations"]:
                        kit.small_row(record["meaning"], record["equation"])
                with kit.more(f"LLM 모델: {log['model']}").style("margin-top:0"):
                    kit.html("LLM 은 값과 이유만 답하고, 소자 크기와 예상 성능은 모두 식으로 계산합니다. "
                             "아래 회차의 인용문은 LLM 이 답한 문장을 고치지 않고 옮긴 것입니다.", "dk-text")
        previous = None
        for record in iterations:
            render_iteration(record, previous, plain)
            previous = record


def render_iteration(record: dict, previous, plain: dict) -> None:
    """설계 회차 하나: 바꾼 것 -> 결과. 계산값과 측정값 비교는 접어 둔다."""
    passed_all = record.get("all_pass", False)
    with kit.scene(anchor=f"iteration-{record['iteration']}"):
        with kit.card():
            kit.html(f'<div style="display:flex;align-items:baseline;gap:14px;flex-wrap:wrap">'
                     f'<span class="head" style="margin:0">{record["iteration"]}회차</span>'
                     f'<span class="num" style="font-size:34px">{record["passed"]}<small>/ {record["judged"]} 통과</small></span>'
                     f'{kit.chip("모두 통과", "pass") if passed_all else kit.chip("미달 있음", "fail")}</div>')
            kit.meter(record["passed"], record["judged"])
            if record.get("error"):
                kit.html(f'<p>{kit.escape(record["error"])}</p>')
                return
            keys = list(sizing.CHOICE_RANGES)
            before = previous.get("choices") if previous else None
            changed = [k for k in keys if before is None or record["choices"][k] != before[k]]
            kit.sub_title("처음 고른 값" if before is None else "바꾼 값").style("margin-top:18px")
            for key in changed:
                kit.goal_row(sizing.CHOICE_RANGES[key]["label"], "", choice_text(key, record["choices"][key]),
                             was=choice_text(key, before[key]) if before else "", state="changed" if before else "")
                if before and record["reasons"].get(key):
                    kit.html(f'LLM 의 설명: {kit.escape(record["reasons"][key])}', "dk-quote")
            if before is None:
                with kit.more("값마다 고른 이유 (LLM 의 설명)"):
                    for key in keys:
                        kit.small_row(sizing.CHOICE_RANGES[key]["label"], record["reasons"].get(key, ""))
            failed = [r for r in record["rows"] if r["status"] == run_sim.STATUS_FAIL]
            kit.sub_title("결과").style("margin-top:20px")
            if not failed:
                kit.goal_row("목표를 모두 통과", "", chips=kit.chip("통과", "pass"))
            for item in failed:
                kit.goal_row(plain.get(item["measure"], item["label"]), item["label"],
                             value_text(item["value"], item["unit"]), f"목표 {run_sim.target_text(item)}",
                             chips=kit.chip(item["margin"], "fail"), state="fail")
            with kit.more("식으로 계산한 값과 시뮬레이션 측정값"):
                for key, scale, unit in PREDICTED_METRICS:
                    predicted, measured = record["predicted"][key] * scale, record["measured"][key] * scale
                    kit.small_row(plain.get(key, key), f"계산 {predicted:.4g} → 측정 {measured:.4g} {unit}",
                                  f"{(measured - predicted) / predicted * 100:+.0f}%")
            with kit.more("계산된 소자 크기"):
                for name, value in record["sizes"].items():
                    kit.small_row(name, "", f"{value:g}")


# ---------------------------------------------------------------- 4단계: 검증 결과
def render_result_step(records: dict) -> None:
    log, plain, names = records["log"], records["plain"], records["names"]
    final = log["iterations"][-1]
    judged = [r for r in final["rows"] if r["status"] in JUDGED]
    excluded = [r for r in final["rows"] if r["status"] == run_sim.STATUS_EXCLUDED]
    passed = sum(r["status"] == run_sim.STATUS_PASS for r in judged)
    lede = (f"최종 설계를 설계 목표 {len(judged)}개로 판정한 결과 <strong>{passed}개를 통과</strong>했습니다. "
            f"데이터시트의 나머지 {len(excluded)}개 항목은 아직 측정하지 않았습니다.")
    with kit.panel(3, "4단계 · 검증 결과", "최종 설계의 항목별 검증", lede):
        with kit.scene():
            kit.io_cards(
                {"head": "최종 설계의 넷리스트",
                 "body": f"트랜지스터 {records['transistors'].get(FINAL_DESIGN, 0)}개 · {FINAL_DESIGN}.cir<br>GF180MCU 공정 모델"},
                {"head": "테스트벤치 측정과 판정",
                 "body": f"테스트벤치 {len(TESTBENCH_ANALYSES)}종(직류, 주파수 응답, 슬루율, 정착시간, 출력 구동)으로 "
                         "데이터시트와 같은 조건에서 측정합니다."},
                {"head": "목표 통과", "number": passed, "unit": f"/ {len(judged)}"},
            )
        with kit.scene():
            with kit.card():
                kit.sub_title("대표 항목")
                by_measure = {r["measure"]: r for r in judged}
                with kit.figures():
                    for measure in records["headline"]:
                        r = by_measure.get(measure)
                        if r is not None and r["value"] is not None:
                            kit.figure(plain[measure], r["value"], r["unit"], term=r["label"],
                                       note=f"목표 {run_sim.target_text(r)}")
        with kit.scene():
            with kit.card():
                kit.sub_title(f"설계 목표 {len(judged)}개의 판정")
                for r in judged:
                    ok = r["status"] == run_sim.STATUS_PASS
                    kit.goal_row(plain[r["measure"]], r["label"], value_text(r["value"], r["unit"]),
                                 f"목표 {run_sim.target_text(r)}",
                                 chips=kit.chip("통과" if ok else "미달", "pass" if ok else "fail"),
                                 state="" if ok else "fail")
                with kit.more(f"아직 측정하지 않은 {len(excluded)}개와 이유"):
                    for r in excluded:
                        kit.small_row(r["label"], r.get("margin") or "")
        curves = {names[design]: data for design, data in records["curves"].items()}

        def series(x_key: str, y_key: str, x_scale: float = 1.0) -> list:
            return [{"name": name, "x": [x * x_scale for x in data[x_key]], "y": data[y_key]}
                    for name, data in curves.items() if x_key in data and y_key in data]

        with kit.scene(hold=9):
            with kit.columns():
                kit.response_chart("주파수에 따른 이득 · RL 2 kΩ, CL 10 pF", series("freq", "mag_db"),
                                   x_label="주파수 (Hz)", y_label="dB", x_log=True,
                                   limits=({"label": "0 dB", "value": 0, "axis": "y"},))
                kit.response_chart("주파수에 따른 위상", series("freq", "phase"),
                                   x_label="주파수 (Hz)", y_label="°", x_log=True,
                                   limits=({"label": "-180°", "value": -180, "axis": "y"},))
        with kit.scene(hold=9):
            kit.response_chart("계단 입력에 대한 출력 · RL 10 kΩ, CL 50 pF", series("slew_t", "slew_out", MICRO),
                               x_label="시간 (µs)", y_label="V", height="340px")
