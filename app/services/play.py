"""Parties en solo, corrigées par le serveur.

Le navigateur ne reçoit jamais les bonnes réponses d'une question avant d'y avoir répondu,
et n'envoie jamais de score : il envoie seulement les réponses choisies pour la question
en cours. Le serveur vérifie que c'est bien la question attendue, corrige, enregistre et
calcule le score. On ne peut ni répondre deux fois, ni sauter une question.
"""

from __future__ import annotations

import enum
import logging
import secrets
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models import PlayAnswer, PlaySession, Question, Quiz, QuizStatus, User, utcnow
from app.services import correction

journal = logging.getLogger(__name__)


def demarrer(user: User, quiz: Quiz) -> PlaySession:
    """Reprend la partie en cours de ce joueur sur ce quiz, ou en commence une."""
    en_cours: PlaySession | None = db.session.scalar(
        select(PlaySession).where(
            PlaySession.user_id == user.id,
            PlaySession.quiz_id == quiz.id,
            PlaySession.finished_at.is_(None),
        )
    )
    if en_cours is not None:
        return en_cours
    ids = [q.id for q in quiz.questions]
    partie = PlaySession(
        token=secrets.token_urlsafe(32),
        user_id=user.id,
        quiz_id=quiz.id,
        question_ids=ids,
        total=len(ids),
    )
    db.session.add(partie)
    db.session.commit()
    return partie


def trouver(token: str, user: User) -> PlaySession | None:
    """La partie de ce joueur (une partie d'un autre joueur reste introuvable)."""
    if not token or len(token) > 64:
        return None
    partie: PlaySession | None = db.session.scalar(
        select(PlaySession).where(PlaySession.token == token, PlaySession.user_id == user.id)
    )
    return partie


def question_courante(partie: PlaySession) -> Question | None:
    if partie.finished or partie.current_index >= partie.total:
        return None
    return db.session.get(Question, partie.question_ids[partie.current_index])


class Refus(enum.Enum):
    TERMINEE = "Cette partie est terminée."
    MAUVAISE_QUESTION = "Cette question n'est plus la question en cours."


@dataclass(frozen=True)
class Correction:
    reponse: PlayAnswer | None = None
    refus: Refus | correction.Refus | None = None


def repondre(partie: PlaySession, question_id: int, choix: list[int]) -> Correction:
    question = question_courante(partie)
    if question is None:
        return Correction(refus=Refus.TERMINEE)
    if question.id != question_id:
        return Correction(refus=Refus.MAUVAISE_QUESTION)
    verdict = correction.corriger(question, choix)
    if isinstance(verdict, correction.Refus):
        return Correction(refus=verdict)
    juste = verdict
    reponse = PlayAnswer(
        session_id=partie.id,
        position=partie.current_index,
        question_id=question.id,
        selected_ids=correction.a_enregistrer(question, choix),
        is_correct=juste,
    )
    db.session.add(reponse)
    partie.current_index += 1
    if juste:
        partie.score += 1
    if partie.current_index >= partie.total:
        partie.finished_at = utcnow()
    try:
        db.session.commit()
    except IntegrityError:
        # Double envoi simultané : la première réponse a déjà été enregistrée.
        db.session.rollback()
        return Correction(refus=Refus.MAUVAISE_QUESTION)
    return Correction(reponse=reponse)


def reponse_a(partie: PlaySession, position: int) -> PlayAnswer | None:
    reponse: PlayAnswer | None = db.session.scalar(
        select(PlayAnswer).where(
            PlayAnswer.session_id == partie.id, PlayAnswer.position == position
        )
    )
    return reponse


def a_termine(user: User, quiz: Quiz) -> bool:
    return bool(
        db.session.scalar(
            select(func.count())
            .select_from(PlaySession)
            .where(
                PlaySession.user_id == user.id,
                PlaySession.quiz_id == quiz.id,
                PlaySession.finished_at.is_not(None),
            )
        )
    )


def historique(user: User, limite: int = 10) -> list[PlaySession]:
    return list(
        db.session.scalars(
            select(PlaySession)
            .where(PlaySession.user_id == user.id, PlaySession.finished_at.is_not(None))
            .order_by(PlaySession.finished_at.desc())
            .limit(limite)
        )
    )


def jouable(quiz: Quiz) -> bool:
    return quiz.status is QuizStatus.PUBLISHED and bool(quiz.questions)
