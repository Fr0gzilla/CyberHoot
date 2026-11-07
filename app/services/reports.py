"""Signalements de quiz ou d'avis par les joueurs, traités par les administrateurs."""

from __future__ import annotations

from sqlalchemy import ColumnElement, func, select

from app.extensions import db
from app.models import Quiz, Report, ReportStatus, Review, User, utcnow


def signaler(user: User, motif: str, quiz: Quiz | None = None, avis: Review | None = None) -> bool:
    """Un seul signalement ouvert par joueur et par cible ; False s'il existe déjà."""
    motif = motif.strip()[:500]
    if not motif or (quiz is None) == (avis is None):
        return False
    cible: ColumnElement[bool]  # if/else plutôt que ternaire : typage plus précis pour mypy
    if quiz is not None:  # noqa: SIM108
        cible = Report.quiz_id == quiz.id
    else:
        cible = Report.review_id == avis.id  # type: ignore[union-attr,assignment]
    deja = db.session.scalar(
        select(Report.id).where(
            Report.reporter_id == user.id, Report.status == ReportStatus.OPEN, cible
        )
    )
    if deja is not None:
        return False
    db.session.add(
        Report(
            reporter_id=user.id,
            quiz_id=quiz.id if quiz else None,
            review_id=avis.id if avis else None,
            reason=motif,
        )
    )
    db.session.commit()
    return True


def ouverts() -> list[Report]:
    return list(
        db.session.scalars(
            select(Report).where(Report.status == ReportStatus.OPEN).order_by(Report.created_at)
        )
    )


def nombre_ouverts() -> int:
    return (
        db.session.scalar(select(func.count(Report.id)).where(Report.status == ReportStatus.OPEN))
        or 0
    )


def clore(signalement: Report, admin: User, resolution: str) -> None:
    signalement.status = ReportStatus.CLOSED
    signalement.handled_at = utcnow()
    signalement.handled_by_id = admin.id
    signalement.resolution = resolution[:255]
    db.session.commit()
