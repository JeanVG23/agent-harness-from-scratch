"""Adaptateurs unifiés pour les frameworks agentiques tiers (Smolagents et Pydantic-AI)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class FrameworkRunResult:
    """Résultat d'exécution normalisé pour un framework externe."""
    final_answer: str
    tools_called: tuple[str, ...]
    duration_s: float
    steps_count: int
    success: bool
    error: str | None = None
    raw_output: Any = None
