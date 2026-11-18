"""Offline coverage for timeout recovery in per-page HKG extraction."""

import pytest
from ai_analog_designer.pdf_to_graph.hardware_kg_builder import (
    HardwareKnowledgeGraphBuilder,
    HKGExtractionError,
)


def parsed_document():
    return {
        "source_file": "test-device.pdf",
        "pages": {
            1: {"text": "pin configuration", "layout_text": "pin configuration", "classes": ["pin_configuration"]},
            2: {"text": "electrical characteristics min typ max", "layout_text": "electrical characteristics min typ max", "classes": ["electrical"]},
        },
    }


class RecoveryLLM:
    def __init__(self):
        self.tags = []

    def complete_json(self, _prompt, **kwargs):
        tag = kwargs["tag"]
        self.tags.append((tag, kwargs.get("timeout_profile")))
        if tag == "hkg_pins":
            return {"ic_device": {"name": "TEST"}, "pins": [{"name": "IN", "pin_number": "1"}]}
        if tag.startswith("hkg_specs_retry"):
            return {"electrical_parameters": [{"symbol": "VOS", "typ": "1", "unit": "mV"}]}
        raise TimeoutError("primary provider timed out")


def test_timed_out_spec_page_retries_with_extraction_profile():
    llm = RecoveryLLM()
    builder = HardwareKnowledgeGraphBuilder(llm_client=llm, parallel_spec_calls=1)

    data = builder.extract_raw(parsed_document())

    assert [entry["symbol"] for entry in data["electrical_parameters"]] == ["VOS"]
    assert data["provenance"]["failed_spec_pages"] == []
    assert ("hkg_specs_p2", "extraction") in llm.tags
    assert ("hkg_specs_retry_p2", "extraction") in llm.tags


class ExhaustedLLM(RecoveryLLM):
    def complete_json(self, _prompt, **kwargs):
        tag = kwargs["tag"]
        self.tags.append((tag, kwargs.get("timeout_profile")))
        if tag == "hkg_pins":
            return {"ic_device": {"name": "TEST"}, "pins": []}
        raise TimeoutError("all provider routes timed out")


def test_zero_specification_pages_is_terminal_not_a_silent_empty_result():
    builder = HardwareKnowledgeGraphBuilder(llm_client=ExhaustedLLM(), parallel_spec_calls=1)

    with pytest.raises(HKGExtractionError, match="no usable rows"):
        builder.extract_raw(parsed_document())
