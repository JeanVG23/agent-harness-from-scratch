"""Structures de données fondamentales pour le Tool Calling et le Harness."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Literal

Role = Literal["system", "user", "assistant", "tool"]
RiskLevel = Literal["read", "write", "destructive"]


@dataclass(frozen=True, slots=True)
class ToolDef:
    """Définition complète d'un outil avec son schéma JSON et son handler."""
    name: str
    description: str
    parameters: dict[str, Any]
    handler: Callable[..., Any]
    risk_level: RiskLevel = "read"

    def to_openai_schema(self) -> dict[str, Any]:
        """Convertit la définition en schéma de fonction standardisé OpenAI/Ollama."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


@dataclass(frozen=True, slots=True)
class ToolCall:
    """Demande d'appel d'outil émise par le modèle."""
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True, slots=True)
class CoercionRecord:
    """Trace d'une correction déterministe effectuée sur un argument d'outil."""
    parameter: str
    original_value: Any
    coerced_value: Any
    action: str
    detail: str


@dataclass(frozen=True, slots=True)
class ToolResult:
    """Résultat de l'exécution d'un outil par le harness."""
    tool_call_id: str
    name: str
    output: str
    is_error: bool = False
    execution_time_ms: float = 0.0
    coercions: tuple[CoercionRecord, ...] = ()


@dataclass(slots=True)
class Message:
    """Message dans l'historique d'échange avec le LLM."""
    role: Role | str
    content: str | None = None
    tool_calls: list[ToolCall] = field(default_factory=list)
    tool_call_id: str | None = None
    name: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convertit le message en dictionnaire JSON pour l'API Ollama/OpenAI."""
        data: dict[str, Any] = {
            "role": str(self.role),
            "content": self.content or "",
        }

        if self.tool_calls:
            data["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.name,
                        "arguments": tc.arguments,
                    },
                }
                for tc in self.tool_calls
            ]

        if self.tool_call_id is not None:
            data["tool_call_id"] = self.tool_call_id

        if self.name is not None:
            data["name"] = self.name

        return data
