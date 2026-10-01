# Harness & Tools construits à la main

Ce projet explore, étape par étape, la construction en Python d’un moteur d'exécution d'outils (**Agent Harness**) et de son banc d'évaluation (**Evaluation Harness**).

Comme pour le projet RAG précédent, l’objectif est **pédagogique** : comprendre et implémenter soi-même les mécanismes fondamentaux (introspection des fonctions, génération de schémas JSON, boucle agentique, gestion d'erreurs, abstention, garde-fous) **sans dépendance à un framework magique**, avant de confronter notre solution à des outils existants (**Smolagents**, **Pydantic-AI**).

---

## 1. Pourquoi « Harness & Tools » ?

Dans l'écosystème IA :
* **Un Outil (Tool)** n'est qu'une fonction déterministe (Python, API REST, etc.) associée à une spécification formelle (schéma JSON) décrivant son nom, son rôle et ses arguments attendus.
* **Un LLM** ne sait rien exécuter par lui-même : il lit du texte et produit du texte (ou des tokens structurés demandant l'appel d'une fonction).
* **Le Harness (ou Runtime Agentique)** est la pièce maîtresse intermédiaire :
  1. Il expose les outils au modèle sous forme compréhensible (prompt ou champ `tools` de l'API).
  2. Il réceptionne l'intention du modèle (`tool_call`).
  3. Il valide les types et arguments par rapport au schéma.
  4. Il exécute la fonction dans un environnement contrôlé (gestion des exceptions, timeouts).
  5. Il formate le résultat et le renvoie au modèle pour poursuivre le raisonnement ou clore la réponse.
  6. Il gère la boucle multi-tours, la mémoire de la conversation, et protège contre les boucles infinies.

En parallèle, un **Harness d'évaluation** mesure si le modèle choisit les bons outils, respecte les signatures, sait enchaîner plusieurs actions et sait s'abstenir quand aucune fonction ne convient.

---

## 2. Domaine support : L'Assistant Personnel & de Tâches

Pour que la complexité réside dans l'ingénierie du harness et non dans le métier, le domaine est volontairement simple et sans ambiguïté :
* **Horloge & Dates (`clock`)** : Obtenir l'heure/date actuelle avec fuseau horaire, calculer un décalage de jours.
* **Calculatrice arithmétique (`calculator`)** : Évaluer des expressions mathématiques de manière sécurisée (analyseur AST, sans `eval`).
* **Gestionnaire de Notes (`notes`)** : Créer, rechercher par mot-clé, lire et lister des notes.
* **Gestionnaire de Tâches To-Do (`todo`)** : Ajouter, lister et cocher des tâches terminées.

Ce domaine permet de couvrir :
1. Des outils en lecture seule (`get_current_time`, `search_notes`).
2. Des outils avec mutation d'état (`create_note`, `add_todo`, `complete_todo`).
3. Des dépendances multi-étapes (ex. : *« Calcule 14 * 25 puis enregistre une note avec le résultat »* ou *« Quelle est la date dans 3 jours et ajoute une tâche pour ce jour-là »*).
4. Des cas d'abstention (ex. : *« Quel temps fait-il à Tokyo ? »* $\rightarrow$ aucun outil météo, le modèle doit s'abstenir d'inventer).

---

## 3. Feuille de route des itérations

Chaque version fera l'objet d'un rapport dans `experiments/` et d'une mesure chiffrée :

- **Étape 1 : Socle & Définition des Outils (en cours)**
  - Introspection automatique des signatures Python (type hints + docstrings) vers le schéma JSON compatible OpenAI/Ollama.
  - Implémentation des outils métiers isolés et testés unitairement.
- **Étape 2 : v0 — ReAct pur en prompt texte**
  - Injection des schémas d'outils dans le system prompt.
  - Formatage imposé (ex: `Action: tool_name`, `Action Input: {...}`).
  - Parsing manuel et boucle d'exécution sans support natif.
- **Étape 3 : v1 — Tool Calling natif (Ollama/OpenAI)**
  - Utilisation du paramètre `tools` de l'API.
  - Validation et dispatch automatique des appels JSON.
- **Étape 4 : v2 — Boucle multi-step & Trajectoire**
  - Enchaînement de plusieurs outils jusqu'à résolution.
  - Détection de boucles infinies et limites de pas.
- **Étape 5 : v3 — Robustesse & Auto-correction**
  - Renvoyer l'erreur d'exécution ou de validation au LLM pour qu'il corrige ses arguments.
- **Étape 6 : v4 — Garde-fous & Confirmation humaine**
  - Interception des actions destructives (suppression de note) nécessitant un accord explicite.
- **Étape 7 : Banc d'évaluation & Métriques**
  - Dataset de test : précision du choix d'outil, validité des arguments, taux d'abstention, nombre d'étapes moyen.
- **Étape 8 : Comparatif avec Smolagents & Pydantic-AI**
  - Réalisation de la même tâche avec ces bibliothèques et confrontation des architectures.

---

## 4. Organisation du code

```text
harness_tools/
├── pyproject.toml
├── README.md
├── src/
│   └── harness_tools/
│       ├── __init__.py
│       ├── models.py              # Types de données : ToolDef, ToolCall, ToolResult, etc.
│       ├── tools/
│       │   ├── __init__.py
│       │   ├── registry.py        # Introspection automatique & registre
│       │   ├── clock.py           # Outil horloge/dates
│       │   ├── calculator.py      # Outil calcul arithmétique (AST)
│       │   ├── notes.py           # Outil notes
│       │   └── todo.py            # Outil to-do
│       ├── llm/
│       │   └── client.py          # Client Ollama unifié (local / cloud)
│       └── harness/
│           ├── loop.py            # Boucle d'exécution agentique
│           └── guardrails.py      # Sécurité et limites
├── tests/
│   ├── test_registry.py
│   └── test_tools.py
├── evaluation/
│   ├── protocol.md
│   └── dataset.json
├── experiments/
└── comparisons/
```
