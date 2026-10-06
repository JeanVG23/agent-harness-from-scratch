"""Tests unitaires pour le Harness v4 (Garde-fous, Criticité et Human-in-the-Loop)."""

from __future__ import annotations

from unittest.mock import MagicMock

from harness_tools.harness.native_v4 import (
    NativeHarnessV4,
    should_request_approval,
)
from harness_tools.llm.client import OllamaClient
from harness_tools.models import Message, ToolCall, ToolDef
from harness_tools.tools.registry import ToolRegistry


def test_should_request_approval_matrix():
    """Vérifie la matrice de décision de criticité."""
    # Politique 'all' : aucune confirmation requise
    assert not should_request_approval("read", "all")
    assert not should_request_approval("write", "all")
    assert not should_request_approval("destructive", "all")

    # Politique 'write' : seule 'destructive' requiert confirmation
    assert not should_request_approval("read", "write")
    assert not should_request_approval("write", "write")
    assert should_request_approval("destructive", "write")

    # Politique 'read' : 'write' et 'destructive' requièrent confirmation
    assert not should_request_approval("read", "read")
    assert should_request_approval("write", "read")
    assert should_request_approval("destructive", "read")


def test_v4_read_operation_no_approval_needed():
    """Une action en lecture s'exécute directement sans solliciter le validateur humain."""
    registry = ToolRegistry()
    registry.register(lambda: "2026-10-05", name="get_date", description="Donne la date", risk_level="read")

    client = MagicMock(spec=OllamaClient)
    client.chat.side_effect = [
        Message(
            role="assistant",
            content=None,
            tool_calls=(ToolCall(id="call_1", name="get_date", arguments={}),),
        ),
        Message(
            role="assistant",
            content="Aujourd'hui nous sommes le 2026-10-05.",
            tool_calls=(),
        ),
    ]

    confirmation_mock = MagicMock(return_value=True)
    harness = NativeHarnessV4(
        client=client,
        registry=registry,
        auto_approve="write",
        confirmation_handler=confirmation_mock,
    )

    result = harness.run("Quelle est la date ?")

    assert result.success
    assert confirmation_mock.call_count == 0
    assert result.approvals_requested == 0
    assert result.approvals_granted == 0
    assert result.approvals_rejected == 0
    assert "2026-10-05" in result.final_answer


def test_v4_destructive_operation_approved():
    """Une action destructive autorisée par l'humain s'exécute normalement."""
    deleted_items: list[str] = []

    def mock_delete(title: str) -> str:
        deleted_items.append(title)
        return f"Note '{title}' supprimée avec succès."

    registry = ToolRegistry()
    registry.register(mock_delete, name="delete_note", description="Supprime une note", risk_level="destructive")

    client = MagicMock(spec=OllamaClient)
    client.chat.side_effect = [
        Message(
            role="assistant",
            content=None,
            tool_calls=(ToolCall(id="call_del_1", name="delete_note", arguments={"title": "Projet X"}),),
        ),
        Message(
            role="assistant",
            content="La note 'Projet X' a bien été supprimée suite à votre accord.",
            tool_calls=(),
        ),
    ]

    confirmation_mock = MagicMock(return_value=True)
    harness = NativeHarnessV4(
        client=client,
        registry=registry,
        auto_approve="write",
        confirmation_handler=confirmation_mock,
    )

    result = harness.run("Supprime la note Projet X")

    assert result.success
    assert confirmation_mock.call_count == 1
    # Vérification des arguments passés au confirmation handler
    call_args = confirmation_mock.call_args[0]
    tc_arg: ToolCall = call_args[0]
    tool_arg: ToolDef = call_args[1]
    assert tc_arg.name == "delete_note"
    assert tc_arg.arguments == {"title": "Projet X"}
    assert tool_arg.risk_level == "destructive"

    # Vérification que l'effet de bord a bien eu lieu
    assert deleted_items == ["Projet X"]
    assert result.approvals_requested == 1
    assert result.approvals_granted == 1
    assert result.approvals_rejected == 0
    assert len(result.steps[0].approvals) == 1
    assert result.steps[0].approvals[0].approved is True


def test_v4_destructive_operation_rejected():
    """Une action destructive refusée par l'humain n'est JAMAIS exécutée et le LLM s'adapte."""
    deleted_items: list[str] = []

    def mock_delete(title: str) -> str:
        deleted_items.append(title)
        return f"Note '{title}' supprimée avec succès."

    registry = ToolRegistry()
    registry.register(mock_delete, name="delete_note", description="Supprime une note", risk_level="destructive")

    client = MagicMock(spec=OllamaClient)
    client.chat.side_effect = [
        Message(
            role="assistant",
            content=None,
            tool_calls=(ToolCall(id="call_del_2", name="delete_note", arguments={"title": "Projet Y"}),),
        ),
        Message(
            role="assistant",
            content="Très bien, vous avez refusé la suppression. La note Projet Y est conservée.",
            tool_calls=(),
        ),
    ]

    # L'utilisateur refuse expressément
    confirmation_mock = MagicMock(return_value=False)
    harness = NativeHarnessV4(
        client=client,
        registry=registry,
        auto_approve="write",
        confirmation_handler=confirmation_mock,
    )

    result = harness.run("Supprime la note Projet Y")

    assert result.success
    assert confirmation_mock.call_count == 1

    # GARANTIE ABSOLUE : L'outil n'a JAMAIS été appelé
    assert deleted_items == []
    assert result.approvals_requested == 1
    assert result.approvals_granted == 0
    assert result.approvals_rejected == 1

    # Vérification du message tool envoyé au LLM
    second_chat_call_messages = client.chat.call_args_list[1][0][0]
    tool_message = next(m for m in second_chat_call_messages if m.role == "tool")
    assert "refusée" in tool_message.content or "annulée" in tool_message.content
    assert result.steps[0].approvals[0].approved is False


def test_v4_auto_approve_read_policy():
    """Avec auto_approve='read', les outils 'write' requièrent aussi une confirmation."""
    notes_added: list[str] = []

    def mock_add(title: str) -> str:
        notes_added.append(title)
        return f"Note '{title}' créée."

    registry = ToolRegistry()
    registry.register(mock_add, name="create_note", description="Crée une note", risk_level="write")

    client = MagicMock(spec=OllamaClient)
    client.chat.side_effect = [
        Message(
            role="assistant",
            content=None,
            tool_calls=(ToolCall(id="call_create", name="create_note", arguments={"title": "Nouvelle"}),),
        ),
        Message(role="assistant", content="Note créée.", tool_calls=()),
    ]

    confirmation_mock = MagicMock(return_value=True)
    harness = NativeHarnessV4(
        client=client,
        registry=registry,
        auto_approve="read",  # Politique stricte : même l'écriture requiert validation
        confirmation_handler=confirmation_mock,
    )

    result = harness.run("Crée une note")

    assert confirmation_mock.call_count == 1
    assert result.approvals_requested == 1
    assert result.approvals_granted == 1
    assert notes_added == ["Nouvelle"]


def test_v4_auto_approve_all_policy():
    """Avec auto_approve='all', aucune confirmation n'est demandée, même pour 'destructive'."""
    deleted_items: list[str] = []

    def mock_delete(title: str) -> str:
        deleted_items.append(title)
        return "Supprimé."

    registry = ToolRegistry()
    registry.register(mock_delete, name="delete_note", description="Supprime une note", risk_level="destructive")

    client = MagicMock(spec=OllamaClient)
    client.chat.side_effect = [
        Message(
            role="assistant",
            content=None,
            tool_calls=(ToolCall(id="del_unattended", name="delete_note", arguments={"title": "Tout"}),),
        ),
        Message(role="assistant", content="C'est supprimé.", tool_calls=()),
    ]

    confirmation_mock = MagicMock(return_value=True)
    harness = NativeHarnessV4(
        client=client,
        registry=registry,
        auto_approve="all",  # Mode automatisé / non supervisé
        confirmation_handler=confirmation_mock,
    )

    result = harness.run("Supprime tout")

    assert confirmation_mock.call_count == 0
    assert result.approvals_requested == 0
    assert deleted_items == ["Tout"]
