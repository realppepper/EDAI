"""
Integration & unit tests for the unified EDAI x AnalogVerifier platform:
  - jiyun: FLAN-T5/block topology exploration, GF180 gm/ID sizing, SVG schematic
  - seungcheol: SPICE sweep engine (including P0 WHEN vs FIND .meas fix), provenance review, base circuit generator
  - analogverifier: NetlistValidator guardrails, HermesAnalogTools (11 tools), ToolDecisionRouter, FastMCP server, Studio HTTP routes
"""
from __future__ import annotations

import base64
import json
import os
import threading
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

import pytest

from ai_analog_designer.circuit_synthesis.flan_t5_topology import (
    assemble_block_topology,
    generate_topology_candidates,
)
from ai_analog_designer.circuit_synthesis.gm_id_sizer import (
    auto_size,
    check_opamp_pdg,
    parse_table_text,
    rule_problems,
)
from ai_analog_designer.circuit_synthesis.netlist_validator import NetlistValidator
from ai_analog_designer.circuit_synthesis.schematic_svg import render_schematic_svg
from ai_analog_designer.hermes_core.base_circuit_generator import (
    generate_base_circuit,
    local_extract,
    validate_confirmation,
)
from ai_analog_designer.hermes_core.hermes_tools import HermesAnalogTools
from ai_analog_designer.hermes_core.tool_decision_router import ToolDecisionRouter
from ai_analog_designer.neuro_symbolic_verifier.spice_sweep_engine import (
    extract_meas_kinds,
    parse_measurements,
    validate_project,
)
from ai_analog_designer.web_studio.studio_server import StudioRequestHandler


def test_jiyun_block_assembly_and_gm_id_sizing_passes_netlist_validator():
    asm = assemble_block_topology("stage1_pmos_mirror_load", "stage2_class_a", "comp_miller_rz")
    assert asm["ok"] is True
    assert not asm["problems"]

    tbl = parse_table_text(asm["table"])
    assert not rule_problems(tbl)

    sized = auto_size(
        tbl,
        unit_current=20e-6,
        output_scale=5.0,
        simulator="analytical",
        subckt_name="LM358_TEST",
        pin_names=["INP", "INM", "OUT", "VCC", "GND"],
    )
    assert sized["ok"] is True
    assert ".subckt LM358_TEST INP INM OUT VCC GND" in sized["subckt_ltspice"]

    val = NetlistValidator().validate(
        sized["subckt_ltspice"],
        expected_subckt_name="LM358_TEST",
        expected_pins=[{"name": p} for p in ("INP", "INM", "OUT", "VCC", "GND")],
    )
    assert val["is_valid"] is True, f"Validator failed: {val['errors']}"
    assert len(sized["sizes"]) >= 6
    assert "MPM1" in val["cleaned_netlist"]


def test_topology_candidates_and_pdg_5pin_check():
    pins = [
        {"name": "IN+", "role": "SIGNAL", "description": "Non-inverting input"},
        {"name": "IN-", "role": "SIGNAL", "description": "Inverting input"},
        {"name": "OUT", "role": "OUTPUT", "description": "Output"},
        {"name": "VCC", "role": "POWER", "description": "Positive supply"},
        {"name": "GND", "role": "GROUND", "description": "Ground"},
    ]
    pdg_fit = check_opamp_pdg(pins)
    assert pdg_fit["ok"] is True

    res = generate_topology_candidates(
        specifications=[{"symbol": "Aol", "min": 80, "unit": "dB"}],
        max_candidates=4,
        auto_size_preview=True,
        subckt_name="LM358B",
        pin_names=[p["name"] for p in pins],
    )
    assert res["ok"] is True
    assert res["valid_count"] >= 2
    assert any(c.get("sizing_preview", {}).get("ok") for c in res["candidates"])


def test_schematic_svg_renders_from_table_and_spice():
    cands = generate_topology_candidates(max_candidates=1)["candidates"]
    svg_tbl = render_schematic_svg(structure_table=cands[0]["table"], title="Test OpAmp")
    assert svg_tbl["ok"] is True
    assert "<svg" in svg_tbl["svg"] and "</svg>" in svg_tbl["svg"]

    net = ".subckt CS IN OUT VDD GND\nM1 OUT IN GND GND GNM W=20u L=2u\nR1 VDD OUT 10k\n.ends CS\n"
    svg_net = render_schematic_svg(netlist=net, title="CS Amp")
    assert svg_net["ok"] is True
    assert svg_net["device_count"] == 2
    assert "<svg" in svg_net["svg"]


def test_p0_when_vs_find_measurement_parsing():
    netlist = """* P0 WHEN vs FIND test
.param RD=10k
V1 in 0 1
R1 in out {RD}
.tran 1n 5u
.meas TRAN settling_time WHEN V(VOUT)=0.098 CROSS=1
.meas TRAN v_at_time FIND V(VOUT) AT=99
.meas TRAN power_mw PARAM='0.4'
.meas TRAN bad_ac FIND V(VOUT) AT=10
.meas TRAN failed_m MAX V(VOUT)
.end
"""
    kinds = extract_meas_kinds(netlist)
    assert kinds["settling_time"] == "when"
    assert kinds["v_at_time"] == "find"

    log = (
        "settling_time: V(VOUT)=0.098 AT 1.00010459867e-06\n"
        "v_at_time: V(VOUT)=2.45 AT 99\n"
        "power_mw: -5*iavg*1000=0.4\n"
        "bad_ac: (20.1dB, -45.2deg)\n"
        "Measurement \"failed_m\" FAIL'ed\n"
    )
    parsed = parse_measurements(
        log,
        ["settling_time", "v_at_time", "power_mw", "bad_ac", "failed_m"],
        netlist_source=netlist,
    )
    assert parsed["settling_time"] == pytest.approx(1.00010459867e-06)
    assert parsed["v_at_time"] == pytest.approx(2.45)
    assert parsed["power_mw"] == pytest.approx(0.4)
    assert "bad_ac" not in parsed
    assert "failed_m" not in parsed

    # Also verify standalone log auto-detection without netlist_source
    auto_parsed = parse_measurements("settling_time: V(VOUT)=0.098 AT 1.00010459867e-06\n", ["settling_time"])
    assert auto_parsed["settling_time"] == pytest.approx(1.00010459867e-06)


def test_base_circuit_generator_and_review_snapshot():
    cir_sample = (
        "Common Source Amp\n"
        ".param RD=10000\n"
        "VDD vdd 0 5\n"
        "VIN in 0 SIN(1.1 0.005 1000)\n"
        "RDR vdd out {RD}\n"
        "M1 out in 0 0 NDEMO W=20u L=2u\n"
        ".model NDEMO NMOS (LEVEL=1 VTO=0.7 KP=100u)\n"
        ".tran 2u 8m 4m 2u\n"
        ".meas tran gain PP V(out)\n"
        ".end\n"
    )
    settings_sample = {
        "title": "CS",
        "parameters": [{"name": "RD", "min": 5000, "max": 20000, "initial": 10000, "step": 2500}],
        "goals": [{"measure": "gain", "op": ">=", "value": 0.1, "unit": "V"}],
        "objective": {"measure": "gain", "sense": "max"},
        "method": "feedback",
        "max_runs": 10,
        "timeout_s": 20,
    }
    mock_payload = json.dumps({
        "summary": "Generated CS stage",
        "evidence": ["User brief"],
        "assumptions": ["Level-1 generic NMOS"],
        "netlist": cir_sample,
        "settings": settings_sample,
        "warnings": [],
    })

    class FakeLLM:
        default_model = "fake-model"
        def chat_completion(self, **_kwargs):
            return mock_payload

    b64_txt = base64.b64encode(b"Target gain >= 0.1 V").decode()
    rev = local_extract([{"name": "brief.txt", "base64": b64_txt}])
    snap = validate_confirmation(
        {"confirmed": True, "goals": "Gain >= 0.1V", "fields": [{"name": "gain", "value": "0.1"}]},
        rev,
    )
    assert snap["user_confirmed"] is True

    out = generate_base_circuit("Design a common source amplifier", simulator="ltspice", llm_client=FakeLLM())
    assert out["verified_by_spice"] is False
    assert out["guardrail_validation"]["is_valid"] is True


def test_hermes_tools_and_router_expanded_actions(tmp_path):
    with patch.dict(os.environ, {"IEEE_API_KEY": "dummy-test-key"}):
        tools = HermesAnalogTools(
            output_dir=str(tmp_path),
            dut_name="LM358_TEST",
            pins=[{"name": "INP"}, {"name": "INM"}, {"name": "OUT"}, {"name": "VCC"}, {"name": "GND"}],
            specifications=[{"symbol": "Aol", "min": 80, "unit": "dB"}],
            pdg_schedule={"VCC": 0.0, "OUT": 5e-6},
        )
        names = {s["function"]["name"] for s in tools.get_tool_schemas()}
        assert {
            "generate_topology_candidates",
            "auto_size_gm_id",
            "generate_base_circuit",
            "sweep_parameters_grid",
        } <= names

        cands = tools.dispatch("generate_topology_candidates", {"max_candidates": 2})
        assert cands["ok"] is True and cands["valid_count"] >= 1

        sized = tools.dispatch("auto_size_gm_id", {"structure_table": cands["candidates"][0]["table"], "output_scale": 5.0})
        assert sized["ok"] is True
        assert sized["validator"]["is_valid"] is True

    router = ToolDecisionRouter(dut_name="LM358_TEST")
    assert "auto_size_gm_id" in router.SUPPORTED_TOOLS
    assert "sweep_parameters_grid" in router.SUPPORTED_TOOLS
    with patch.dict(os.environ, {"ANALOG_DISABLE_LLM_PLANNER": "1"}):
        d = router.evaluate_state(turn_idx=2, pass_rate=50.0, has_netlist=False, syntax_valid=True, history_tool_names=[])
        assert d["selected_tool"] == "synthesize_circuit_netlist"


def test_mcp_server_registers_unified_tools():
    from ai_analog_designer import mcp_server

    tool_names = set(mcp_server.mcp._tool_manager._tools.keys())
    assert {
        "search_ieee_papers",
        "extract_hkg_pdg",
        "tool_generate_topology_candidates",
        "tool_auto_size_gm_id",
        "tool_validate_netlist_syntax",
        "tool_sweep_parameters_grid",
        "tool_render_schematic_svg",
    } <= tool_names


def test_unified_web_studio_routes():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), StudioRequestHandler)
    port = srv.server_address[1]
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    base = f"http://127.0.0.1:{port}"
    try:
        with urllib.request.urlopen(f"{base}/", timeout=5) as r:
            html = r.read().decode("utf-8")
            assert "EDAI" in html and "gm/ID" in html

        with urllib.request.urlopen(f"{base}/classic", timeout=5) as r:
            classic = r.read().decode("utf-8")
            assert "Interactive Analog Circuit Design Studio" in classic

        with urllib.request.urlopen(f"{base}/api/edai/status", timeout=5) as r:
            st = json.loads(r.read().decode("utf-8"))
            assert "simulator" in st and "ieee_mcp_ready" in st

        req = urllib.request.Request(
            f"{base}/api/topology/candidates",
            data=json.dumps({"max_candidates": 2}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=5) as r:
            cands = json.loads(r.read().decode("utf-8"))
            assert cands["ok"] is True and cands["valid_count"] >= 1
            tbl = cands["candidates"][0]["table"]

        req2 = urllib.request.Request(
            f"{base}/api/topology/auto_size",
            data=json.dumps({"structure_table": tbl, "output_scale": 5}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req2, timeout=5) as r:
            sized = json.loads(r.read().decode("utf-8"))
            assert sized["ok"] is True
            assert "<svg" in sized["schematic_svg"]
    finally:
        srv.shutdown()
        srv.server_close()
