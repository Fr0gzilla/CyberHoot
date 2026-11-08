"""Parties en direct : salle d'attente, questions chronométrées, points, classement.

Principes :
- l'heure qui compte est celle du serveur : le chrono et les points de rapidité sont calculés
  ici, jamais d'après ce que dit le navigateur ;
- chaque changement d'écran passe par `_transition`, une mise à jour conditionnelle sur le
  numéro de version : deux clics simultanés de l'animateur ne font avancer la partie qu'une
  fois ;
- la fin d'une question (chrono écoulé, ou tout le monde a répondu) est constatée à la
  lecture de l'état (`actualiser`) : aucun minuteur côté serveur n'est nécessaire ;
- les navigateurs interrogent l'état toutes les secondes (`etat`) : pas de WebSocket, donc
  rien à configurer derrière un pare-feu d'établissement, et une reconnexion naturelle.
"""

from __future__ import annotations

import enum
import logging
import re
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError, OperationalError

from app.extensions import db
from app.models import (
    LiveAnswer,
    LiveGame,
    LivePlayer,
    LiveStatus,
    Question,
    Quiz,
    User,
    utcnow,
)
from app.services import correction, live_bilan, pseudos

journal = logging.getLogger(__name__)

CHRONO_MIN, CHRONO_MAX = 10, 60
JOUEURS_MAX = 200


def _maintenant() -> datetime:
    return utcnow()


def _ms(delta: timedelta) -> int:
    return int(delta.total_seconds() * 1000)


# --- Création et salle d'attente -----------------------------------------------------------


def _nouveau_pin() -> str:
    for _ in range(50):
        pin = f"{secrets.randbelow(1_000_000):06d}"
        if db.session.scalar(select(LiveGame.id).where(LiveGame.pin == pin)) is None:
            return pin
    raise RuntimeError("aucun code PIN libre")  # pragma: no cover


def creer(hote: User, quiz: Quiz, chrono: int = 20, joueurs_max: int = JOUEURS_MAX) -> LiveGame:
    partie = LiveGame(
        pin=_nouveau_pin(),
        host_id=hote.id,
        quiz_id=quiz.id,
        question_ids=[q.id for q in quiz.questions],
        time_limit=min(max(chrono, CHRONO_MIN), CHRONO_MAX),
        max_players=min(max(joueurs_max, 2), JOUEURS_MAX),
    )
    db.session.add(partie)
    db.session.commit()
    journal.info("partie en direct %s créée (quiz %s)", partie.id, quiz.id)
    return partie


def trouver_par_pin(pin: str) -> LiveGame | None:
    pin = pin.strip().replace(" ", "")
    if not re.fullmatch(r"\d{6}", pin):
        return None
    partie: LiveGame | None = db.session.scalar(select(LiveGame).where(LiveGame.pin == pin))
    return partie


class RefusEntree(enum.Enum):
    PARTIE_TERMINEE = "Cette partie est terminée."
    COMPLET = "La partie est complète."
    PSEUDO_INVALIDE = "Pseudo de 1 à 20 caractères : lettres, chiffres, espaces, - ou _."
    PSEUDO_INTERDIT = "Ce pseudo n'est pas accepté : choisissez-en un autre."
    PSEUDO_PRIS = "Ce pseudo est déjà pris dans cette partie."


@dataclass(frozen=True)
class Entree:
    joueur: LivePlayer | None = None
    refus: RefusEntree | None = None


def joueurs_actifs(partie: LiveGame) -> list[LivePlayer]:
    return [j for j in partie.players if not j.kicked]


def rejoindre(partie: LiveGame, pseudo: str, compte: User | None = None) -> Entree:
    pseudo = " ".join(pseudo.split())
    if not partie.active:
        return Entree(refus=RefusEntree.PARTIE_TERMINEE)
    if not pseudos.valide(pseudo):
        return Entree(refus=RefusEntree.PSEUDO_INVALIDE)
    cle = pseudos.cle(pseudo)
    if not pseudos.accepte(cle):
        return Entree(refus=RefusEntree.PSEUDO_INTERDIT)
    if len(joueurs_actifs(partie)) >= partie.max_players:
        return Entree(refus=RefusEntree.COMPLET)
    joueur = LivePlayer(
        game_id=partie.id,
        user_id=compte.id if compte else None,
        nickname=pseudo,
        nickname_key=cle[:20],
        token=secrets.token_urlsafe(32),
    )
    db.session.add(joueur)
    try:
        # La partie elle-même n'est pas modifiée : des dizaines d'arrivées simultanées ne se
        # bloquent pas entre elles. L'écran d'animation voit le nombre de joueurs changer.
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return Entree(refus=RefusEntree.PSEUDO_PRIS)
    return Entree(joueur=joueur)


def joueur_par_jeton(partie: LiveGame, jeton: str | None) -> LivePlayer | None:
    if not jeton:
        return None
    joueur: LivePlayer | None = db.session.scalar(
        select(LivePlayer).where(LivePlayer.game_id == partie.id, LivePlayer.token == jeton)
    )
    return joueur if joueur is not None and not joueur.kicked else None


# --- Déroulement ---------------------------------------------------------------------------


def _toucher(partie: LiveGame) -> None:
    """Nouvelle version (les écrans se rafraîchissent) sans changer d'écran."""
    db.session.execute(
        update(LiveGame)
        .where(LiveGame.id == partie.id)
        .values(version=LiveGame.version + 1, last_activity_at=_maintenant())
    )
    db.session.refresh(partie)


def _transition(partie: LiveGame, attendus: set[LiveStatus], **valeurs: Any) -> bool:
    """Change d'écran si la partie est toujours dans l'état vu par l'appelant (une seule fois).

    Si plusieurs requêtes tentent le même changement au même instant (fin du chrono vue par
    tous les écrans), une seule réussit ; un interblocage de la base est traité comme un
    échec sans conséquence : la requête suivante constatera l'état à jour.
    """
    try:
        resultat = db.session.execute(
            update(LiveGame)
            .where(
                LiveGame.id == partie.id,
                LiveGame.version == partie.version,
                LiveGame.status.in_(attendus),
            )
            .values(version=LiveGame.version + 1, last_activity_at=_maintenant(), **valeurs)
        )
        db.session.commit()
        reussi = bool(resultat.rowcount)  # type: ignore[attr-defined]
    except OperationalError:
        db.session.rollback()
        journal.info("partie %s : changement d'écran concurrent, ignoré", partie.id)
        reussi = False
    db.session.refresh(partie)
    return reussi


def _lancer_question(partie: LiveGame, index: int) -> bool:
    debut = _maintenant()
    return _transition(
        partie,
        {LiveStatus.LOBBY, LiveStatus.REVEAL},
        status=LiveStatus.QUESTION,
        current_index=index,
        question_started_at=debut,
        question_deadline=debut + timedelta(seconds=partie.time_limit),
        paused_remaining_ms=None,
    )


def demarrer(partie: LiveGame) -> bool:
    if partie.status is not LiveStatus.LOBBY or not joueurs_actifs(partie) or not partie.total:
        return False
    return _lancer_question(partie, 0)


def suivant(partie: LiveGame) -> bool:
    """Question en cours → correction ; correction → question suivante ou podium."""
    actualiser(partie)
    if partie.status in {LiveStatus.QUESTION, LiveStatus.PAUSED}:
        return _transition(
            partie,
            {LiveStatus.QUESTION, LiveStatus.PAUSED},
            status=LiveStatus.REVEAL,
            paused_remaining_ms=None,
        )
    if partie.status is LiveStatus.REVEAL:
        if partie.current_index + 1 < partie.total:
            return _lancer_question(partie, partie.current_index + 1)
        return terminer(partie)
    return False


def pause(partie: LiveGame) -> bool:
    actualiser(partie)
    if partie.status is not LiveStatus.QUESTION or partie.question_deadline is None:
        return False
    reste = max(0, _ms(partie.question_deadline - _maintenant()))
    return _transition(
        partie,
        {LiveStatus.QUESTION},
        status=LiveStatus.PAUSED,
        paused_remaining_ms=reste,
        question_deadline=None,
    )


def reprendre(partie: LiveGame) -> bool:
    if partie.status is not LiveStatus.PAUSED or partie.question_started_at is None:
        return False
    reste = timedelta(milliseconds=partie.paused_remaining_ms or 0)
    maintenant = _maintenant()
    deja_ecoule = timedelta(seconds=partie.time_limit) - reste
    # Le début est décalé de la durée de la pause : les points de rapidité restent justes.
    return _transition(
        partie,
        {LiveStatus.PAUSED},
        status=LiveStatus.QUESTION,
        question_started_at=maintenant - deja_ecoule,
        question_deadline=maintenant + reste,
        paused_remaining_ms=None,
    )


def terminer(partie: LiveGame) -> bool:
    if not partie.active:
        return False
    if not _transition(
        partie,
        set(LiveStatus) - {LiveStatus.FINISHED},
        status=LiveStatus.FINISHED,
        pin=None,
        ended_at=_maintenant(),
        question_deadline=None,
    ):
        return False
    live_bilan.enregistrer_resultats(partie)
    live_bilan.attribuer_badges(partie)
    journal.info("partie en direct %s terminée", partie.id)
    return True


def exclure(partie: LiveGame, joueur_id: int) -> bool:
    joueur = db.session.get(LivePlayer, joueur_id)
    if joueur is None or joueur.game_id != partie.id or joueur.kicked:
        return False
    joueur.kicked = True
    _toucher(partie)
    db.session.commit()
    return True


def actualiser(partie: LiveGame) -> None:
    """Passe à la correction si le chrono est écoulé ou si tous les joueurs ont répondu."""
    if partie.status is not LiveStatus.QUESTION or partie.question_deadline is None:
        return
    fini = _maintenant() >= partie.question_deadline
    actifs = len(joueurs_actifs(partie))
    if fini or (actifs and live_bilan.nombre_reponses(partie) >= actifs):
        _transition(partie, {LiveStatus.QUESTION}, status=LiveStatus.REVEAL)


def question_courante(partie: LiveGame) -> Question | None:
    if not 0 <= partie.current_index < partie.total:
        return None
    return db.session.get(Question, partie.question_ids[partie.current_index])


# --- Réponses et points ----------------------------------------------------------------------


class RefusReponse(enum.Enum):
    PAS_DE_QUESTION = "Aucune question n'est ouverte."
    MAUVAISE_QUESTION = "Cette question est terminée."
    DEJA_REPONDU = "Vous avez déjà répondu."
    TROP_TARD = "Temps écoulé !"


def repondre(
    partie: LiveGame, joueur: LivePlayer, position: int, choix: list[int]
) -> LiveAnswer | RefusReponse | correction.Refus:
    actualiser(partie)
    if partie.status is not LiveStatus.QUESTION or partie.question_started_at is None:
        return RefusReponse.PAS_DE_QUESTION
    if position != partie.current_index:
        return RefusReponse.MAUVAISE_QUESTION
    maintenant = _maintenant()
    if partie.question_deadline is None or maintenant > partie.question_deadline:
        return RefusReponse.TROP_TARD
    question = question_courante(partie)
    if question is None:
        return RefusReponse.PAS_DE_QUESTION
    verdict = correction.corriger(question, choix)
    if isinstance(verdict, correction.Refus):
        return verdict
    ecoule = max(0, _ms(maintenant - partie.question_started_at))
    juste = verdict
    gain = live_bilan.points(juste, ecoule, partie.time_limit)
    reponse = LiveAnswer(
        game_id=partie.id,
        player_id=joueur.id,
        position=position,
        question_id=question.id,
        selected_ids=correction.a_enregistrer(question, choix),
        is_correct=juste,
        points=gain,
        elapsed_ms=ecoule,
    )
    db.session.add(reponse)
    try:
        db.session.flush()
    except IntegrityError:
        db.session.rollback()
        return RefusReponse.DEJA_REPONDU
    # Addition faite par la base : deux réponses simultanées ne s'écrasent pas.
    db.session.execute(
        update(LivePlayer).where(LivePlayer.id == joueur.id).values(score=LivePlayer.score + gain)
    )
    db.session.commit()
    actualiser(partie)
    return reponse


# --- Lecture : état, classement, statistiques -----------------------------------------------


def etat(partie: LiveGame) -> dict[str, Any]:
    """État public de la partie, interrogé chaque seconde par les écrans (aucun secret)."""
    actualiser(partie)
    reste: int | None = None
    if partie.status is LiveStatus.QUESTION and partie.question_deadline is not None:
        reste = max(0, _ms(partie.question_deadline - _maintenant()))
    elif partie.status is LiveStatus.PAUSED:
        reste = partie.paused_remaining_ms
    return {
        "version": partie.version,
        "statut": partie.status.value,
        "question": partie.current_index + 1,
        "total": partie.total,
        "reste_ms": reste,
        "chrono_s": partie.time_limit,
        "reponses": live_bilan.nombre_reponses(partie),
        "joueurs": len(joueurs_actifs(partie)),
    }
