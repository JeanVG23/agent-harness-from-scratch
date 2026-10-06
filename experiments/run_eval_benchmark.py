"""Script d'exécution du banc d'évaluation (Evaluation Harness) sur le modèle local avec Ollama."""

import time

from harness_tools.eval.dataset import get_default_eval_dataset
from harness_tools.eval.evaluator import Evaluator
from harness_tools.llm.client import OllamaClient


def run_benchmark(model: str = "qwen2.5:3b"):
    print(f"=== BANC D'ÉVALUATION FORMEL (EVALUATION HARNESS) | MODÈLE: {model} ===\n")
    client = OllamaClient(model=model, timeout=120.0)
    dataset = get_default_eval_dataset()
    evaluator = Evaluator(client)

    print(f"Lancement de l'évaluation sur {len(dataset)} cas de test...\n")
    print(f"{'ID Cas':<22} | {'Catégorie':<12} | {'Statut':<8} | {'Outils appelés':<30} | {'Durée':<7}")
    print("-" * 90)

    results = []
    start_total = time.perf_counter()

    for case in dataset:
        case_res = evaluator.evaluate_case(case)
        results.append(case_res)
        status_str = "✅ PASS" if case_res.passed else "❌ FAIL"
        tools_str = ", ".join(case_res.tools_called) if case_res.tools_called else "(aucun / abstention)"
        if len(tools_str) > 28:
            tools_str = tools_str[:25] + "..."
        print(f"{case.id:<22} | {case.category:<12} | {status_str:<8} | {tools_str:<30} | {case_res.duration_s:.2f}s")

    total_time = time.perf_counter() - start_total

    total = len(results)
    passed = sum(1 for r in results if r.passed)
    pass_rate = (passed / total) * 100

    non_abstain = [r for r in results if r.category != "abstention"]
    tool_acc = (sum(1 for r in non_abstain if r.tool_selection_ok) / len(non_abstain)) * 100 if non_abstain else 100.0

    abstain_cases = [r for r in results if r.category == "abstention"]
    abstain_acc = (sum(1 for r in abstain_cases if r.abstention_ok) / len(abstain_cases)) * 100 if abstain_cases else 100.0

    avg_steps = sum(r.steps_count for r in results) / total
    avg_dur = sum(r.duration_s for r in results) / total

    print("-" * 90)
    print("\n=== BILAN CONSOLIDÉ DES MÉTRIQUES ===")
    print(f"Taux de succès global (Pass Rate)       : {pass_rate:.1f}% ({passed}/{total})")
    print(f"Précision de sélection d'outil (Tool Acc): {tool_acc:.1f}%")
    print(f"Taux d'abstention légitime (Abstention)  : {abstain_acc:.1f}%")
    print(f"Nombre moyen d'étapes (Avg Steps)       : {avg_steps:.2f}")
    print(f"Latence moyenne par cas (Avg Latency)   : {avg_dur:.2f}s")
    print(f"Durée totale de la campagne              : {total_time:.2f}s\n")

    # Détails des échecs s'il y en a
    failed = [r for r in results if not r.passed]
    if failed:
        print("=== ANALYSE QUALITATIVE DES ÉCHECS ===")
        for r in failed:
            print(f"- Cas [{r.case_id}] ({r.category}) :")
            print(f"  Outils appelés : {r.tools_called}")
            print(f"  Tool Selection OK : {r.tool_selection_ok} | Abstention OK : {r.abstention_ok} | Keywords OK : {r.keywords_ok} | HITL OK : {r.hitl_ok}")
            print(f"  Réponse : {r.final_answer[:150]}...")
            print()


if __name__ == "__main__":
    run_benchmark()
