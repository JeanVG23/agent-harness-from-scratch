# Harness & Tools construits à la main

Ce projet explore, étape par étape, la construction en Python d’un moteur d'exécution d'outils (**Agent Harness**) et de son banc d'évaluation (**Evaluation Harness**).

L’objectif est **pédagogique et architectural** : comprendre et implémenter soi-même les mécanismes fondamentaux (introspection des fonctions, génération de schémas JSON, boucle agentique, gestion d'erreurs, abstention, garde-fous) **sans dépendance à un framework magique**, avant de confronter notre solution à des outils existants (**Smolagents**, **Pydantic-AI**).

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
* **Gestionnaire de Notes (`notes`)** : Créer, rechercher par mot-clé, lire et lister des notes (stockage mémoire).
* **Gestionnaire de Tâches To-Do (`todo`)** : Ajouter, lister et cocher des tâches terminées (stockage mémoire).

Ce domaine permet de couvrir :
1. Des outils en lecture seule (`get_current_time`, `search_notes`).
2. Des outils avec mutation d'état (`create_note`, `add_todo`, `complete_todo`).
3. Des dépendances multi-étapes (*« Calcule 14 * 25 puis enregistre une note avec le résultat »*).
4. Des cas d'abstention (*« Quel temps fait-il à Tokyo ? »* $\rightarrow$ aucun outil météo, le modèle doit s'abstenir d'inventer).

---

## 3. Feuille de route des itérations

Chaque version fait l'objet d'un rapport documenté et chiffré dans `experiments/` :

- [x] **Étape 1 : Socle & Définition des Outils**
  - Introspection automatique des signatures Python (type hints + docstrings) vers schéma JSON compatible OpenAI/Ollama.
  - Implémentation des outils métiers isolés, registre centralisé et tests unitaires.
  - 📄 Rapport : [`experiments/v0-tool-introspection.md`](experiments/v0-tool-introspection.md)
- [x] **Étape 2 : v0 — ReAct pur en prompt texte**
  - Injection des schémas d'outils dans le system prompt.
  - Formatage imposé (`Thought` / `Action` / `Action Input` / `Final Answer`).
  - Parsing manuel par regex et exécution sans support natif d'API.
  - 📄 Rapport : [`experiments/v0-react-prompting.md`](experiments/v0-react-prompting.md)
- [x] **Étape 3 : v1 — Tool Calling natif (Ollama/OpenAI)**
  - Utilisation du paramètre `tools` natif d'API avec payload JSON structuré.
  - Comparatif quantitatif v0 vs v1 (latence, fidélité aux schémas, tokens consommés).
  - 📄 Rapports : [`experiments/v1-native-tool-calling.md`](experiments/v1-native-tool-calling.md) et [`experiments/v0-v1-architecture-comparison.md`](experiments/v0-v1-architecture-comparison.md)
- [x] **Étape 4 : v2 — Boucle multi-step & Trajectoire**
  - Enchaînement séquentiel d'outils avec passage de données entre étapes.
  - Historique de trajectoire, détection d'empreinte d'appels (*Call Fingerprint*) et coupure anti-boucle infinie.
  - 📄 Rapport : [`experiments/v2-multi-step.md`](experiments/v2-multi-step.md)
- [x] **Étape 5 : v3 — Robustesse, Coercion déterministe & Auto-correction**
  - **Pilier 1 (Déterministe)** : Résolution du piège d'introspection Python (`eval_str=True`) et normalisation stricte sans LLM (`coercion.py`, entiers, booléens, tableaux, octets nuls).
  - **Pilier 2 (Agentique)** : Rétroaction didactique avec rappel de schéma et boucle réflexive d'auto-correction lors des erreurs métier.
  - 📄 Rapport : [`experiments/v3-deterministic-coercion.md`](experiments/v3-deterministic-coercion.md)
- [ ] **Étape 6 : v4 — Garde-fous & Confirmation humaine**
  - Interception des actions destructives (suppression de note) nécessitant un accord explicite.
- [ ] **Étape 7 : Banc d'évaluation & Métriques**
  - Dataset de test : précision du choix d'outil, validité des arguments, taux d'abstention.
- [ ] **Étape 8 : Comparatif avec Smolagents & Pydantic-AI**
  - Réalisation de la même tâche avec ces bibliothèques et confrontation des architectures.

---

## 4. Organisation du code

```text
agent-harness-from-scratch/
├── pyproject.toml
├── LICENSE
├── README.md
├── src/
│   └── harness_tools/
│       ├── __init__.py
│       ├── models.py              # Types de données : ToolDef, ToolCall, ToolResult, CoercionRecord, Message
│       ├── tools/
│       │   ├── __init__.py
│       │   ├── registry.py        # Introspection automatique & registre d'outils
│       │   ├── coercion.py        # Normalisation déterministe des types & assainissement
│       │   ├── clock.py           # Outil horloge / dates
│       │   ├── calculator.py      # Outil calcul arithmétique (AST sécurisé)
│       │   ├── notes.py           # Outil gestionnaire de notes en mémoire
│       │   ├── todo.py            # Outil to-do list en mémoire
│       │   └── default_tools.py   # Collection des outils par défaut
│       ├── llm/
│       │   ├── __init__.py
│       │   └── client.py          # Client HTTP standard Ollama (local / cloud)
│       └── harness/
│           ├── __init__.py
│           ├── react_v0.py        # Runtime v0 : ReAct prompté + parseur regex
│           ├── native_v1.py       # Runtime v1 : Tool Calling natif d'API (1 tour)
│           ├── native_v2.py       # Runtime v2 : Multi-étapes & Détection de boucles infinies
│           └── native_v3.py       # Runtime v3 : Robustesse, Coercion & Auto-correction
├── tests/
│   ├── test_client.py             # Tests unitaires hermétiques du client HTTP
│   ├── test_coercion.py           # Tests unitaires de la normalisation déterministe
│   ├── test_native_v1.py          # Tests unitaires du harness v1 (mocks)
│   ├── test_native_v2.py          # Tests unitaires du harness v2 (multi-step & boucles)
│   ├── test_native_v3.py          # Tests unitaires du harness v3 (robustesse & auto-correction)
│   ├── test_react_v0.py           # Tests unitaires du harness v0 (mocks)
│   ├── test_registry.py           # Tests de l'introspection et du registre
│   └── test_tools.py              # Tests fonctionnels des outils métiers
└── experiments/
    ├── v0-tool-introspection.md   # Spécification et benchmark des schémas JSON
    ├── v0-react-prompting.md      # Résultats d'expérience v0 (ReAct)
    ├── v1-native-tool-calling.md  # Résultats d'expérience v1 (Tool Calling natif)
    ├── v0-v1-architecture-comparison.md # Analyse comparative et diagrammes de flux
    ├── v2-multi-step.md           # Résultats d'expérience v2 (Chaînage & Garde-fous)
    ├── v3-deterministic-coercion.md # Résultats d'expérience v3 (Robustesse & Auto-correction)
    ├── run_v0_sample.py           # Script d'exécution live v0 (Ollama)
    ├── run_v1_comparison.py       # Benchmark comparatif en direct v0 vs v1
    ├── run_v2_sample.py           # Test live multi-étapes v2
    └── run_v3_sample.py           # Test live robustesse & auto-correction v3
```

---

## 5. Démarrage rapide

### Prérequis
* Python `>= 3.11`
* Gestionnaire de paquets [uv](https://docs.astral.sh/uv/) (recommandé) ou `pip`
* [Ollama](https://ollama.ai/) avec un modèle local (ex. `qwen2.5:7b` ou `minimax-m3:cloud`) pour exécuter les benchmarks réels.

### Installation

```bash
git clone git@github.com:JeanVG23/agent-harness-from-scratch.git
cd agent-harness-from-scratch
uv sync
```

### Lancer les tests unitaires
Les tests sont **100 % hermétiques** (aucun serveur LLM ou accès réseau externe requis, temps d'exécution < 100 ms) :

```bash
uv run pytest
```

### Lancer les benchmarks réels (avec Ollama)
Assurez-vous qu'Ollama est démarré localement :

```bash
# Démonstration du runtime ReAct v0
uv run python experiments/run_v0_sample.py

# Benchmark comparatif direct v0 (ReAct) vs v1 (Natif)
uv run python experiments/run_v1_comparison.py

# Démonstration du runtime multi-étapes v2
uv run python experiments/run_v2_sample.py

# Démonstration du runtime robuste v3 (coercion + auto-correction)
uv run python experiments/run_v3_sample.py
```
