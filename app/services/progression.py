"""Progression d'un joueur et attribution des badges.

Les badges sont des données de référence (migration 0004) : chaque badge a une règle et un
seuil. Ce service est le seul à les attribuer ; il est appelé à la fin d'une partie en solo,
à la fin d'une partie en direct (animateur et joueurs connectés) et à la publication d'un quiz.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy import ColumnElement, func, select

from app.extensions import db
from app.models import (
    Badge,
    BadgeRule,
    Category,
    LiveGame,
    LivePlayer,
    PlayAnswer,
    PlaySession,
    Quiz,
    QuizStatus,
    User,
    UserBadge,
    utcnow,
)

journal = logging.getLogger(__name__)
SEUIL_EXPERT = 0.8
JOUEURS_MIN_DIRECT = 3


# --- Statistiques ----------------------------------------------------------------------------


@dataclass(frozen=True)
class Theme:
    categorie: Category
    reponses: int
    justes: int

    @property
    def pourcentage(self) -> int | None:
        return round(100 * self.justes / self.reponses) if self.reponses else None


def par_theme(user: User) -> list[Theme]:
    """Réussite par catégorie, sur toutes les réponses des parties du joueur."""
    lignes = {
        cat_id: (n, justes or 0)
        for cat_id, n, justes in db.session.execute(
            select(
                Quiz.category_id,
                func.count(PlayAnswer.id),
                func.sum(func.cast(PlayAnswer.is_correct, db.Integer)),
            )
            .join(PlaySession, PlayAnswer.session_id == PlaySession.id)
            .join(Quiz, PlaySession.quiz_id == Quiz.id)
            .where(PlaySession.user_id == user.id)
            .group_by(Quiz.category_id)
        ).all()
    }
    return [
        Theme(categorie, *lignes.get(categorie.id, (0, 0)))
        for categorie in db.session.scalars(select(Category).order_by(Category.position))
    ]


def _jours_joues(user: User) -> list[date]:
    dates = db.session.scalars(
        select(PlaySession.finished_at).where(
            PlaySession.user_id == user.id, PlaySession.finished_at.is_not(None)
        )
    )
    return sorted({d.date() for d in dates if d is not None})


def series(user: User, aujourd_hui: date | None = None) -> tuple[int, int]:
    """(série en cours, meilleure série) en jours consécutifs avec au moins une partie."""
    jours = _jours_joues(user)
    meilleure = courante = 0
    precedent: date | None = None
    for jour in jours:
        courante = courante + 1 if precedent and jour - precedent == timedelta(days=1) else 1
        meilleure = max(meilleure, courante)
        precedent = jour
    aujourd_hui = aujourd_hui or utcnow().date()
    en_cours = courante if precedent and aujourd_hui - precedent <= timedelta(days=1) else 0
    return en_cours, meilleure


def parties_terminees(user: User) -> int:
    return (
        db.session.scalar(
            select(func.count(PlaySession.id)).where(
                PlaySession.user_id == user.id, PlaySession.finished_at.is_not(None)
            )
        )
        or 0
    )


def _une_partie(user: User, *conditions: ColumnElement[bool]) -> bool:
    return (
        db.session.scalar(
            select(PlaySession.id)
            .where(
                PlaySession.user_id == user.id, PlaySession.finished_at.is_not(None), *conditions
            )
            .limit(1)
        )
        is not None
    )


def _parties_direct(user: User, comme_vainqueur: bool) -> int:
    """Parties en direct terminées d'au moins 3 joueurs, animées ou gagnées par ce compte."""
    nombre = 0
    requete = select(LiveGame).where(LiveGame.ended_at.is_not(None))
    if not comme_vainqueur:
        requete = requete.where(LiveGame.host_id == user.id)
    else:
        requete = requete.join(LivePlayer).where(LivePlayer.user_id == user.id)
    for partie in db.session.scalars(requete.distinct()):
        joueurs = sorted(
            (j for j in partie.players if not j.kicked), key=lambda j: (-j.score, j.joined_at)
        )
        if len(joueurs) < JOUEURS_MIN_DIRECT:
            continue
        if not comme_vainqueur or joueurs[0].user_id == user.id:
            nombre += 1
    return nombre


# --- Badges ----------------------------------------------------------------------------------


def _merite(user: User, badge: Badge, themes: dict[int, Theme]) -> bool:
    seuil = badge.threshold
    match badge.rule:
        case BadgeRule.PARTIES:
            return parties_terminees(user) >= seuil
        case BadgeRule.SANS_FAUTE:
            return _une_partie(
                user, PlaySession.total >= seuil, PlaySession.score == PlaySession.total
            )
        case BadgeRule.ZERO:
            return _une_partie(user, PlaySession.total >= seuil, PlaySession.score == 0)
        case BadgeRule.SERIE:
            return series(user)[1] >= seuil
        case BadgeRule.EXPERT:
            theme = themes.get(badge.category_id or 0)
            return bool(
                theme and theme.reponses >= seuil and theme.justes >= SEUIL_EXPERT * theme.reponses
            )
        case BadgeRule.ANIMATEUR:
            return _parties_direct(user, comme_vainqueur=False) >= seuil
        case BadgeRule.VAINQUEUR:
            return _parties_direct(user, comme_vainqueur=True) >= seuil
        case BadgeRule.CREATEUR:
            publies = db.session.scalar(
                select(func.count(Quiz.id)).where(
                    Quiz.creator_id == user.id, Quiz.status == QuizStatus.PUBLISHED
                )
            )
            return (publies or 0) >= seuil
    return False  # pragma: no cover  (toutes les règles sont traitées ci-dessus)


def attribuer(user: User) -> list[Badge]:
    """Attribue les badges désormais mérités ; renvoie les nouveaux."""
    possedes = set(
        db.session.scalars(select(UserBadge.badge_id).where(UserBadge.user_id == user.id))
    )
    a_verifier = [
        b
        for b in db.session.scalars(select(Badge).order_by(Badge.position))
        if b.id not in possedes
    ]
    if not a_verifier:
        return []
    themes = {t.categorie.id: t for t in par_theme(user)}
    nouveaux = [b for b in a_verifier if _merite(user, b, themes)]
    for badge in nouveaux:
        db.session.add(UserBadge(user_id=user.id, badge_id=badge.id))
    db.session.commit()
    if nouveaux:
        journal.info("compte %s : %d nouveau(x) badge(s)", user.id, len(nouveaux))
    return nouveaux


def badges_de(user: User) -> list[UserBadge]:
    return list(
        db.session.scalars(
            select(UserBadge).where(UserBadge.user_id == user.id).order_by(UserBadge.obtained_at)
        )
    )


def tous_les_badges() -> list[Badge]:
    return list(db.session.scalars(select(Badge).order_by(Badge.position)))
