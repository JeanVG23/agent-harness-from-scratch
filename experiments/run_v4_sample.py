"""Script d'expérimentation en direct pour le Harness v4 (Garde-fous & Human-in-the-Loop) avec Ollama."""

import time
from harness_tools.harness.native_v4 import NativeHarnessV4
from harness_tools.llm.client import OllamaClient
from harness_tools.models import ToolCall, ToolDef
from harness_tools.tools.default_tools import create_default_registry
from harness_tools.tools.notes import clear_notes, create_note, list_notes
from harness_tools.tools.todo import clear_todos


def run_v4_experiments(model: str = "qwen2.5:3b"):
    client = OllamaClient(model=model, timeout=120.0)
    registry = create_default_registry()

    print(f"=== TEST HARNESS V4 (GARDE-FOUS & HUMAN-IN-THE-LOOP) — MODÈLE: {model} ===\n")

    # Scénario 1 : Création de note (Action 'write' sous auto_approve='write' -> aucune confirmation)
    clear_notes()
    clear_todos()
    harness_1 = NativeHarnessV4(
        client=client,
        registry=registry,
        auto_approve="write",
        confirmation_handler=lambda tc, tool: True,
    )
    print("--- Scénario 1 : Action Écriture ('write') sous politique auto_approve='write' ---")
    p1 = "Crée une note 'Idées Vacances' avec le contenu 'Islande et Norvège'."
    print(f"Prompt : '{p1}'")
    s1 = time.perf_counter()
    r1 = harness_1.run(p1)
    e1 = time.perf_counter() - s1
    print(f"Statut : {'SUCCÈS' if r1.success else 'ÉCHEC'}")
    print(f"Demandes d'approbation : {r1.approvals_requested} (Accordées: {r1.approvals_granted}, Refusées: {r1.approvals_rejected})")
    print(f"Réponse finale : {r1.final_answer}")
    print(f"Notes actuelles : {list_notes()}")
    print(f"Durée : {e1:.2f}s\n")

    # Scénario 2 : Action Destructive ('destructive') avec ACCORD humain
    create_note("Note Temporaire", "À effacer bientôt")
    print("--- Scénario 2 : Action Destructive ('destructive') avec ACCORD de l'humain ---")
    p2 = "Supprime la note 'Note Temporaire'."
    print(f"Prompt : '{p2}'")

    def approve_handler(tc: ToolCall, tool: ToolDef) -> bool:
        print(f"  👉 [HUMAN INTERVENTION] Demande reçue pour l'outil '{tc.name}' (Criticité: {tool.risk_level}) -> ACCORDÉ ✅")
        return True

    harness_2 = NativeHarnessV4(
        client=client,
        registry=registry,
        auto_approve="write",
        confirmation_handler=approve_handler,
    )
    s2 = time.perf_counter()
    r2 = harness_2.run(p2)
    e2 = time.perf_counter() - s2
    print(f"Statut : {'SUCCÈS' if r2.success else 'ÉCHEC'}")
    print(f"Demandes d'approbation : {r2.approvals_requested} (Accordées: {r2.approvals_granted}, Refusées: {r2.approvals_rejected})")
    print(f"Réponse finale : {r2.final_answer}")
    print(f"Notes actuelles après suppression : {list_notes()}")
    print(f"Durée : {e2:.2f}s\n")

    # Scénario 3 : Action Destructive ('destructive') avec REFUS humain
    create_note("Données Confidentielles", "Code secret: 4242")
    print("--- Scénario 3 : Action Destructive ('destructive') avec REFUS de l'humain ---")
    p3 = "Supprime la note 'Données Confidentielles'."
    print(f"Prompt : '{p3}'")

    def reject_handler(tc: ToolCall, tool: ToolDef) -> bool:
        print(f"  👉 [HUMAN INTERVENTION] Demande reçue pour l'outil '{tc.name}' (Criticité: {tool.risk_level}) -> REFUSÉ ❌")
        return False

    harness_3 = NativeHarnessV4(
        client=client,
        registry=registry,
        auto_approve="write",
        confirmation_handler=reject_handler,
    )
    s3 = time.perf_counter()
    r3 = harness_3.run(p3)
    e3 = time.perf_counter() - s3
    print(f"Statut : {'SUCCÈS' if r3.success else 'ÉCHEC'}")
    print(f"Demandes d'approbation : {r3.approvals_requested} (Accordées: {r3.approvals_granted}, Refusées: {r3.approvals_rejected})")
    print(f"Réponse finale : {r3.final_answer}")
    print(f"Notes actuelles après refus (préservation garantie) : {list_notes()}")
    print(f"Durée : {e3:.2f}s\n")


if __name__ == "__main__":
    run_v4_experiments()
