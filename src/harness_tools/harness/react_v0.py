"""Harness v0 : Implémentation du pattern ReAct (Reasoning + Acting) par prompting textuel."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import re
from typing import Any

from harness_tools.llm.client import OllamaClient
from harness_tools.models import Message
from harness_tools.tools.registry import ToolRegistry


@dataclass
class ReActStep:
    """Représentation d'une étape de raisonnement et d'action."""
    thought: str = ""
    action: str | None = None
    action_input: dict[str, Any] | None = None
    observation: str | None = None


@dataclass
class ReActResult:
    """Résultat final de l'exécution de la boucle ReAct."""
    final_answer: str
    steps: list[ReActStep] = field(default_factory=list)
    success: bool = True
    error: str | None = None


def _format_tools_description(registry: ToolRegistry) -> str:
    """Génère la documentation textuelle des outils pour le prompt ReAct."""
    lines: list[str] = []
    for tool in registry._tools.values():
        props = tool.parameters.get("properties", {})
        param_desc = ", ".join(f"{name}: {info.get('type', 'any')}" for name, info in props.items())
        lines.append(f"- {tool.name}({param_desc}) : {tool.description}")
    return "\n".join(lines)


def _build_system_prompt(registry: ToolRegistry) -> str:
    """Construit le prompt système imposant le protocole ReAct."""
    tools_desc = _format_tools_description(registry)
    return (
        "Tu es un assistant personnel doté d'outils. Tu réponds aux demandes en réfléchissant pas à pas.\n\n"
        "Pour chaque étape, tu dois STRICTEMENT suivre ce format :\n"
        "Thought: Ce que tu penses et prévois de faire.\n"
        "Action: Le nom exact de l'outil à appeler (ou 'None' si aucun outil n'est requis).\n"
        "Action Input: Les arguments de l'outil sous forme d'objet JSON valide (ex: {\"expression\": \"14 * 25\"}).\n"
        "Observation: N'écris JAMAIS ce champ toi-même. L'environnement te fournira l'Observation après ton Action.\n\n"
        "Quand tu as toutes les informations nécessaires ou si aucun outil n'est requis :\n"
        "Thought: J'ai maintenant la réponse finale.\n"
        "Final Answer: Ta réponse finale claire et complète pour l'utilisateur.\n\n"
        f"Outils disponibles :\n{tools_desc}\n"
    )


def _parse_react_response(text: str) -> tuple[str, str | None, dict[str, Any] | None, str | None]:
    """Parse la réponse textuelle du LLM pour extraire Thought, Action, Action Input ou Final Answer.
    
    Retourne : (thought, action, action_input, final_answer)
    """
    # Règle défensive : si le modèle a halluciné "Observation:", on coupe tout ce qui suit
    clean_text = text
    obs_match = re.search(r"\bObservation\s*:", clean_text, re.IGNORECASE)
    if obs_match:
        clean_text = clean_text[:obs_match.start()].strip()

    # Détection de Final Answer
    final_match = re.search(r"Final Answer\s*:\s*(.*)", clean_text, re.IGNORECASE | re.DOTALL)
    if final_match:
        final_answer = final_match.group(1).strip()
        thought_match = re.search(r"Thought\s*:\s*(.*?)(?=Final Answer|$)", clean_text, re.IGNORECASE | re.DOTALL)
        thought = thought_match.group(1).strip() if thought_match else ""
        return thought, None, None, final_answer

    # Extraction Thought
    thought_match = re.search(r"Thought\s*:\s*(.*?)(?=Action\s*:|$)", clean_text, re.IGNORECASE | re.DOTALL)
    thought = thought_match.group(1).strip() if thought_match else ""

    # Extraction Action
    action_match = re.search(r"Action\s*:\s*([a-zA-Z0-9_-]+)", clean_text)
    action = action_match.group(1).strip() if action_match else None

    # Extraction Action Input
    action_input_match = re.search(r"Action Input\s*:\s*(.*)", clean_text, re.DOTALL)
    action_input: dict[str, Any] | None = None
    if action_input_match:
        raw_input = action_input_match.group(1).strip()
        # Nettoyage d'éventuels backticks markdown
        raw_input = re.sub(r"^```(?:json)?\s*", "", raw_input)
        raw_input = re.sub(r"\s*```$", "", raw_input).strip()
        try:
            parsed = json.loads(raw_input)
            if isinstance(parsed, dict):
                action_input = parsed
            else:
                action_input = {"_raw": parsed}
        except json.JSONDecodeError:
            # Si le modèle a omis les accolades autour d'une clé-valeur
            if ":" in raw_input and not raw_input.startswith("{"):
                try:
                    action_input = json.loads("{" + raw_input + "}")
                except json.JSONDecodeError:
                    action_input = {"_raw": raw_input}
            else:
                action_input = {"_raw": raw_input}

    return thought, action, action_input, None


class ReActHarnessV0:
    """Moteur d'orchestration ReAct basé sur le prompting textuel."""

    def __init__(self, client: OllamaClient, registry: ToolRegistry) -> None:
        self.client = client
        self.registry = registry

    def run(self, user_prompt: str, max_steps: int = 5) -> ReActResult:
        """Exécute la boucle ReAct pour répondre à la demande de l'utilisateur."""
        system_prompt = _build_system_prompt(self.registry)
        messages: list[Message] = [
            Message(role="system", content=system_prompt),
            Message(role="user", content=f"Question: {user_prompt}"),
        ]

        steps: list[ReActStep] = []

        for step_idx in range(max_steps):
            response = self.client.chat(messages, tools=None)
            response_text = response.content or ""

            thought, action, action_input, final_answer = _parse_react_response(response_text)
            current_step = ReActStep(thought=thought, action=action, action_input=action_input)

            # Cas 1 : Le modèle a trouvé la réponse finale
            if final_answer is not None:
                steps.append(current_step)
                return ReActResult(final_answer=final_answer, steps=steps, success=True)

            # Cas 2 : Le modèle demande une action d'outil
            if action and action.lower() != "none":
                # Si le parser n'a pas pu décoder un dictionnaire valide
                if action_input is None or ("_raw" in action_input and not isinstance(action_input["_raw"], dict)):
                    obs_text = "Erreur : Action Input doit être un objet JSON valide (ex: {\"param\": \"valeur\"})."
                else:
                    tool_res = self.registry.execute(action, action_input)
                    obs_text = tool_res.output

                current_step.observation = obs_text
                steps.append(current_step)

                # Mise à jour de l'historique de conversation textuelle
                step_log = (
                    f"Thought: {thought}\n"
                    f"Action: {action}\n"
                    f"Action Input: {json.dumps(action_input, ensure_ascii=False)}\n"
                    f"Observation: {obs_text}"
                )
                messages.append(Message(role="assistant", content=step_log))
                messages.append(Message(role="user", content="Continue."))
                continue

            # Cas 3 : Réponse sans format ReAct exploitable
            current_step.observation = "Erreur de format : Tu dois produire soit 'Action:' et 'Action Input:', soit 'Final Answer:'."
            steps.append(current_step)
            messages.append(Message(role="assistant", content=response_text))
            messages.append(Message(role="user", content="Format invalide. Poursuis en suivant STRICTEMENT le format Thought / Action / Action Input ou Final Answer."))

        return ReActResult(
            final_answer="Échec : Nombre maximum d'étapes atteint sans Final Answer.",
            steps=steps,
            success=False,
            error=f"Limite de {max_steps} étapes atteinte.",
        )
