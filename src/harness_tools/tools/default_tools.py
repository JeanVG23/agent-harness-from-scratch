"""Enregistrement par défaut des outils de l'Assistant Personnel."""

from __future__ import annotations

from harness_tools.tools.calculator import calculate
from harness_tools.tools.clock import calculate_date_offset, get_current_time
from harness_tools.tools.notes import (
    create_note,
    delete_note,
    list_notes,
    read_note,
    search_notes,
)
from harness_tools.tools.registry import ToolRegistry
from harness_tools.tools.todo import add_todo, complete_todo, list_todos


def create_default_registry() -> ToolRegistry:
    """Crée et retourne un ToolRegistry configuré avec l'ensemble des outils de l'assistant."""
    registry = ToolRegistry()

    # Outils Horloge & Dates
    registry.register(get_current_time)
    registry.register(calculate_date_offset)

    # Outil Calculatrice
    registry.register(calculate)

    # Outils Notes
    registry.register(create_note, risk_level="write")
    registry.register(read_note, risk_level="read")
    registry.register(search_notes, risk_level="read")
    registry.register(list_notes, risk_level="read")
    registry.register(delete_note, risk_level="destructive")

    # Outils To-Do
    registry.register(add_todo, risk_level="write")
    registry.register(list_todos, risk_level="read")
    registry.register(complete_todo, risk_level="write")

    return registry
