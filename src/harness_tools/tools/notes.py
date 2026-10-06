"""Outil Gestionnaire de Notes personnelles."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Note:
    """Représentation d'une note personnelle."""
    title: str
    content: str
    tags: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))


# Dépôt en mémoire pour les notes
_NOTES_STORE: dict[str, Note] = {}


def clear_notes() -> None:
    """Réinitialise l'entrepôt de notes (principalement pour les tests)."""
    _NOTES_STORE.clear()


# `tags` n'est jamais modifié (lecture seule) : B006 ne s'applique pas ici, et le
# `default: []` fait partie du schéma JSON présenté au modèle (voir registry.py).
def create_note(title: str, content: str, tags: list[str] = []) -> str:  # noqa: B006
    """Crée ou met à jour une note textuelle avec un titre, un contenu et des tags optionnels.

    Args:
        title: Le titre unique de la note (ex: 'Idées vacances', 'Courses').
        content: Le texte ou corps de la note.
        tags: Liste de mots-clés pour classer la note (ex: ['pro', 'urgent']).
    """
    clean_title = title.strip()
    if not clean_title:
        return "Erreur : Le titre de la note ne peut pas être vide."

    clean_content = content.strip()
    clean_tags = [t.strip().lower() for t in tags if t and t.strip()]

    is_update = clean_title.lower() in _NOTES_STORE
    _NOTES_STORE[clean_title.lower()] = Note(
        title=clean_title,
        content=clean_content,
        tags=clean_tags,
    )

    action = "mise à jour" if is_update else "créée"
    tags_info = f" (tags: {', '.join(clean_tags)})" if clean_tags else ""
    return f"Succès : La note '{clean_title}' a été {action} avec succès{tags_info}."


def read_note(title: str) -> str:
    """Lit et affiche le contenu complet d'une note à partir de son titre exact.

    Args:
        title: Le titre de la note à consulter.
    """
    key = title.strip().lower()
    note = _NOTES_STORE.get(key)
    if not note:
        available = [n.title for n in _NOTES_STORE.values()]
        available_str = ", ".join(f"'{t}'" for t in available) if available else "aucune"
        return f"Erreur : Aucune note trouvée avec le titre '{title}'. Notes existantes : {available_str}."

    tags_line = f"\nTags: {', '.join(note.tags)}" if note.tags else ""
    return f"--- Note : {note.title} ---\nDate: {note.created_at}{tags_line}\n\n{note.content}"


def search_notes(query: str) -> str:
    """Recherche parmi les notes existantes celles qui contiennent un mot-clé dans leur titre, contenu ou tags.

    Args:
        query: Le terme ou mot-clé à rechercher.
    """
    q = query.strip().lower()
    if not q:
        return "Erreur : Requête de recherche vide."

    matches: list[Note] = []
    for note in _NOTES_STORE.values():
        if q in note.title.lower() or q in note.content.lower() or any(q in t for t in note.tags):
            matches.append(note)

    if not matches:
        return f"Aucune note ne correspond à la recherche '{query}'."

    results = [f"- {n.title} (tags: {', '.join(n.tags) or 'aucun'}) : {n.content[:80]}..." for n in matches]
    return f"Résultats de recherche pour '{query}' ({len(matches)} note(s)) :\n" + "\n".join(results)


def list_notes() -> str:
    """Liste tous les titres des notes enregistrées."""
    if not _NOTES_STORE:
        return "Aucune note enregistrée pour le moment."

    notes = sorted(_NOTES_STORE.values(), key=lambda n: n.title.lower())
    lines = [f"- {n.title} [tags: {', '.join(n.tags) or 'aucun'}] (créée le {n.created_at})" for n in notes]
    return f"Notes enregistrées ({len(notes)}) :\n" + "\n".join(lines)


def delete_note(title: str) -> str:
    """Supprime définitivement une note à partir de son titre.

    Args:
        title: Le titre de la note à supprimer.
    """
    key = title.strip().lower()
    if key in _NOTES_STORE:
        actual_title = _NOTES_STORE[key].title
        del _NOTES_STORE[key]
        return f"Succès : La note '{actual_title}' a été supprimée."
    available = [n.title for n in _NOTES_STORE.values()]
    available_str = ", ".join(f"'{t}'" for t in available) if available else "aucune"
    return f"Erreur : Impossible de supprimer, la note '{title}' n'existe pas. Notes existantes : {available_str}."
