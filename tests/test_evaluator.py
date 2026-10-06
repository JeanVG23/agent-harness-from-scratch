"""Tests unitaires pour l'Evaluation Harness (calcul des métriques, abstention, conformité)."""

from __future__ import annotations

from unittest.mock import MagicMock

from harness_tools.eval.dataset import EvalCase, get_default_eval_dataset
from harness_tools.eval.evaluator import Evaluator
from harness_tools.llm.client import OllamaClient
from harness_tools.models import Message, ToolCall


def test_eval_dataset_integrity():
    """Vérifie la cohérence du dataset de référence (12 cas, catégories valides)."""
    dataset = get_default_eval_dataset()
    assert len(dataset) == 12

    ids = [c.id for c in dataset]
    assert len(ids) == len(set(ids)), "Les IDs de cas doivent être uniques"

    categories = {c.category for c in dataset}
    assert categories == {"direct", "multi_step", "abstention", "destructive"}


def test_evaluator_direct_success():
    """Vérifie l'évaluation positive d'un cas direct."""
    client = MagicMock(spec=OllamaClient)
    client.chat.side_effect = [
        Message(
            role="assistant",
            content=None,
            tool_calls=(ToolCall(id="call_calc", name="calculate", arguments={"expression": "10 * 5"}),),
        ),
        Message(role="assistant", content="Le résultat est 50.", tool_calls=()),
    ]

    case = EvalCase(
        id="test_calc",
        prompt="Calcule 10 * 5",
        category="direct",
        expected_tools=("calculate",),
        expected_output_keywords=("50",),
    )

    evaluator = Evaluator(client)
    res = evaluator.evaluate_case(case)

    assert res.passed
    assert res.tool_selection_ok
    assert res.keywords_ok
    assert res.tools_called == ("calculate",)


def test_evaluator_abstention_success():
    """Vérifie qu'un modèle qui ne déclenche aucun outil réussit le test d'abstention."""
    client = MagicMock(spec=OllamaClient)
    client.chat.side_effect = [
        Message(
            role="assistant",
            content="Je suis un assistant spécialisé et je n'ai pas accès aux prévisions météo.",
            tool_calls=(),
        ),
    ]

    case = EvalCase(
        id="test_weather",
        prompt="Météo à Nice ?",
        category="abstention",
        should_abstain=True,
        forbidden_tools=("calculate", "create_note"),
    )

    evaluator = Evaluator(client)
    res = evaluator.evaluate_case(case)

    assert res.passed
    assert res.abstention_ok
    assert len(res.tools_called) == 0


def test_evaluator_abstention_failure_when_hallucinating():
    """Vérifie qu'un modèle qui appelle un outil interdit en cas d'abstention échoue."""
    client = MagicMock(spec=OllamaClient)
    client.chat.side_effect = [
        Message(
            role="assistant",
            content=None,
            tool_calls=(ToolCall(id="call_wrong", name="create_note", arguments={"title": "Météo", "content": "Soleil"}),),
        ),
        Message(role="assistant", content="Note météo créée.", tool_calls=()),
    ]

    case = EvalCase(
        id="test_weather_hallucinated",
        prompt="Météo à Nice ?",
        category="abstention",
        should_abstain=True,
        forbidden_tools=("create_note",),
    )

    evaluator = Evaluator(client)
    res = evaluator.evaluate_case(case)

    assert not res.passed
    assert not res.abstention_ok


def test_evaluator_run_suite_metrics():
    """Vérifie l'agrégation statistique sur une mini suite."""
    client = MagicMock(spec=OllamaClient)
    # Deux cas simples qui répondent directement sans outils
    client.chat.side_effect = [
        Message(role="assistant", content="Bonjour !", tool_calls=()),
        Message(role="assistant", content="Au revoir !", tool_calls=()),
    ]

    cases = [
        EvalCase(id="c1", prompt="Dis bonjour", category="abstention", should_abstain=True),
        EvalCase(id="c2", prompt="Dis au revoir", category="abstention", should_abstain=True),
    ]

    evaluator = Evaluator(client)
    summary = evaluator.run_suite(cases)

    assert summary.total_cases == 2
    assert summary.passed_cases == 2
    assert summary.pass_rate == 100.0
    assert summary.abstention_accuracy == 100.0
