"""Script de test comparatif en direct : Native Tool Calling v1 avec Ollama."""

import time
from harness_tools.harness.native_v1 import NativeHarnessV1
from harness_tools.llm.client import OllamaClient
from harness_tools.tools.default_tools import create_default_registry


def run_comparison():
    model = "qwen3.5:4b"
    client = OllamaClient(model=model, timeout=60.0)
    registry = create_default_registry()
    harness = NativeHarnessV1(client=client, registry=registry)

    test_queries = [
        "Combien font 14 * 25 ?",
        "Quelle heure est-il actuellement à Paris ?",
        "Bonjour, qui es-tu ?",
    ]

    print(f"=== TEST NATIVE TOOL CALLING V1 — MODÈLE: {model} ===\n")

    for i, query in enumerate(test_queries, 1):
        print(f"--- Requête {i} : '{query}' ---")
        start = time.perf_counter()
        result = harness.run(query, max_steps=4)
        elapsed = time.perf_counter() - start

        print(f"Statut : {'SUCCÈS' if result.success else 'ÉCHEC'}")
        print(f"Nombre d'étapes : {len(result.steps)} | Durée totale : {elapsed:.2f}s")
        for step in result.steps:
            print(f"  [Étape {step.step_number}] ({step.duration_ms:.1f}ms)")
            if step.tool_calls:
                for tc in step.tool_calls:
                    print(f"    ToolCall: {tc.name} | Args: {tc.arguments}")
            if step.tool_results:
                for tr in step.tool_results:
                    print(f"    ToolResult: {tr.output} ({tr.execution_time_ms:.2f}ms)")
            if step.assistant_content:
                print(f"    Assistant text: {step.assistant_content.strip()}")
        print(f"  => Réponse finale : {result.final_answer.strip()}\n")


if __name__ == "__main__":
    run_comparison()
