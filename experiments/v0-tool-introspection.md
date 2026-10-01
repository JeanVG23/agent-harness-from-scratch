# Étape 1 — Socle, Introspection & Définition des Outils

Rapport technique rédigé le 1er octobre 2026.

## 1. Objectifs de l'étape

1. Poser les fondations de données (`models.py`) pour représenter les concepts du Tool Calling indépendamment de tout framework externe.
2. Implémenter un moteur d'introspection en Python pur (`registry.py`) capable de transformer n'importe quelle fonction documentée en un schéma JSON conforme à la spécification fonctionnelle standard (utilisée par OpenAI, Ollama, Anthropic).
3. Créer un jeu d'outils cohérent pour notre assistant personnel, couvrant :
   - Des opérations déterministes en lecture seule (`clock`).
   - Des calculs mathématiques sécurisés (`calculator`).
   - Des opérations avec état et persistance en mémoire (`notes`, `todo`).
4. Valider l'exécution isolée et la gestion défensive des erreurs par une suite de tests unitaires.

---

## 2. Choix techniques et Raisonnement

### 2.1 Introspection Python vs Déclaration Manuelle
* **Problème :** Écrire les schémas JSON à la main pour chaque outil est fastidieux, propice aux erreurs de syntaxe, et crée un risque de divergence entre le code Python réel et la spécification donnée au LLM.
* **Solution retenue :** Utiliser la réflexivité de Python (`inspect.signature` et parsing de `__doc__`).
* **Mécanique interne :**
  - **Types :** Extraction des annotations de types (`str`, `int`, `float`, `bool`, `list[T]`, `Optional[T]`) et conversion vers le standard JSON Schema (`string`, `integer`, `number`, `boolean`, `array`, `anyOf`).
  - **Descriptions :** Extraction automatique de la description générale et de chaque argument grâce au découpage des docstrings (formats Google `Args:` et Sphinx `:param:`).
  - **Obligatoire vs Optionnel :** Détection de l'absence de valeur par défaut (`inspect.Parameter.empty`) pour peupler le tableau `required`.

### 2.2 Sécurité de la Calculatrice (AST vs `eval`)
* **Problème :** Donner un outil de calcul à un agent présente un risque d'injection de code si l'on utilise un simple `eval()`.
* **Solution retenue :** Analyseur syntaxique basé sur `ast.parse(mode="eval")`.
* **Sécurité :** Seuls les nœuds autorisés (`ast.BinOp`, `ast.UnaryOp`, constantes numériques et une liste blanche de fonctions `math`) sont exécutés. Toute tentative d'accès à des attributs, variables globales, ou imports (`__import__`) lève une exception et protège le système.

### 2.3 Structure canonique des échanges
Les dataclasses `ToolDef`, `ToolCall`, `ToolResult` et `Message` normalisent le format :
* `ToolCall` : identifiant d'appel, nom de la fonction, arguments décodés.
* `ToolResult` : référence à l'identifiant d'appel, chaîne de sortie textuelle, booléen d'erreur `is_error`, et métrique de durée `execution_time_ms`.
* `execute()` défensif : le registre ne lève jamais d'exception non interceptée vers l'appelant ; il renvoie un `ToolResult(is_error=True, output="...")` clair et exploitable par le LLM pour sa boucle d'auto-correction.

---

## 3. Résultats des tests unitaires

Exécution via `uv run pytest` : **13 tests passés avec succès** (0.13s) :
- `test_function_introspection_schema` : validation de la fidélité du schéma généré.
- `test_openai_schema_format` : conformité avec l'enveloppe `{"type": "function", "function": ...}`.
- `test_tool_execution_success` : dispatch dynamique et exécution nominale.
- `test_tool_execution_missing_required` : capture des arguments manquants.
- `test_tool_execution_unknown_tool` : capture des outils inconnus avec suggestion des outils disponibles.
- `test_tool_execution_catches_exception` : capture des exceptions applicatives (ex. division par zéro).
- `test_calculator_*` : arithmétique, précédence des opérateurs, fonctions mathématiques, sécurité.
- `test_clock_*` : date, heure, fuseaux IANA, décalages relatifs.
- `test_notes_*` : cycle de vie complet CRUD, recherche par mot-clé, tags.
- `test_todo_*` : ajout, filtrage par statut, clôture de tâche.

---

## 4. Prochaine étape

Passer à l'**Étape 2 (Client LLM et premières boucles d'exécution)** :
1. Implémenter le client Ollama léger (`src/harness_tools/llm/client.py`) supportant le streaming, la complétion JSON et les appels `tools: [...]`.
2. Mettre en place la version **v0** (ReAct via prompting texte pur) et **v1** (Tool Calling natif).
