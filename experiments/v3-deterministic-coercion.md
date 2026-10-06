# Étape 5 : Robustesse, Coercion Déterministe & Auto-Correction Agentique (harness v3)

Rapport d'expérience réalisé le 5 octobre 2026.

## 1. Contexte & Problématique observée en v2

Lors de l'expérience v2 ([`v2-multi-step.md`](v2-multi-step.md)), le scénario de chaînage Date $\rightarrow$ Tâche To-Do avait échoué :
```
Instruction : "Quelle est la date dans 5 jours et ajoute une tâche 'Rapport IA' avec cette date d'échéance."
Échec v2 : calculate_date_offset(days="5")
TypeError: unsupported type for timedelta days component: str
```
Le modèle `qwen3.5:4b` s'était retrouvé bloqué par cette erreur de type, répétant en panique le même appel jusqu'à l'interception par le garde-fou de boucle infinie.

---

## 2. Découverte de la Cause Racine : Le piège de l'introspection Python

En analysant la génération des schémas d'outils, nous avons identifié un piège fondamental de l'écosystème Python :
- Dans les modules utilisant `from __future__ import annotations` (comme `clock.py`), Python stocke les annotations de type sous forme de chaînes littérales (`"int"` au lieu de `<class 'int'>`).
- `inspect.signature(fn)` sans le paramètre `eval_str=True` renvoyait donc `param.annotation = 'int'` (de type `str`).
- La fonction `_type_to_json_schema` ne reconnaissait pas cette chaîne comme l'objet `<class 'int'>`, et basculait par défaut sur `{"type": "string"}`.
- **Conséquence directe :** Le schéma JSON envoyé à Ollama stipulait explicitement que `days` devait être une chaîne ! Le modèle LLM ne faisait donc qu'obéir scrupuleusement au schéma erroné fourni par le harness.

---

## 3. Architecture v3 : La Défense en Profondeur à Deux Piliers

Pour garantir la résilience du runtime sans introduire de dépendance externe lourde (YAGNI strict), la v3 déploie deux lignes de défense complémentaires :

```
             APPEL DU LLM (JSON brut)
                        │
                        ▼
   ┌─────────────────────────────────────────┐
   │ PILIER 1 : Coercion Déterministe (hors-LLM)│
   │  [coercion.py] : Normalisation stricte  │
   └────────────────────┬────────────────────┘
                        │
       ┌────────────────┴────────────────┐
       │ Succès                          │ Échec de coercion ou
       ▼                                 │ Erreur métier de l'outil
  Exécution outil                        ▼
                                ┌─────────────────────────────────────────┐
                                │ PILIER 2 : Rétroaction Didactique (LLM) │
                                │  [format_didactic_error]                │
                                │  Rappel du schéma + Directive réflexive │
                                └────────────────────┬────────────────────┘
                                                     │
                                                     ▼
                                        Tour k+1 : Auto-Correction
```

### Pilier 1 : Normalisation Déterministe ([`coercion.py`](../src/harness_tools/tools/coercion.py))
- **Entiers stricts (`integer`)** : `"5"` $\rightarrow$ `5`, `"5.0"` $\rightarrow$ `5` (vérifié via `.is_integer()`), rejet de `5.5` (refus de la troncature silencieuse pour éviter la corruption sémantique) et de `"cinq"`, rejet des booléens (`True`/`False`).
- **Booléens stricts (`boolean`)** : Neutralisation du piège Python `bool("false") == True`. Validation explicite de `"true"`/`"1"`/`1` et `"false"`/`"0"`/`0`.
- **Désérialisation de listes (`array`)** : Parsing JSON direct des chaînes de tableaux : `'["ia", "cours"]'` $\rightarrow$ `["ia", "cours"]`.
- **Nettoyage des littéraux nuls** : `"null"`, `"None"` $\rightarrow$ `None`.
- **Nettoyage des octets nuls** : Suppression déterministe des `\x00` dans les chaînes pour protéger les bibliothèques C sous-jacentes (`ZoneInfo`, `open`).
- **Filtrage des paramètres hallucinés (`drop_unexpected`)** : Retrait automatique des clés superflues (`thought`, `comment`) générées par les modèles.
- **Auditabilité totale** : Chaque modification produit un [`CoercionRecord`](../src/harness_tools/models.py).

### Pilier 2 : Boucle Réflexive d'Auto-Correction ([`native_v3.py`](../src/harness_tools/harness/native_v3.py))
Lorsqu'une erreur survient (coercion impossible ou ressource inexistante) :
- `format_didactic_error()` structure la réponse transmise au modèle avec :
  1. Le diagnostic précis de l'échec.
  2. Le rappel exhaustif des paramètres attendus par l'outil avec leurs types et descriptions.
  3. Une directive claire : *« Ne répète pas cet appel à l'identique. Corrige tes arguments pour respecter le schéma, ou tente une autre action. »*
- Le harness trace les métriques de résilience : `total_errors_encountered` et `self_corrections_count`.

---

## 4. Résultats Expérimentaux en Direct (Banc Ollama, modèle `qwen2.5:3b`)

Script d'exécution : [`experiments/run_v3_sample.py`](run_v3_sample.py)
Empreinte mémoire : 1.9 Go | Vitesse d'inférence globale : **34.38s pour les 3 scénarios**.

### Scénario 1 : Chaînage nominal Calcul $\rightarrow$ Note
> **Instruction :** *« Calcule 15 * 12, puis crée une note intitulée 'Budget 2026' contenant ce montant. »*
- **Résultat :** **SUCCÈS TOTAL en 2 étapes (18.52s)**.
- Étape 1 : Appel combiné `calculate(15 * 12)` $\rightarrow$ `180` et `create_note(title="Budget 2026", content="180", tags=["budget", "2026"])`.
- Étape 2 : Conclusion textuelle immédiate.

### Scénario 2 : Robustesse de typage Date $\rightarrow$ To-Do (Ancien échec v2)
> **Instruction :** *« Quelle est la date dans 5 jours et ajoute une tâche 'Rapport IA' avec cette date d'échéance. »*
- **Résultat :** **SUCCÈS TOTAL en 2 étapes (4.35s)**.
- Étape 1 : `calculate_date_offset(days=5)` $\rightarrow$ `Samedi 10/10/2026` + `add_todo(task="Rapport IA", due_date="...")`.
- Étape 2 : Confirmation finale.
- *Analyse :* Contrairement à la v2 où `days="5"` provoquait un `TypeError` et une boucle infinie, le typage corrigé et la coercion garantissent une exécution instantanée.

### Scénario 3 : Auto-Correction Agentique (Erreur métier $\rightarrow$ Récupération réflexive)
> **Instruction :** *« Consulte la note 'Recette Tarte' et si elle n'existe pas, crée une note 'Recette Tarte' avec le contenu 'Pommes et cannelle'. »*
- **Étape 1 (2.5s) :** `read_note(title="Recette Tarte")`
  - Retour de l'outil : `❌ [Erreur] : Aucune note trouvée avec le titre 'Recette Tarte'.`
  - L'erreur est immédiatement identifiée par le registry et balisée avec le format didactique.
- **Étape 2 (6.5s) :** 🔄 **[Auto-Correction réussie]**
  - Le modèle analyse l'erreur, confirme l'absence et bifurque vers `create_note` puis vérifie.
- **Étape 3 (2.4s) :** Synthèse finale : *« La note 'Recette Tarte' a été créée avec le contenu "Pommes et cannelle". »*
- **Statut :** **SUCCÈS TOTAL en 3 étapes (11.51s)** | Erreurs : 1 | Auto-corrections : 1.

---

## 5. Bilan Quantitatif Comparatif

| Capacité | v1 (Tool Calling) | v2 (Multi-Step) | v3 (Robustesse & Self-Correction) |
| :--- | :--- | :--- | :--- |
| **Typage des schémas** | Chaînes par défaut | Chaînes par défaut | **Types réels évalués (`integer`, `array`)** |
| **Résistance à `days="5"`** | Crash `TypeError` | Crash $\rightarrow$ Boucle infinie | **Coercion déterministe immédiate (0ms)** |
| **Gestion des erreurs métier** | Non traitée | Répétition en panique | **Rétroaction didactique + Auto-correction** |
| **Observabilité** | Aucune trace | `loop_warning_triggered` | **`CoercionRecord`, `self_corrections_count`** |
| **Couverture de tests** | 24 tests | 28 tests | **45 tests (100% passants)** |
| **Dépendances tierces** | 0 (stdlib pure) | 0 (stdlib pure) | **0 (stdlib pure)** |
