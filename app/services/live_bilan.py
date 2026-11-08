"""Parties en direct : réponses reçues, classement, statistiques, export et bilan final.

Lecture seule pendant la partie ; à la fin, les résultats rejoignent l'historique des joueurs
connectés et les badges sont attribués.
"""

from __future__ import annotations

import csv
import io
import secrets

from sqlalchemy import func, select

from app.extensions import db
from app.models import LiveAnswer, LiveGame, LivePlayer, PlayAnswer, PlaySession, User
from app.services import progression

POINTS_JUSTE = 500  # pour une bonne réponse…
POINTS_RAPIDITE = 500  # …plus jusqu'à 500 selon la rapidité


def nombre_reponses(partie: LiveGame) -> int:
    if partie.current_index < 0:
        return 0
    return (
        db.session.scalar(
            select(func.count(LiveAnswer.id)).where(
                LiveAnswer.game_id == partie.id, LiveAnswer.position == partie.current_index
            )
        )
        or 0
    )


def classement(partie: LiveGame, limite: int | None = None) -> list[LivePlayer]:
    requete = (
        select(LivePlayer)
        .where(LivePlayer.game_id == partie.id, LivePlayer.kicked.is_(False))
        .order_by(LivePlayer.score.desc(), LivePlayer.joined_at)
    )
    if limite:
        requete = requete.limit(limite)
    return list(db.session.scalars(requete))


def rang(partie: LiveGame, joueur: LivePlayer) -> int:
    devant = db.session.scalar(
        select(func.count(LivePlayer.id)).where(
            LivePlayer.game_id == partie.id,
            LivePlayer.kicked.is_(False),
            LivePlayer.score > joueur.score,
        )
    )
    return (devant or 0) + 1


def histogramme(partie: LiveGame) -> dict[int, int]:
    """Nombre de joueurs ayant choisi chaque réponse de la question en cours."""
    compte: dict[int, int] = {}
    for (selection,) in db.session.execute(
        select(LiveAnswer.selected_ids).where(
            LiveAnswer.game_id == partie.id, LiveAnswer.position == partie.current_index
        )
    ):
        for option_id in selection:
            compte[option_id] = compte.get(option_id, 0) + 1
    return compte


def reussite(partie: LiveGame) -> tuple[int, int]:
    """Bonnes réponses et réponses reçues pour la question en cours."""
    lignes = db.session.execute(
        select(LiveAnswer.is_correct, func.count(LiveAnswer.id))
        .where(LiveAnswer.game_id == partie.id, LiveAnswer.position == partie.current_index)
        .group_by(LiveAnswer.is_correct)
    ).all()
    par_verdict = {bool(juste): n for juste, n in lignes}
    return par_verdict.get(True, 0), sum(par_verdict.values())


def export_csv(partie: LiveGame) -> str:
    sortie = io.StringIO()
    ecrivain = csv.writer(sortie, delimiter=";")
    ecrivain.writerow(["Rang", "Pseudo", "Score", "Bonnes réponses"])
    justes = dict(
        db.session.execute(
            select(LiveAnswer.player_id, func.count(LiveAnswer.id))
            .where(LiveAnswer.game_id == partie.id, LiveAnswer.is_correct.is_(True))
            .group_by(LiveAnswer.player_id)
        ).all()
    )
    for i, joueur in enumerate(classement(partie), start=1):
        # Un pseudo commençant par = + - @ serait interprété comme formule par un tableur.
        pseudo = f"'{joueur.nickname}" if joueur.nickname[:1] in "=+-@" else joueur.nickname
        ecrivain.writerow([i, pseudo, joueur.score, justes.get(joueur.id, 0)])
    return sortie.getvalue()


def enregistrer_resultats(partie: LiveGame) -> None:
    """Les joueurs connectés retrouvent la partie dans leur historique (score = bonnes réponses)."""
    for joueur in partie.players:
        if joueur.user_id is None or joueur.kicked:
            continue
        reponses = list(
            db.session.scalars(
                select(LiveAnswer)
                .where(LiveAnswer.player_id == joueur.id)
                .order_by(LiveAnswer.position)
            )
        )
        session = PlaySession(
            token=secrets.token_urlsafe(32),
            user_id=joueur.user_id,
            quiz_id=partie.quiz_id,
            question_ids=partie.question_ids,
            current_index=partie.total,
            score=sum(1 for r in reponses if r.is_correct),
            total=partie.total,
            started_at=partie.created_at,
            finished_at=partie.ended_at,
        )
        session.answers = [
            PlayAnswer(
                position=r.position,
                question_id=r.question_id,
                selected_ids=r.selected_ids,
                is_correct=r.is_correct,
            )
            for r in reponses
        ]
        db.session.add(session)
    db.session.commit()


def attribuer_badges(partie: LiveGame) -> None:
    comptes = {j.user_id for j in partie.players if j.user_id and not j.kicked}
    if partie.host_id:
        comptes.add(partie.host_id)
    for compte_id in comptes:
        compte = db.session.get(User, compte_id)
        if compte is not None:
            progression.attribuer(compte)


def points(juste: bool, ecoule_ms: int, limite_s: int) -> int:
    if not juste:
        return 0
    part = max(0.0, 1 - ecoule_ms / (limite_s * 1000))
    return POINTS_JUSTE + round(POINTS_RAPIDITE * part)


def reponse_de(partie: LiveGame, joueur: LivePlayer, position: int) -> LiveAnswer | None:
    reponse: LiveAnswer | None = db.session.scalar(
        select(LiveAnswer).where(LiveAnswer.player_id == joueur.id, LiveAnswer.position == position)
    )
    return reponse
