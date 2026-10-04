# Architecture & Flux d'Exécution : De v0 à v2

Ce document synthétise les différences architecturales et mécaniques entre l'approche **v0 (ReAct par Prompting Textuel)**, l'approche **v1 (Tool Calling Natif d'API)** et l'approche **v2 (Enchaînement Multi-Étapes & Garde-Fous Anti-Boucle)**.

---

## 1. Principe Fondamental : Qui Fait Quoi ?

Avant d'examiner les flux, rappelons la frontière d'exécution :
* **Le LLM (Ollama) :** Est un système *stateless* (sans état) qui génère des tokens probables. Il n'a **aucun terminal**, aucun accès réseau direct, et ne peut exécuter aucune ligne de code.
* **Le Harness (notre runtime Python local) :** Est le moteur exécutif. Il détient les fonctions Python réelles ([`clock.py`](file:///Users/jeanvangysel/code/website/harness_tools/src/harness_tools/tools/clock.py), [`calculator.py`](file:///Users/jeanvangysel/code/website/harness_tools/src/harness_tools/tools/calculator.py), [`notes.py`](file:///Users/jeanvangysel/code/website/harness_tools/src/harness_tools/tools/notes.py), [`todo.py`](file:///Users/jeanvangysel/code/website/harness_tools/src/harness_tools/tools/todo.py)), appelle l'API d'Ollama, valide les données, exécute les calculs en mémoire et réinjecte l'information.

---

## 2. Diagramme de Séquence : v0 (ReAct Prompté)

Dans la version v0 ([`react_v0.py`](file:///Users/jeanvangysel/code/website/harness_tools/src/harness_tools/harness/react_v0.py)), tout repose sur du **texte brut** et du **parsing par expressions régulières (Regex)**.

```mermaid
sequenceDiagram
    autonumber
    actor User as Utilisateur
    participant Harness as Harness Python (react_v0)
    participant Regex as Parseur Regex & JSON
    participant Registry as ToolRegistry (Python local)
    participant Ollama as Serveur Ollama (LLM)

    User->>Harness: run("Combien font 14 * 25 ?")
    Note over Harness: Construit le prompt avec la description textuelle des outils<br/>et le format imposé (Thought / Action / Action Input)
    
    Harness->>Ollama: POST /api/chat (prompt texte complet, stop=["\nObservation:"])
    Note over Ollama: Le LLM génère du texte libre :<br/>"Thought: Je dois calculer.<br/>Action: calculate<br/>Action Input: {\"expression\": \"14 * 25\"}"
    Ollama-->>Harness: Texte brut généré
    
    Harness->>Regex: parse_react_output(texte)
    Regex-->>Harness: tool_name="calculate", args={"expression": "14 * 25"}
    
    Harness->>Registry: execute("calculate", {"expression": "14 * 25"})
    Note over Registry: Exécution en mémoire Python : eval AST sécurisé
    Registry-->>Harness: ToolResult(output="350")
    
    Note over Harness: Concaténation manuelle au prompt :<br/>+ "\nObservation: 350\nThought:"
    Harness->>Ollama: POST /api/chat (prompt accumulé)
    Note over Ollama: Le LLM reprend son monologue :<br/>"Final Answer: Le résultat est 350."
    Ollama-->>Harness: Texte avec Final Answer
    
    Harness->>Regex: parse_react_output(texte)
    Regex-->>Harness: final_answer="Le résultat est 350."
    Harness-->>User: "Le résultat est 350."
```

### Vulnérabilités & Coûts de la v0 :
1. **Fragilité syntaxique (*Parsing Hell*) :** Si le LLM oublie un guillemet, modifie la casse (`action:` au lieu de `Action:`), ou ajoute du bavardage, la regex échoue.
2. **Besoin de *Stop Sequences* :** Nécessité absolue de couper la génération (`\nObservation:`) pour empêcher le LLM d'inventer lui-même une fausse observation.
3. **Surcoût en tokens & latence :** Génération forcée de monologues verbeux ralentissant l'inférence (jusqu'à 7× plus lent sur petit modèle).

---

## 3. Diagramme de Séquence : v1 (Tool Calling Natif 1-Shot)

Dans la version v1 ([`native_v1.py`](file:///Users/jeanvangysel/code/website/harness_tools/src/harness_tools/harness/native_v1.py)), les outils sont déclarés via le paramètre officiel `tools` de l'API HTTP, et le modèle répond avec des structures de données typées.

```mermaid
sequenceDiagram
    autonumber
    actor User as Utilisateur
    participant Harness as Harness Python (native_v1)
    participant Registry as ToolRegistry (Python local)
    participant Ollama as Serveur Ollama / llama.cpp

    User->>Harness: run("Combien font 14 * 25 ?")
    Note over Harness: Récupère les schémas formels JSON Schema :<br/>tools = registry.to_openai_tools()
    
    Harness->>Ollama: POST /api/chat (messages, tools=[schemas])
    Note over Ollama: Tokens spéciaux activés + grammaire contrainte.<br/>Le LLM émet directement un tool call.
    Ollama-->>Harness: HTTP 200 {tool_calls: [{"name": "calculate", "arguments": {"expression": "14 * 25"}}]}
    
    Note over Harness: Vérification simple : if not response.tool_calls<br/>Ici la liste n'est pas vide -> dispatch automatique
    
    Harness->>Registry: execute("calculate", {"expression": "14 * 25"})
    Note over Registry: Exécution locale en mémoire Python (1 ms)
    Registry-->>Harness: ToolResult(output="350")
    
    Note over Harness: Ajout dans l'historique structuré :<br/>1. message assistant avec tool_calls<br/>2. message {role: "tool", content: "350"}
    
    Harness->>Ollama: POST /api/chat (messages mis à jour, tools=[schemas])
    Note over Ollama: Le LLM lit le résultat sous le rôle 'tool'.<br/>Il n'émet plus de tool_calls.
    Ollama-->>Harness: HTTP 200 {content: "Le résultat de 14 * 25 est 350.", tool_calls: []}
    
    Note over Harness: if not response.tool_calls -> Fin de boucle atteinte
    Harness-->>User: "Le résultat de 14 * 25 est 350."
```

---

## 4. Diagramme de Séquence : v2 (Chaînage Multi-Étapes & Passage de Données)

Dans la version v2 ([`native_v2.py`](file:///Users/jeanvangysel/code/website/harness_tools/src/harness_tools/harness/native_v2.py)), le harness orchestre des **trajectoires séquentielles** où le résultat d'un premier outil est réinjecté pour alimenter les paramètres d'un second outil.

```mermaid
sequenceDiagram
    autonumber
    actor User as Utilisateur
    participant Harness as Harness Python (native_v2)
    participant Registry as ToolRegistry (Python local)
    participant Ollama as Serveur Ollama (LLM)

    User->>Harness: run("Calcule 15 * 12, puis crée une note 'Budget 2026' contenant ce montant.")
    
    rect rgb(240, 248, 255)
    Note over Harness,Ollama: Étape 1 : Appel du premier outil (calculate)
    Harness->>Ollama: POST /api/chat (messages, tools)
    Ollama-->>Harness: tool_calls: [calculate(expression="15 * 12")]
    Harness->>Registry: execute("calculate", {"expression": "15 * 12"})
    Registry-->>Harness: ToolResult(output="180")
    Note over Harness: Enregistrement dans l'historique :<br/>{role: "tool", name: "calculate", content: "180"}
    end

    rect rgb(245, 255, 245)
    Note over Harness,Ollama: Étape 2 : Le LLM exploite '180' pour le second outil (create_note)
    Harness->>Ollama: POST /api/chat (messages mis à jour avec le résultat 180)
    Ollama-->>Harness: tool_calls: [create_note(title="Budget 2026", content="180")]
    Harness->>Registry: execute("create_note", {"title": "Budget 2026", "content": "180"})
    Registry-->>Harness: ToolResult(output="Succès : La note 'Budget 2026' a été créée.")
    Note over Harness: Enregistrement dans l'historique :<br/>{role: "tool", name: "create_note", content: "Succès..."}
    end

    rect rgb(255, 255, 240)
    Note over Harness,Ollama: Étape 3 : Conclusion finale
    Harness->>Ollama: POST /api/chat (messages complets)
    Ollama-->>Harness: {content: "La note Budget 2026 a été créée avec le montant de 180.", tool_calls: []}
    end

    Harness-->>User: "La note Budget 2026 a été créée avec le montant de 180."
```

---

## 5. Diagramme de Séquence : v2 (Mécanisme Anti-Boucle Infinie)

Lorsqu'un LLM fait face à une erreur ou une réponse inattendue, il a tendance à s'enfermer dans un **attracteur auto-régressif** et à ré-exécuter le même appel identique à l'infini.

Voici comment le **Garde-Fou v2 (*Loop Guard*)** intercepte cette anomalie (constatée en direct sur `calculate_date_offset(days="5")`) :

```mermaid
sequenceDiagram
    autonumber
    actor User as Utilisateur
    participant Harness as Harness Python (native_v2)
    participant Detector as Détecteur d'Empreinte (Call Fingerprint)
    participant Registry as ToolRegistry (Python local)
    participant Ollama as Serveur Ollama (LLM)

    User->>Harness: run("Quelle est la date dans 5 jours et ajoute une tâche...")
    
    rect rgb(255, 245, 245)
    Note over Harness,Ollama: Tour 1 : Premier appel avec erreur de typage (str au lieu de int)
    Harness->>Ollama: POST /api/chat (messages, tools)
    Ollama-->>Harness: tool_call: calculate_date_offset(days="5")
    Harness->>Detector: check(name="calculate_date_offset", args={"days": "5"})
    Detector-->>Harness: count = 1 (OK)
    Harness->>Registry: execute(name, args)
    Note over Registry: TypeError: unsupported type for timedelta days component: str
    Registry-->>Harness: ToolResult(output="TypeError: unsupported type...")
    Harness->>Ollama: POST /api/chat (messages + {role: "tool", content: "TypeError..."})
    end

    rect rgb(255, 230, 230)
    Note over Harness,Ollama: Tour 2 : Le modèle panique et répète à l'identique
    Ollama-->>Harness: tool_call: calculate_date_offset(days="5")
    Harness->>Detector: check(name="calculate_date_offset", args={"days": "5"})
    Detector-->>Harness: count = 2 (SEUIL D'ALERTE ATTEINT)
    Harness->>Registry: execute(name, args)
    Registry-->>Harness: ToolResult(output="TypeError...")
    Note over Harness: Greffe d'un avertissement système réflexif :<br/>"[Garde-fou Système] : Tu viens de ré-exécuter cet outil avec des arguments identiques..."
    Harness->>Ollama: POST /api/chat (messages + {role: "tool", content: "TypeError... + Warning"})
    end

    rect rgb(255, 200, 200)
    Note over Harness,Ollama: Tour 3 : Récidive -> Coupure immédiate (Circuit Breaker)
    Ollama-->>Harness: tool_call: calculate_date_offset(days="5")
    Harness->>Detector: check(name="calculate_date_offset", args={"days": "5"})
    Detector-->>Harness: count = 3 (> max_repeated_calls -> ALARME)
    Note over Harness: COURT-CIRCUIT IMMÉDIAT !<br/>Aucun appel à Registry, aucun appel à Ollama.<br/>loop_detected = True
    Harness-->>User: "Arrêt de sécurité : Boucle infinie détectée sur l'outil 'calculate_date_offset' avec les mêmes arguments répétés 3 fois."
    end
```

---

## 6. Machine à États de l'Harness v2 (Flowchart)

```mermaid
flowchart TD
    Start(["Requête utilisateur"]) --> Init["Initialisation des messages<br/>(system + user)"]
    Init --> LoopCheck{"Étape <= max_steps ?"}
    
    LoopCheck -->|Non| MaxExceeded["Échec : Limite max_steps atteinte"]
    LoopCheck -->|Oui| CallLLM["Appel Ollama POST /api/chat<br/>(messages, tools)"]
    
    CallLLM --> HasToolCall{"Présence de tool_calls ?"}
    
    HasToolCall -->|Non| FinalAnswer["Réponse finale textuelle ✅"]
    
    HasToolCall -->|Oui| HashArgs["Calcul de l'empreinte canonique :<br/>name + json_trié(arguments)"]
    
    HashArgs --> CountRep{"Répétitions consécutives ?"}
    
    CountRep -->|"> max_repeated_calls (3)"| CircuitBreaker["🚨 Coupure de Sécurité<br/>(Circuit Breaker anti-boucle)"]
    CircuitBreaker --> ReturnLoop["Arrêt immédiat :<br/>loop_detected = True<br/>Économie de tokens et de temps"]
    
    CountRep -->|"== max_repeated_calls (2)"| ExecWarn["Exécution de l'outil +<br/>Injection de l'avertissement réflexif"]
    
    CountRep -->|"< max_repeated_calls (1)"| ExecNorm["Exécution nominale de l'outil"]
    
    ExecWarn --> InjectToolMsg["Ajout message {role: 'tool', content: ...}"]
    ExecNorm --> InjectToolMsg
    
    InjectToolMsg --> NextStep["Étape suivante (step + 1)"]
    NextStep --> LoopCheck
```

---

## 7. Synthèse Comparative des 3 Versions

| Dimension | v0 — ReAct Textuel | v1 — Tool Calling Natif | v2 — Multi-Étapes & Garde-Fous |
|---|---|---|---|
| **Protocole d'échange** | Texte libre + Regex | API `tools: [...]` + grammaires JSON | API `tools: [...]` + grammaires JSON |
| **Type de trajectoire** | 1 action basique | 1 action optimisée | **Multi-actions en cascade** (donnée $T_1 \to T_2$) |
| **Garde-fou de boucle** | Aucun (bloqué au `max_steps`) | Aucun (bloqué au `max_steps`) | **Détecteur d'empreinte canonique + Circuit Breaker** |
| **Gestion des répétitions** | Aveugle | Aveugle | **Avertissement réflexif à $N=2$, coupure à $N=3$** |
| **Latence moyenne (4B)** | Très lente (17s à 62s) | Très rapide (8s à 13s) | Contrôlée (arrêt précoce en cas de dérive) |
| **Persistance mémoire** | Simulée en texte | En mémoire | Validée sur états réels (`notes`, `todo`) |
