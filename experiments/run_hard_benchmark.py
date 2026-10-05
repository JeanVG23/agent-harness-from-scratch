"""Script d'évaluation des pièges extrêmes et cas de stress (Hard Traps Benchmark)."""

import time
from harness_tools.eval.dataset import get_hard_eval_dataset
from harness_tools.eval.evaluator import Evaluator
from harness_tools.llm.client import OllamaClient


def run_hard_traps(model: str = "qwen2.5:3b"):
    print(f"=== BANC DE STRESS & PIÈGES COMPLEXES (HARD TRAPS) — MODÈLE: {model} ===\n")
    client = OllamaClient(model=model, timeout=120.0)
    dataset = get_hard_eval_dataset()
    evaluator = Evaluator(client)

    print(f"Lancement de l'évaluation sur {len(dataset)} pièges retors...\n")
    print(f"{'ID Piège':<26} | {'Catégorie':<8} | {'Statut':<8} | {'Outils appelés':<30} | {'Durée':<6}")
    print("-" * 88)

    results = []
    start_total = time.perf_counter()

    for case in dataset:
        case_res = evaluator.evaluate_case(case)
        results.append(case_res)
        status_str = "✅ PASS" if case_res.passed else "❌ FAIL"
        tools_str = ", ".join(case_res.tools_called) if case_res.tools_called else "(aucun / abstention)"
        if len(tools_str) > 28:
            tools_str = tools_str[:25] + "..."
        print(f"{case.id:<26} | {case.category:<8} | {status_str:<8} | {tools_str:<30} | {case_res.duration_s:.2f}s")

    total_time = time.perf_counter() - start_total
    passed = sum(1 for r in results if r.passed)
    total = len(results)

    print("-" * 88)
    print(f"\nRésultat final des pièges : {passed}/{total} réussis ({(passed/total)*100:.1f}%) en {total_time:.2f}s\n")

    print("=== DÉBRIEFING DÉTAILLÉ CAS PAR CAS ===")
    for r in results:
        status_icon = "✅" if r.passed else "❌"
        print(f"\n{status_icon} [{r.case_id}]")
        print(f"   Outils invoqués     : {r.tools_called}")
        print(f"   Sélection d'outils  : {'OK' if r.tool_selection_ok else 'ÉCHEC'}")
        print(f"   Abstention/Interdit : {'OK' if r.abstention_ok else 'ÉCHEC'}")
        print(f"   État mémoire réel   : {'CONFORME' if r.state_check_ok else 'ALTÉRÉ / NON CONFORME'}")
        print(f"   Nombre d'étapes     : {r.steps_count} en {r.duration_s:.2f}s")
        if not r.passed and r.error_message:
            print(f"   Diagnostic d'erreur : {r.error_message}")
        print(f"   Extrait de réponse  : {r.final_answer.strip()[:180]}...")


if __name__ == "__main__":
    run_hard_traps()
