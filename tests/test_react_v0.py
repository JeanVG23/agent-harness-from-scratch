"""Tests unitaires hermétiques pour l'Harness ReAct v0."""

from unittest.mock import MagicMock
import pytest

from harness_tools.harness.react_v0 import (
    ReActHarnessV0,
    _build_system_prompt,
    _parse_react_response,
)
from harness_tools.models import Message
from harness_tools.tools.calculator import calculate
from harness_tools.tools.registry import ToolRegistry


def test_parse_react_action():
    text = (
        "Thought: Je dois calculer 14 * 25.\n"
        "Action: calculate\n"
        "Action Input: {\"expression\": \"14 * 25\"}\n"
    )
    thought, action, action_input, final_answer = _parse_react_response(text)

    assert thought == "Je dois calculer 14 * 25."
    assert action == "calculate"
    assert action_input == {"expression": "14 * 25"}
    assert final_answer is None


def test_parse_react_final_answer():
    text = (
        "Thought: J'ai fini mon calcul.\n"
        "Final Answer: Le résultat de 14 * 25 est 350."
    )
    thought, action, action_input, final_answer = _parse_react_response(text)

    assert action is None
    assert action_input is None
    assert final_answer == "Le résultat de 14 * 25 est 350."


def test_parse_react_truncates_hallucinated_observation():
    text = (
        "Thought: Je calcule.\n"
        "Action: calculate\n"
        "Action Input: {\"expression\": \"2 + 2\"}\n"
        "Observation: 4\n"
        "Thought: Je sais que c'est 4.\n"
        "Final Answer: C'est 4."
    )
    thought, action, action_input, final_answer = _parse_react_response(text)

    # L'observation hallucinée par le modèle a été coupée avant Final Answer
    assert action == "calculate"
    assert action_input == {"expression": "2 + 2"}
    assert final_answer is None


def test_react_harness_end_to_end_mock():
    registry = ToolRegistry()
    registry.register(calculate)

    mock_client = MagicMock()
    # Étape 1 : Le modèle demande une action
    msg_step1 = Message(
        role="assistant",
        content=(
            "Thought: Je dois évaluer l'expression arithmétique.\n"
            "Action: calculate\n"
            "Action Input: {\"expression\": \"14 * 25\"}"
        ),
    )
    # Étape 2 : Le modèle analyse l'observation et formule la réponse finale
    msg_step2 = Message(
        role="assistant",
        content=(
            "Thought: La calculatrice m'a renvoyé 350.\n"
            "Final Answer: 14 fois 25 font 350."
        ),
    )
    mock_client.chat.side_effect = [msg_step1, msg_step2]

    harness = ReActHarnessV0(client=mock_client, registry=registry)
    result = harness.run("Combien font 14 * 25 ?")

    assert result.success is True
    assert result.final_answer == "14 fois 25 font 350."
    assert len(result.steps) == 2
    assert result.steps[0].action == "calculate"
    assert result.steps[0].observation == "350"
