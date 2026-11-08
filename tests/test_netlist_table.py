"""netlist_table.py 시험: 블록으로 조립되는 구조를 표로 바꿨다가 되돌려도 연결이 같은지 본다."""

import netlist_table as nt
import topology


def assembled_netlists():
    library = topology.load_library()
    for selection, result in topology.all_structures():
        if not result["errors"]:
            yield selection, topology.netlist_text(selection, result["instances"], library)


def round_trip(netlist: str):
    table = nt.to_table(nt.parse_ngspice(netlist))
    sizes = {row["name"]: row["params"] for row in table["rows"]}
    again = nt.parse_table_text(nt.table_text(table))
    rebuilt = nt.to_ngspice(again, sizes)
    return table, nt.to_table(nt.parse_ngspice(rebuilt)), rebuilt


def test_all_assembled_structures_round_trip():
    count = 0
    for selection, netlist in assembled_netlists():
        table, back, _ = round_trip(netlist)
        assert nt.signature(table) == nt.signature(back), selection
        assert nt.table_text(table) == nt.table_text(back), selection
        count += 1
    assert count == 32


def test_sizes_survive_round_trip():
    _, netlist = next(assembled_netlists())
    original = nt.parse_ngspice(netlist)
    _, _, rebuilt = round_trip(netlist)
    back = nt.parse_ngspice(rebuilt)
    assert sorted(str(d["params"]) for d in original["devices"]) == sorted(str(d["params"]) for d in back["devices"])


def test_spectre_reader():
    text = """M9 (VOUT1 net17 net36 VDD) pmos4
M7 (net36 VIN1 VSS VSS) nmos4
M8 (net17 VIN2 VSS VSS) nmos4
M1 (net17 net17 VDD VDD) pmos4
C0 (net17 VOUT1) capacitor"""
    table = nt.to_table(nt.parse_spectre(text, ["VDD", "VSS", "VIN1", "VIN2", "VOUT1"]))
    assert table["ports"] == ["VDD", "VSS", "IN1", "IN2", "OUT"]
    assert [row["name"] for row in table["rows"]] == ["PM1", "PM2", "NM1", "NM2", "C1"]
    assert nt.parse_table_text(nt.table_text(table))["rows"][0]["pins"] == table["rows"][0]["pins"]


def test_spectre_reader_rejects_unsupported():
    import pytest
    with pytest.raises(nt.UnsupportedCircuit):
        nt.parse_spectre("I1 (a b CLK VDD VSS) TRANSMISSION_GATE", ["VDD", "VSS", "VIN1", "VIN2", "VOUT1"])
    with pytest.raises(nt.UnsupportedCircuit):
        nt.parse_spectre("M1 (VOUT1 VIN1 VSS VSS) nmos4", ["VDD", "VSS", "VIN1", "VIN2", "VOUT1", "VOUT2"])
