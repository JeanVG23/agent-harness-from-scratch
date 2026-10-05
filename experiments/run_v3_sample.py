"""Script de test en direct pour le Harness v3 (Robustesse, Coercion Déterministe & Auto-Correction) avec Ollama."""

import time
from harness_tools.harness.native_v3 import NativeHarnessV3
from harness_tools.llm.client import OllamaClient
from harness_tools.tools.default_tools import create_default_registry
from harness_tools.tools.notes import clear_notes, list_notes
from harness_tools.tools.todo import clear_todos, list_todos


def run_v3_experiments(model: str = "qwen2.5:3b"):
    client = OllamaClient(model=model, timeout=120.0)
    registry = create_default_registry()
    harness = NativeHarnessV3(
        client=client,
        registry=registry,
        max_steps=8,
        max_repeated_calls=2,
        enable_coercion=True,
        enable_didactic_feedback=True,
    )

    clear_notes()
    clear_todos()

    test_scenarios = [
        (
            "Scénario 1 (Chaînage nominal Calcul -> Note)",
            "Calcule 15 * 12, puis crée une note intitulée 'Budget 2026' contenant ce montant.",
        ),
        (
            "Scénario 2 (Robustesse de typage Date -> To-Do - Échec en v2, sauvé en v3)",
            "Quelle est la date dans 5 jours et ajoute une tâche 'Rapport IA' avec cette date d'échéance.",
        ),
        (
            "Scénario 3 (Auto-Correction agentique : Erreur métier -> Récupération réflexive)",
            "Consulte la note 'Recette Tarte' et si elle n'existe pas, crée une note 'Recette Tarte' avec le contenu 'Pommes et cannelle'.",
        ),
    ]

    print(f"=== TEST HARNESS V3 (ROBUSTESSE & AUTO-CORRECTION) — MODÈLE: {model} ===\n")

    for title, prompt in test_scenarios:
        print(f"--- {title} ---")
        print(f"Instruction : '{prompt}'")
        start = time.perf_counter()
        result = harness.run(prompt)
        elapsed = time.perf_counter() - start

        print(f"Statut : {'SUCCÈS' if result.success else 'ÉCHEC'} | Boucle détectée : {result.loop_detected}")
        print(
            f"Étapes : {len(result.steps)} | "
            f"Coercions : {result.total_coercions} | "
            f"Erreurs : {result.total_errors_encountered} | "
            f"Auto-corrections : {result.self_corrections_count} | "
            f"Durée : {elapsed:.2f}s"
        )

        for step in result.steps:
            warning_mark = " ⚠️ [Loop Warning]" if step.loop_warning_triggered else ""
            recovery_mark = " 🔄 [Auto-Correction réussie]" if step.recovered_from_error else ""
            print(f"  [Étape {step.step_number}] ({step.duration_ms:.1f}ms){warning_mark}{recovery_mark}")
            if step.tool_calls:
                for tc in step.tool_calls:
                    print(f"    -> ToolCall : {tc.name} | Arguments : {tc.arguments}")
            if step.coercions:
                for c in step.coercions:
                    print(f"    🔧 Coercion : param '{c.parameter}' [{c.action}] : {c.detail}")
            if step.tool_results:
                for tr in step.tool_results:
                    err_mark = " ❌ [Erreur]" if tr.is_error else " ✅ [Succès]"
                    # N'afficher que la première ligne du retour pour concision
                    summary_out = tr.output.split("\n")[0]
                    print(f"    <- ToolResult{err_mark} : {summary_out} ({tr.execution_time_ms:.2f}ms)")
            if step.assistant_content:
                print(f"    Assistant text : {step.assistant_content.strip()}")

        print(f"  => Réponse finale : {result.final_answer.strip()}\n")

    print("=== ÉTAT FINAL DE LA MÉMOIRE APRÈS EXÉCUTION ===")
    print(list_notes())
    print()
    print(list_todos())


if __name__ == "__main__":
    run_v3_experiments()
