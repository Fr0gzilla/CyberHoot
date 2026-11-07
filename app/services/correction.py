"""Lecture et correction d'une réponse, pour tous les types de questions.

Partagé par les parties en solo et en direct : une seule règle de correction.

- choix (unique ou multiple), vrai/faux, phishing : la réponse est l'ensemble des réponses
  cochées ; elle est juste si c'est exactement l'ensemble des bonnes réponses (pour le
  phishing : tous les indices suspects, et aucun passage anodin) ;
- remettre dans l'ordre : la réponse est la liste des étapes dans l'ordre choisi ; elle est
  juste si c'est l'ordre attendu (celui saisi par le créateur).
"""

from __future__ import annotations

import enum
import random

from werkzeug.datastructures import MultiDict

from app.models import AnswerOption, Question, QuestionKind

CHOIX_MAX = 12


class Refus(enum.Enum):
    AUCUN_CHOIX = "Choisissez au moins une réponse."
    CHOIX_INVALIDE = "Réponse invalide."
    UN_SEUL_CHOIX = "Une seule réponse est attendue pour cette question."
    ORDRE_INCOMPLET = "Donnez un rang différent à chaque étape (1, 2, 3…)."


def ordre_affiche(question: Question, graine: str) -> list[AnswerOption]:
    """Ordre de présentation des réponses.

    Pour « remettre dans l'ordre », les étapes sont mélangées (sinon la réponse serait
    donnée) ; le mélange dépend de la partie, pour rester le même si la page est rechargée.
    """
    options = list(question.options)
    if question.kind is QuestionKind.ORDER:
        # Mélange d'affichage, sans enjeu de sécurité : pas besoin d'aléa cryptographique.
        random.Random(f"{graine}:{question.id}").shuffle(options)  # noqa: S311  # nosec B311
        if [o.id for o in options] == question.ordre_attendu and len(options) > 1:
            options.reverse()
    return options


def lire(question: Question, formulaire: MultiDict[str, str]) -> list[int]:
    """Réponse envoyée par le formulaire, sous forme de liste d'identifiants de réponses."""
    if question.kind is QuestionKind.ORDER:
        rangs: dict[int, int] = {}
        for option in question.options:
            valeur = formulaire.get(f"rang-{option.id}", "")
            if valeur.isdigit():
                rangs[option.id] = int(valeur)
        return sorted(rangs, key=lambda option_id: rangs[option_id]) if _permutation(rangs) else []
    return [int(v) for v in formulaire.getlist("choix") if v.isdigit()][:CHOIX_MAX]


def _permutation(rangs: dict[int, int]) -> bool:
    return sorted(rangs.values()) == list(range(1, len(rangs) + 1))


def corriger(question: Question, reponse: list[int]) -> bool | Refus:
    """True ou False si la réponse est recevable, sinon la raison du refus."""
    identifiants = {option.id for option in question.options}
    if question.kind is QuestionKind.ORDER:
        if sorted(reponse) != sorted(identifiants):
            return Refus.ORDRE_INCOMPLET
        return reponse == question.ordre_attendu
    selection = set(reponse)
    if not selection:
        return Refus.AUCUN_CHOIX
    if not selection <= identifiants:
        return Refus.CHOIX_INVALIDE
    if not question.multiple and len(selection) > 1:
        return Refus.UN_SEUL_CHOIX
    return selection == question.correct_ids


def a_enregistrer(question: Question, reponse: list[int]) -> list[int]:
    """Forme stockée : l'ordre compte pour « remettre dans l'ordre », pas pour les autres."""
    return list(reponse) if question.kind is QuestionKind.ORDER else sorted(set(reponse))
