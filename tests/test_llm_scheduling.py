"""Offline checks for the task-aware LLM scheduler."""
import pytest
from ai_analog_designer.llm_client import LLMClient


@pytest.fixture(autouse=True)
def clean_scheduler_environment(monkeypatch):
    for name in (
        "LLM_PROVIDER", "LLM_MODEL", "LLM_FALLBACK_MODELS", "LLM_FAST_MODEL",
        "LLM_CAPABLE_MODEL", "LLM_FRONTIER_MODEL", "LLM_EXTRACT_MODEL",
        "LLM_HERMES_MODEL", "LLM_SYNTH_MODEL", "LLM_TB_MODEL", "LLM_SCHEDULER",
        "LLM_HERMES_ESCALATE_AFTER",
    ):
        monkeypatch.delenv(name, raising=False)


def nim_client():
    return LLMClient(provider="nim", api_key="test-key")


def test_structured_page_extraction_starts_fast_and_reserves_frontier_for_recovery():
    client = nim_client()

    assert client.model_chain_for("hkg_specs_p4") == [
        "nvidia/nemotron-3.5-bolt-e4b",
        "nvidia/nemotron-3.5-lightning-30b-a3b",
    ]
    assert client.model_chain_for("hkg_specs_retry_p4") == [
        "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning",
    ]


def test_extraction_timeout_profile_is_longer_without_relaxing_normal_turns():
    client = nim_client()
    fast = client.model_tiers["fast"]

    assert client._timeouts_for_model(fast) == (35.0, 12.0)
    assert client._timeouts_for_model(fast, "extraction") == (45.0, 15.0)


def test_pin_extraction_can_escalate_but_does_not_start_on_frontier():
    client = nim_client()

    assert client.model_chain_for("hkg_pins") == [
        "nvidia/nemotron-3.5-lightning-30b-a3b",
        "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning",
        "nvidia/nemotron-3.5-bolt-e4b",
    ]


def test_hermes_uses_frontier_only_after_configured_repair_turn():
    client = nim_client()

    assert client.model_chain_for("hermes_turn_1") == [
        "nvidia/nemotron-3.5-lightning-30b-a3b",
        "nvidia/nemotron-3.5-bolt-e4b",
        "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning",
    ]
    assert client.model_chain_for("hermes_turn_3")[0] == "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning"


def test_hermes_does_not_turn_the_client_default_into_an_explicit_override(tmp_path):
    from ai_analog_designer.hermes_core import HermesAgent, HermesAnalogTools

    client = nim_client()
    tools = HermesAnalogTools(
        output_dir=str(tmp_path),
        dut_name="ROUTING_TEST",
        pins=[],
        specifications=[],
        pdg_schedule={},
    )
    agent = HermesAgent(workspace_dir=str(tmp_path / "hermes"), tools=tools, llm_client=client)

    assert agent.model is None
    assert client.model_chain_for("hermes_turn_2") == [
        "nvidia/nemotron-3.5-lightning-30b-a3b",
        "nvidia/nemotron-3.5-bolt-e4b",
        "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning",
    ]


def test_task_override_beats_automatic_routing(monkeypatch):
    monkeypatch.setenv("LLM_EXTRACT_MODEL", "vendor/custom-extractor")
    client = nim_client()

    assert client.model_chain_for("hkg_specs_p1") == ["vendor/custom-extractor"]


def test_legacy_mode_retains_original_frontier_first_chain(monkeypatch):
    monkeypatch.setenv("LLM_SCHEDULER", "legacy")
    client = nim_client()

    assert client.model_chain_for("hkg_specs_p1") == [
        "nvidia/nemotron-3.5-lightning-30b-a3b",
        "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning",
        "poolside/laguna-xs-2.1",
    ]


def test_invalid_json_escalates_to_next_scheduled_model(monkeypatch):
    client = nim_client()
    invoked = []

    def fake_complete(*_args, **kwargs):
        model = kwargs["model"]
        invoked.append(model)
        return "not-json" if len(invoked) == 1 else '{"ok": true}'

    monkeypatch.setattr(client, "complete", fake_complete)

    assert client.complete_json("extract", tag="hkg_specs_p1") == {"ok": True}
    assert invoked == ["nvidia/nemotron-3.5-bolt-e4b", "nvidia/nemotron-3.5-lightning-30b-a3b"]


def test_transport_failure_escalates_to_next_scheduled_model(monkeypatch):
    client = nim_client()
    invoked = []

    def fake_complete(*_args, **kwargs):
        model = kwargs["model"]
        invoked.append(model)
        if len(invoked) == 1:
            raise RuntimeError("fast model timed out")
        return '{"ok": true}'

    monkeypatch.setattr(client, "complete", fake_complete)

    assert client.complete_json("extract", tag="hkg_specs_p1") == {"ok": True}
    assert invoked == ["nvidia/nemotron-3.5-bolt-e4b", "nvidia/nemotron-3.5-lightning-30b-a3b"]


def test_harness2_uses_the_application_provider_instead_of_forcing_openrouter(tmp_path):
    from ai_analog_designer.circuit_synthesis.harness2.harness2_architect import (
        Harness2CircuitArchitect,
    )

    client = nim_client()
    architect = Harness2CircuitArchitect(llm_client=client, library_root=str(tmp_path / "library"))

    assert architect.proposer.improver_provider == "nim"
    assert architect.proposer.synthesizer_provider == "nim"
    assert architect.proposer.get_improver_client() is client
    assert architect.proposer.get_synthesizer_client() is client
