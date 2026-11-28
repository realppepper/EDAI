"""
실행 하나의 최종 회로를 ZIP 하나로 묶는다 (UI 의 '최종 회로 받기' 버튼, ui_server.py /api/zip).

    <칩>_final.cir       우리 회로 넷리스트 (final.json 의 .subckt, GF180 6 V 소자)
    <칩>_schematic.png   최종 회로도 (9단계 schematic/before_harness.png)
    설명.txt             칩, 공정·전원, 전류원 전류·출력단 배율·보상, 우리 측정 판정, 데이터시트 전체 검증 개수, 만든 날짜

실행 폴더의 파일만 읽고 새 파일은 만들지 않는다 (ZIP 은 메모리에서 만들어 바로 보낸다).
"""

import io
import json
import re
import zipfile
from pathlib import Path

SCHEMATIC = "schematic/before_harness.png"     # 하네스는 검증만 하므로 하네스 전 회로가 최종 회로


def _read(run_dir: Path, name: str):
    path = run_dir / name
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def part_name(run_dir: Path) -> str:
    inp = _read(run_dir, "input.json") or {}
    name = str(inp.get("title") or inp.get("extracted_part") or run_dir.name)
    return re.sub(r"[^A-Za-z0-9_-]+", "_", name).strip("_") or "circuit"


def netlist_text(final: dict, part: str) -> str:
    return "\n".join([
        f"* {part} 최종 회로 (EDAI 구조 생성 시스템)",
        "* 공정: GF180MCU 6 V 소자 (nfet_06v0, pfet_06v0), 전원 5 V 단일",
        "* 단자 순서: INP INN OUT VDD VSS",
        "* ngspice 에서 쓸 때 PDK 모델을 먼저 불러온다. 예:",
        "*   .include <gf180mcu_fd_pr>/models/ngspice/design.ngspice",
        "*   .lib <gf180mcu_fd_pr>/models/ngspice/sm141064.ngspice typical",
        "*   .include " + f"{part}_final.cir",
        "",
        final["subckt"].strip(),
        "",
    ])


def isolated_bodies(final: dict) -> list:
    """바디가 전원(VDD/VSS)이 아닌 MOS 이름. AB급 출력단의 소스 팔로워가 그렇다 (structure_blocks.push_pull_output)."""
    names = []
    for part in str(final.get("table") or "").split(";"):
        tokens = part.split()
        pins = dict(x.split("=", 1) for x in tokens[1:] if "=" in x)
        if tokens and pins.get("B") not in (None, "VDD", "VSS"):
            names.append(tokens[0])
    return names


def readme_text(run_dir: Path, final: dict, part: str) -> str:
    status = _read(run_dir, "status.json") or {}
    harness = _read(run_dir, "harness/result.json") or {}
    lines = [f"{part} 최종 회로", "",
             f"실행: {run_dir.name}",
             f"시작 {status.get('started') or '-'} / 끝 {status.get('finished') or '-'}", "",
             "공정·전원: GF180MCU 6 V 소자, 5 V 단일 전원",
             f"구조: {final.get('label') or '-'}" + (f" (규칙: {', '.join(final['rules'])})" if final.get("rules") else ""),
             f"전류원 전류: {final.get('unit_current', 20e-6) * 1e6:.3g} µA, 출력단 배율: x{final.get('output_scale', 0):g}"
             + (f", 보상 커패시터: {final['compensation_pf']:g} pF" if final.get("compensation_pf") else ""), "",
             f"우리 측정 판정: {final.get('passed')}/{final.get('judged')} 통과"]
    isolated = isolated_bodies(final)
    if isolated:
        lines[-1:-1] = [f"주의: {', '.join(isolated)} 는 바디를 소스에 묶었다. 실제 칩에서는 분리된 웰(NMOS 는 deep N-well)에 만든다", ""]
    for row in final.get("spec") or []:
        value = row.get("value")
        shown = "-" if value is None else f"{value:.4g} {row.get('unit', '')}"
        lines.append(f"  {'통과' if row.get('status') == 'PASS' else '실패'}  {row.get('label')}: {shown} (목표 {row.get('target')})")
    import make_run_report                       # 예전 실행(개수 기록 없음)도 결과 화면과 같은 방식으로 센다
    counts = make_run_report.harness_counts(run_dir)
    if counts:
        lines += ["", "데이터시트 전체 검증 (하네스 에이전트): "
                  + (f"판정 {counts['judged']}개 중 {counts['passed']}개 통과" if counts.get("judged") else "판정할 항목 없음")
                  + f" (데이터시트 {counts.get('total')}줄 중 시뮬레이션으로 확인할 수 없는 줄 {counts.get('not_testable', 0)}개, "
                    f"다른 전원 조건 {counts.get('supply', 0)}개 제외)" + (" - 예전 채점" if counts.get("old") else "")]
    lines += ["", "파일",
              f"  {part}_final.cir      넷리스트 (.subckt)",
              f"  {part}_schematic.png  회로도", ""]
    return "\n".join(lines)


def build(run_dir: Path) -> tuple:
    """(ZIP 파일 이름, ZIP 바이트). 최종 회로가 없으면 ValueError."""
    final = _read(run_dir, "final.json")
    if not final or ".subckt" not in (final.get("subckt") or ""):
        raise ValueError("최종 회로가 아직 없어요 (6단계 이후에 받을 수 있어요)")
    part = part_name(run_dir)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(f"{part}_final.cir", netlist_text(final, part))
        png = run_dir / SCHEMATIC
        if png.exists():
            z.write(png, f"{part}_schematic.png")
        z.writestr("설명.txt", readme_text(run_dir, final, part))
    return f"{part}_최종회로.zip", buf.getvalue()
