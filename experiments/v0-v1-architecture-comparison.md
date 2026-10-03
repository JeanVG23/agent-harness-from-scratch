# Architecture & Flux d'Exécution : Comparatif v0 vs v1

Ce document synthétise les différences architecturales et mécaniques entre l'approche **v0 (ReAct par Prompting Textuel)** et l'approche **v1 (Tool Calling Natif d'API)**.

---

## 1. Principe Fondamental : Qui Fait Quoi ?

Avant d'examiner les flux, rappelons la frontière d'exécution :
* **Le LLM (Ollama) :** Est un système *stateless* (sans état) qui génère des tokens probables. Il n'a **aucun terminal**, aucun accès réseau direct, et ne peut exécuter aucune ligne de code.
* **Le Harness (notre script Python local) :** Est le moteur exécutif. Il détient les fonctions Python réelles ([`clock.py`](file:///Users/jeanvangysel/code/website/harness_tools/src/harness_tools/tools/clock.py), [`calculator.py`](file:///Users/jeanvangysel/code/website/harness_tools/src/harness_tools/tools/calculator.py)), appelle l'API d'Ollama, valide les données, exécute les calculs en mémoire et réinjecte l'information.

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

## 3. Diagramme de Séquence : v1 (Tool Calling Natif)

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

## 4. Comparatif Architectural Synthétique

```mermaid
flowchart TD
    subgraph V0["v0 — ReAct Prompté (Artisanat Textuel)"]
        direction TB
        P0["System Prompt<br/>(Markdown textuel des outils)"] --> L0["LLM en génération libre"]
        L0 --> T0["Texte brut :<br/>Thought / Action / Action Input"]
        T0 --> R0["Parseur Regex & json.loads()"]
        R0 --> E0["Exécution Python locale"]
        E0 --> C0["Concaténation de chaînes :<br/>Observation: ..."]
        C0 --> L0
    end

    subgraph V1["v1 — Tool Calling Natif (Protocole d'API)"]
        direction TB
        P1["Payload HTTP :<br/>messages + tools JSON Schema"] --> L1["LLM sous contrainte grammaticale<br/>(Tokens spéciaux)"]
        L1 --> T1["Payload HTTP structuré :<br/>tool_calls: [...]"]
        T1 --> R1["Désérialisation JSON directe<br/>(0 Regex)"]
        R1 --> E1["Exécution Python locale"]
        E1 --> C1["Message structuré :<br/>{role: 'tool', content: ...}"]
        C1 --> L1
    end
```

---

## 5. Synthèse des Différences

| Dimension | v0 — ReAct Textuel | v1 — Tool Calling Natif |
|---|---|---|
| **Canal de déclaration** | Texte libre dans le `system_prompt` | Paramètre API HTTP officiel `tools: [...]` |
| **Spécification des outils** | Chaînes formatées à la main | Schémas formels **JSON Schema** standardisés |
| **Expression de l'intention** | Texte simulé (`Action: foo`) | Tableau d'objets `tool_calls` |
| **Mécanisme de capture** | Expressions régulières ([`re.search`](https://docs.python.org/3/library/re.html#re.search)) | Champ de réponse HTTP déjà désérialisé |
| **Garantie syntaxique** | Faible (dépend du respect des consignes) | Élevée (grammaires de décodage côté moteur d'inférence) |
| **Réinjection de la donnée** | Concaténation textuelle (`\nObservation: ...`) | Rôle sémantique dédié `{role: "tool"}` |
| **Latence observée (4B)** | Élevée (verbiage et monologues intermédiaires) | Optimale (émissions compactes et directes) |
