"""Registre d'outils et générateur de schémas JSON par introspection Python."""

from __future__ import annotations

import inspect
import json
import re
import time
from typing import Any, Callable, get_args, get_origin, Union
import types

from harness_tools.models import ToolDef, ToolResult


def _parse_docstring(docstring: str | None) -> tuple[str, dict[str, str]]:
    """Extrait la description générale et les descriptions des paramètres d'une docstring.
    
    Supporte les formats Google style (Args:) et Sphinx (:param x:).
    """
    if not docstring:
        return "", {}

    lines = inspect.cleandoc(docstring).split("\n")
    main_desc_lines: list[str] = []
    param_docs: dict[str, str] = {}

    current_section: str | None = None
    current_param: str | None = None

    google_arg_pattern = re.compile(r"^(\w+)(?:\s*\([^)]+\))?\s*:\s*(.*)$")
    sphinx_param_pattern = re.compile(r"^:param\s+(\w+)\s*:\s*(.*)$")

    for line in lines:
        stripped = line.strip()
        
        # Détection Sphinx
        sphinx_match = sphinx_param_pattern.match(stripped)
        if sphinx_match:
            current_section = "params"
            current_param = sphinx_match.group(1)
            param_docs[current_param] = sphinx_match.group(2).strip()
            continue

        # Détection Google style
        if stripped.lower() in ("args:", "arguments:", "parameters:"):
            current_section = "params"
            current_param = None
            continue
        elif stripped.lower() in ("returns:", "raises:", "yields:", "example:", "examples:"):
            current_section = "other"
            current_param = None
            continue

        if current_section == "params":
            arg_match = google_arg_pattern.match(stripped)
            if arg_match:
                current_param = arg_match.group(1)
                param_docs[current_param] = arg_match.group(2).strip()
            elif current_param and (line.startswith("    ") or line.startswith("\t") or line.startswith("  ")):
                # Ligne de continuation de la description du paramètre
                param_docs[current_param] += " " + stripped
        elif current_section is None:
            main_desc_lines.append(line)

    main_desc = "\n".join(main_desc_lines).strip()
    return main_desc, param_docs


def _type_to_json_schema(py_type: Any) -> dict[str, Any]:
    """Convertit un type Python en schéma JSON Schema."""
    if py_type is inspect.Parameter.empty or py_type is Any:
        return {"type": "string"}

    origin = get_origin(py_type)
    args = get_args(py_type)

    # Gestion de Union / Optional (ex: str | None ou Optional[str])
    if origin in (Union, types.UnionType):
        non_none_args = [a for a in args if a is not type(None)]
        if len(non_none_args) == 1:
            return _type_to_json_schema(non_none_args[0])
        # Union de plusieurs types réels -> anyOf
        return {"anyOf": [_type_to_json_schema(a) for a in non_none_args]}

    # Types de base
    if py_type is str:
        return {"type": "string"}
    elif py_type is int:
        return {"type": "integer"}
    elif py_type is float:
        return {"type": "number"}
    elif py_type is bool:
        return {"type": "boolean"}
    elif py_type in (list, tuple) or origin in (list, tuple):
        item_schema = {"type": "string"}
        if args:
            item_schema = _type_to_json_schema(args[0])
        return {"type": "array", "items": item_schema}
    elif py_type is dict or origin is dict:
        return {"type": "object"}

    # Fallback par défaut
    return {"type": "string"}


def function_to_tool_def(fn: Callable[..., Any], name: str | None = None, description: str | None = None) -> ToolDef:
    """Construit un ToolDef complet à partir de l'introspection d'une fonction Python."""
    fn_name = name or fn.__name__
    doc_desc, param_docs = _parse_docstring(fn.__doc__)
    fn_desc = description or doc_desc or f"Fonction {fn_name}"

    sig = inspect.signature(fn)
    properties: dict[str, Any] = {}
    required: list[str] = []

    for param_name, param in sig.parameters.items():
        # Ignorer self ou *args/**kwargs
        if param_name in ("self", "cls") or param.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD):
            continue

        param_schema = _type_to_json_schema(param.annotation)
        
        # Ajout de la documentation du paramètre si présente
        if param_name in param_docs:
            param_schema["description"] = param_docs[param_name]

        # Valeur par défaut
        if param.default is not inspect.Parameter.empty:
            param_schema["default"] = param.default
        else:
            required.append(param_name)

        properties[param_name] = param_schema

    parameters_schema: dict[str, Any] = {
        "type": "object",
        "properties": properties,
        "required": required,
    }

    return ToolDef(
        name=fn_name,
        description=fn_desc,
        parameters=parameters_schema,
        handler=fn,
    )


class ToolRegistry:
    """Registre centralisé pour gérer les outils et exécuter les appels."""

    def __init__(self) -> None:
        self._tools: dict[str, ToolDef] = {}

    def register(self, fn: Callable[..., Any], name: str | None = None, description: str | None = None) -> ToolDef:
        """Enregistre une fonction Python comme outil."""
        tool_def = function_to_tool_def(fn, name=name, description=description)
        self._tools[tool_def.name] = tool_def
        return tool_def

    def get(self, name: str) -> ToolDef | None:
        """Récupère la définition d'un outil par son nom."""
        return self._tools.get(name)

    def list_tools(self) -> list[ToolDef]:
        """Retourne la liste de tous les outils enregistrés."""
        return list(self._tools.values())

    def to_openai_tools(self) -> list[dict[str, Any]]:
        """Génère la liste de schémas au format OpenAI / Ollama tools: [...]."""
        return [tool.to_openai_schema() for tool in self._tools.values()]

    def execute(self, name: str, arguments: dict[str, Any], tool_call_id: str = "") -> ToolResult:
        """Exécute un outil de manière sécurisée et chronométrée.
        
        Capture les erreurs d'arguments et exceptions pour renvoyer un ToolResult exploitable.
        """
        start_time = time.perf_counter()
        tool = self.get(name)

        if tool is None:
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            available = ", ".join(self._tools.keys()) or "aucun"
            return ToolResult(
                tool_call_id=tool_call_id,
                name=name,
                output=f"Erreur : L'outil '{name}' n'existe pas. Outils disponibles : {available}",
                is_error=True,
                execution_time_ms=elapsed_ms,
            )

        try:
            # Vérification des arguments obligatoires
            required_params = tool.parameters.get("required", [])
            missing_params = [p for p in required_params if p not in arguments]
            if missing_params:
                elapsed_ms = (time.perf_counter() - start_time) * 1000
                return ToolResult(
                    tool_call_id=tool_call_id,
                    name=name,
                    output=f"Erreur d'arguments : Paramètre(s) obligatoire(s) manquant(s) : {', '.join(missing_params)}",
                    is_error=True,
                    execution_time_ms=elapsed_ms,
                )

            # Exécution réelle
            raw_result = tool.handler(**arguments)
            elapsed_ms = (time.perf_counter() - start_time) * 1000

            # Normalisation du résultat sous forme de chaîne
            if isinstance(raw_result, str):
                output_str = raw_result
            elif isinstance(raw_result, (dict, list)):
                output_str = json.dumps(raw_result, ensure_ascii=False, indent=2)
            else:
                output_str = str(raw_result)

            return ToolResult(
                tool_call_id=tool_call_id,
                name=name,
                output=output_str,
                is_error=False,
                execution_time_ms=elapsed_ms,
            )

        except TypeError as exc:
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            return ToolResult(
                tool_call_id=tool_call_id,
                name=name,
                output=f"Erreur de type d'arguments pour '{name}': {exc}",
                is_error=True,
                execution_time_ms=elapsed_ms,
            )
        except Exception as exc:
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            return ToolResult(
                tool_call_id=tool_call_id,
                name=name,
                output=f"Exception lors de l'exécution de '{name}': {type(exc).__name__}: {exc}",
                is_error=True,
                execution_time_ms=elapsed_ms,
            )


# Registre global par commodité
_GLOBAL_REGISTRY = ToolRegistry()


def register_tool(name: str | None = None, description: str | None = None) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Décorateur pour enregistrer une fonction dans le registre global."""
    def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
        _GLOBAL_REGISTRY.register(fn, name=name, description=description)
        return fn
    return decorator
