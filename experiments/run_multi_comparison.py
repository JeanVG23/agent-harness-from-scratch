"""Comparatif tripartite répété : N runs, température alignée, notation commune, jeu dev et holdout.

Remplace `run_framework_comparison.py` pour toute conclusion comparative : même scorer pour les
trois runtimes (mots-clés de sortie compris), même température, plusieurs runs et un jeu mis de côté.

Exemples :
    uv run python experiments/run_multi_comparison.py --model qwen2.5:3b --runs 5 --dataset both
    uv run python experiments/run_multi_comparison.py --model gemma4:31b-cloud --runs 3 --dataset both
    uv run python experiments/run_multi_comparison.py --report experiments/results/<a>.jsonl [<b>.jsonl ...]
"""

from __future__ import annotations

import argparse
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from harness_tools.eval.dataset import (
    EvalCase,
    get_hard_eval_dataset,
    get_holdout_eval_dataset,
)
from harness_tools.eval.evaluator import _apply_setup, score_case
from harness_tools.eval.multirun import (
    RunRecord,
    format_report,
    load_records,
    save_record,
)
from harness_tools.frameworks.pydantic_ai_adapter import PydanticAIAdapter
from harness_tools.frameworks.smolagents_adapter import SmolagentsAdapter
from harness_tools.harness.native_v4 import NativeHarnessV4
from harness_tools.llm.client import OllamaClient
from harness_tools.tools.default_tools import create_default_registry

RESULTS_DIR = Path(__file__).parent / "results"
ALL_RUNNERS = ("harness_v4", "smolagents", "pydantic_ai")
DEFAULT_HOST = "http://localhost:11434"


def build_runners(
    model: str, temperature: float, names: tuple[str, ...], host: str = DEFAULT_HOST
) -> dict[str, Any]:
    """Instancie les runtimes demandés, tous sur le même modèle et la même température."""
    runners: dict[str, Any] = {}
    if "harness_v4" in names:
        runners["harness_v4"] = NativeHarnessV4(
            client=OllamaClient(model=model, host=host, timeout=180.0, temperature=temperature),
            registry=create_default_registry(),
            auto_approve="write",
            confirmation_handler=lambda tc, td: True,
        )
    if "smolagents" in names:
        runners["smolagents"] = SmolagentsAdapter(model_id=model, api_base=f"{host}/v1", verbosity=0, temperature=temperature)
    if "pydantic_ai" in names:
        runners["pydantic_ai"] = PydanticAIAdapter(model_name=model, base_url=f"{host}/v1", temperature=temperature)
    return runners


def run_case(case: EvalCase, runner_name: str, runner: Any) -> dict[str, Any]:
    """Exécute un cas sur un runtime et le note avec le scorer commun."""
    _apply_setup(case.setup_fn_name)
    start = time.perf_counter()
    try:
        result = runner.run(case.prompt)
        if runner_name == "harness_v4":
            tools_called = tuple(tc.name for step in result.steps for tc in step.tool_calls)
            steps_count = len(result.steps)
            run_ok, error = result.success, result.error
        else:
            tools_called = result.tools_called
            steps_count = result.steps_count
            run_ok, error = result.success, result.error
        final_answer = result.final_answer
    except Exception as exc:
        tools_called, steps_count, run_ok, error, final_answer = (), 0, False, str(exc), ""
    duration_s = time.perf_counter() - start

    score = score_case(case, tools_called, final_answer, run_ok=run_ok)
    return {
        "passed": score.passed,
        "duration_s": duration_s,
        "steps_count": steps_count,
        "tools_called": tools_called,
        "tool_selection_ok": score.tool_selection_ok,
        "abstention_ok": score.abstention_ok,
        "keywords_ok": score.keywords_ok,
        "state_ok": score.state_ok,
        "error": error if error else (None if score.passed else score.state_err or None),
        "final_answer": final_answer,
    }


def select_datasets(choice: str) -> list[tuple[str, list[EvalCase]]]:
    """« hard » = les 7 pièges du comparatif v7 (jeu de développement), « holdout » = jeu mis de côté."""
    datasets = {"hard": get_hard_eval_dataset, "holdout": get_holdout_eval_dataset}
    names = list(datasets) if choice == "both" else [choice]
    return [(name, datasets[name]()) for name in names]


def run_campaign(args: argparse.Namespace) -> Path:
    runner_names = tuple(args.runners.split(","))
    runners = build_runners(args.model, args.temperature, runner_names, args.host)
    datasets = select_datasets(args.dataset)

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    safe_model = re.sub(r"[^A-Za-z0-9._-]+", "_", args.model)
    out_path = Path(args.out) if args.out else RESULTS_DIR / f"{safe_model}-{args.dataset}-{stamp}.jsonl"

    total = args.runs * sum(len(cases) for _, cases in datasets) * len(runners)
    print(f"=== {args.model} | T={args.temperature} | {args.runs} runs | jeux : {args.dataset} | {total} évaluations ===")
    print(f"Résultats bruts : {out_path}\n")

    done = 0
    for run_index in range(1, args.runs + 1):
        for dataset_name, cases in datasets:
            for case in cases:
                for runner_name, runner in runners.items():
                    res = run_case(case, runner_name, runner)
                    save_record(
                        out_path,
                        RunRecord(
                            model=args.model,
                            temperature=args.temperature,
                            runner=runner_name,
                            dataset=dataset_name,
                            run_index=run_index,
                            case_id=case.id,
                            **res,
                        ),
                    )
                    done += 1
                    status = "PASS" if res["passed"] else "FAIL"
                    print(
                        f"[{done}/{total}] run {run_index} | {dataset_name} | {case.id:<34} | "
                        f"{runner_name:<11} | {status} ({res['duration_s']:.1f}s)",
                        flush=True,
                    )
    return out_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--model", default="qwen2.5:3b")
    parser.add_argument("--runs", type=int, default=5)
    parser.add_argument("--dataset", choices=["hard", "holdout", "both"], default="both")
    parser.add_argument("--runners", default=",".join(ALL_RUNNERS), help="Liste séparée par des virgules")
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--host", default=DEFAULT_HOST, help="Serveur Ollama (ex: un second serveur lancé avec un autre contexte)")
    parser.add_argument("--out", help="Fichier JSONL de sortie (défaut : experiments/results/...)")
    parser.add_argument("--report", nargs="+", help="Agrège un ou plusieurs fichiers JSONL sans rien exécuter")
    args = parser.parse_args()

    if args.report:
        print(format_report([rec for path in args.report for rec in load_records(Path(path))]))
        return

    out_path = run_campaign(args)
    print("\n" + format_report(load_records(out_path)))


if __name__ == "__main__":
    main()
