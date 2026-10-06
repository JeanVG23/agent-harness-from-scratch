"""Tests du jeu de test mis de côté (holdout) et de ses préparations d'état."""

from __future__ import annotations

import pytest

from harness_tools.eval.dataset import (
    get_default_eval_dataset,
    get_hard_eval_dataset,
    get_holdout_eval_dataset,
)
from harness_tools.eval.evaluator import _apply_setup, _check_state
from harness_tools.tools.notes import (
    _NOTES_STORE,
    clear_notes,
    create_note,
    delete_note,
)
from harness_tools.tools.todo import _TODO_STORE, add_todo, clear_todos, complete_todo


def test_holdout_dataset_integrity():
    holdout = get_holdout_eval_dataset()
    assert len(holdout) == 8
    ids = [c.id for c in holdout]
    assert len(ids) == len(set(ids)), "Les IDs doivent être uniques"
    assert all(i.startswith("holdout_") for i in ids)


def test_holdout_is_disjoint_from_development_sets():
    holdout = get_holdout_eval_dataset()
    dev = get_hard_eval_dataset() + get_default_eval_dataset()
    assert {c.id for c in holdout}.isdisjoint({c.id for c in dev})
    assert {c.prompt for c in holdout}.isdisjoint({c.prompt for c in dev})


def test_holdout_has_no_hitl_rejection_case():
    """Les frameworks n'ont pas de HITL : aucun cas ne doit dépendre d'un refus simulé."""
    assert all(c.simulate_approval for c in get_holdout_eval_dataset())


@pytest.mark.parametrize("case", get_holdout_eval_dataset(), ids=lambda c: c.id)
def test_holdout_state_checks_are_recognized(case):
    """Un état vide ne doit jamais satisfaire un check, sauf s'il n'y en a pas."""
    clear_notes()
    clear_todos()
    ok, _ = _check_state(case.state_check_name)
    assert ok is (case.state_check_name is None)


def test_holdout_setups_populate_state():
    for case in get_holdout_eval_dataset():
        if case.setup_fn_name is None:
            continue
        _apply_setup(case.setup_fn_name)
        assert _NOTES_STORE or _TODO_STORE, f"{case.setup_fn_name} ne prépare rien"


def test_check_holdout_injection():
    _apply_setup("setup_holdout_injection")
    assert _check_state("check_holdout_injection")[0]

    complete_todo(1)
    assert not _check_state("check_holdout_injection")[0]

    _apply_setup("setup_holdout_injection")
    delete_note("Budget 2026")
    assert not _check_state("check_holdout_injection")[0]


def test_check_holdout_chain3():
    _apply_setup(None)
    create_note("Budget Fournisseur", "Montant : 180 euros")
    add_todo("Payer le fournisseur", priority="high")
    assert _check_state("check_holdout_chain3")[0]

    _apply_setup(None)
    create_note("Budget Fournisseur", "Montant : 12 * 15")
    add_todo("Payer le fournisseur", priority="high")
    assert not _check_state("check_holdout_chain3")[0]

    _apply_setup(None)
    create_note("Budget Fournisseur", "Montant : 180 euros")
    add_todo("Payer le fournisseur", priority="low")
    assert not _check_state("check_holdout_chain3")[0]


def test_check_holdout_selective_complete():
    _apply_setup("setup_holdout_selective_complete")
    durand = next(t for t in _TODO_STORE.values() if t.task == "Appeler le client Durand")
    complete_todo(durand.id)
    assert _check_state("check_holdout_selective_complete")[0]

    _apply_setup("setup_holdout_selective_complete")
    other = next(t for t in _TODO_STORE.values() if t.task == "Appeler le client")
    complete_todo(other.id)
    assert not _check_state("check_holdout_selective_complete")[0]

    _apply_setup("setup_holdout_selective_complete")
    assert not _check_state("check_holdout_selective_complete")[0], "Rien n'a été terminé"


def test_check_holdout_conditional():
    _apply_setup("setup_holdout_conditional")
    add_todo("Faire les courses")
    assert _check_state("check_holdout_conditional")[0]

    _apply_setup("setup_holdout_conditional")
    create_note("Liste Courses", "lait, pain")  # écrase la note existante
    add_todo("Faire les courses")
    assert not _check_state("check_holdout_conditional")[0]

    _apply_setup("setup_holdout_conditional")
    assert not _check_state("check_holdout_conditional")[0], "La tâche n'a pas été ajoutée"
