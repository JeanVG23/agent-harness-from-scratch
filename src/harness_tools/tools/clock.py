"""Outil Horloge et calcul de dates."""

from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def get_current_time(timezone: str = "Europe/Paris") -> str:
    """Retourne la date et l'heure actuelles précises dans un fuseau horaire donné.

    Args:
        timezone: Le nom IANA du fuseau horaire (ex: 'Europe/Paris', 'UTC', 'America/New_York').
    """
    try:
        tz = ZoneInfo(timezone)
    except (ZoneInfoNotFoundError, ValueError):
        return f"Erreur : Fuseau horaire '{timezone}' inconnu. Utilisez un fuseau IANA valide comme 'Europe/Paris' ou 'UTC'."

    now = datetime.now(tz)
    jour_semaine = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"][now.weekday()]
    return now.strftime(f"{jour_semaine} %d/%m/%Y %H:%M:%S (%Z, UTC%z)")


def calculate_date_offset(days: int, start_date: str | None = None) -> str:
    """Calcule une date future ou passée en ajoutant ou soustrayant un nombre de jours.

    Args:
        days: Le nombre de jours à ajouter (positif pour le futur, négatif pour le passé).
        start_date: La date de départ au format AAAA-MM-JJ (optionnel, par défaut aujourd'hui).
    """
    try:
        if start_date:
            base = datetime.strptime(start_date.strip(), "%Y-%m-%d")
        else:
            base = datetime.now()
    except ValueError:
        return f"Erreur : Format de date invalide pour '{start_date}'. Le format attendu est AAAA-MM-JJ."

    target = base + timedelta(days=days)
    jour_semaine = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"][target.weekday()]
    return target.strftime(f"{jour_semaine} %d/%m/%Y (AAAA-MM-JJ: %Y-%m-%d)")
