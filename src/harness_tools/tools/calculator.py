"""Outil Calculatrice sécurisée par analyseur syntaxique AST (sans eval arbitraire)."""

from __future__ import annotations

import ast
import math
import operator
from typing import Any, Callable

# Opérateurs arithmétiques autorisés
_OPERATORS: dict[type[ast.AST], Callable[..., Any]] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}

# Fonctions mathématiques autorisées
_SAFE_FUNCTIONS: dict[str, Callable[..., Any]] = {
    "abs": abs,
    "round": round,
    "min": min,
    "max": max,
    "sqrt": math.sqrt,
    "pow": math.pow,
    "log": math.log,
    "exp": math.exp,
    "ceil": math.ceil,
    "floor": math.floor,
}

_SAFE_CONSTANTS: dict[str, float] = {
    "pi": math.pi,
    "e": math.e,
}


def _eval_node(node: ast.AST) -> float | int:
    """Évalue récursivement un nœud de l'arbre syntaxique abstrait."""
    if isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float)):
            return node.value
        raise ValueError(f"Littéral non numérique interdit : {node.value!r}")

    elif isinstance(node, ast.BinOp):
        op_type = type(node.op)
        if op_type not in _OPERATORS:
            raise ValueError(f"Opérateur binaire non supporté : {op_type.__name__}")
        left = _eval_node(node.left)
        right = _eval_node(node.right)
        
        # Protection contre la division par zéro
        if op_type in (ast.Div, ast.FloorDiv, ast.Mod) and right == 0:
            raise ZeroDivisionError("Division par zéro.")
        # Protection contre les puissances gigantesques
        if op_type is ast.Pow and (right > 1000 or (isinstance(left, (int, float)) and left > 1000 and right > 10)):
            raise ValueError("Calcul trop volumineux (dépassement de capacité).")
            
        return _OPERATORS[op_type](left, right)

    elif isinstance(node, ast.UnaryOp):
        op_type = type(node.op)
        if op_type not in _OPERATORS:
            raise ValueError(f"Opérateur unaire non supporté : {op_type.__name__}")
        operand = _eval_node(node.operand)
        return _OPERATORS[op_type](operand)

    elif isinstance(node, ast.Name):
        name = node.id.lower()
        if name in _SAFE_CONSTANTS:
            return _SAFE_CONSTANTS[name]
        raise ValueError(f"Constante ou variable inconnue : '{node.id}'")

    elif isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name):
            raise ValueError("Appels de fonctions complexes non autorisés.")
        func_name = node.func.id.lower()
        if func_name not in _SAFE_FUNCTIONS:
            raise ValueError(f"Fonction interdite ou inconnue : '{func_name}'")
        args = [_eval_node(arg) for arg in node.args]
        return _SAFE_FUNCTIONS[func_name](*args)

    raise ValueError(f"Expression non autorisée ou invalide : {type(node).__name__}")


def calculate(expression: str) -> str:
    """Calcule le résultat d'une expression mathématique arithmétique.

    Supporte les opérations +, -, *, /, //, %, **, parenthèses, constantes (pi, e) et fonctions usuelles (sqrt, round, abs, min, max).

    Args:
        expression: L'expression mathématique à évaluer (ex: '25 * 4 + 10', 'sqrt(144) + 8', 'round(100 / 3, 2)').
    """
    clean_expr = expression.strip()
    if not clean_expr:
        return "Erreur : Expression vide."

    try:
        parsed = ast.parse(clean_expr, mode="eval")
        result = _eval_node(parsed.body)
        
        # Formatage lisible du résultat
        if isinstance(result, float) and result.is_integer():
            result = int(result)
        return str(result)
    except ZeroDivisionError:
        return "Erreur : Division par zéro."
    except SyntaxError as err:
        return f"Erreur de syntaxe mathématique : {err.msg}"
    except Exception as err:
        return f"Erreur de calcul : {err}"
