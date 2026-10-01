"""Enregistrement par défaut des outils de l'Assistant Personnel."""

from __future__ import annotations

from harness_tools.tools.calculator import calculate
from harness_tools.tools.clock import calculate_date_offset, get_current_time
from harness_tools.tools.notes import create_note, delete_note, list_notes, read_note, search_notes
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
    registry.register(create_note)
    registry.register(read_note)
    registry.register(search_notes)
    registry.register(list_notes)
    registry.register(delete_note)

    # Outils To-Do
    registry.register(add_todo)
    registry.register(list_todos)
    registry.register(complete_todo)

    return registry
