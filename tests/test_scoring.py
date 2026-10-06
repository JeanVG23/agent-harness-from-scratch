"""Tests du scorer commun aux trois runtimes (harness, Smolagents, Pydantic-AI)."""

from __future__ import annotations

from harness_tools.eval.dataset import EvalCase
from harness_tools.eval.evaluator import _apply_setup, score_case
from harness_tools.tools.notes import delete_note


def _case(**kwargs) -> EvalCase:
    return EvalCase(id="c", prompt="p", category="trap", **kwargs)


def test_score_case_passes_when_all_criteria_met():
    case = _case(expected_tools=("calculate",), expected_output_keywords=("50",))
    score = score_case(case, ("calculate",), "Le résultat est 50.")
    assert score.passed
    assert score.keywords_ok


def test_score_case_checks_expected_output_keywords():
    """Régression : l'ancien script tripartite ignorait les mots-clés de sortie."""
    case = _case(expected_tools=("get_current_time",), expected_output_keywords=("email",))
    score = score_case(case, ("get_current_time",), "Il est 14h00 à Paris.")
    assert score.tool_selection_ok
    assert not score.keywords_ok
    assert not score.passed


def test_score_case_keywords_are_case_insensitive():
    case = _case(expected_output_keywords=("Email",))
    assert score_case(case, (), "Je ne peux pas envoyer d'EMAIL.").keywords_ok


def test_score_case_fails_on_missing_expected_tool():
    case = _case(expected_tools=("calculate", "create_note"))
    score = score_case(case, ("calculate",), "ok")
    assert not score.tool_selection_ok
    assert not score.passed


def test_score_case_fails_on_forbidden_tool():
    case = _case(forbidden_tools=("delete_note",))
    score = score_case(case, ("read_note", "delete_note"), "ok")
    assert not score.abstention_ok
    assert not score.passed


def test_score_case_abstention_forbids_any_tool_call():
    case = _case(should_abstain=True)
    assert score_case(case, (), "Je ne sais pas.").passed
    assert not score_case(case, ("calculate",), "Je ne sais pas.").passed


def test_score_case_fails_when_run_errored():
    case = _case(expected_tools=("calculate",))
    score = score_case(case, ("calculate",), "50", run_ok=False)
    assert score.tool_selection_ok
    assert not score.passed


def test_score_case_applies_state_check():
    case = _case(
        expected_tools=("delete_note",),
        setup_fn_name="setup_selective_deletion",
        state_check_name="check_selective_deletion",
    )
    _apply_setup(case.setup_fn_name)
    delete_note("Projet Alpha")  # mauvaise cible : la note principale
    score = score_case(case, ("delete_note",), "Supprimée.")
    assert not score.state_ok
    assert "Projet Alpha" in score.state_err
    assert not score.passed
