"""Tests unitaires hermétiques pour l'Harness Native v2 (Multi-step & Anti-boucle)."""

from unittest.mock import MagicMock

from harness_tools.harness.native_v2 import NativeHarnessV2, _compute_call_fingerprint
from harness_tools.models import Message, ToolCall
from harness_tools.tools.calculator import calculate
from harness_tools.tools.notes import clear_notes, create_note, search_notes
from harness_tools.tools.registry import ToolRegistry


def test_compute_call_fingerprint():
    fp1 = _compute_call_fingerprint("calculate", {"expression": "2 + 2"})
    fp2 = _compute_call_fingerprint("calculate", {"expression": "2 + 2"})
    fp3 = _compute_call_fingerprint("calculate", {"expression": "3 + 3"})

    assert fp1 == fp2
    assert fp1 != fp3


def test_multi_step_sequential_chaining():
    clear_notes()
    registry = ToolRegistry()
    registry.register(calculate)
    registry.register(create_note)

    mock_client = MagicMock()
    # Tour 1 : Calcul
    call1 = Message(
        role="assistant",
        tool_calls=[ToolCall(id="c1", name="calculate", arguments={"expression": "15 * 12"})],
    )
    # Tour 2 : Création de note avec le résultat du calcul
    call2 = Message(
        role="assistant",
        tool_calls=[ToolCall(id="c2", name="create_note", arguments={"title": "Budget", "content": "180"})],
    )
    # Tour 3 : Synthèse finale
    call3 = Message(
        role="assistant",
        content="J'ai calculé 180 et créé la note Budget avec succès.",
        tool_calls=[],
    )
    mock_client.chat.side_effect = [call1, call2, call3]

    harness = NativeHarnessV2(client=mock_client, registry=registry)
    result = harness.run("Calcule 15 * 12 puis crée la note Budget.")

    assert result.success is True
    assert "180" in result.final_answer
    assert len(result.steps) == 3
    assert result.steps[0].tool_calls[0].name == "calculate"
    assert result.steps[1].tool_calls[0].name == "create_note"
    assert result.steps[2].assistant_content != ""
    assert not result.loop_detected


def test_infinite_loop_detection_and_cutoff():
    registry = ToolRegistry()
    registry.register(search_notes)

    mock_client = MagicMock()
    # Le modèle répète exactement le même appel
    repeated_call = Message(
        role="assistant",
        tool_calls=[ToolCall(id="c_rep", name="search_notes", arguments={"query": "introuvable"})],
    )
    mock_client.chat.return_value = repeated_call

    harness = NativeHarnessV2(
        client=mock_client,
        registry=registry,
        max_steps=10,
        max_repeated_calls=2,
    )
    result = harness.run("Cherche la note introuvable.")

    assert result.success is False
    assert result.loop_detected is True
    assert "Boucle infinie détectée" in result.final_answer
    # L'arrêt se produit immédiatement au 3e appel répété, bien avant les 10 étapes max !
    assert len(result.steps) <= 3


def test_loop_warning_allows_recovery():
    registry = ToolRegistry()
    registry.register(search_notes)

    mock_client = MagicMock()
    # Appel 1
    call1 = Message(role="assistant", tool_calls=[ToolCall(id="c1", name="search_notes", arguments={"query": "test"})])
    # Appel 2 (répétition -> warning déclenché)
    call2 = Message(role="assistant", tool_calls=[ToolCall(id="c2", name="search_notes", arguments={"query": "test"})])
    # Appel 3 (le modèle comprend l'avertissement et formule sa conclusion)
    call3 = Message(role="assistant", content="Aucune note n'a été trouvée pour 'test'.", tool_calls=[])
    mock_client.chat.side_effect = [call1, call2, call3]

    harness = NativeHarnessV2(
        client=mock_client,
        registry=registry,
        max_steps=5,
        max_repeated_calls=2,
    )
    result = harness.run("Trouve test.")

    assert result.success is True
    assert result.loop_detected is False
    assert len(result.steps) == 3
    assert result.steps[1].loop_warning_triggered is True
