"""Module d'évaluation formelle (Evaluation Harness) pour agents avec outils."""

from harness_tools.eval.dataset import (
    EvalCase,
    get_default_eval_dataset,
    get_full_eval_dataset,
    get_hard_eval_dataset,
    get_holdout_eval_dataset,
)
from harness_tools.eval.evaluator import (
    CaseEvalResult,
    CaseScore,
    EvalSummary,
    Evaluator,
    score_case,
)

__all__ = [
    "CaseEvalResult",
    "CaseScore",
    "EvalCase",
    "EvalSummary",
    "Evaluator",
    "get_default_eval_dataset",
    "get_full_eval_dataset",
    "get_hard_eval_dataset",
    "get_holdout_eval_dataset",
    "score_case",
]
