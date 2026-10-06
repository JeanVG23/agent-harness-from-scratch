"""Tests unitaires pour les adaptateurs de frameworks tiers (Smolagents & Pydantic-AI)."""

from __future__ import annotations

import pytest

# Les frameworks tiers sont des dépendances optionnelles (extra `frameworks`).
pytest.importorskip("smolagents")
pytest.importorskip("pydantic_ai")

from harness_tools.frameworks.pydantic_ai_adapter import PydanticAIAdapter
from harness_tools.frameworks.smolagents_adapter import SmolagentsAdapter


def test_smolagents_adapter_initialization():
    """Vérifie l'instanciation de l'adaptateur Smolagents."""
    adapter = SmolagentsAdapter(model_id="qwen2.5:3b")
    assert adapter.model_id == "qwen2.5:3b"
    assert adapter.max_steps == 8


def test_pydantic_ai_adapter_initialization():
    """Vérifie l'instanciation de l'adaptateur Pydantic-AI."""
    adapter = PydanticAIAdapter(model_name="qwen2.5:3b")
    assert adapter.model_name == "qwen2.5:3b"
    assert adapter.base_url == "http://localhost:11434/v1"


def test_smolagents_tool_tracking():
    """Vérifie que les outils enveloppés enregistrent fidèlement les invocations."""
    adapter = SmolagentsAdapter()
    calls: list[str] = []
    tools = adapter._build_tracked_tools(calls)
    assert len(tools) == 11

    # Trouver l'outil calculate et l'exécuter
    calc_tool = next(t for t in tools if t.name == "calculate")
    res = calc_tool(expression="10 + 5")
    assert "15" in str(res)
    assert calls == ["calculate"]


def test_pydantic_ai_tool_tracking():
    """Vérifie que les outils enveloppés Pydantic-AI enregistrent fidèlement les invocations."""
    adapter = PydanticAIAdapter()
    calls: list[str] = []
    agent = adapter._build_agent_with_tracking(calls)
    tools_dict = agent._function_toolset.tools
    assert len(tools_dict) == 11
    assert "create_note" in tools_dict


def test_smolagents_temperature_defaults_to_zero_and_reaches_the_request():
    """La température doit être alignée sur le harness (0.0) et partir dans la requête."""
    adapter = SmolagentsAdapter()
    assert adapter.temperature == 0.0
    kwargs = adapter.model._prepare_completion_kwargs(
        messages=[{"role": "user", "content": [{"type": "text", "text": "salut"}]}]
    )
    assert kwargs["temperature"] == 0.0


def test_smolagents_temperature_is_configurable():
    adapter = SmolagentsAdapter(temperature=0.7)
    kwargs = adapter.model._prepare_completion_kwargs(
        messages=[{"role": "user", "content": [{"type": "text", "text": "salut"}]}]
    )
    assert kwargs["temperature"] == 0.7


def test_pydantic_ai_temperature_defaults_to_zero_and_is_a_model_setting():
    adapter = PydanticAIAdapter()
    assert adapter.temperature == 0.0
    assert adapter.model.settings["temperature"] == 0.0


def test_pydantic_ai_temperature_is_configurable():
    adapter = PydanticAIAdapter(temperature=0.7)
    assert adapter.model.settings["temperature"] == 0.7
