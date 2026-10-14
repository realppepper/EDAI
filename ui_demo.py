"""
EDAI 화면 서버. 첫 화면(/)은 ui_app.py 에 있고, 이 파일에는 서버 실행과
초기 캐스코드 시험 화면(/cascode)이 있다.

캐스코드 시험 화면 (NiceGUI).
UI 프레임워크를 팀이 확정하기 전에 "어떤 느낌인지" 보기 위한 프로토타입이다.
LLM 재설계 단계는 아직 없고, 이미 있는 설계를 시뮬레이션한다. 비교 설계는 필요할 때 추가한다.

실행 (WSL):
    ~/.venvs/edai/bin/pip install nicegui plotly   # 최초 1회
    ~/.venvs/edai/bin/python ui_demo.py
    -> Windows 브라우저에서 http://localhost:8080
"""

import asyncio
from pathlib import Path

import plotly.graph_objects as go
from nicegui import run, ui

import run_sim
import schematic
import ui_app  # noqa: F401  (첫 화면 / 는 ui_app.py 에 있다)

HERE = Path(__file__).resolve().parent
# 발표용: 시뮬레이션은 순식간에 끝나므로 단계와 로그가 눈에 보이도록 일부러 멈춘다
STEP_DELAY_S = 1.5
LINE_DELAY_S = 0.5
STEPS = ["넷리스트 확인", "시뮬레이션 (ngspice)", "스펙 판정", "회로도 생성"]

STATE_STYLE = {
    "pending": ("radio_button_unchecked", "text-slate-300"),
    "running": ("autorenew", "text-sky-500 animate-spin"),
    "done": ("check_circle", "text-emerald-500"),
    "error": ("error", "text-rose-500"),
}


def design_elements(name: str) -> dict:
    """설계의 회로 본체와 AC 테스트벤치를 합쳐 읽은 소자 목록."""
    return schematic.parse_netlists([HERE / f"{name}.cir", run_sim.testbench_path(name, "ac")])


def design_spec(name: str) -> dict:
    """설계에 적용하는 스펙 파일 내용."""
    return run_sim.load_spec(run_sim.spec_path(name))


def spec_rows(r: dict) -> list:
    """스펙 파일 기준으로 판정한 행 중 PASS/FAIL이 난 항목."""
    rows = run_sim.judge(r, design_spec(r["name"]))
    return [row for row in rows if row["status"] in (run_sim.STATUS_PASS, run_sim.STATUS_FAIL)]


def spec_checks(r: dict) -> list:
    """(항목, 결과, 목표, 여유, 통과 여부) 목록."""
    return [
        (row["label"], f"{row['value']:.4g} {row['unit']}", run_sim.target_text(row),
         row["margin"], row["status"] == run_sim.STATUS_PASS)
        for row in spec_rows(r)
    ]


def bode_figure(results: list) -> go.Figure:
    """설계별 주파수 응답을 겹쳐 그린 인터랙티브 그래프."""
    fig = go.Figure()
    y_min = min(float(r["mag_db"].min()) for r in results)
    y_max = max(float(r["mag_db"].max()) for r in results) + 2
    for r in results:
        fig.add_trace(go.Scatter(
            x=r["freq"], y=r["mag_db"], mode="lines", name=r["name"], line=dict(width=3),
            hovertemplate="%{x:.3s}Hz<br>%{y:.2f} dB<extra>" + r["name"] + "</extra>",
        ))
        fig.add_trace(go.Scatter(
            x=[r["f3db"]], y=[r["gain_dc"] - 3], mode="markers", marker=dict(size=11),
            showlegend=False,
            hovertemplate="-3dB @ %{x:.3s}Hz<extra>" + r["name"] + "</extra>",
        ))
    spec = design_spec(results[0]["name"])
    gain_min = run_sim.spec_limit(spec, "gain_dc", "min")
    bw_min = run_sim.spec_limit(spec, "f3db", "min")
    if gain_min is not None:
        fig.add_trace(go.Scatter(
            x=[results[0]["freq"][0], results[0]["freq"][-1]],
            y=[gain_min] * 2, mode="lines", name="이득 스펙",
            line=dict(dash="dash", color="gray", width=1), hoverinfo="skip",
        ))
    if bw_min is not None:
        fig.add_trace(go.Scatter(
            x=[bw_min] * 2, y=[y_min, y_max], mode="lines", name="대역폭 스펙",
            line=dict(dash="dot", color="gray", width=1), hoverinfo="skip",
        ))
    fig.update_xaxes(type="log", title="Frequency (Hz)")
    fig.update_yaxes(title="Gain (dB)", range=[y_min, y_max])
    fig.update_layout(
        template="plotly_white", height=420, margin=dict(l=60, r=20, t=20, b=50),
        legend=dict(orientation="h", y=-0.2), hovermode="closest",
    )
    return fig


def schematic_svg(base: str, cand: str) -> tuple:
    """cand 설계의 회로도 SVG와 base 대비 바뀐 소자 목록 (같은 설계면 변경 없음)."""
    prev = design_elements(base)
    curr = design_elements(cand)
    schematic.check_topology(prev)
    schematic.check_topology(curr)
    changes = schematic.find_changes(prev, curr)
    svg = schematic.draw_cascode(curr, changes).get_imagedata("svg").decode()
    return svg[svg.find("<svg"):], changes


@ui.page("/cascode")
def index():
    ui.add_css(".schematic svg { width: 100%; height: auto; max-height: 460px; }")
    ui.query("body").classes("bg-slate-100")

    with ui.header().classes("bg-slate-900 items-center px-8 py-4 gap-4"):
        ui.icon("memory").classes("text-3xl text-sky-400")
        with ui.column().classes("gap-0"):
            ui.label("EDAI").classes("text-xl font-bold tracking-wider")
            ui.label("AI 기반 아날로그 회로 설계 자동화 · 시험 화면").classes("text-xs text-slate-400")
        ui.space()
        ui.link("EDAI 화면으로", "/").classes("text-sky-300 text-sm")

    # 회로도 틀이 캐스코드용뿐이라 이 화면에는 캐스코드 설계만 올린다
    designs = [d for d in run_sim.available_designs() if run_sim.circuit_kind(d) == "cascode"]
    with ui.column().classes("w-full max-w-7xl mx-auto p-6 gap-6"):
        with ui.card().classes("w-full rounded-2xl shadow-sm"):
            with ui.row().classes("w-full items-end gap-6"):
                base_sel = ui.select(designs, value=designs[0], label="설계").classes("w-48")
                cand_sel = ui.select(designs, value=designs[-1], label="비교 설계").classes("w-48")
                cand_sel.set_visibility(False)
                compare_btn = ui.button("비교 설계 추가", icon="add").props("flat no-caps")
                slow = ui.switch("단계 천천히 보기", value=True)
                ui.space()
                run_btn = ui.button("실행", icon="play_arrow").props("unelevated size=lg") \
                    .classes("rounded-xl px-8 bg-sky-600")

        with ui.row().classes("w-full gap-6 no-wrap items-stretch"):
            with ui.card().classes("w-80 rounded-2xl shadow-sm"):
                ui.label("진행 단계").classes("text-sm font-semibold text-slate-500")
                step_icons = []
                for i, name in enumerate(STEPS):
                    with ui.row().classes("items-center gap-3 py-1"):
                        icon = ui.icon(STATE_STYLE["pending"][0]).classes(f"text-2xl {STATE_STYLE['pending'][1]}")
                        ui.label(f"{i + 1}. {name}").classes("text-base")
                    step_icons.append(icon)
            with ui.card().classes("flex-1 rounded-2xl shadow-sm"):
                ui.label("진행 로그").classes("text-sm font-semibold text-slate-500")
                log = ui.log(max_lines=200).classes("w-full h-44 text-xs font-mono bg-slate-50 rounded-lg")

        results_area = ui.column().classes("w-full gap-6")

    def set_step(i: int, state: str) -> None:
        name, classes = STATE_STYLE[state]
        step_icons[i].name = name
        step_icons[i].classes(replace=f"text-2xl {classes}")

    async def pause(seconds: float = STEP_DELAY_S) -> None:
        if slow.value:
            await asyncio.sleep(seconds)

    async def say(message: str) -> None:
        log.push(message)
        await pause(LINE_DELAY_S)

    def toggle_compare() -> None:
        comparing = not cand_sel.visible
        cand_sel.set_visibility(comparing)
        if comparing and cand_sel.value == base_sel.value:
            cand_sel.value = next((d for d in designs if d != base_sel.value), base_sel.value)
        compare_btn.text = "비교 제거" if comparing else "비교 설계 추가"
        compare_btn.props(f"icon={'close' if comparing else 'add'}")

    async def on_run() -> None:
        base = base_sel.value
        cand = cand_sel.value if cand_sel.visible else base
        names = [base] if base == cand else [base, cand]
        run_btn.disable()
        results_area.clear()
        log.clear()
        for i in range(len(STEPS)):
            set_step(i, "pending")
        current = 0
        try:
            set_step(0, "running")
            await say(f"설계: {', '.join(names)}")
            for n in names:
                schematic.check_topology(design_elements(n))
                await say(f"  {n}.cir + 테스트벤치(tb_{run_sim.circuit_kind(n)}_*.cir) 연결 확인 OK")
            await pause()
            set_step(0, "done")

            current = 1
            set_step(1, "running")
            results = []
            for n in names:
                await say(f"  {n}: ngspice DC 동작점 · AC 해석 실행 중...")
                r = await run.io_bound(run_sim.evaluate, n)
                results.append(r)
                await say(f"  {n}: 공급전류 {r['id'] * 1e6:.1f} µA, Vout {r['vout_dc']:.2f} V, Vx {r['vx_dc']:.2f} V")
            await pause()
            set_step(1, "done")

            current = 2
            set_step(2, "running")
            for r in results:
                for label, value, target, margin, ok in spec_checks(r):
                    await say(f"  {r['name']}: {label} {value} (목표 {target}, 여유 {margin}) → {'PASS' if ok else 'FAIL'}")
            await pause()
            render_specs(results)
            set_step(2, "done")

            current = 3
            set_step(3, "running")
            svg, changes = schematic_svg(base, names[-1])
            await say(f"  회로도 생성: {names[-1]}")
            for name, (old, new) in changes.items():
                await say(f"  변경: {name}  {old} → {new}")
            await pause()
            render_plots(results, svg, changes)
            set_step(3, "done")
            await say("완료")
        except Exception as e:  # 시험 화면: 어느 단계에서 왜 멈췄는지 보여준다
            set_step(current, "error")
            log.push(f"에러: {e}")
            ui.notify(str(e), type="negative")
        finally:
            run_btn.enable()

    def render_specs(results: list) -> None:
        with results_area:
            if len(results) > 1:
                base, cand = results[0], results[-1]
                margins = {row["measure"]: row["margin"] for row in spec_rows(cand)}
                with ui.row().classes("w-full gap-6"):
                    kpi("소비전력", f"{base['power'] * 1e3:.2f} → {cand['power'] * 1e3:.3f} mW",
                        f"{base['power'] / cand['power']:.1f}배 감소", "bolt")
                    kpi("DC 이득", f"{base['gain_dc']:.1f} → {cand['gain_dc']:.1f} dB",
                        f"스펙 대비 {margins.get('gain_dc', '-')}", "trending_up")
                    kpi("-3dB 대역폭", f"{base['f3db'] / 1e6:.2f} → {cand['f3db'] / 1e6:.2f} MHz",
                        f"스펙 대비 {margins.get('f3db', '-')}", "graphic_eq")
            with ui.row().classes("w-full gap-6 no-wrap items-stretch"):
                for r in results:
                    spec_card(r)

    def render_plots(results: list, svg: str, changes: dict) -> None:
        with results_area:
            with ui.row().classes("w-full gap-6 no-wrap items-stretch"):
                with ui.card().classes("flex-[3] rounded-2xl shadow-sm"):
                    ui.label("주파수 응답 (마우스를 올리면 값 표시)").classes("text-sm font-semibold text-slate-500")
                    ui.plotly(bode_figure(results)).classes("w-full")
                with ui.card().classes("flex-[2] rounded-2xl shadow-sm"):
                    ui.label(f"회로도 · {results[-1]['name']}").classes("text-sm font-semibold text-slate-500")
                    ui.html(svg, sanitize=False).classes("schematic w-full")
                    if changes:
                        with ui.row().classes("gap-2"):
                            for name, (old, new) in changes.items():
                                ui.chip(f"{name}: {old} → {new}", icon="edit") \
                                    .props("outline color=red-7 dense")

    def kpi(title: str, value: str, note: str, icon: str) -> None:
        with ui.card().classes("flex-1 rounded-2xl shadow-sm"):
            with ui.row().classes("items-center gap-2"):
                ui.icon(icon).classes("text-xl text-sky-600")
                ui.label(title).classes("text-sm font-semibold text-slate-500")
            ui.label(value).classes("text-2xl font-bold text-slate-800")
            ui.label(note).classes("text-sm text-emerald-600 font-medium")

    def spec_card(r: dict) -> None:
        checks = spec_checks(r)
        passed = all(c[4] for c in checks)
        with ui.card().classes("flex-1 rounded-2xl shadow-sm"):
            with ui.row().classes("w-full items-center"):
                ui.label("스펙 충족 여부").classes("text-lg font-bold text-slate-800")
                ui.label(r["name"]).classes("text-sm text-slate-500")
                ui.space()
                ui.badge("전체 PASS" if passed else "전체 FAIL", color="positive" if passed else "negative") \
                    .classes("text-sm px-3 py-1")
            with ui.grid(columns=5).classes("w-full gap-x-4 gap-y-2 items-center"):
                for header in ["항목", "결과", "목표", "여유", "판정"]:
                    ui.label(header).classes("text-xs font-semibold text-slate-400")
                for label, value, target, margin, ok in checks:
                    ui.label(label).classes("text-slate-600")
                    ui.label(value).classes("font-semibold text-slate-800")
                    ui.label(target).classes("text-slate-500")
                    ui.label(margin).classes("text-emerald-600" if ok else "text-rose-600")
                    ui.badge("PASS" if ok else "FAIL", color="positive" if ok else "negative") \
                        .classes("justify-self-start")

    compare_btn.on_click(toggle_compare)
    run_btn.on_click(on_run)


if __name__ in {"__main__", "__mp_main__"}:
    ui.run(title="EDAI 시험 화면", host="0.0.0.0", port=8080, reload=False, show=False)
