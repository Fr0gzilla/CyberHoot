"""Administration : statistiques, comptes, catégories, badges."""

from __future__ import annotations

import enum
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from sqlalchemy import func, or_, select

from app.extensions import db
from app.models import (
    Badge,
    LiveGame,
    PlaySession,
    Quiz,
    QuizStatus,
    Role,
    RoleName,
    User,
    user_role,
    utcnow,
)

COMPTES_PAR_PAGE = 25


@dataclass(frozen=True)
class Statistiques:
    comptes: int
    actifs_30j: int
    quiz_publies: int
    quiz_en_attente: int
    parties_30j: int
    direct_30j: int
    parties_par_jour: list[tuple[date, int]]


def statistiques() -> Statistiques:
    maintenant = utcnow()
    il_y_a_30j = maintenant - timedelta(days=30)

    def compter(requete: Any) -> int:
        return int(db.session.scalar(requete) or 0)

    fins = db.session.scalars(
        select(PlaySession.finished_at).where(
            PlaySession.finished_at >= maintenant - timedelta(days=14)
        )
    )
    par_jour: dict[date, int] = {}
    for fin in fins:
        if fin is not None:
            par_jour[fin.date()] = par_jour.get(fin.date(), 0) + 1
    jours = [maintenant.date() - timedelta(days=i) for i in range(13, -1, -1)]
    return Statistiques(
        comptes=compter(select(func.count(User.id))),
        actifs_30j=compter(
            select(func.count(func.distinct(PlaySession.user_id))).where(
                PlaySession.finished_at >= il_y_a_30j
            )
        ),
        quiz_publies=compter(
            select(func.count(Quiz.id)).where(Quiz.status == QuizStatus.PUBLISHED)
        ),
        quiz_en_attente=compter(
            select(func.count(Quiz.id)).where(Quiz.status == QuizStatus.PENDING)
        ),
        parties_30j=compter(
            select(func.count(PlaySession.id)).where(PlaySession.finished_at >= il_y_a_30j)
        ),
        direct_30j=compter(
            select(func.count(LiveGame.id)).where(LiveGame.created_at >= il_y_a_30j)
        ),
        parties_par_jour=[(jour, par_jour.get(jour, 0)) for jour in jours],
    )


@dataclass(frozen=True)
class PageComptes:
    comptes: list[User]
    page: int
    pages: int
    total: int


def comptes(recherche: str = "", role: str = "", page: int = 1) -> PageComptes:
    requete = select(User)
    recherche = recherche.strip()[:100]
    if recherche:
        motif = f"%{recherche.replace('%', '').replace('_', '')}%"
        requete = requete.where(or_(User.username.ilike(motif), User.email.ilike(motif)))
    if role in {r.value for r in RoleName}:
        requete = requete.join(user_role).join(Role).where(Role.name == role)
    total = db.session.scalar(select(func.count()).select_from(requete.subquery())) or 0
    pages = max(1, -(-total // COMPTES_PAR_PAGE))
    page = min(max(1, page), pages)
    liste = list(
        db.session.scalars(
            requete.order_by(User.created_at.desc())
            .offset((page - 1) * COMPTES_PAR_PAGE)
            .limit(COMPTES_PAR_PAGE)
        )
    )
    return PageComptes(liste, page, pages, total)


class Refus(enum.Enum):
    SOI_MEME = "Vous ne pouvez pas modifier vos propres droits ni désactiver votre compte."
    DERNIER_ADMIN = "Il doit rester au moins un administrateur actif."
    ROLE_INCONNU = "Rôle inconnu."
    JOUEUR = "Le rôle joueur ne se retire pas."


def _admins_actifs() -> int:
    return (
        db.session.scalar(
            select(func.count(User.id))
            .join(user_role)
            .join(Role)
            .where(Role.name == RoleName.ADMIN.value, User.is_enabled.is_(True))
        )
        or 0
    )


def changer_role(admin: User, cible: User, role: str, ajouter: bool) -> Refus | None:
    if cible.id == admin.id:
        return Refus.SOI_MEME
    objet = db.session.scalar(select(Role).where(Role.name == role))
    if objet is None:
        return Refus.ROLE_INCONNU
    if role == RoleName.PLAYER.value and not ajouter:
        return Refus.JOUEUR
    if ajouter and objet not in cible.roles:
        cible.roles.append(objet)
    elif not ajouter and objet in cible.roles:
        if role == RoleName.ADMIN.value and _admins_actifs() <= 1:
            return Refus.DERNIER_ADMIN
        cible.roles.remove(objet)
    db.session.commit()
    return None


def changer_activation(admin: User, cible: User, actif: bool) -> Refus | None:
    if cible.id == admin.id:
        return Refus.SOI_MEME
    if not actif and cible.has_role(RoleName.ADMIN) and _admins_actifs() <= 1:
        return Refus.DERNIER_ADMIN
    cible.is_enabled = actif
    db.session.commit()
    return None


def badges() -> list[Badge]:
    return list(db.session.scalars(select(Badge).order_by(Badge.position)))
