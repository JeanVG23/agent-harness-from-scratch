"""Harness v1 : Implémentation du Tool Calling natif d'API (Ollama / OpenAI)."""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from harness_tools.llm.client import OllamaClient
from harness_tools.models import Message, ToolCall, ToolResult
from harness_tools.tools.registry import ToolRegistry


@dataclass
class NativeStep:
    """Représente une étape d'exécution dans la boucle native."""
    step_number: int
    tool_calls: list[ToolCall] = field(default_factory=list)
    tool_results: list[ToolResult] = field(default_factory=list)
    assistant_content: str = ""
    duration_ms: float = 0.0


@dataclass
class NativeResult:
    """Résultat final d'une exécution native."""
    final_answer: str
    steps: list[NativeStep] = field(default_factory=list)
    success: bool = True
    error: str | None = None
    total_duration_ms: float = 0.0


class NativeHarnessV1:
    """Runtime agentique exploitant le Tool Calling natif au niveau des tokens."""

    def __init__(self, client: OllamaClient, registry: ToolRegistry) -> None:
        self.client = client
        self.registry = registry

    def run(self, user_prompt: str, max_steps: int = 5) -> NativeResult:
        """Exécute la boucle de tool calling jusqu'à obtention d'une réponse finale textuelle."""
        start_total = time.perf_counter()
        tools_schema = self.registry.to_openai_tools()

        messages: list[Message] = [
            Message(
                role="system",
                content=(
                    "Tu es un assistant personnel doté d'outils. Réponds à la demande de l'utilisateur de manière concise et précise. "
                    "Utilise les outils à ta disposition dès que nécessaire. Si aucun outil n'est requis ou si tu as toutes les informations, "
                    "donne directement ta réponse finale."
                ),
            ),
            Message(role="user", content=user_prompt),
        ]

        steps: list[NativeStep] = []

        for step_idx in range(1, max_steps + 1):
            step_start = time.perf_counter()
            response_msg = self.client.chat(messages, tools=tools_schema)

            # Cas 1 : Le modèle ne demande aucun outil -> c'est sa réponse finale
            if not response_msg.tool_calls:
                step_elapsed = (time.perf_counter() - step_start) * 1000
                steps.append(
                    NativeStep(
                        step_number=step_idx,
                        assistant_content=response_msg.content or "",
                        duration_ms=step_elapsed,
                    )
                )
                total_elapsed = (time.perf_counter() - start_total) * 1000
                return NativeResult(
                    final_answer=response_msg.content or "",
                    steps=steps,
                    success=True,
                    total_duration_ms=total_elapsed,
                )

            # Cas 2 : Le modèle a émis un ou plusieurs tool_calls
            messages.append(response_msg)
            current_results: list[ToolResult] = []

            for tc in response_msg.tool_calls:
                tool_res = self.registry.execute(tc.name, tc.arguments, tool_call_id=tc.id)
                current_results.append(tool_res)

                # Réinjection du résultat sous le rôle 'tool'
                messages.append(
                    Message(
                        role="tool",
                        name=tc.name,
                        tool_call_id=tc.id,
                        content=tool_res.output,
                    )
                )

            step_elapsed = (time.perf_counter() - step_start) * 1000
            steps.append(
                NativeStep(
                    step_number=step_idx,
                    tool_calls=list(response_msg.tool_calls),
                    tool_results=current_results,
                    assistant_content=response_msg.content or "",
                    duration_ms=step_elapsed,
                )
            )

        total_elapsed = (time.perf_counter() - start_total) * 1000
        return NativeResult(
            final_answer="Échec : Nombre maximal d'étapes atteint sans réponse finale.",
            steps=steps,
            success=False,
            error=f"Limite de {max_steps} étapes atteinte.",
            total_duration_ms=total_elapsed,
        )
