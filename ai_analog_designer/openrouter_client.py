"""Backwards-compatibility shim. The real implementation is provider-agnostic: see llm_client.py."""
from .llm_client import LLMClient, _load_env, repair_truncated_json  # noqa: F401

OpenRouterClient = LLMClient
