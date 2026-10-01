"""Outil Gestionnaire de Tâches To-Do."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class TodoItem:
    """Représentation d'une tâche à accomplir."""
    id: int
    task: str
    priority: str = "medium"  # low, medium, high
    completed: bool = False
    due_date: str | None = None
    created_at: str = field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))


# Dépôt en mémoire pour les tâches
_TODO_STORE: dict[int, TodoItem] = {}
_NEXT_TODO_ID: int = 1


def clear_todos() -> None:
    """Réinitialise l'entrepôt de tâches (pour les tests)."""
    global _NEXT_TODO_ID
    _TODO_STORE.clear()
    _NEXT_TODO_ID = 1


def add_todo(task: str, priority: str = "medium", due_date: str | None = None) -> str:
    """Ajoute une nouvelle tâche à faire dans la liste de to-do.

    Args:
        task: La description de la tâche à accomplir (ex: 'Acheter du pain', 'Préparer la soutenance').
        priority: Priorité de la tâche, parmi 'low', 'medium', 'high' (par défaut 'medium').
        due_date: Date d'échéance optionnelle au format AAAA-MM-JJ (ex: '2026-10-15').
    """
    global _NEXT_TODO_ID
    clean_task = task.strip()
    if not clean_task:
        return "Erreur : La description de la tâche ne peut pas être vide."

    clean_priority = priority.strip().lower()
    if clean_priority not in ("low", "medium", "high"):
        clean_priority = "medium"

    todo_id = _NEXT_TODO_ID
    _NEXT_TODO_ID += 1

    item = TodoItem(
        id=todo_id,
        task=clean_task,
        priority=clean_priority,
        due_date=due_date.strip() if due_date else None,
    )
    _TODO_STORE[todo_id] = item

    due_str = f", échéance: {item.due_date}" if item.due_date else ""
    return f"Succès : Tâche #{todo_id} ajoutée : '{clean_task}' [priorité: {clean_priority}{due_str}]."


def list_todos(status: str = "all") -> str:
    """Liste les tâches enregistrées selon leur statut.

    Args:
        status: Filtre sur le statut, parmi 'all' (toutes), 'pending' (en attente), 'completed' (terminées).
    """
    filter_status = status.strip().lower()
    if filter_status not in ("all", "pending", "completed"):
        filter_status = "all"

    items = list(_TODO_STORE.values())
    if filter_status == "pending":
        items = [t for t in items if not t.completed]
    elif filter_status == "completed":
        items = [t for t in items if t.completed]

    if not items:
        return f"Aucune tâche trouvée (filtre: '{filter_status}')."

    lines: list[str] = []
    for t in sorted(items, key=lambda x: x.id):
        mark = "[X]" if t.completed else "[ ]"
        due_str = f" | Échéance: {t.due_date}" if t.due_date else ""
        lines.append(f"{mark} #{t.id} : {t.task} (priorité: {t.priority}{due_str})")

    return f"Liste des tâches ({len(items)}) :\n" + "\n".join(lines)


def complete_todo(task_id: int) -> str:
    """Marque une tâche comme terminée à partir de son identifiant numérique.

    Args:
        task_id: L'identifiant numérique de la tâche (ex: 1, 2).
    """
    item = _TODO_STORE.get(task_id)
    if not item:
        available_ids = [str(t.id) for t in _TODO_STORE.values() if not t.completed]
        ids_str = ", ".join(available_ids) if available_ids else "aucune"
        return f"Erreur : Tâche #{task_id} introuvable. Tâches en attente existantes : {ids_str}."

    if item.completed:
        return f"Info : La tâche #{task_id} ('{item.task}') était déjà marquée comme terminée."

    item.completed = True
    return f"Succès : Tâche #{task_id} ('{item.task}') cochée comme terminée."
