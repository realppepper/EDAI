"""블록 찾기, 조립, 구조를 다시 정하는 루프를 확인한다. LLM 은 부르지 않고 정해 둔 답으로 대신한다.

실행 (WSL, 프로젝트 폴더에서):  ~/.venvs/edai/bin/python -m pytest tests/test_topology.py -q
마지막 시험은 ngspice 로 회로 두 개를 실제로 시뮬레이션하므로 30초쯤 걸린다.
"""
import json

import pytest

import llm_design
import llm_topology
import run_sim
import topology

RANGE = ["stage1", "input_range", "includes_0v"]
FOLDED_AB = [["stage1", "type", "folded_cascode"], RANGE, ["stage2", "type", "class_ab"], ["compensation", "type", "miller_rz"]]


def sizes(path) -> list:
    """회로 파일의 트랜지스터를 (소자 종류, 크기) 목록으로 만든다. 이름과 노드는 보지 않는다."""
    lines = [line.split() for line in path.read_text(encoding="utf-8").splitlines() if line.upper().startswith("XM")]
    return sorted(" ".join(tokens[5:]) for tokens in lines)


def test_retrieve_finds_block_by_properties() -> None:
    library = topology.load_library()
    found = topology.retrieve([["stage1", "gain", "high"], ["stage1", "input_range", "includes_0v"],
                               ["stage2", "source_current", "high"], ["stage2", "sink_current", "high"],
                               ["compensation", "zero", "cancelled"]], library)
    assert found["errors"] == []
    assert found["selection"] == {"stage1": "stage1_pmos_folded_cascode", "stage2": "stage2_class_ab",
                                  "compensation": "comp_miller_rz"}


def test_retrieve_reports_problems() -> None:
    library = topology.load_library()
    rest = [["stage2", "type", "none"], ["compensation", "type", "none"]]
    unknown = topology.retrieve([["stage1", "gain", "huge"]] + rest, library)
    assert any("모음에 없는" in error for error in unknown["errors"])
    ambiguous = topology.retrieve([["stage1", "gain", "high"]] + rest, library)
    assert any("여러 개" in error for error in ambiguous["errors"])


def test_retrieve_follows_requirements_when_pairs_conflict() -> None:
    """함께 가질 수 없는 쌍을 적으면 성능 요구(입력 범위) 쪽을 따르고, 어긋난 쌍을 알려 준다."""
    library = topology.load_library()
    found = topology.retrieve([["stage1", "type", "folded_cascode"], ["stage1", "input_pair", "NMOS"],
                               ["stage1", "input_range", "includes_0v"], ["stage2", "type", "none"],
                               ["compensation", "type", "none"]], library)
    assert found["errors"] == []
    assert found["selection"]["stage1"] == "stage1_pmos_folded_cascode"
    assert any("input_pair 는 nmos 가 아니라 pmos" in note for note in found["notes"])


def test_stages_must_match_drive_levels() -> None:
    """1단이 구동할 수 있는 게이트와 2단이 필요로 하는 게이트가 맞지 않으면 조립하지 않는다."""
    library = topology.load_library()
    for stage1, stage2, word in (("stage1_pmos_mirror_load", "stage2_class_ab", "PMOS 게이트"),
                                 ("stage1_pmos_mirror_load", "stage2_class_a_pmos", "PMOS 게이트"),
                                 ("stage1_nmos_mirror_load", "stage2_class_a", "NMOS 게이트")):
        result = topology.assemble({"stage1": stage1, "stage2": stage2, "compensation": "comp_miller_rz"}, library)
        assert any(word in error for error in result["errors"])
    matched = topology.assemble({"stage1": "stage1_nmos_mirror_load", "stage2": "stage2_class_a_pmos",
                                 "compensation": "comp_miller_rz"}, library)
    assert matched["errors"] == []


def test_every_buildable_structure_is_connected() -> None:
    """조립되는 구조에는 떠 있는 노드가 없어야 한다 (all_structures 가 연결 점검까지 한다)."""
    combos = topology.all_structures()
    buildable = [result for _, result in combos if not result["errors"]]
    assert len(combos) == 50 and len(buildable) == 32


def test_assembled_circuits_match_hand_made_ones(monkeypatch) -> None:
    monkeypatch.setattr(topology, "DESIGN_NAME", "opamp_test_gen")
    path = run_sim.HERE / "opamp_test_gen.cir"
    try:
        for types, original in ((("folded_cascode", "class_a", "miller_rz"), "opamp_a"),
                                (("folded_cascode", "class_ab", "miller_rz"), "opamp_b")):
            record = topology.build(topology.selection_from_types(*types))
            assert record["errors"] == []
            assert sizes(path) == sizes(run_sim.HERE / f"{original}.cir")
    finally:
        path.unlink(missing_ok=True)


def test_loop_fixes_errors_and_regenerates(monkeypatch, tmp_path) -> None:
    """1) 조립할 수 없는 구조 -> 고치게 함, 2) 미달인 구조 -> 결과를 돌려주고 다시 받음, 3) 통과."""
    answers = iter([
        {"analysis": "a", "strategy": "s", "triplets": [["stage1", "type", "five_transistor"], RANGE, ["stage2", "type", "class_ab"],
                                                        ["compensation", "type", "miller_rz"]]},
        {"analysis": "a", "strategy": "s", "triplets": [["stage1", "type", "five_transistor"], RANGE, ["stage2", "type", "class_a"],
                                                        ["compensation", "type", "miller_rz"]]},
        {"analysis": "a", "strategy": "s", "triplets": FOLDED_AB},
    ])
    prompts = []

    def fake_llm(messages: list) -> dict:
        prompts.append(messages[-1]["content"])
        return {"text": json.dumps(next(answers), ensure_ascii=False), "usage": {}}

    monkeypatch.setattr(llm_design, "ask_llm", fake_llm)
    monkeypatch.setattr(topology, "DESIGN_NAME", "opamp_test_gen")
    monkeypatch.setattr(llm_topology, "LOG_FILE", tmp_path / "topology_log.json")
    try:
        log = llm_topology.topology_loop()
    finally:
        (run_sim.HERE / "opamp_test_gen.cir").unlink(missing_ok=True)
        for leftover in run_sim.OUT_DIR.glob("opamp_test_gen*"):
            leftover.unlink()
    assert "만들 수 없습니다" in prompts[1]                 # 조립 오류를 돌려줌
    assert "미달" in prompts[2] and "이미 시도한" in prompts[2]   # 실제 성능을 돌려줌
    assert [r["passed"] for r in log["rounds"]] == [10, 15]
    assert log["final"] == 2 and log["best"] == 2
    assert len(log["rounds"][0]["attempts"]) == 2
