"""Module de normalisation déterministe et de coercion des arguments d'outils."""

from __future__ import annotations

import json
from typing import Any

from harness_tools.models import CoercionRecord


def coerce_value(
    value: Any,
    expected_type: str,
    item_type: str | None = None,
) -> tuple[Any, bool, str | None]:
    """Tente une conversion déterministe d'une valeur vers un type cible JSON Schema.

    Retourne:
        (valeur_convertie, a_ete_modifiee, message_erreur_ou_none)
    """
    # 1. Gestion des valeurs nulles / None
    if value is None:
        return None, False, None

    if isinstance(value, str):
        stripped_lower = value.strip().lower()
        if stripped_lower in ("null", "none"):
            return None, True, None

    # 2. Type attendu : integer
    if expected_type == "integer":
        if isinstance(value, bool):
            return value, False, f"Booléen '{value}' invalide pour un entier"
        if isinstance(value, int):
            return value, False, None
        if isinstance(value, float):
            if value.is_integer():
                return int(value), True, None
            return value, False, f"Flottant non entier '{value}' non convertible en entier sans perte"
        if isinstance(value, str):
            stripped = value.strip()
            try:
                return int(stripped), True, None
            except ValueError:
                pass
            try:
                f = float(stripped)
                if f.is_integer():
                    return int(f), True, None
                return value, False, f"Chaîne décimale '{value}' non convertible en entier sans perte"
            except ValueError:
                return value, False, f"Chaîne '{value}' non convertible en entier"
        return value, False, f"Type '{type(value).__name__}' incompatible avec integer"

    # 3. Type attendu : number (float ou int)
    if expected_type == "number":
        if isinstance(value, bool):
            return value, False, f"Booléen '{value}' invalide pour un nombre"
        if isinstance(value, (int, float)):
            return value, False, None
        if isinstance(value, str):
            stripped = value.strip()
            try:
                f = float(stripped)
                val = int(f) if f.is_integer() else f
                return val, True, None
            except ValueError:
                return value, False, f"Chaîne '{value}' non convertible en nombre"
        return value, False, f"Type '{type(value).__name__}' incompatible avec number"

    # 4. Type attendu : boolean
    if expected_type == "boolean":
        if isinstance(value, bool):
            return value, False, None
        if isinstance(value, (int, float)):
            if value == 1:
                return True, True, None
            elif value == 0:
                return False, True, None
            return value, False, f"Nombre '{value}' non convertible en booléen (attend 0 ou 1)"
        if isinstance(value, str):
            s = value.strip().lower()
            if s in ("true", "1", "yes", "oui", "vrai", "t"):
                return True, True, None
            elif s in ("false", "0", "no", "non", "faux", "f"):
                return False, True, None
            return value, False, f"Chaîne '{value}' non convertible en booléen"
        return value, False, f"Type '{type(value).__name__}' incompatible avec boolean"

    # 5. Type attendu : string
    if expected_type == "string":
        if isinstance(value, str):
            clean_str = value.replace("\x00", "")
            if clean_str != value:
                return clean_str, True, None
            return value, False, None
        if isinstance(value, (int, float, bool)):
            return str(value), True, None
        if isinstance(value, (list, dict)):
            return json.dumps(value, ensure_ascii=False), True, None
        return str(value).replace("\x00", ""), True, None

    # 6. Type attendu : array
    if expected_type == "array":
        if isinstance(value, list):
            if not item_type:
                return value, False, None
            new_list = []
            modified = False
            for idx, item in enumerate(value):
                c_item, c_mod, c_err = coerce_value(item, item_type)
                if c_err:
                    return value, False, f"Élément [{idx}] de la liste invalide : {c_err}"
                if c_mod:
                    modified = True
                new_list.append(c_item)
            return new_list, modified, None

        if isinstance(value, str):
            stripped = value.strip()
            if (stripped.startswith("[") and stripped.endswith("]")) or (
                stripped.startswith("(") and stripped.endswith(")")
            ):
                try:
                    parsed = json.loads(stripped)
                    if isinstance(parsed, list):
                        res, _, err = coerce_value(parsed, "array", item_type=item_type)
                        return res, True, err
                except json.JSONDecodeError:
                    pass
            return value, False, f"Chaîne '{value}' non convertible en tableau"

        return value, False, f"Type '{type(value).__name__}' incompatible avec array"

    # 7. Type non géré ou générique
    return value, False, None


def sanitize_arguments(
    parameters_schema: dict[str, Any],
    arguments: dict[str, Any],
    drop_unexpected: bool = True,
) -> tuple[dict[str, Any], list[CoercionRecord], list[str]]:
    """Assainit déterministement les arguments d'un appel d'outil selon son schéma JSON.

    Args:
        parameters_schema: Schéma JSON complet des paramètres (contient 'properties').
        arguments: Dictionnaire des arguments bruts extraits de l'appel LLM.
        drop_unexpected: Si True, supprime les arguments non déclarés dans le schéma.

    Returns:
        Un tuple (arguments_nettoyés, liste_des_modifications, liste_des_erreurs).
    """
    properties = parameters_schema.get("properties", {})
    sanitized: dict[str, Any] = {}
    records: list[CoercionRecord] = []
    errors: list[str] = []

    for param_name, arg_val in arguments.items():
        # Cas 1 : Argument non déclaré dans le schéma
        if param_name not in properties:
            if drop_unexpected:
                records.append(
                    CoercionRecord(
                        parameter=param_name,
                        original_value=arg_val,
                        coerced_value=None,
                        action="drop_unexpected",
                        detail=f"Paramètre '{param_name}' absent du schéma de l'outil, ignoré déterministement.",
                    )
                )
                continue
            sanitized[param_name] = arg_val
            continue

        # Cas 2 : Argument déclaré -> Vérification et Coercion
        param_spec = properties[param_name]
        expected_type = param_spec.get("type", "string")
        item_spec = param_spec.get("items", {})
        item_type = item_spec.get("type") if isinstance(item_spec, dict) else None

        coerced_val, was_modified, err = coerce_value(arg_val, expected_type, item_type)

        if err:
            errors.append(f"Paramètre '{param_name}': {err}")
            sanitized[param_name] = arg_val
        elif was_modified:
            action = "nullify" if coerced_val is None else "type_cast"
            records.append(
                CoercionRecord(
                    parameter=param_name,
                    original_value=arg_val,
                    coerced_value=coerced_val,
                    action=action,
                    detail=(
                        f"Coercion {type(arg_val).__name__} ({repr(arg_val)}) -> "
                        f"{type(coerced_val).__name__} ({repr(coerced_val)}) vers '{expected_type}'"
                    ),
                )
            )
            sanitized[param_name] = coerced_val
        else:
            sanitized[param_name] = coerced_val

    return sanitized, records, errors
