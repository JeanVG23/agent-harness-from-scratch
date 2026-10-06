"""Adaptateur Pydantic-AI pour notre banc d'évaluation comparatif."""

from __future__ import annotations

import functools
import os
import time
from collections.abc import Callable
from typing import Any

# Masquer la bannière télémétrique de Pydantic-AI dans les benchmarks
os.environ["PYDANTIC_AI_NO_BANNER"] = "1"

from pydantic_ai import Agent
from pydantic_ai.models.ollama import OllamaModel
from pydantic_ai.providers.ollama import OllamaProvider
from pydantic_ai.settings import ModelSettings

from harness_tools.frameworks import FrameworkRunResult
from harness_tools.tools.calculator import calculate
from harness_tools.tools.clock import calculate_date_offset, get_current_time
from harness_tools.tools.notes import (
    create_note,
    delete_note,
    list_notes,
    read_note,
    search_notes,
)
from harness_tools.tools.todo import add_todo, complete_todo, list_todos


class PydanticAIAdapter:
    """Encapsule un agent Pydantic-AI avec les outils du projet et le suivi des appels."""

    def __init__(
        self,
        model_name: str = "qwen2.5:3b",
        base_url: str = "http://localhost:11434/v1",
        system_prompt: str | None = None,
        temperature: float = 0.0,
    ) -> None:
        self.model_name = model_name
        self.base_url = base_url
        self.temperature = temperature
        self.system_prompt = system_prompt or (
            "Tu es un assistant personnel méthodique capable d'enchaîner plusieurs actions pour accomplir des tâches complexes.\n"
            "- Si une tâche requiert des actions ou des informations, utilise TOUJOURS les outils disponibles et n'invente jamais de résultat.\n"
            "- Ne calcule JAMAIS de tête et ne devine JAMAIS une date : appelle systématiquement les outils dédiés.\n"
            "- Exploite scrupuleusement les résultats obtenus lors des étapes précédentes."
        )

        self.provider = OllamaProvider(base_url=self.base_url)
        self.model = OllamaModel(
            self.model_name,
            provider=self.provider,
            settings=ModelSettings(temperature=self.temperature),
        )

    def _build_agent_with_tracking(self, calls_record: list[str]) -> Agent:
        """Construit une instance fraîche d'Agent Pydantic-AI avec outils tracés."""
        agent = Agent(self.model, system_prompt=self.system_prompt)

        def make_tracked(fn: Callable[..., Any], canonical_name: str) -> Callable[..., Any]:
            @functools.wraps(fn)
            def wrapper(*args: Any, **kwargs: Any) -> Any:
                calls_record.append(canonical_name)
                return fn(*args, **kwargs)
            return wrapper

        raw_tools = [
            (calculate, "calculate"),
            (calculate_date_offset, "calculate_date_offset"),
            (get_current_time, "get_current_time"),
            (create_note, "create_note"),
            (read_note, "read_note"),
            (search_notes, "search_notes"),
            (list_notes, "list_notes"),
            (delete_note, "delete_note"),
            (add_todo, "add_todo"),
            (list_todos, "list_todos"),
            (complete_todo, "complete_todo"),
        ]

        for fn, canonical_name in raw_tools:
            agent.tool_plain(make_tracked(fn, canonical_name))

        return agent

    def run(self, prompt: str) -> FrameworkRunResult:
        """Exécute une requête avec Pydantic-AI et retourne un FrameworkRunResult standardisé."""
        calls_record: list[str] = []
        agent = self._build_agent_with_tracking(calls_record)

        start_time = time.perf_counter()
        try:
            res = agent.run_sync(prompt)
            duration = time.perf_counter() - start_time
            messages = res.all_messages()
            steps_count = max(1, len(messages) // 2)
            final_text = str(res.output) if res.output is not None else ""
            return FrameworkRunResult(
                final_answer=final_text,
                tools_called=tuple(calls_record),
                duration_s=duration,
                steps_count=steps_count,
                success=True,
                raw_output=res,
            )
        except Exception as exc:
            duration = time.perf_counter() - start_time
            return FrameworkRunResult(
                final_answer="",
                tools_called=tuple(calls_record),
                duration_s=duration,
                steps_count=0,
                success=False,
                error=str(exc),
            )
