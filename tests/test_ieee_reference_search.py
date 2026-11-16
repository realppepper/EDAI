"""
Test suite for IEEE Academic Literature & Triple-Engine Searcher.
"""
from ai_analog_designer.hermes_core.web_reference_search import (
    WebCircuitReferenceSearcher,
)


def test_ieee_academic_search_live():
    searcher = WebCircuitReferenceSearcher()
    res = searcher.search_ieee_academic("operational amplifier two-stage Miller compensation differential pair", max_results=2)
    assert res["provider"] == "ieee_academic"
    assert res["ok"] is True
    assert len(res["papers"]) >= 1
    p = res["papers"][0]
    assert "title" in p
    assert "abstract" in p
    assert len(p["abstract"]) > 0


def test_spice_hints_filtering_rejects_ltspice_a_devices():
    searcher = WebCircuitReferenceSearcher()
    dirty_text = """
    Here is a model:
    .subckt FAKE_555 1 2 3
    A1 1 2 3 SCHMITT
    R1 1 2 1k
    .ends FAKE_555
    """
    hints = searcher._extract_spice_hints([dirty_text])
    assert len(hints) == 0  # Rejects A-device

    clean_text = """
    Here is a real transistor circuit:
    .subckt REAL_OPAMP INP INN OUT VCC VEE
    Q1 C1 INP E1 QNPN
    Q2 C2 INN E1 QNPN
    R1 VCC C1 10k
    .ends REAL_OPAMP
    """
    clean_hints = searcher._extract_spice_hints([clean_text])
    assert len(clean_hints) == 1
    assert "REAL_OPAMP" in clean_hints[0]
