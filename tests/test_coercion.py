"""Tests unitaires pour la normalisation et la coercion déterministe des arguments."""

from harness_tools.tools.clock import calculate_date_offset
from harness_tools.tools.coercion import coerce_value, sanitize_arguments
from harness_tools.tools.registry import ToolRegistry


def test_coerce_integer():
    # String numérique
    val, mod, err = coerce_value("5", "integer")
    assert val == 5 and mod is True and err is None

    # String avec espaces
    val, mod, err = coerce_value("  42  ", "integer")
    assert val == 42 and mod is True and err is None

    # String flottante représentant un entier exact
    val, mod, err = coerce_value("5.0", "integer")
    assert val == 5 and mod is True and err is None

    # Flottant exact
    val, mod, err = coerce_value(10.0, "integer")
    assert val == 10 and mod is True and err is None

    # Entier déjà correct
    val, mod, err = coerce_value(7, "integer")
    assert val == 7 and mod is False and err is None

    # Échecs attendus : perte de précision
    val, mod, err = coerce_value(5.5, "integer")
    assert mod is False and err is not None

    val, mod, err = coerce_value("5.5", "integer")
    assert mod is False and err is not None

    # Échec attendu : chaîne non numérique
    val, mod, err = coerce_value("cinq", "integer")
    assert mod is False and err is not None

    # Piège Python : un booléen ne doit pas être silencieusement casté en entier
    val, mod, err = coerce_value(True, "integer")
    assert mod is False and err is not None


def test_coerce_number():
    # String décimale
    val, mod, err = coerce_value("3.14", "number")
    assert val == 3.14 and mod is True and err is None

    # String entière vers number
    val, mod, err = coerce_value("42", "number")
    assert val == 42 and mod is True and err is None

    # Déjà float
    val, mod, err = coerce_value(2.718, "number")
    assert val == 2.718 and mod is False and err is None

    # Échec : texte alphabétique
    val, mod, err = coerce_value("pi", "number")
    assert mod is False and err is not None


def test_coerce_boolean_strict():
    # Chaînes True
    for truthy_str in ("true", "True", "1", "yes", "oui", "vrai"):
        val, mod, err = coerce_value(truthy_str, "boolean")
        assert val is True and mod is True and err is None

    # Chaînes False - Évite le piège bool("false") == True de Python !
    for falsy_str in ("false", "False", "0", "no", "non", "faux"):
        val, mod, err = coerce_value(falsy_str, "boolean")
        assert val is False and mod is True and err is None

    # Nombres 1 et 0
    val, mod, err = coerce_value(1, "boolean")
    assert val is True and mod is True and err is None

    val, mod, err = coerce_value(0, "boolean")
    assert val is False and mod is True and err is None

    # Déjà booléen
    val, mod, err = coerce_value(True, "boolean")
    assert val is True and mod is False and err is None

    # Invalide
    val, mod, err = coerce_value(2, "boolean")
    assert mod is False and err is not None

    val, mod, err = coerce_value("maybe", "boolean")
    assert mod is False and err is not None


def test_coerce_string():
    # Déjà string
    val, mod, err = coerce_value("Paris", "string")
    assert val == "Paris" and mod is False and err is None

    # Entier vers string
    val, mod, err = coerce_value(123, "string")
    assert val == "123" and mod is True and err is None

    # Bool vers string
    val, mod, err = coerce_value(True, "string")
    assert val == "True" and mod is True and err is None

    # Suppression des octets nuls (\x00)
    val, mod, err = coerce_value("Europe\x00/Paris", "string")
    assert val == "Europe/Paris" and mod is True and err is None


def test_coerce_array():
    # Déjà liste
    val, mod, err = coerce_value(["a", "b"], "array")
    assert val == ["a", "b"] and mod is False and err is None

    # Chaîne JSON sérialisée
    val, mod, err = coerce_value('["ia", "cours"]', "array")
    assert val == ["ia", "cours"] and mod is True and err is None

    # Liste d'entiers avec éléments à convertir
    val, mod, err = coerce_value(["1", "2", 3], "array", item_type="integer")
    assert val == [1, 2, 3] and mod is True and err is None

    # Invalide
    val, mod, err = coerce_value("not_a_list", "array")
    assert mod is False and err is not None


def test_coerce_null_literals():
    for null_val in ("null", "None", "NULL", "none", None):
        val, mod, _err = coerce_value(null_val, "string")
        if null_val is None:
            assert val is None and mod is False
        else:
            assert val is None and mod is True


def test_sanitize_arguments_drop_unexpected():
    schema = {
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "limit": {"type": "integer"},
        },
    }
    raw_args = {
        "query": "intelligence artificielle",
        "limit": "10",
        "thought": "Je dois chercher les documents",  # Paramètre halluciné par le LLM
    }

    sanitized, records, errors = sanitize_arguments(schema, raw_args, drop_unexpected=True)

    assert errors == []
    assert "thought" not in sanitized
    assert sanitized["query"] == "intelligence artificielle"
    assert sanitized["limit"] == 10

    # Vérification de l'observabilité
    actions = [r.action for r in records]
    assert "type_cast" in actions
    assert "drop_unexpected" in actions


def test_registry_integration_solves_v2_breakage():
    """Vérifie que calculate_date_offset(days='5') qui plantait en v2 fonctionne grâce à la coercion."""
    registry = ToolRegistry(enable_coercion=True)
    registry.register(calculate_date_offset)

    # Appel avec chaîne au lieu d'un int (comme dans le log v2)
    result = registry.execute("calculate_date_offset", {"days": "5"})

    assert not result.is_error
    assert len(result.coercions) == 1
    assert result.coercions[0].parameter == "days"
    assert result.coercions[0].original_value == "5"
    assert result.coercions[0].coerced_value == 5


def test_registry_integration_explicit_validation_error():
    """Vérifie qu'un argument non convertible produit une erreur didactique et non un crash python."""
    registry = ToolRegistry(enable_coercion=True)
    registry.register(calculate_date_offset)

    result = registry.execute("calculate_date_offset", {"days": "cinq"})

    assert result.is_error
    assert "Erreur de validation des arguments" in result.output
    assert "days" in result.output


def test_registry_can_disable_coercion_for_benchmarking():
    """Vérifie que l'on peut désactiver la coercion pour reproduire les échecs v2."""
    registry = ToolRegistry(enable_coercion=False)
    registry.register(calculate_date_offset)

    # En mode sans coercion, Python lève son TypeError comme en v2
    result = registry.execute("calculate_date_offset", {"days": "5"})

    assert result.is_error
    assert "Erreur de type d'arguments" in result.output
