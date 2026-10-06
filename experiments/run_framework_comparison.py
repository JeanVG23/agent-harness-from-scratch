"""Script d'évaluation comparative tripartite : Harness Maison vs Smolagents vs Pydantic-AI."""

from __future__ import annotations

import argparse
import time
from typing import Any

from harness_tools.eval.dataset import (
    EvalCase,
    get_default_eval_dataset,
    get_full_eval_dataset,
    get_hard_eval_dataset,
)
from harness_tools.eval.evaluator import _apply_setup, _check_state
from harness_tools.frameworks.pydantic_ai_adapter import PydanticAIAdapter
from harness_tools.frameworks.smolagents_adapter import SmolagentsAdapter
from harness_tools.harness.native_v4 import NativeHarnessV4
from harness_tools.llm.client import OllamaClient
from harness_tools.tools.default_tools import create_default_registry


def evaluate_runner_case(
    case: EvalCase,
    runner_name: str,
    runner: Any,
) -> dict[str, Any]:
    """Évalue un cas de test unitaire sur un runner spécifique avec validation des critères formels."""
    _apply_setup(case.setup_fn_name)

    start_time = time.perf_counter()
    tools_called: tuple[str, ...] = ()
    final_answer = ""
    error_msg: str | None = None

    try:
        if runner_name == "harness_v4":
            result = runner.run(case.prompt)
            called_list = []
            for step in result.steps:
                for tc in step.tool_calls:
                    called_list.append(tc.name)
            tools_called = tuple(called_list)
            final_answer = result.final_answer
            steps_count = len(result.steps)
        else:
            # SmolagentsAdapter ou PydanticAIAdapter
            result = runner.run(case.prompt)
            tools_called = result.tools_called
            final_answer = result.final_answer
            steps_count = result.steps_count
            error_msg = result.error
    except Exception as exc:
        duration_s = time.perf_counter() - start_time
        return {
            "passed": False,
            "duration_s": duration_s,
            "tools_called": (),
            "steps_count": 0,
            "error": str(exc),
            "final_answer": "",
        }

    duration_s = time.perf_counter() - start_time

    # 1. Sélection d'outils attendus
    tool_selection_ok = True
    if case.expected_tools:
        for exp in case.expected_tools:
            if exp not in tools_called:
                tool_selection_ok = False
                break

    # 2. Abstention / Outils interdits
    abstention_ok = True
    if case.forbidden_tools and any(f in tools_called for f in case.forbidden_tools):
        abstention_ok = False

    if case.should_abstain and not case.expected_tools and len(tools_called) > 0:
        abstention_ok = False

    # 3. Vérification de l'état mémoire
    state_ok, state_err = _check_state(case.state_check_name)

    passed = tool_selection_ok and abstention_ok and state_ok and (error_msg is None)

    return {
        "passed": passed,
        "duration_s": duration_s,
        "tools_called": tools_called,
        "steps_count": steps_count,
        "tool_selection_ok": tool_selection_ok,
        "abstention_ok": abstention_ok,
        "state_ok": state_ok,
        "state_err": state_err,
        "error": error_msg,
        "final_answer": final_answer,
    }


def run_benchmark(dataset_type: str = "hard", model_name: str = "qwen2.5:3b") -> None:
    print(f"=== GRAND COMPARATIF TRIPARTITE | MODÈLE: {model_name} ===")
    print(f"Suite sélectionnée : {dataset_type.upper()}\n")

    if dataset_type == "hard":
        dataset = get_hard_eval_dataset()
    elif dataset_type == "standard":
        dataset = get_default_eval_dataset()
    else:
        dataset = get_full_eval_dataset()

    # Initialisation des 3 Runtimes
    client = OllamaClient(model=model_name, timeout=120.0)
    registry = create_default_registry()
    harness_v4 = NativeHarnessV4(
        client=client,
        registry=registry,
        auto_approve="write",
        confirmation_handler=lambda tc, td: True,
    )
    smolagents_runner = SmolagentsAdapter(model_id=model_name, verbosity=0)
    pydantic_ai_runner = PydanticAIAdapter(model_name=model_name)

    runners = [
        ("Harness V4", "harness_v4", harness_v4),
        ("Smolagents (Code)", "smolagents", smolagents_runner),
        ("Pydantic-AI (JSON)", "pydantic_ai", pydantic_ai_runner),
    ]

    print(f"{'ID Cas':<25} | {'Harness V4':<14} | {'Smolagents':<14} | {'Pydantic-AI':<14}")
    print("-" * 75)

    scores: dict[str, list[dict[str, Any]]] = {r[0]: [] for r in runners}

    for case in dataset:
        row = [f"{case.id:<25}"]
        for label, r_name, runner_obj in runners:
            eval_res = evaluate_runner_case(case, r_name, runner_obj)
            scores[label].append(eval_res)
            status_str = f"{'✅ PASS' if eval_res['passed'] else '❌ FAIL'} ({eval_res['duration_s']:.1f}s)"
            row.append(f"{status_str:<14}")
        print(" | ".join(row))

    print("-" * 75)
    print("\n=== BILAN CONSOLIDÉ DES PERFORMANCES ===")
    for label, res_list in scores.items():
        passed_count = sum(1 for r in res_list if r["passed"])
        total_count = len(res_list)
        pct = (passed_count / total_count) * 100
        avg_dur = sum(r["duration_s"] for r in res_list) / total_count
        total_dur = sum(r["duration_s"] for r in res_list)
        print(f"• {label:<22} : {passed_count}/{total_count} réussis ({pct:.1f}%) | Latence moy: {avg_dur:.2f}s | Durée totale: {total_dur:.1f}s")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", choices=["hard", "standard", "full"], default="hard")
    parser.add_argument("--model", default="qwen2.5:3b")
    args = parser.parse_args()

    run_benchmark(dataset_type=args.dataset, model_name=args.model)
