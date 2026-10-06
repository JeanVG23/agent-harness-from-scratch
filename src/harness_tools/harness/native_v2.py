"""Harness v2 : Enchaînement multi-outils, gestion des dépendances et détection de boucles infinies."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any

from harness_tools.llm.client import OllamaClient
from harness_tools.models import Message, ToolCall, ToolResult
from harness_tools.tools.registry import ToolRegistry


def _compute_call_fingerprint(name: str, arguments: dict[str, Any]) -> str:
    """Calcule une empreinte canonique stable pour un appel d'outil afin de détecter les répétitions."""
    try:
        canonical_args = json.dumps(arguments, sort_keys=True, ensure_ascii=False)
    except Exception:
        canonical_args = str(sorted(arguments.items()))
    return f"{name}:{canonical_args}"


@dataclass
class StepTraceV2:
    """Trace détaillée d'une étape d'exécution."""
    step_number: int
    tool_calls: list[ToolCall] = field(default_factory=list)
    tool_results: list[ToolResult] = field(default_factory=list)
    assistant_content: str = ""
    duration_ms: float = 0.0
    loop_warning_triggered: bool = False


@dataclass
class NativeResultV2:
    """Résultat final d'une trajectoire multi-étapes v2."""
    final_answer: str
    steps: list[StepTraceV2] = field(default_factory=list)
    success: bool = True
    error: str | None = None
    loop_detected: bool = False
    total_duration_ms: float = 0.0


class NativeHarnessV2:
    """Runtime agentique v2 avec support multi-étapes et garde-fous anti-boucle infinie."""

    def __init__(
        self,
        client: OllamaClient,
        registry: ToolRegistry,
        max_steps: int = 8,
        max_repeated_calls: int = 2,
    ) -> None:
        self.client = client
        self.registry = registry
        self.max_steps = max_steps
        self.max_repeated_calls = max_repeated_calls

    def run(self, user_prompt: str) -> NativeResultV2:
        """Exécute la trajectoire agentique avec garde-fous."""
        start_total = time.perf_counter()
        tools_schema = self.registry.to_openai_tools()

        messages: list[Message] = [
            Message(
                role="system",
                content=(
                    "Tu es un assistant personnel méthodique capable d'enchaîner plusieurs actions pour accomplir des tâches complexes.\n"
                    "- Si une tâche requiert plusieurs actions successives (ex: faire un calcul puis enregistrer le résultat dans une note), "
                    "réalise-les étape par étape sans inventer de résultat.\n"
                    "- Exploite les résultats obtenus lors des étapes précédentes.\n"
                    "- Ne répète jamais le même appel d'outil avec les mêmes arguments si tu as déjà reçu une réponse.\n"
                    "- Dès que la tâche est entièrement accomplie, donne directement ta réponse finale."
                ),
            ),
            Message(role="user", content=user_prompt),
        ]

        steps: list[StepTraceV2] = []
        recent_fingerprints: list[str] = []

        for step_idx in range(1, self.max_steps + 1):
            step_start = time.perf_counter()
            response_msg = self.client.chat(messages, tools=tools_schema)

            # Cas 1 : Fin de la trajectoire (réponse textuelle finale sans outil)
            if not response_msg.tool_calls:
                step_elapsed = (time.perf_counter() - step_start) * 1000
                steps.append(
                    StepTraceV2(
                        step_number=step_idx,
                        assistant_content=response_msg.content or "",
                        duration_ms=step_elapsed,
                    )
                )
                total_elapsed = (time.perf_counter() - start_total) * 1000
                return NativeResultV2(
                    final_answer=response_msg.content or "",
                    steps=steps,
                    success=True,
                    total_duration_ms=total_elapsed,
                )

            # Cas 2 : Demande d'un ou plusieurs appels d'outils
            messages.append(response_msg)
            current_results: list[ToolResult] = []
            loop_warning = False

            for tc in response_msg.tool_calls:
                fp = _compute_call_fingerprint(tc.name, tc.arguments)
                recent_fingerprints.append(fp)

                # Comptage du nombre de répétitions consécutives de cette empreinte
                repetition_count = 0
                for past_fp in reversed(recent_fingerprints):
                    if past_fp == fp:
                        repetition_count += 1
                    else:
                        break

                # Détection de boucle stricte : dépassement du seuil toléré
                if repetition_count > self.max_repeated_calls:
                    total_elapsed = (time.perf_counter() - start_total) * 1000
                    return NativeResultV2(
                        final_answer=(
                            f"Arrêt de sécurité : Boucle infinie détectée sur l'outil '{tc.name}' "
                            f"avec les mêmes arguments répétés {repetition_count} fois."
                        ),
                        steps=steps,
                        success=False,
                        loop_detected=True,
                        error=f"Boucle infinie détectée sur '{tc.name}'.",
                        total_duration_ms=total_elapsed,
                    )

                # Exécution normale de l'outil
                tool_res = self.registry.execute(tc.name, tc.arguments, tool_call_id=tc.id)

                # Si l'appel a déjà été fait 1 fois et se répète, on injecte un avertissement dans la réponse
                tool_output = tool_res.output
                if repetition_count == self.max_repeated_calls:
                    loop_warning = True
                    tool_output += (
                        "\n[Garde-fou Système] : Tu viens de ré-exécuter cet outil avec des arguments identiques. "
                        "Exploite ce résultat sans répéter cet appel, ou formule ta réponse finale."
                    )

                current_results.append(tool_res)
                messages.append(
                    Message(
                        role="tool",
                        name=tc.name,
                        tool_call_id=tc.id,
                        content=tool_output,
                    )
                )

            step_elapsed = (time.perf_counter() - step_start) * 1000
            steps.append(
                StepTraceV2(
                    step_number=step_idx,
                    tool_calls=list(response_msg.tool_calls),
                    tool_results=current_results,
                    assistant_content=response_msg.content or "",
                    duration_ms=step_elapsed,
                    loop_warning_triggered=loop_warning,
                )
            )

        total_elapsed = (time.perf_counter() - start_total) * 1000
        return NativeResultV2(
            final_answer=f"Échec : Nombre maximal de {self.max_steps} étapes atteint sans conclusion.",
            steps=steps,
            success=False,
            error=f"Limite de {self.max_steps} étapes atteinte.",
            total_duration_ms=total_elapsed,
        )
