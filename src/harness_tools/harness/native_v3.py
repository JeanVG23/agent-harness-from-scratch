"""Harness v3 : Robustesse, normalisation déterministe des types et auto-correction."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any

from harness_tools.llm.client import OllamaClient
from harness_tools.models import CoercionRecord, Message, ToolCall, ToolDef, ToolResult
from harness_tools.tools.registry import ToolRegistry


def _compute_call_fingerprint(name: str, arguments: dict[str, Any]) -> str:
    """Calcule une empreinte canonique stable pour un appel d'outil afin de détecter les répétitions."""
    try:
        canonical_args = json.dumps(arguments, sort_keys=True, ensure_ascii=False)
    except Exception:
        canonical_args = str(sorted(arguments.items()))
    return f"{name}:{canonical_args}"


def format_didactic_error(tool: ToolDef | None, tool_result: ToolResult) -> str:
    """Formate une erreur d'exécution d'outil avec des conseils pédagogiques pour guider l'auto-correction du LLM."""
    if not tool_result.is_error:
        return tool_result.output

    lines = [
        f"❌ [Échec d'exécution de l'outil '{tool_result.name}']",
        f"Diagnostic : {tool_result.output}",
    ]

    if tool is not None:
        params_info = []
        properties = tool.parameters.get("properties", {})
        required = tool.parameters.get("required", [])

        for p_name, p_spec in properties.items():
            req_str = "obligatoire" if p_name in required else "optionnel"
            p_type = p_spec.get("type", "any")
            p_desc = p_spec.get("description", "")
            params_info.append(f"  - {p_name} ({p_type}, {req_str}) : {p_desc}")

        if params_info:
            lines.append(f"Schéma attendu pour '{tool.name}' :")
            lines.extend(params_info)

    lines.append(
        "Conseil d'auto-correction : Analyse l'erreur ci-dessus, adapte tes arguments pour respecter le schéma "
        "ou choisis une autre stratégie. Ne réitère pas le même appel erroné sans modification."
    )

    return "\n".join(lines)


@dataclass
class StepTraceV3:
    """Trace détaillée d'une étape d'exécution v3."""
    step_number: int
    tool_calls: list[ToolCall] = field(default_factory=list)
    tool_results: list[ToolResult] = field(default_factory=list)
    coercions: list[CoercionRecord] = field(default_factory=list)
    assistant_content: str = ""
    duration_ms: float = 0.0
    loop_warning_triggered: bool = False
    recovered_from_error: bool = False


@dataclass
class NativeResultV3:
    """Résultat final d'une trajectoire multi-étapes v3."""
    final_answer: str
    steps: list[StepTraceV3] = field(default_factory=list)
    success: bool = True
    error: str | None = None
    loop_detected: bool = False
    total_duration_ms: float = 0.0
    total_coercions: int = 0
    total_errors_encountered: int = 0
    self_corrections_count: int = 0


class NativeHarnessV3:
    """Runtime agentique v3 avec coercion déterministe, feedback didactique et auto-correction."""

    def __init__(
        self,
        client: OllamaClient,
        registry: ToolRegistry,
        max_steps: int = 8,
        max_repeated_calls: int = 2,
        enable_coercion: bool = True,
        enable_didactic_feedback: bool = True,
    ) -> None:
        self.client = client
        self.registry = registry
        self.max_steps = max_steps
        self.max_repeated_calls = max_repeated_calls
        self.enable_coercion = enable_coercion
        self.enable_didactic_feedback = enable_didactic_feedback

    def run(self, user_prompt: str) -> NativeResultV3:
        """Exécute la trajectoire agentique avec robustesse, auto-correction et observabilité."""
        start_total = time.perf_counter()
        tools_schema = self.registry.to_openai_tools()

        messages: list[Message] = [
            Message(
                role="system",
                content=(
                    "Tu es un assistant personnel méthodique capable d'enchaîner plusieurs actions pour accomplir des tâches complexes.\n"
                    "- Si une tâche requiert des actions ou des informations, utilise TOUJOURS les outils disponibles et n'invente jamais de résultat.\n"
                    "- Ne calcule JAMAIS de tête et ne devine JAMAIS une date : appelle systématiquement 'calculate' pour les calculs et 'calculate_date_offset' pour les dates.\n"
                    "- Exploite scrupuleusement les résultats obtenus lors des étapes précédentes.\n"
                    "- Respecte les types attendus par les outils (ex: nombres entiers pour les compteurs/délais, format AAAA-MM-JJ pour les dates).\n"
                    "- Si un outil renvoie un message d'erreur, analyse attentivement l'erreur et adapte tes arguments au tour suivant au lieu de répéter le même appel.\n"
                    "- Dès que la tâche est entièrement accomplie, donne directement ta réponse finale."
                ),
            ),
            Message(role="user", content=user_prompt),
        ]

        steps: list[StepTraceV3] = []
        recent_fingerprints: list[str] = []
        all_coercions_count = 0
        total_errors_encountered = 0
        self_corrections_count = 0
        has_pending_error = False

        for step_idx in range(1, self.max_steps + 1):
            step_start = time.perf_counter()
            response_msg = self.client.chat(messages, tools=tools_schema)

            # Cas 1 : Fin de trajectoire (réponse textuelle finale sans appel d'outil)
            if not response_msg.tool_calls:
                step_elapsed = (time.perf_counter() - step_start) * 1000
                recovered = False
                if has_pending_error:
                    self_corrections_count += 1
                    recovered = True
                    has_pending_error = False

                steps.append(
                    StepTraceV3(
                        step_number=step_idx,
                        assistant_content=response_msg.content or "",
                        duration_ms=step_elapsed,
                        recovered_from_error=recovered,
                    )
                )
                total_elapsed = (time.perf_counter() - start_total) * 1000
                return NativeResultV3(
                    final_answer=response_msg.content or "",
                    steps=steps,
                    success=True,
                    total_duration_ms=total_elapsed,
                    total_coercions=all_coercions_count,
                    total_errors_encountered=total_errors_encountered,
                    self_corrections_count=self_corrections_count,
                )

            # Cas 2 : Exécution des appels d'outils
            messages.append(response_msg)
            current_results: list[ToolResult] = []
            current_coercions: list[CoercionRecord] = []
            loop_warning = False

            for tc in response_msg.tool_calls:
                fp = _compute_call_fingerprint(tc.name, tc.arguments)
                recent_fingerprints.append(fp)

                # Comptage du nombre de répétitions consécutives
                repetition_count = 0
                for past_fp in reversed(recent_fingerprints):
                    if past_fp == fp:
                        repetition_count += 1
                    else:
                        break

                # Détection de boucle stricte
                if repetition_count > self.max_repeated_calls:
                    total_elapsed = (time.perf_counter() - start_total) * 1000
                    return NativeResultV3(
                        final_answer=(
                            f"Arrêt de sécurité : Boucle infinie détectée sur l'outil '{tc.name}' "
                            f"avec les mêmes arguments répétés {repetition_count} fois."
                        ),
                        steps=steps,
                        success=False,
                        loop_detected=True,
                        error=f"Boucle infinie détectée sur '{tc.name}'.",
                        total_duration_ms=total_elapsed,
                        total_coercions=all_coercions_count,
                        total_errors_encountered=total_errors_encountered,
                        self_corrections_count=self_corrections_count,
                    )

                # Exécution sécurisée avec le registre (et coercion si activée)
                tool_res = self.registry.execute(
                    tc.name,
                    tc.arguments,
                    tool_call_id=tc.id,
                    coerce=self.enable_coercion,
                )

                if tool_res.coercions:
                    current_coercions.extend(tool_res.coercions)
                    all_coercions_count += len(tool_res.coercions)

                # Formatage du retour pour le LLM (didactique si erreur et activé)
                if tool_res.is_error and self.enable_didactic_feedback:
                    tool_obj = self.registry.get(tc.name)
                    tool_output = format_didactic_error(tool_obj, tool_res)
                else:
                    tool_output = tool_res.output

                if repetition_count == self.max_repeated_calls:
                    loop_warning = True
                    tool_output += (
                        "\n⚠️ [Garde-fou Système] : Tu viens de ré-exécuter cet outil avec des arguments identiques. "
                        "Analyse le résultat ou adapte tes paramètres, ou formule ta réponse finale."
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

            step_has_errors = any(tr.is_error for tr in current_results)
            recovered = False
            if has_pending_error:
                if not step_has_errors:
                    # Tous les outils de cette étape ont réussi après une erreur précédente
                    self_corrections_count += 1
                    recovered = True
                    has_pending_error = False
                else:
                    # L'erreur persiste
                    has_pending_error = True
                    total_errors_encountered += sum(1 for tr in current_results if tr.is_error)
            else:
                if step_has_errors:
                    has_pending_error = True
                    total_errors_encountered += sum(1 for tr in current_results if tr.is_error)

            step_elapsed = (time.perf_counter() - step_start) * 1000
            steps.append(
                StepTraceV3(
                    step_number=step_idx,
                    tool_calls=list(response_msg.tool_calls),
                    tool_results=current_results,
                    coercions=current_coercions,
                    assistant_content=response_msg.content or "",
                    duration_ms=step_elapsed,
                    loop_warning_triggered=loop_warning,
                    recovered_from_error=recovered,
                )
            )

        total_elapsed = (time.perf_counter() - start_total) * 1000
        return NativeResultV3(
            final_answer=f"Échec : Nombre maximal de {self.max_steps} étapes atteint sans conclusion.",
            steps=steps,
            success=False,
            error=f"Limite de {self.max_steps} étapes atteinte.",
            total_duration_ms=total_elapsed,
            total_coercions=all_coercions_count,
            total_errors_encountered=total_errors_encountered,
            self_corrections_count=self_corrections_count,
        )
