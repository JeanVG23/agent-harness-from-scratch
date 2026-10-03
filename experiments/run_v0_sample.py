"""Script de test en direct pour le Harness ReAct v0 avec Ollama."""

import time
from harness_tools.harness.react_v0 import ReActHarnessV0
from harness_tools.llm.client import OllamaClient
from harness_tools.tools.default_tools import create_default_registry


def run_sample():
    model = "qwen3.5:4b"
    client = OllamaClient(model=model, timeout=60.0)
    registry = create_default_registry()
    harness = ReActHarnessV0(client=client, registry=registry)

    test_queries = [
        "Combien font 14 * 25 ?",
        "Quelle heure est-il actuellement à Paris ?",
        "Bonjour, qui es-tu ?",
    ]

    print(f"=== TEST RE-ACT V0 — MODÈLE: {model} ===\n")

    for i, query in enumerate(test_queries, 1):
        print(f"--- Requête {i} : '{query}' ---")
        start = time.perf_counter()
        result = harness.run(query, max_steps=4)
        elapsed = time.perf_counter() - start

        print(f"Statut : {'SUCCÈS' if result.success else 'ÉCHEC'}")
        print(f"Nombre d'étapes : {len(result.steps)} | Durée : {elapsed:.2f}s")
        for idx, step in enumerate(result.steps, 1):
            print(f"  [Étape {idx}]")
            if step.thought:
                print(f"    Thought: {step.thought}")
            if step.action:
                print(f"    Action: {step.action} | Args: {step.action_input}")
            if step.observation:
                print(f"    Observation: {step.observation}")
        print(f"  => Réponse finale : {result.final_answer}\n")


if __name__ == "__main__":
    run_sample()
