"""
동작한 후보를 저장된 회로로 다시 시뮬레이션해 파형을 남긴다 (화면에 그래프를 그리기 위해).
select_structure.py 는 측정값만 남기고 파형은 버리기 때문에 따로 돈다. 크기 정하기는 다시 하지 않는다.

남기는 파형: 개방루프 주파수 응답(이득·위상), 슬루율 계단 응답, 정착시간 계단 응답
결과: data/selection_<부품>_curves.json  {후보 번호(0부터): {파형 이름: [값...]}}
이미 있는 후보는 건너뛰므로, 선택이 진행 중일 때 돌리고 끝난 뒤 다시 돌려도 된다.

사용법 (WSL, 프로젝트 폴더에서):
    ~/.venvs/edai/bin/python selection_curves.py lm358      (부품을 빼면 tlv271)
"""

import json
import sys

import numpy as np

import run_sim

DEFAULT_PART = "tlv271"
DESIGN_NAME = "opamp_curves"      # select_structure 가 쓰는 임시 이름과 겹치지 않게
CURVES = ("freq", "mag_db", "phase", "slew_t", "slew_out", "settle_t", "settle_out")


def thin(values) -> list:
    step = max(1, len(values) // run_sim.CURVE_MAX_POINTS)
    return [round(float(v), 6) for v in np.real(values)[::step]]


def curves_of(subckt: str) -> dict:
    path = run_sim.HERE / f"{DESIGN_NAME}.cir"
    path.write_text("* selection_curves.py 가 만든 임시 회로\n" + subckt, encoding="utf-8")
    try:
        result = run_sim.evaluate(DESIGN_NAME)
    finally:
        path.unlink(missing_ok=True)
        for leftover in run_sim.OUT_DIR.glob(f"{DESIGN_NAME}*"):
            leftover.unlink()
    return {key: thin(result[key]) for key in CURVES if result.get(key) is not None}


def main() -> None:
    part = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_PART
    selection = json.loads((run_sim.HERE / "data" / f"selection_{part}.json").read_text(encoding="utf-8"))
    out_file = run_sim.HERE / "data" / f"selection_{part}_curves.json"
    saved = json.loads(out_file.read_text(encoding="utf-8")) if out_file.exists() else {}
    for index, entry in enumerate(selection["entries"]):
        if not entry.get("best") or str(index) in saved:
            continue
        variant = next(v for v in entry["variants"] if v["output_scale"] == entry["best"]["output_scale"])
        try:
            saved[str(index)] = curves_of(variant["subckt"])
            print(f"  후보 {index + 1}: 파형 저장", flush=True)
        except RuntimeError as error:
            print(f"  후보 {index + 1}: 시뮬레이션 실패 {error}", flush=True)
        out_file.write_text(json.dumps(saved), encoding="utf-8")
    print(f"파형 {len(saved)}개 -> {out_file.name}")


if __name__ == "__main__":
    main()
