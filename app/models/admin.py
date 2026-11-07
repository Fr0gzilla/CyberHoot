"""Administration : journal d'audit, signalements, double authentification."""

from __future__ import annotations

import enum
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db
from app.models.account import User, utcnow
from app.models.quiz import Quiz, Review, _enum


class AuditLog(db.Model):  # type: ignore[name-defined,misc]
    """Journal d'audit : ajouté par l'application, jamais modifié ; purgé après 12 mois."""

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=utcnow, index=True
    )
    # Compte à l'origine de l'action (NULL : visiteur, ou compte supprimé depuis).
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("user.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # Pseudo au moment de l'action : le journal reste lisible après une suppression.
    username: Mapped[str | None] = mapped_column(String(32), nullable=True)
    ip: Mapped[str | None] = mapped_column(String(45), nullable=True)
    action: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    target: Mapped[str | None] = mapped_column(String(120), nullable=True)
    details: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    user: Mapped[User | None] = relationship()


class ReportStatus(enum.StrEnum):
    OPEN = "open"
    CLOSED = "closed"


class Report(db.Model):  # type: ignore[name-defined,misc]
    """Signalement d'un quiz ou d'un avis par un joueur."""

    __tablename__ = "report"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    reporter_id: Mapped[int | None] = mapped_column(
        ForeignKey("user.id", ondelete="SET NULL"), nullable=True
    )
    quiz_id: Mapped[int | None] = mapped_column(
        ForeignKey("quiz.id", ondelete="CASCADE"), nullable=True, index=True
    )
    review_id: Mapped[int | None] = mapped_column(
        ForeignKey("review.id", ondelete="CASCADE"), nullable=True
    )
    reason: Mapped[str] = mapped_column(String(500), nullable=False)
    status: Mapped[ReportStatus] = mapped_column(
        _enum(ReportStatus, "report_status"), nullable=False, default=ReportStatus.OPEN, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    handled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    handled_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("user.id", ondelete="SET NULL"), nullable=True
    )
    resolution: Mapped[str | None] = mapped_column(String(255), nullable=True)

    reporter: Mapped[User | None] = relationship(foreign_keys=[reporter_id])
    quiz: Mapped[Quiz | None] = relationship()
    review: Mapped[Review | None] = relationship()


class RecoveryCode(db.Model):  # type: ignore[name-defined,misc]
    """Code de secours de la double authentification : haché, à usage unique."""

    __tablename__ = "recovery_code"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("user.id", ondelete="CASCADE"), nullable=False, index=True
    )
    code_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
