# Expérience v1 — Tool Calling Natif d'API (Ollama / OpenAI)

Rapport d'expérience réalisé le 3 octobre 2026.

## 1. Objectif de l'expérience

Remplacer la baseline ReAct par prompting textuel (v0) par une implémentation tirant parti du **Tool Calling natif** au niveau des tokens d'Ollama.

Dans cette version :
- Aucun format ReAct textuel (`Thought:`, `Action:`, etc.) n'est imposé dans le system prompt.
- Les outils sont déclarés via le paramètre API officiel `tools: [...]` généré automatiquement par notre [`ToolRegistry`](file:///Users/jeanvangysel/code/website/harness_tools/src/harness_tools/tools/registry.py).
- Le modèle renvoie des objets structurés `tool_calls`.
- Le harness exécute le code Python et réinjecte la réponse avec le rôle officiel `{role: "tool", content: ...}`.

---

## 2. Tableau comparatif direct (v0 ReAct vs v1 Natif)

Mesures réalisées sur la même machine (Mac M4) et le même modèle local (**`qwen3.5:4b`**) :

| Requête | Métrique | v0 (ReAct texte) | v1 (Tool Calling natif) | Gain constaté |
|---|---|---:|---:|:---:|
| **1. Calcul** : *« Combien font 14 * 25 ? »* | Étapes<br>Durée | 2 étapes<br>17.71 s | 2 étapes<br>**13.81 s** | **- 22 % de latence** |
| **2. Date/Heure** : *« Quelle heure est-il actuellement à Paris ? »* | Étapes<br>Durée | 2 étapes<br>62.30 s | 2 étapes<br>**8.48 s** | **7,3× plus rapide** 🚀 |
| **3. Sans outil** : *« Bonjour, qui es-tu ? »* | Étapes<br>Durée | 1 étape<br>6.35 s | 1 étape<br>9.95 s | Réponse v1 plus complète |

---

## 3. Analyse pédagogique des résultats

### 3.1 D'où vient le gain spectaculaire de 7,3× sur la requête 2 ?
Dans la version v0 (ReAct texte) :
1. Le modèle devait rédiger un monologue intérieur verbeux (`Thought: Je dois obtenir l'heure...`).
2. Après l'observation, on lui renvoyait tout le texte accumulé, l'obligeant à relire ses propres réflexions pour en formuler une autre.
3. Le décodage non contraint sur un petit modèle 4B entraîne une dispersion de probabilités et une génération lente de tokens de remplissage.

Dans la version v1 (Tool Calling natif) :
1. **Étape 1 (4.46s) :** Le modèle émet directement l'appel compact `tool_calls: [{"name": "get_current_time", "arguments": {"timezone": "Europe/Paris"}}]`.
2. **Exécution Python (1.81ms) :** La fonction s'exécute quasi-instantanément en mémoire locale.
3. **Étape 2 (4.01s) :** Le modèle reçoit le message propre `{role: "tool", content: "..."}` et produit immédiatement la synthèse : *« Il est actuellement 11h16 en France (heure d'été CEST). »*.
4. **Total : 8.48s**, sans aucune gymnastique de parsing regex ni perte de tokens.

### 3.2 Robustesse structurelle
- **Zéro parsing regex :** L'objet `tool_calls` est désérialisé directement par le protocole JSON de l'API.
- **Rôles sémantiques distincts :** La séparation claire entre `user`, `assistant` et `tool` évite que le modèle ne confonde ce qu'il a dit, ce que l'utilisateur demande et ce que l'environnement renvoie.
- **Conscience des outils :** Sur la requête 3 (*« Bonjour, qui es-tu ? »*), le modèle a inspecté la liste des schémas reçus dans `tools` pour décrire spontanément ses 4 domaines de compétences (notes, to-do, calcul, dates) sans qu'on ait eu besoin de l'écrire dans le system prompt !

---

## 4. Prochaine étape : v2 (Enchaînement multi-outils & Trajectoires complexes)

Nos deux tests (v0 et v1) ont validé le cas nominal à **1 outil simple**.

Dans l'**Étape 3 / v2**, nous devons confronter le harness à des scénarios plus exigeants :
1. **Dépendances multi-étapes séquentielles :**
   - *« Calcule 15 * 12, puis crée une note intitulée 'Budget' avec ce résultat. »* (Outil 1 : `calculate` $\rightarrow$ Outil 2 : `create_note`).
   - *« Quelle est la date dans 5 jours et ajoute une tâche 'Rapport' pour cette échéance. »* (Outil 1 : `calculate_date_offset` $\rightarrow$ Outil 2 : `add_todo`).
2. **Garde-fous de trajectoire :**
   - Que se passe-t-il si le modèle boucle indéfiniment en appelant le même outil ?
   - Comment détecter et interrompre une répétition de boucle (*loop detection*) ?
