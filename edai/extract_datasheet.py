"""
데이터시트 PDF -> 스펙 추출 결과 (박준석 AnalogVerifier 의 1단계를 그대로 가져다 씀).

    1. PDF 읽기: analogverifier/ai_analog_designer/pdf_to_graph/pdf_parser.py (NVIDIA nemotron-parse)
    2. 스펙 추출: analogverifier/ai_analog_designer/pdf_to_graph/hardware_kg_builder.py (LLM, 페이지마다)
    3. 측정 계획: analogverifier/.../verification_flow.plan_for -> spec_from_plan.py 로 우리 스펙 파일
결과는 data/extraction/<이름>_hkg.json, <이름>_SPEC_EVALUATION.json, spec_<이름>.json. 추출 형식은 박준석 시스템의 HKG 캐시와 같아서 spec_from_hkg.py 가 바로 읽는다.
API 키는 .env 에서 환경변수로만 넘긴다 (출력하지 않음).

사용법 (WSL 가상환경):
    ~/.venvs/edai/bin/python extract_datasheet.py <pdf> [이름]
    예) ~/.venvs/edai/bin/python extract_datasheet.py pdfs/TLV271.PDF tlv271
    --reuse: data/extraction/<이름>_hkg.json 이 있으면 PDF 추출을 건너뛰고 스펙 만들기만
"""

import json
import os
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
# 박준석 시스템(ai_analog_designer) 이 있는 폴더 = 이 저장소 루트 (main). 다른 곳이면 EDAI_AV_DIR 로
AV_DIR = Path(os.environ.get("EDAI_AV_DIR") or HERE.parent)
OUT_DIR = HERE / "data" / "extraction"
ENV_FILES = (HERE / ".env", AV_DIR / ".env")      # 키 파일: edai/.env 먼저, 없으면 저장소 루트 .env
ENV_KEYS = ("NVIDIA_API_KEY", "IEEE_API_KEY")
MAX_PAGES = 30                 # 박준석 시스템 Studio 기본값과 같게


def load_keys() -> None:
    """.env 에서 필요한 키만 환경변수로 (이미 있으면 그대로 둠). WSL 안에서 돌면 ngspice 경로도 직접 준다."""
    if os.name != "nt":
        os.environ.setdefault("AV_NGSPICE", os.path.expanduser("~/ngspice/bin/ngspice"))
        os.environ.setdefault("AV_PDK_DIR", os.path.expanduser("~/pdk/gf180mcu_fd_pr/models/ngspice"))
        os.environ.setdefault("EDAI_NGSPICE", os.path.expanduser("~/ngspice/bin/ngspice"))   # 박준석 ngspice_runner 용
        # 하네스 시뮬레이터: ngspice (ai_analog_designer/neuro_symbolic_verifier/sim_backend.py). LTspice 로 하려면 ltspice
        os.environ.setdefault("AV_SIMULATOR", "ngspice")
    # 하네스 시험 전원의 최대값 = 우리 회로를 만들고 잰 전원 (GF180 6 V 소자, run_sim.OPAMP_VDD). 데이터시트가 15 V 로
    # 시험해도 그 이상은 걸지 않음 (LM358 에서 15 V 로 걸어 전원 전류 0.78 A, PDG 1단계 탈락, 2026-11-23)
    os.environ.setdefault("AV_MAX_SUPPLY_V", "5")
    env_file = next((f for f in ENV_FILES if f.exists()), None)
    if env_file is None:
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            if key.strip() in ENV_KEYS and key.strip() not in os.environ:
                os.environ[key.strip()] = value.strip().strip('"').strip("'")


def extract(pdf: Path, name: str, log=print) -> Path:
    """PDF 하나를 추출해 저장하고 결과 파일 경로를 돌려준다. log 는 진행 상황을 받는 함수."""
    load_keys()
    if not os.environ.get("NVIDIA_API_KEY"):
        raise RuntimeError(".env 에 NVIDIA_API_KEY 가 없습니다")
    sys.path.insert(0, str(AV_DIR))
    from ai_analog_designer.pdf_to_graph.pdf_parser import PDFDatasheetParser
    from ai_analog_designer.pdf_to_graph.hardware_kg_builder import HardwareKnowledgeGraphBuilder

    t0 = time.time()
    parser = PDFDatasheetParser(max_pages=MAX_PAGES)
    parsed = parser.parse_pdf(str(pdf), progress_callback=lambda done, total, page, err:
                              log(f"PDF 읽기 {done}/{total} (쪽 {page}){' - 글자만 읽음' if err else ''}"))
    log(f"PDF 읽기 끝 ({time.time() - t0:.0f} s)")
    builder = HardwareKnowledgeGraphBuilder()
    hkg = builder.build_kg_from_parsed_pdf(parsed, progress_callback=lambda done, total, page, err:
                                           log(f"스펙 표 추출 {done}/{total} (쪽 {page}){' - 다시 시도' if err else ''}"))
    raw = hkg.graph.get("raw_extraction", {})
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    # 쪽별 원문 (PDG 감사가 근거 글이 그 쪽에 있는지 확인할 때 씀)
    (OUT_DIR / f"{name}_pages.json").write_text(json.dumps(
        {str(k): v for k, v in PDFDatasheetParser.audit_pages(parsed).items()}, ensure_ascii=False), encoding="utf-8")
    out = OUT_DIR / f"{name}_hkg.json"
    out.write_text(json.dumps(raw, ensure_ascii=False, indent=1), encoding="utf-8")
    log(f"추출 끝: 스펙 {len(raw.get('electrical_parameters', []))}줄, 핀 {len(raw.get('pins', []))}개 "
        f"({time.time() - t0:.0f} s) -> {out}")
    return out


EMPTY_NETLIST = "* 빈 회로: 측정 계획(항목별 측정 종류와 목표값)만 얻으려고 넣는다\n"


def build_pdg(hkg_file: Path, out_dir: Path, log=print, pages_file: Path = None) -> dict:
    """추출 결과 -> PDG (핀 사이 의존 관계와 전원 켜는 순서). 박준석 시스템 2단계를 그대로 부른다, LLM 없음.
    결과: out_dir/pdg.json (노드, 연결, 순서, 감사 점수), out_dir/pdg.svg (그림)."""
    sys.path.insert(0, str(AV_DIR))
    from ai_analog_designer.pdf_to_graph.hardware_kg_builder import HardwareKnowledgeGraphBuilder
    from ai_analog_designer.pdf_to_graph.pdg_extractor import PortDependencyGraphExtractor
    from ai_analog_designer.pdf_to_graph.pdg_fidelity_verifier import PDGFidelityVerifier
    from ai_analog_designer.pdf_to_graph.pdg_visualizer import PDGVisualizer

    raw = json.loads(hkg_file.read_text(encoding="utf-8"))
    hkg = HardwareKnowledgeGraphBuilder.__new__(HardwareKnowledgeGraphBuilder)._json_to_networkx_graph(raw)
    if pages_file and pages_file.exists():         # 없으면 감사 점수가 낮게 나온다 (근거 글을 원문과 못 맞춤)
        hkg.graph["parsed_pages"] = {int(k): v for k, v in json.loads(pages_file.read_text(encoding="utf-8")).items()}
    pdg, schedule, levels = PortDependencyGraphExtractor().extract_pdg(hkg)
    try:
        audit = PDGFidelityVerifier.audit_pdg(hkg, pdg, schedule)
    except Exception as error:                      # 감사는 쪽 원문이 있어야 하는 항목이 있어 실패해도 그림은 만든다
        audit = {"error": f"{type(error).__name__}: {error}"}
    data = {"nodes": [{"name": n, "role": d.get("role")} for n, d in pdg.nodes(data=True)],
            "edges": [{"from": a, "to": b, **{k: v for k, v in d.items() if isinstance(v, (str, int, float, type(None)))}}
                      for a, b, d in pdg.edges(data=True)],
            "schedule_us": schedule, "levels": levels,
            "audit": {k: v for k, v in audit.items() if isinstance(v, (str, int, float, bool, type(None)))},
            "audit_with_pages": bool(pages_file and pages_file.exists())}
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "pdg.json").write_text(json.dumps(data, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    (out_dir / "pdg.svg").write_text(PDGVisualizer.to_svg(raw.get("pins", []), schedule, pdg), encoding="utf-8")
    log(f"PDG: 핀 {pdg.number_of_nodes()}개, 의존 관계 {pdg.number_of_edges()}개, 순서 단계 {len(levels)}")
    return data


def plan_specs(hkg_file: Path, name: str, log=print) -> Path:
    """추출 결과 -> 박준석 시스템 측정 계획 -> 우리 스펙 파일 (spec_<name>.json, data/train/<name>.json).
    측정 계획은 verification_flow.verify 에 빈 회로를 넣어 얻는다 (컴파일 단계에서 멈추고 항목별 계획만 남음).
    계획 단계에서 LLM 을 한 번 부른다 (박준석 시스템 spec_planner 의 확률적 보완)."""
    load_keys()
    sys.path.insert(0, str(AV_DIR))
    from ai_analog_designer.neuro_symbolic_verifier.verification_flow import plan_for, verify
    import spec_from_hkg
    import spec_from_plan

    hkg = json.loads(hkg_file.read_text(encoding="utf-8"))
    t0 = time.time()
    plan = plan_for(hkg["ic_device"], hkg["pins"], hkg["electrical_parameters"])
    log(f"측정 계획: {plan['summary']['planned']}줄 계획 / 전기 사양 {plan['summary']['electrical_rows']}줄 "
        f"({time.time() - t0:.0f} s)")
    work = HERE / "sim_out" / "plan" / name
    ev = verify(EMPTY_NETLIST, plan, {}, str(work), dut_name=hkg["ic_device"].get("name"), label="plan")
    ev_file = OUT_DIR / f"{name}_SPEC_EVALUATION.json"
    ev_file.write_text(json.dumps(ev, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    part = str(hkg["ic_device"].get("name") or name).upper()
    spec = spec_from_plan.build(ev, hkg, part, whole=True)
    spec["extraction"]["file"] = hkg_file.name
    spec["plan"]["file"] = ev_file.name
    spec_file = HERE / f"spec_{name}.json"
    spec_file.write_text(json.dumps(spec, ensure_ascii=False, indent=1), encoding="utf-8")
    sentence = spec_from_hkg.model_input(spec)
    (HERE / "data" / "train" / f"{name}.json").write_text(json.dumps(sentence, ensure_ascii=False, indent=1),
                                                          encoding="utf-8")
    log(f"판정 항목 {len(spec['specs'])}개 -> {spec_file.name}")
    return spec_file


def main() -> None:
    pdf = Path(sys.argv[1])
    name = sys.argv[2] if len(sys.argv) > 2 else pdf.stem.lower()
    log = lambda m: print(m, flush=True)  # noqa: E731
    hkg_file = OUT_DIR / f"{name}_hkg.json"
    if "--reuse" in sys.argv and hkg_file.exists():
        log(f"추출 결과 다시 씀: {hkg_file}")
    else:
        hkg_file = extract(pdf, name, log=log)
    plan_specs(hkg_file, name, log=log)


if __name__ == "__main__":
    main()
