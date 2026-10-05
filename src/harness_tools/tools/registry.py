"""Registre d'outils et générateur de schémas JSON par introspection Python."""

from __future__ import annotations

import inspect
import json
import re
import time
import types
from typing import Any, Callable, Union, get_args, get_origin

from harness_tools.models import CoercionRecord, ToolDef, ToolResult
from harness_tools.tools.coercion import sanitize_arguments


def _parse_docstring(docstring: str | None) -> tuple[str, dict[str, str]]:
    """Extrait la description générale et les descriptions des paramètres d'une docstring au format Google (Args:)."""
    if not docstring:
        return "", {}

    lines = inspect.cleandoc(docstring).split("\n")
    main_desc_lines: list[str] = []
    param_docs: dict[str, str] = {}

    current_section: str | None = None
    current_param: str | None = None

    arg_pattern = re.compile(r"^(\w+)(?:\s*\([^)]+\))?\s*:\s*(.*)$")

    for line in lines:
        stripped = line.strip()

        if stripped.lower() in ("args:", "arguments:", "parameters:"):
            current_section = "params"
            current_param = None
            continue
        elif stripped.lower() in ("returns:", "raises:", "yields:", "example:", "examples:"):
            current_section = "other"
            current_param = None
            continue

        if current_section == "params":
            arg_match = arg_pattern.match(stripped)
            if arg_match:
                current_param = arg_match.group(1)
                param_docs[current_param] = arg_match.group(2).strip()
            elif current_param and (line.startswith("    ") or line.startswith("\t") or line.startswith("  ")):
                param_docs[current_param] += " " + stripped
        elif current_section is None:
            main_desc_lines.append(line)

    main_desc = "\n".join(main_desc_lines).strip()
    return main_desc, param_docs


def _type_to_json_schema(py_type: Any) -> dict[str, Any]:
    """Convertit un type Python standard en type JSON Schema."""
    if py_type is inspect.Parameter.empty or py_type is Any:
        return {"type": "string"}

    # Gestion des annotations sous forme de chaînes (ex: modules avec 'from __future__ import annotations')
    if isinstance(py_type, str):
        type_map = {
            "int": {"type": "integer"},
            "float": {"type": "number"},
            "bool": {"type": "boolean"},
            "str": {"type": "string"},
            "list": {"type": "array", "items": {"type": "string"}},
            "dict": {"type": "object"},
        }
        stripped = py_type.strip()
        if stripped in type_map:
            return type_map[stripped]
        if "|" in stripped:
            first_part = stripped.split("|")[0].strip()
            if first_part in type_map:
                return type_map[first_part]
        if stripped.startswith("list[") and stripped.endswith("]"):
            inner = stripped[5:-1].strip()
            inner_schema = type_map.get(inner, {"type": "string"})
            return {"type": "array", "items": inner_schema}

    origin = get_origin(py_type)
    args = get_args(py_type)

    # Gestion de Optional[T] / T | None
    if origin in (Union, types.UnionType):
        non_none = [a for a in args if a is not type(None)]
        if non_none:
            return _type_to_json_schema(non_none[0])
        return {"type": "string"}

    if py_type is str:
        return {"type": "string"}
    elif py_type is int:
        return {"type": "integer"}
    elif py_type is float:
        return {"type": "number"}
    elif py_type is bool:
        return {"type": "boolean"}
    elif py_type is list or origin is list:
        item_schema = _type_to_json_schema(args[0]) if args else {"type": "string"}
        return {"type": "array", "items": item_schema}

    return {"type": "string"}


def function_to_tool_def(fn: Callable[..., Any], name: str | None = None, description: str | None = None) -> ToolDef:
    """Construit un ToolDef complet à partir de l'introspection d'une fonction Python."""
    fn_name = name or fn.__name__
    doc_desc, param_docs = _parse_docstring(fn.__doc__)
    fn_desc = description or doc_desc or f"Fonction {fn_name}"

    try:
        sig = inspect.signature(fn, eval_str=True)
    except Exception:
        sig = inspect.signature(fn)
    properties: dict[str, Any] = {}
    required: list[str] = []

    for param_name, param in sig.parameters.items():
        if param_name in ("self", "cls"):
            continue

        param_schema = _type_to_json_schema(param.annotation)

        if param_name in param_docs:
            param_schema["description"] = param_docs[param_name]

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
    """Registre d'outils et exécuteur d'appels."""

    def __init__(self, enable_coercion: bool = True) -> None:
        self._tools: dict[str, ToolDef] = {}
        self.enable_coercion = enable_coercion

    def register(self, fn: Callable[..., Any], name: str | None = None, description: str | None = None) -> ToolDef:
        """Enregistre une fonction Python comme outil."""
        tool_def = function_to_tool_def(fn, name=name, description=description)
        self._tools[tool_def.name] = tool_def
        return tool_def

    def get(self, name: str) -> ToolDef | None:
        """Récupère un outil par son nom."""
        return self._tools.get(name)

    def to_openai_tools(self) -> list[dict[str, Any]]:
        """Exporte les définitions au format JSON attendu par les APIs Ollama / OpenAI."""
        return [tool.to_openai_schema() for tool in self._tools.values()]

    def execute(
        self,
        name: str,
        arguments: dict[str, Any],
        tool_call_id: str = "",
        coerce: bool | None = None,
    ) -> ToolResult:
        """Exécute un outil de manière sécurisée et chronométrée."""
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

        should_coerce = self.enable_coercion if coerce is None else coerce
        coercion_records: list[CoercionRecord] = []
        call_arguments = arguments

        if should_coerce:
            sanitized_args, records, validation_errors = sanitize_arguments(
                tool.parameters, arguments, drop_unexpected=True
            )
            coercion_records = records

            if validation_errors:
                elapsed_ms = (time.perf_counter() - start_time) * 1000
                return ToolResult(
                    tool_call_id=tool_call_id,
                    name=name,
                    output=f"Erreur de validation des arguments pour '{name}' : {'; '.join(validation_errors)}",
                    is_error=True,
                    execution_time_ms=elapsed_ms,
                    coercions=tuple(coercion_records),
                )
            call_arguments = sanitized_args

        try:
            # Vérification des paramètres obligatoires
            required_params = tool.parameters.get("required", [])
            missing_params = [p for p in required_params if p not in call_arguments]
            if missing_params:
                elapsed_ms = (time.perf_counter() - start_time) * 1000
                return ToolResult(
                    tool_call_id=tool_call_id,
                    name=name,
                    output=f"Erreur d'arguments : Paramètre(s) obligatoire(s) manquant(s) : {', '.join(missing_params)}",
                    is_error=True,
                    execution_time_ms=elapsed_ms,
                    coercions=tuple(coercion_records),
                )

            raw_result = tool.handler(**call_arguments)
            elapsed_ms = (time.perf_counter() - start_time) * 1000

            # Conversion en texte pour le contexte LLM
            if isinstance(raw_result, str):
                output_str = raw_result
            elif isinstance(raw_result, (dict, list)):
                output_str = json.dumps(raw_result, ensure_ascii=False)
            else:
                output_str = str(raw_result)

            is_business_error = isinstance(raw_result, str) and (
                output_str.startswith("Erreur") or output_str.startswith("Error")
            )

            return ToolResult(
                tool_call_id=tool_call_id,
                name=name,
                output=output_str,
                is_error=is_business_error,
                execution_time_ms=elapsed_ms,
                coercions=tuple(coercion_records),
            )

        except TypeError as exc:
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            return ToolResult(
                tool_call_id=tool_call_id,
                name=name,
                output=f"Erreur de type d'arguments pour '{name}': {exc}",
                is_error=True,
                execution_time_ms=elapsed_ms,
                coercions=tuple(coercion_records),
            )
        except Exception as exc:
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            return ToolResult(
                tool_call_id=tool_call_id,
                name=name,
                output=f"Exception lors de l'exécution de '{name}': {type(exc).__name__}: {exc}",
                is_error=True,
                execution_time_ms=elapsed_ms,
                coercions=tuple(coercion_records),
            )
