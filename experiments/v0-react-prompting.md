# Expérience v0 — Baseline ReAct par Prompting Textuel

Rapport d'expérience réalisé le 3 octobre 2026.

## 1. Objectif de l'expérience

Tester la faisabilité et la robustesse de l'approche historique **ReAct (Reasoning + Acting, Yao et al. 2022)** sur notre assistant personnel sans utiliser les fonctionnalités natives de *Tool Calling* d'Ollama.

Dans cette baseline :
- Les outils et leurs types sont injectés sous forme de texte brut dans le *system prompt*.
- Le modèle doit formuler ses intentions avec la syntaxe imposée : `Thought:`, `Action:`, `Action Input:`, `Final Answer:`.
- Le runtime Python utilise des expressions régulières pour détecter l'action, intercepter l'appel, exécuter la fonction Python et réinjecter `Observation: <résultat>`.

---

## 2. Configuration du test

- **Modèle testé :** `qwen3.5:4b` (tournant en local sur Mac M4).
- **Température :** `0.0`.
- **Harness :** [`ReActHarnessV0`](file:///Users/jeanvangysel/code/website/harness_tools/src/harness_tools/harness/react_v0.py) avec limite de 4 étapes max.
- **Registre d'outils :** `calculator`, `clock`, `notes`, `todo`.
- **Script exécuté :** [`experiments/run_v0_sample.py`](file:///Users/jeanvangysel/code/website/harness_tools/experiments/run_v0_sample.py).

---

## 3. Résultats observés en direct

| Requête | Outil attendu | Étapes | Durée | Statut | Comportement observé |
|---|---|---:|---:|:---:|---|
| *« Combien font 14 * 25 ? »* | `calculate` | 2 | 17.7s | **Succès** | Choisit `calculate`, passe `{"expression": "14 * 25"}`, exploite l'observation `350` et conclut. |
| *« Quelle heure est-il actuellement à Paris ? »* | `get_current_time` | 2 | 62.3s | **Succès** | Déduit correctement le fuseau IANA `Europe/Paris`, lit l'observation et reformule la date/heure. |
| *« Bonjour, qui es-tu ? »* | Aucun (réponse directe) | 1 | 6.4s | **Succès** | S'abstient proprement d'appeler un outil et produit directement `Final Answer:`. |

---

## 4. Analyse critique (Les limites du ReAct textuel)

Même si les trois requêtes ont abouti, ce banc d'essai met en lumière des faiblesses structurelles majeures :

1. **Latence très élevée (jusqu'à 62s pour une requête à 1 outil) :**
   - Le modèle génère beaucoup de tokens "bavards" pour chaque transition (`Thought: Je dois obtenir l'heure...`).
   - À chaque tour, tout l'historique textuel (`Thought + Action + Action Input + Observation`) est ré-injecté, ce qui ré-échantillonne tout le contexte.
2. **Fragilité du parsing regex :**
   - Le succès dépend entièrement du respect strict de la syntaxe par le modèle. Si le LLM produit ```json ou oublie les accolades autour des arguments, le harness doit multiplier les heuristiques défensives.
3. **Risque d'hallucination de l'Observation :**
   - Le modèle a une tendance naturelle à vouloir deviner lui-même le résultat de l'outil et à rédiger `Observation:` dans sa propre complétion. Le harness a dû intégrer une coupure défensive systématique sur le mot `Observation:`.
4. **Absence de garantie de schéma :**
   - Les arguments JSON ne sont pas contraints au moment du décodage par le moteur d'inférence. Si un argument est mal typé (ex: `days: "cinq"` au lieu de `days: 5`), l'erreur ne se manifeste qu'au runtime Python.

---

## 5. Motivation pour la version v1 (Tool Calling natif)

Ces limites motivent directement le passage au **Tool Calling natif** :
- Le schéma JSON est transmis directement dans le payload de l'API (`tools: [...]`).
- L'inférence est guidée par une grammaire formelle au niveau des logits de sortie.
- Plus besoin de regex : le LLM renvoie directement un champ `tool_calls` structuré.
