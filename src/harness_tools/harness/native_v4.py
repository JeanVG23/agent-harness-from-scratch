"""Harness v4 : Garde-fous, Niveaux de Criticité et Confirmation Humaine (Human-in-the-Loop)."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import sys
import time
from typing import Any, Callable, Literal

from harness_tools.llm.client import OllamaClient
from harness_tools.models import CoercionRecord, Message, RiskLevel, ToolCall, ToolDef, ToolResult
from harness_tools.tools.registry import ToolRegistry


def _compute_call_fingerprint(name: str, arguments: dict[str, Any]) -> str:
    """Calcule une empreinte canonique stable pour un appel d'outil afin de détecter les répétitions."""
    try:
        canonical_args = json.dumps(arguments, sort_keys=True, ensure_ascii=False)
    except Exception:
        canonical_args = str(sorted(arguments.items()))
    return f"{name}:{canonical_args}"


def format_didactic_error(tool: ToolDef | None, tool_result: ToolResult) -> str:
    """Formate une erreur d'exécution d'outil avec des conseils didactiques pour guider le LLM."""
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
        "Conseil d'auto-correction : Analyse l'erreur ci-dessus, adapte tes arguments ou ton plan d'action. "
        "Si l'action a été annulée ou refusée par l'utilisateur, prends-en acte dans ta réponse finale sans répéter la même demande."
    )

    return "\n".join(lines)


def should_request_approval(
    tool_risk: RiskLevel,
    auto_approve_level: Literal["read", "write", "all"],
) -> bool:
    """Détermine si un appel d'outil requiert une confirmation selon la politique de criticité."""
    if auto_approve_level == "all":
        return False
    if auto_approve_level == "write":
        return tool_risk == "destructive"
    if auto_approve_level == "read":
        return tool_risk in ("write", "destructive")
    return True


def default_console_confirmation(tc: ToolCall, tool: ToolDef) -> bool:
    """Gestionnaire de confirmation par défaut en ligne de commande (CLI)."""
    if not sys.stdin.isatty():
        # Sécurité : par défaut en mode non-interactif, refuser les actions critiques non confirmées
        return False

    prompt = (
        f"\n⚠️  [Confirmation Humaine Requise]\n"
        f"Action : '{tc.name}' (Niveau de risque : {tool.risk_level.upper()})\n"
        f"Arguments : {json.dumps(tc.arguments, ensure_ascii=False, indent=2)}\n"
        f"Description : {tool.description}\n"
        f"Autoriser cette exécution ? [o/N] : "
    )
    try:
        reply = input(prompt).strip().lower()
        return reply in ("o", "oui", "y", "yes")
    except (EOFError, KeyboardInterrupt):
        return False


@dataclass(frozen=True, slots=True)
class ApprovalRecord:
    """Trace d'une demande de confirmation humaine pour un outil sensible."""
    tool_call_id: str
    tool_name: str
    risk_level: RiskLevel
    arguments: dict[str, Any]
    approved: bool
    reason: str = ""


@dataclass
class StepTraceV4:
    """Trace détaillée d'une étape d'exécution v4."""
    step_number: int
    tool_calls: list[ToolCall] = field(default_factory=list)
    tool_results: list[ToolResult] = field(default_factory=list)
    coercions: list[CoercionRecord] = field(default_factory=list)
    approvals: list[ApprovalRecord] = field(default_factory=list)
    assistant_content: str = ""
    duration_ms: float = 0.0
    loop_warning_triggered: bool = False
    recovered_from_error: bool = False


@dataclass
class NativeResultV4:
    """Résultat final d'une trajectoire multi-étapes v4 avec gouvernance HITL."""
    final_answer: str
    steps: list[StepTraceV4] = field(default_factory=list)
    success: bool = True
    error: str | None = None
    loop_detected: bool = False
    total_duration_ms: float = 0.0
    total_coercions: int = 0
    total_errors_encountered: int = 0
    self_corrections_count: int = 0
    approvals_requested: int = 0
    approvals_granted: int = 0
    approvals_rejected: int = 0


class NativeHarnessV4:
    """Runtime agentique v4 avec gouvernance par niveau de criticité et Human-in-the-Loop."""

    def __init__(
        self,
        client: OllamaClient,
        registry: ToolRegistry,
        max_steps: int = 8,
        max_repeated_calls: int = 2,
        enable_coercion: bool = True,
        enable_didactic_feedback: bool = True,
        auto_approve: Literal["read", "write", "all"] = "write",
        confirmation_handler: Callable[[ToolCall, ToolDef], bool] | None = None,
    ) -> None:
        self.client = client
        self.registry = registry
        self.max_steps = max_steps
        self.max_repeated_calls = max_repeated_calls
        self.enable_coercion = enable_coercion
        self.enable_didactic_feedback = enable_didactic_feedback
        self.auto_approve = auto_approve
        self.confirmation_handler = confirmation_handler or default_console_confirmation

    def run(self, user_prompt: str) -> NativeResultV4:
        """Exécute la trajectoire agentique avec vérification HITL avant exécution d'actions sensibles."""
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
                    "- Si une action est refusée par l'utilisateur, prends-en acte immédiatement, ne réitère pas l'action refusée et formule directement ta réponse finale.\n"
                    "- Si un outil renvoie une erreur (ex: argument incorrect ou introuvable), analyse attentivement le message d'erreur et adapte tes arguments ou ton choix d'outil au tour suivant.\n"
                    "- Dès que la tâche est accomplie ou qu'une action est définitivement bloquée par l'utilisateur, formule directement ta réponse finale."
                ),
            ),
            Message(role="user", content=user_prompt),
        ]

        steps: list[StepTraceV4] = []
        recent_fingerprints: list[str] = []
        all_coercions_count = 0
        total_errors_encountered = 0
        self_corrections_count = 0
        has_pending_error = False

        total_approvals_requested = 0
        total_approvals_granted = 0
        total_approvals_rejected = 0

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
                    StepTraceV4(
                        step_number=step_idx,
                        assistant_content=response_msg.content or "",
                        duration_ms=step_elapsed,
                        recovered_from_error=recovered,
                    )
                )
                total_elapsed = (time.perf_counter() - start_total) * 1000
                return NativeResultV4(
                    final_answer=response_msg.content or "",
                    steps=steps,
                    success=True,
                    total_duration_ms=total_elapsed,
                    total_coercions=all_coercions_count,
                    total_errors_encountered=total_errors_encountered,
                    self_corrections_count=self_corrections_count,
                    approvals_requested=total_approvals_requested,
                    approvals_granted=total_approvals_granted,
                    approvals_rejected=total_approvals_rejected,
                )

            # Cas 2 : Exécution des appels d'outils avec contrôle pré-exécution HITL
            messages.append(response_msg)
            current_results: list[ToolResult] = []
            current_coercions: list[CoercionRecord] = []
            current_approvals: list[ApprovalRecord] = []
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
                    return NativeResultV4(
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
                        approvals_requested=total_approvals_requested,
                        approvals_granted=total_approvals_granted,
                        approvals_rejected=total_approvals_rejected,
                    )

                tool_def = self.registry.get(tc.name)
                tool_risk: RiskLevel = tool_def.risk_level if tool_def else "read"

                # 🛑 Contrôle pré-exécution : Demande d'approbation humaine si nécessaire
                if tool_def and should_request_approval(tool_risk, self.auto_approve):
                    total_approvals_requested += 1
                    is_approved = self.confirmation_handler(tc, tool_def)

                    approval_record = ApprovalRecord(
                        tool_call_id=tc.id,
                        tool_name=tc.name,
                        risk_level=tool_risk,
                        arguments=tc.arguments,
                        approved=is_approved,
                    )
                    current_approvals.append(approval_record)

                    if not is_approved:
                        total_approvals_rejected += 1
                        tool_res = ToolResult(
                            tool_call_id=tc.id,
                            name=tc.name,
                            output=(
                                f"REFUS UTILISATEUR : L'exécution de l'outil '{tc.name}' "
                                f"(criticité : {tool_risk.upper()}) a été expressément REFUSÉE par l'utilisateur. "
                                f"L'opération N'A PAS eu lieu et rien n'a été modifié ou supprimé. "
                                f"Informe immédiatement l'utilisateur que sa demande a été annulée suite à son refus."
                            ),
                            is_error=True,
                            execution_time_ms=0.0,
                        )
                        current_results.append(tool_res)
                        messages.append(
                            Message(
                                role="tool",
                                name=tc.name,
                                tool_call_id=tc.id,
                                content=tool_res.output,
                            )
                        )
                        continue

                    total_approvals_granted += 1

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
                    tool_output = format_didactic_error(tool_def, tool_res)
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
                    self_corrections_count += 1
                    recovered = True
                    has_pending_error = False
                else:
                    has_pending_error = True
                    total_errors_encountered += sum(1 for tr in current_results if tr.is_error)
            else:
                if step_has_errors:
                    has_pending_error = True
                    total_errors_encountered += sum(1 for tr in current_results if tr.is_error)

            step_elapsed = (time.perf_counter() - step_start) * 1000
            steps.append(
                StepTraceV4(
                    step_number=step_idx,
                    tool_calls=list(response_msg.tool_calls),
                    tool_results=current_results,
                    coercions=current_coercions,
                    approvals=current_approvals,
                    assistant_content=response_msg.content or "",
                    duration_ms=step_elapsed,
                    loop_warning_triggered=loop_warning,
                    recovered_from_error=recovered,
                )
            )

        total_elapsed = (time.perf_counter() - start_total) * 1000
        return NativeResultV4(
            final_answer=f"Échec : Nombre maximal de {self.max_steps} étapes atteint sans conclusion.",
            steps=steps,
            success=False,
            error=f"Limite de {self.max_steps} étapes atteinte.",
            total_duration_ms=total_elapsed,
            total_coercions=all_coercions_count,
            total_errors_encountered=total_errors_encountered,
            self_corrections_count=self_corrections_count,
            approvals_requested=total_approvals_requested,
            approvals_granted=total_approvals_granted,
            approvals_rejected=total_approvals_rejected,
        )
