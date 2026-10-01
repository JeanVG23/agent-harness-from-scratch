"""Tests unitaires pour les outils de l'Assistant Personnel."""

import pytest
from harness_tools.tools.calculator import calculate
from harness_tools.tools.clock import calculate_date_offset, get_current_time
from harness_tools.tools.notes import clear_notes, create_note, delete_note, list_notes, read_note, search_notes
from harness_tools.tools.todo import add_todo, clear_todos, complete_todo, list_todos


# === Tests Calculatrice ===

def test_calculator_arithmetic():
    assert calculate("2 + 3 * 4") == "14"
    assert calculate("(10 + 20) / 2") == "15"
    assert calculate("2 ** 8") == "256"
    assert calculate("10 // 3") == "3"
    assert calculate("10 % 3") == "1"


def test_calculator_functions():
    assert calculate("sqrt(144)") == "12"
    assert calculate("round(10 / 3, 2)") == "3.33"
    assert calculate("max(5, 12, 3)") == "12"
    assert calculate("abs(-42)") == "42"


def test_calculator_errors():
    assert "Division par zéro" in calculate("10 / 0")
    assert "Erreur" in calculate("__import__('os').system('ls')")
    assert "Erreur de syntaxe" in calculate("2 +* 3")


# === Tests Horloge & Dates ===

def test_clock_current_time():
    res = get_current_time("Europe/Paris")
    assert "/" in res
    assert ":" in res
    assert "Erreur" not in res

    res_utc = get_current_time("UTC")
    assert "UTC" in res_utc

    res_invalid = get_current_time("Invalid/Zone")
    assert "Erreur : Fuseau horaire" in res_invalid


def test_clock_date_offset():
    res = calculate_date_offset(5, start_date="2026-10-01")
    assert "2026-10-06" in res
    assert "Mardi" in res

    res_past = calculate_date_offset(-1, start_date="2026-10-01")
    assert "2026-09-30" in res_past

    res_invalid = calculate_date_offset(2, start_date="bad-date")
    assert "Erreur : Format de date invalide" in res_invalid


# === Tests Notes ===

def test_notes_crud():
    clear_notes()

    # Création
    res = create_note("Idées RAG", "Tester le seuil d'abstention", tags=["ia", "rag"])
    assert "créée avec succès" in res

    # Lecture
    read_res = read_note("Idées RAG")
    assert "Tester le seuil d'abstention" in read_res
    assert "Tags: ia, rag" in read_res

    # Recherche
    search_res = search_notes("abstention")
    assert "Idées RAG" in search_res

    # Liste
    list_res = list_notes()
    assert "Idées RAG" in list_res

    # Mise à jour
    update_res = create_note("Idées RAG", "Contenu enrichi", tags=["ia"])
    assert "mise à jour" in update_res
    assert "Contenu enrichi" in read_note("Idées RAG")

    # Suppression
    del_res = delete_note("Idées RAG")
    assert "supprimée" in del_res
    assert "Erreur" in read_note("Idées RAG")


# === Tests To-Do ===

def test_todo_flow():
    clear_todos()

    # Ajout
    add_res = add_todo("Rédiger le rapport d'expérience", priority="high", due_date="2026-10-05")
    assert "Tâche #1 ajoutée" in add_res
    assert "priorité: high" in add_res

    add_res_2 = add_todo("Faire les courses")
    assert "Tâche #2 ajoutée" in add_res_2

    # Liste en attente
    list_pending = list_todos(status="pending")
    assert "#1" in list_pending
    assert "#2" in list_pending

    # Validation
    comp_res = complete_todo(1)
    assert "cochée comme terminée" in comp_res

    # Liste complétée
    list_completed = list_todos(status="completed")
    assert "#1" in list_completed
    assert "#2" not in list_completed
