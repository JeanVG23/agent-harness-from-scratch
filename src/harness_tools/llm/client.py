"""Client HTTP minimaliste pour l'API Ollama (local ou cloud) en bibliothèque standard."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

from harness_tools.models import Message, ToolCall


class LLMError(RuntimeError):
    """Exception levée en cas d'échec de communication ou de réponse invalide du LLM."""


class OllamaClient:
    """Client synchrone léger pour interroger Ollama (/api/chat)."""

    def __init__(
        self,
        model: str = "qwen3.5:4b",
        host: str = "http://localhost:11434",
        timeout: float = 120.0,
        api_key: str | None = None,
    ) -> None:
        self.model = model
        self.host = host.rstrip("/")
        self.timeout = timeout
        self.api_key = api_key

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def chat(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.0,
    ) -> Message:
        """Envoie une liste de messages et des schémas d'outils optionnels à Ollama."""
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [m.to_dict() for m in messages],
            "stream": False,
            "options": {
                "temperature": temperature,
            },
        }

        if tools:
            payload["tools"] = tools

        url = f"{self.host}/api/chat"
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers=self._headers(), method="POST")

        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                body = response.read().decode("utf-8")
                res_json = json.loads(body)
        except urllib.error.HTTPError as exc:
            err_body = exc.read().decode("utf-8", errors="replace")
            raise LLMError(f"Erreur HTTP {exc.code} lors de l'appel à {url} : {err_body}") from exc
        except urllib.error.URLError as exc:
            raise LLMError(f"Impossible de joindre le serveur Ollama sur {self.host} : {exc.reason}") from exc
        except Exception as exc:
            raise LLMError(f"Erreur inattendue lors de l'appel Ollama : {exc}") from exc

        msg_data = res_json.get("message", {})
        raw_tool_calls = msg_data.get("tool_calls", [])
        parsed_tool_calls: list[ToolCall] = []

        for idx, tc in enumerate(raw_tool_calls):
            func_data = tc.get("function", {})
            raw_args = func_data.get("arguments", {})

            # Arguments parfois sérialisés en chaîne JSON ou déjà sous forme de dictionnaire
            if isinstance(raw_args, str):
                try:
                    args_dict = json.loads(raw_args)
                except json.JSONDecodeError:
                    args_dict = {"_raw": raw_args}
            elif isinstance(raw_args, dict):
                args_dict = raw_args
            else:
                args_dict = {}

            call_id = tc.get("id") or f"call_{idx}"
            parsed_tool_calls.append(
                ToolCall(
                    id=call_id,
                    name=func_data.get("name", ""),
                    arguments=args_dict,
                )
            )

        return Message(
            role="assistant",
            content=msg_data.get("content") or "",
            tool_calls=parsed_tool_calls,
        )
