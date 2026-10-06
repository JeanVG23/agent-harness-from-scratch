"""Tests unitaires hermétiques pour le Runtime Agentique Native v3 (Robustesse & Coercion)."""

from unittest.mock import MagicMock

from harness_tools.harness.native_v3 import NativeHarnessV3, format_didactic_error
from harness_tools.models import Message, ToolCall, ToolResult
from harness_tools.tools.calculator import calculate
from harness_tools.tools.clock import calculate_date_offset
from harness_tools.tools.notes import read_note
from harness_tools.tools.registry import ToolRegistry, function_to_tool_def


def test_format_didactic_error_enriches_output():
    tool_def = function_to_tool_def(calculate_date_offset)
    err_res = ToolResult(
        tool_call_id="c1",
        name="calculate_date_offset",
        output="Chaîne 'cinq' non convertible en entier",
        is_error=True,
    )

    augmented = format_didactic_error(tool_def, err_res)

    assert "❌ [Échec d'exécution de l'outil 'calculate_date_offset']" in augmented
    assert "Diagnostic : Chaîne 'cinq' non convertible en entier" in augmented
    assert "Schéma attendu pour 'calculate_date_offset' :" in augmented
    assert "days (integer, obligatoire)" in augmented
    assert "Conseil d'auto-correction :" in augmented


def test_format_didactic_error_ignores_success():
    tool_def = function_to_tool_def(calculate_date_offset)
    ok_res = ToolResult(
        tool_call_id="c1",
        name="calculate_date_offset",
        output="Samedi 10/10/2026",
        is_error=False,
    )

    out = format_didactic_error(tool_def, ok_res)
    assert out == "Samedi 10/10/2026"


def test_v3_coercion_saves_string_to_int_failure():
    """Vérifie que la coercion déterministe résout l'erreur de type 'days=\"5\"' et incrémente les statistiques."""
    registry = ToolRegistry(enable_coercion=True)
    registry.register(calculate_date_offset)

    mock_client = MagicMock()
    # Tour 1 : Le LLM envoie "5" (string) au lieu de 5 (int)
    call1 = Message(
        role="assistant",
        tool_calls=[ToolCall(id="c1", name="calculate_date_offset", arguments={"days": "5"})],
    )
    # Tour 2 : Synthèse finale
    call2 = Message(
        role="assistant",
        content="Dans 5 jours, nous serons le Vendredi 10/10/2026.",
        tool_calls=[],
    )
    mock_client.chat.side_effect = [call1, call2]

    harness = NativeHarnessV3(client=mock_client, registry=registry)
    result = harness.run("Quelle est la date dans 5 jours ?")

    assert result.success is True
    assert result.total_coercions == 1
    assert result.total_errors_encountered == 0
    assert result.self_corrections_count == 0
    assert len(result.steps) == 2

    step1 = result.steps[0]
    assert len(step1.coercions) == 1
    assert step1.coercions[0].parameter == "days"
    assert step1.coercions[0].original_value == "5"
    assert step1.coercions[0].coerced_value == 5
    assert not step1.tool_results[0].is_error


def test_v3_drops_unexpected_parameters_cleanly():
    """Vérifie qu'un paramètre halluciné par le LLM est retiré déterministement avec traçabilité."""
    registry = ToolRegistry(enable_coercion=True)
    registry.register(calculate)

    mock_client = MagicMock()
    call1 = Message(
        role="assistant",
        tool_calls=[
            ToolCall(
                id="c1",
                name="calculate",
                arguments={"expression": "100 / 4", "comment": "calcul du quart"},
            )
        ],
    )
    call2 = Message(
        role="assistant",
        content="Le résultat est 25.",
        tool_calls=[],
    )
    mock_client.chat.side_effect = [call1, call2]

    harness = NativeHarnessV3(client=mock_client, registry=registry)
    result = harness.run("Divise 100 par 4.")

    assert result.success is True
    assert result.total_coercions == 1
    step1 = result.steps[0]
    assert step1.coercions[0].parameter == "comment"
    assert step1.coercions[0].action == "drop_unexpected"
    assert not step1.tool_results[0].is_error
    assert "25" in step1.tool_results[0].output


def test_v3_validation_error_allows_agentic_recovery_and_metrics():
    """Vérifie qu'une erreur non convertible déterministement renvoie un message didactique et incrémente self_corrections."""
    registry = ToolRegistry(enable_coercion=True)
    registry.register(calculate_date_offset)

    mock_client = MagicMock()
    # Tour 1 : Valeur 'demain' impossible à convertir en entier déterministement
    call1 = Message(
        role="assistant",
        tool_calls=[ToolCall(id="c1", name="calculate_date_offset", arguments={"days": "demain"})],
    )
    # Tour 2 : Le LLM lit l'erreur didactique de validation et corrige avec days=1
    call2 = Message(
        role="assistant",
        tool_calls=[ToolCall(id="c2", name="calculate_date_offset", arguments={"days": 1})],
    )
    # Tour 3 : Synthèse finale
    call3 = Message(
        role="assistant",
        content="Demain sera le Samedi 06/10/2026.",
        tool_calls=[],
    )
    mock_client.chat.side_effect = [call1, call2, call3]

    harness = NativeHarnessV3(client=mock_client, registry=registry)
    result = harness.run("Quelle date sera-t-on demain ?")

    assert result.success is True
    assert len(result.steps) == 3
    assert result.total_errors_encountered == 1
    assert result.self_corrections_count == 1

    # Étape 1 : Erreur de validation didactique
    step1 = result.steps[0]
    assert step1.tool_results[0].is_error is True
    assert not step1.recovered_from_error

    # Étape 2 : Récupération réussie
    step2 = result.steps[1]
    assert step2.tool_results[0].is_error is False
    assert step2.recovered_from_error is True

    assert "Demain sera" in result.final_answer


def test_v3_recovery_via_graceful_final_answer():
    """Vérifie qu'un modèle qui explique poliment l'erreur de l'outil sans relancer est compté comme une récupération."""
    registry = ToolRegistry(enable_coercion=True)
    registry.register(read_note)

    mock_client = MagicMock()
    # Tour 1 : Demande une note inexistante
    call1 = Message(
        role="assistant",
        tool_calls=[ToolCall(id="c1", name="read_note", arguments={"title": "Inconnue"})],
    )
    # Tour 2 : Le LLM constate que la note n'existe pas et l'explique à l'utilisateur
    call2 = Message(
        role="assistant",
        content="Désolé, la note 'Inconnue' n'existe pas dans votre carnet de notes.",
        tool_calls=[],
    )
    mock_client.chat.side_effect = [call1, call2]

    harness = NativeHarnessV3(client=mock_client, registry=registry)
    result = harness.run("Lis la note Inconnue.")

    assert result.success is True
    assert result.total_errors_encountered == 1
    assert result.self_corrections_count == 1
    assert len(result.steps) == 2
    assert result.steps[1].recovered_from_error is True


def test_v3_disable_didactic_feedback():
    """Vérifie que l'option enable_didactic_feedback=False transmet l'output brut."""
    registry = ToolRegistry(enable_coercion=True)
    registry.register(calculate_date_offset)

    mock_client = MagicMock()
    call1 = Message(
        role="assistant",
        tool_calls=[ToolCall(id="c1", name="calculate_date_offset", arguments={"days": "invalide"})],
    )
    mock_client.chat.return_value = call1

    harness = NativeHarnessV3(
        client=mock_client,
        registry=registry,
        enable_didactic_feedback=False,
        max_steps=1,
    )
    harness.run("Test")

    # On vérifie le message injecté dans l'historique
    last_chat_call_args = mock_client.chat.call_args[0]
    sent_messages = last_chat_call_args[0]
    # Le message tool injecté ne doit pas avoir le format enrichi ❌ [Échec
    tool_msg = next(m for m in sent_messages if m.role == "tool")
    assert "❌ [Échec d'exécution" not in tool_msg.content
    assert "Conseil d'auto-correction" not in tool_msg.content
