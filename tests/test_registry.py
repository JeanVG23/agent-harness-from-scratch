"""Tests unitaires pour ToolRegistry et l'introspection automatique des schémas JSON."""

from harness_tools.models import ToolResult
from harness_tools.tools.registry import ToolRegistry, function_to_tool_def


def dummy_func(
    city: str,
    count: int = 5,
    verbose: bool = False,
    tags: list[str] = [],  # noqa: B006 (le défaut alimente le schéma testé)
) -> str:
    """Recherche des lieux dans une ville donnée.

    Args:
        city: Le nom de la ville à cibler.
        count: Nombre maximal de résultats souhaités.
        verbose: Afficher ou non les détails complets.
        tags: Liste des tags de filtrage.
    """
    return f"{city}:{count}:{verbose}:{len(tags)}"


def test_function_introspection_schema():
    tool_def = function_to_tool_def(dummy_func)

    assert tool_def.name == "dummy_func"
    assert "Recherche des lieux" in tool_def.description

    params = tool_def.parameters
    assert params["type"] == "object"
    assert params["required"] == ["city"]

    props = params["properties"]
    assert props["city"]["type"] == "string"
    assert "nom de la ville" in props["city"]["description"]

    assert props["count"]["type"] == "integer"
    assert props["count"]["default"] == 5
    assert "maximal de résultats" in props["count"]["description"]

    assert props["verbose"]["type"] == "boolean"
    assert props["verbose"]["default"] is False

    assert props["tags"]["type"] == "array"
    assert props["tags"]["items"]["type"] == "string"


def test_openai_schema_format():
    registry = ToolRegistry()
    registry.register(dummy_func)
    openai_tools = registry.to_openai_tools()

    assert len(openai_tools) == 1
    tool_schema = openai_tools[0]
    assert tool_schema["type"] == "function"
    assert "function" in tool_schema
    assert tool_schema["function"]["name"] == "dummy_func"
    assert tool_schema["function"]["parameters"]["type"] == "object"


def test_tool_execution_success():
    registry = ToolRegistry()
    registry.register(dummy_func)

    res = registry.execute("dummy_func", {"city": "Paris", "count": 3})
    assert isinstance(res, ToolResult)
    assert not res.is_error
    assert res.output == "Paris:3:False:0"
    assert res.execution_time_ms >= 0


def test_tool_execution_missing_required():
    registry = ToolRegistry()
    registry.register(dummy_func)

    res = registry.execute("dummy_func", {"count": 10})
    assert res.is_error
    assert "Paramètre(s) obligatoire(s) manquant(s)" in res.output
    assert "city" in res.output


def test_tool_execution_unknown_tool():
    registry = ToolRegistry()
    registry.register(dummy_func)

    res = registry.execute("non_existent_tool", {})
    assert res.is_error
    assert "n'existe pas" in res.output


def test_tool_execution_catches_exception():
    def exploding_tool(x: int) -> int:
        """Outil qui plante volontairement."""
        return 10 // x

    registry = ToolRegistry()
    registry.register(exploding_tool)

    res = registry.execute("exploding_tool", {"x": 0})
    assert res.is_error
    assert "ZeroDivisionError" in res.output
