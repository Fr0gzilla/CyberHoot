"""Entretien des parties en direct (lancé par le processus de fond)."""

from __future__ import annotations

from datetime import timedelta

from sqlalchemy import select

from app.extensions import db
from app.models import LiveGame, LiveStatus, utcnow
from app.services import live

INACTIVITE = timedelta(hours=3)
CONSERVATION = timedelta(hours=24)


def purger() -> tuple[int, int]:
    """Termine les parties abandonnées (3 h sans activité) et efface celles finies depuis 24 h.

    Les joueurs anonymes ne laissent ainsi aucune donnée au-delà d'une journée.
    """
    maintenant = utcnow()
    abandonnees = list(
        db.session.scalars(
            select(LiveGame).where(
                LiveGame.status != LiveStatus.FINISHED,
                LiveGame.last_activity_at < maintenant - INACTIVITE,
            )
        )
    )
    for partie in abandonnees:
        live.terminer(partie)
    anciennes = list(
        db.session.scalars(
            select(LiveGame).where(
                LiveGame.status == LiveStatus.FINISHED,
                LiveGame.ended_at < maintenant - CONSERVATION,
            )
        )
    )
    for partie in anciennes:
        db.session.delete(partie)
    db.session.commit()
    return len(abandonnees), len(anciennes)
