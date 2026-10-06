"""Adaptateur Smolagents (Hugging Face) pour notre banc d'évaluation comparatif."""

from __future__ import annotations

import functools
import time
from collections.abc import Callable
from typing import Any

from smolagents import CodeAgent, OpenAIServerModel, tool

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


class SmolagentsAdapter:
    """Encapsule un CodeAgent Smolagents pour exécuter des requêtes sur les outils du projet."""

    def __init__(
        self,
        model_id: str = "qwen2.5:3b",
        api_base: str = "http://localhost:11434/v1",
        max_steps: int = 8,
        verbosity: int = 0,
    ) -> None:
        self.model_id = model_id
        self.api_base = api_base
        self.max_steps = max_steps
        self.verbosity = verbosity

        self.model = OpenAIServerModel(
            model_id=self.model_id,
            api_base=self.api_base,
            api_key="ollama",
        )

    def _build_tracked_tools(self, call_tracker: list[str]) -> list[Any]:
        """Crée des versions des outils qui enregistrent leurs invocations dans call_tracker."""
        def make_wrapper(fn: Callable[..., Any], canonical_name: str) -> Any:
            @functools.wraps(fn)
            def wrapper(*args: Any, **kwargs: Any) -> Any:
                call_tracker.append(canonical_name)
                return fn(*args, **kwargs)
            wrapper.__name__ = fn.__name__
            wrapper.__doc__ = fn.__doc__
            return tool(wrapper)

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

        return [make_wrapper(fn, name) for fn, name in raw_tools]

    def run(self, prompt: str) -> FrameworkRunResult:
        """Exécute une requête avec le CodeAgent Smolagents et retourne un FrameworkRunResult standardisé."""
        calls_record: list[str] = []
        tools = self._build_tracked_tools(calls_record)

        agent = CodeAgent(
            tools=tools,
            model=self.model,
            max_steps=self.max_steps,
            verbosity_level=self.verbosity,
        )

        start_time = time.perf_counter()
        try:
            output = agent.run(prompt)
            duration = time.perf_counter() - start_time
            steps_count = len(getattr(agent.memory, "steps", []))
            final_text = str(output) if output is not None else ""
            return FrameworkRunResult(
                final_answer=final_text,
                tools_called=tuple(calls_record),
                duration_s=duration,
                steps_count=steps_count,
                success=True,
                raw_output=output,
            )
        except Exception as exc:
            duration = time.perf_counter() - start_time
            steps_count = len(getattr(agent.memory, "steps", [])) if hasattr(agent, "memory") else 0
            return FrameworkRunResult(
                final_answer="",
                tools_called=tuple(calls_record),
                duration_s=duration,
                steps_count=steps_count,
                success=False,
                error=str(exc),
            )
