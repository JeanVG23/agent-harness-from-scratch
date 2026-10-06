"""Tests unitaires hermétiques pour l'Harness Native Tool Calling v1."""

from unittest.mock import MagicMock

from harness_tools.harness.native_v1 import NativeHarnessV1
from harness_tools.models import Message, ToolCall
from harness_tools.tools.calculator import calculate
from harness_tools.tools.registry import ToolRegistry


def test_native_harness_direct_answer():
    registry = ToolRegistry()
    mock_client = MagicMock()
    mock_client.chat.return_value = Message(
        role="assistant",
        content="Bonjour ! Je suis prêt à vous aider.",
        tool_calls=[],
    )

    harness = NativeHarnessV1(client=mock_client, registry=registry)
    result = harness.run("Bonjour")

    assert result.success is True
    assert result.final_answer == "Bonjour ! Je suis prêt à vous aider."
    assert len(result.steps) == 1
    assert result.steps[0].tool_calls == []


def test_native_harness_tool_call_flow():
    registry = ToolRegistry()
    registry.register(calculate)

    mock_client = MagicMock()
    # Tour 1 : le modèle demande un appel d'outil structuré
    msg_call = Message(
        role="assistant",
        content="",
        tool_calls=[
            ToolCall(
                id="call_abc123",
                name="calculate",
                arguments={"expression": "14 * 25"},
            )
        ],
    )
    # Tour 2 : après réception du rôle 'tool', le modèle formule sa conclusion
    msg_final = Message(
        role="assistant",
        content="14 fois 25 font 350.",
        tool_calls=[],
    )
    mock_client.chat.side_effect = [msg_call, msg_final]

    harness = NativeHarnessV1(client=mock_client, registry=registry)
    result = harness.run("Combien font 14 * 25 ?")

    assert result.success is True
    assert result.final_answer == "14 fois 25 font 350."
    assert len(result.steps) == 2
    assert len(result.steps[0].tool_calls) == 1
    assert result.steps[0].tool_calls[0].name == "calculate"
    assert result.steps[0].tool_results[0].output == "350"
    assert result.steps[1].tool_calls == []


def test_native_harness_max_steps_exceeded():
    registry = ToolRegistry()
    registry.register(calculate)

    mock_client = MagicMock()
    # Le modèle boucle sans jamais produire de réponse textuelle finale
    infinite_tool_call = Message(
        role="assistant",
        content="",
        tool_calls=[ToolCall(id="c1", name="calculate", arguments={"expression": "1 + 1"})],
    )
    mock_client.chat.return_value = infinite_tool_call

    harness = NativeHarnessV1(client=mock_client, registry=registry)
    result = harness.run("Boucle infinie", max_steps=3)

    assert result.success is False
    assert "Limite de 3 étapes atteinte" in result.error
    assert len(result.steps) == 3
