# Étape 4 : Enchaînement Multi-Étapes & Garde-fous Anti-Boucle (harness v2)

Rapport d'expérience réalisé le 3 octobre 2026.

## 1. Objectifs de la version v2

1. **Valider l'enchaînement séquentiel d'outils avec passage de données :**
   Vérifier si le modèle est capable d'utiliser le résultat d'un premier outil ($T_1$) comme argument d'entrée d'un second outil ($T_2$).
2. **Tester les garde-fous de boucle infinie (*Loop Detection*) :**
   Mesurer la capacité du runtime à intercepter un modèle qui répète un appel identique en boucle lorsqu'il rencontre une difficulté ou un résultat inattendu.

---

## 2. Implémentation du Garde-Fou (Harness v2)

Dans [`native_v2.py`](../src/harness_tools/harness/native_v2.py) :
- **Empreinte canonique (*Call Fingerprint*) :** Pour chaque appel d'outil, on calcule `hash(name, json_trié(args))`.
- **Avertissement préventif :** Si une empreinte se répète 2 fois consécutivement, un avertissement système est greffé au résultat de l'outil pour inciter le modèle à changer de stratégie.
- **Coupure de sécurité :** Si la répétition persiste au-delà du seuil (`max_repeated_calls = 2`), le harness coupe l'exécution immédiatement (`loop_detected = True`) sans gaspiller le reste des étapes autorisées.

---

## 3. Résultats observés en direct (`qwen3.5:4b`)

### Scénario 1 : Chaînage réussi Calcul $\rightarrow$ Note
> **Instruction :** *« Calcule 15 * 12, puis crée une note intitulée 'Budget 2026' contenant ce montant. »*

- **Étape 1 (15.6s) :** `ToolCall: calculate(expression="15 * 12")` $\rightarrow$ `ToolResult: 180`
- **Étape 2 (4.6s) :** `ToolCall: create_note(title="Budget 2026", content="180")` $\rightarrow$ Note créée en mémoire.
- **Étape 3 (3.8s) :** Conclusion de la trajectoire.
- **Verdict : SUCCÈS TOTAL.** Le modèle a extrait la valeur `180` renvoyée par le premier outil et l'a injectée comme paramètre `content` du second outil de façon parfaitement autonome.

---

### Scénario 2 : Bug de typage et interception par le Garde-Fou
> **Instruction :** *« Quelle est la date dans 5 jours et ajoute une tâche 'Rapport IA' avec cette date d'échéance. »*

- **Étape 1 (8.3s) :** Le modèle appelle `calculate_date_offset(days="5")` au lieu de `days=5`.
  - Python renvoie : `Erreur de type d'arguments : unsupported type for timedelta days component: str`.
- **Étape 2 (5.3s) :** Face à l'erreur, le modèle panique et **répète exactement le même appel `days="5"`**.
  - Le harness détecte la répétition : `⚠️ [Loop Warning Triggered]`.
  - Le message d'avertissement est injecté dans le retour de l'outil.
- **Étape 3 :** Le modèle récidive une troisième fois sans corriger la chaîne en entier.
  - **Interception immédiate :** `Arrêt de sécurité : Boucle infinie détectée sur l'outil 'calculate_date_offset' avec les mêmes arguments répétés 3 fois.`
- **Verdict : DÉMONSTRATION DU GARDE-FOU.** Le garde-fou a protégé le système d'une boucle infinie.

---

## 4. Enseignements & Pistes pour la v3

Cette expérience met en évidence deux besoins fondamentaux pour la version **v3 (Robustesse & Auto-Correction)** :

1. **Coercion défensive des types simples :**
   En JSON, les modèles (notamment les modèles de taille intermédiaire comme 4B) envoient parfois des nombres sous forme de chaînes (`"5"` au lieu de `5`). Le dispatcher du `ToolRegistry` devrait effectuer un transtypage automatique quand le schéma JSON spécifie `type: "integer"`.
2. **Messages d'erreur didactiques pour l'auto-correction :**
   L'erreur Python brute `unsupported type for timedelta days component: str` est trop cryptique pour un petit LLM. Un message formaté par le harness du type :
   *« Erreur : Le paramètre 'days' attend un entier numérique (ex: 5), vous avez fourni la chaîne "5". »* permettrait au modèle de corriger ses arguments dès le tour suivant au lieu de boucler.
