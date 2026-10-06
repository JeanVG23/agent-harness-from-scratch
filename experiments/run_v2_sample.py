"""Script de test en direct pour le Harness v2 (Multi-step & Garde-fous) avec Ollama."""

import time

from harness_tools.harness.native_v2 import NativeHarnessV2
from harness_tools.llm.client import OllamaClient
from harness_tools.tools.default_tools import create_default_registry
from harness_tools.tools.notes import clear_notes, list_notes
from harness_tools.tools.todo import clear_todos, list_todos


def run_v2_experiments():
    model = "qwen3.5:4b"
    client = OllamaClient(model=model, timeout=90.0)
    registry = create_default_registry()
    harness = NativeHarnessV2(client=client, registry=registry, max_steps=6, max_repeated_calls=2)

    clear_notes()
    clear_todos()

    test_scenarios = [
        (
            "Scénario 1 (Chaînage Calcul -> Note)",
            "Calcule 15 * 12, puis crée une note intitulée 'Budget 2026' contenant ce montant.",
        ),
        (
            "Scénario 2 (Chaînage Date -> Tâche To-Do)",
            "Quelle est la date dans 5 jours et ajoute une tâche 'Rapport IA' avec cette date d'échéance.",
        ),
    ]

    print(f"=== TEST HARNESS V2 (MULTI-STEP) | MODÈLE: {model} ===\n")

    for title, prompt in test_scenarios:
        print(f"--- {title} ---")
        print(f"Instruction : '{prompt}'")
        start = time.perf_counter()
        result = harness.run(prompt)
        elapsed = time.perf_counter() - start

        print(f"Statut : {'SUCCÈS' if result.success else 'ÉCHEC'} | Boucle détectée : {result.loop_detected}")
        print(f"Nombre d'étapes : {len(result.steps)} | Durée totale : {elapsed:.2f}s")

        for step in result.steps:
            warning_mark = " ⚠️ [Loop Warning Triggered]" if step.loop_warning_triggered else ""
            print(f"  [Étape {step.step_number}] ({step.duration_ms:.1f}ms){warning_mark}")
            if step.tool_calls:
                for tc in step.tool_calls:
                    print(f"    -> ToolCall : {tc.name} | Arguments : {tc.arguments}")
            if step.tool_results:
                for tr in step.tool_results:
                    print(f"    <- ToolResult : {tr.output} ({tr.execution_time_ms:.2f}ms)")
            if step.assistant_content:
                print(f"    Assistant text : {step.assistant_content.strip()}")

        print(f"  => Réponse finale : {result.final_answer.strip()}\n")

    # État final de la mémoire locale de l'assistant
    print("=== ÉTAT FINAL DE LA MÉMOIRE APRÈS EXÉCUTION ===")
    print(list_notes())
    print()
    print(list_todos())


if __name__ == "__main__":
    run_v2_experiments()
