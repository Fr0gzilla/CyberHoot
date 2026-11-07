"""Parties en direct : une salle (code PIN), ses joueurs et leurs réponses."""

from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db
from app.models.account import User, utcnow
from app.models.quiz import Quiz, _enum


class LiveStatus(enum.StrEnum):
    LOBBY = "lobby"  # salle d'attente
    QUESTION = "question"  # question affichée, chrono en cours
    PAUSED = "paused"  # chrono suspendu par l'animateur
    REVEAL = "reveal"  # correction et classement intermédiaire
    FINISHED = "finished"  # podium


class LiveGame(db.Model):  # type: ignore[name-defined,misc]
    __tablename__ = "live_game"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # Libéré (NULL) à la fin de la partie : un même PIN ne sert qu'à une partie active.
    pin: Mapped[str | None] = mapped_column(String(6), unique=True, nullable=True)
    host_id: Mapped[int | None] = mapped_column(
        ForeignKey("user.id", ondelete="SET NULL"), nullable=True, index=True
    )
    quiz_id: Mapped[int] = mapped_column(
        ForeignKey("quiz.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[LiveStatus] = mapped_column(
        _enum(LiveStatus, "live_status"), nullable=False, default=LiveStatus.LOBBY
    )
    question_ids: Mapped[list[int]] = mapped_column(JSON, nullable=False)
    current_index: Mapped[int] = mapped_column(Integer, nullable=False, default=-1)
    time_limit: Mapped[int] = mapped_column(Integer, nullable=False, default=20)
    max_players: Mapped[int] = mapped_column(Integer, nullable=False, default=200)
    question_started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    question_deadline: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    paused_remaining_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Change à chaque changement d'écran : les navigateurs savent qu'ils doivent se rafraîchir.
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    last_activity_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    quiz: Mapped[Quiz] = relationship()
    host: Mapped[User | None] = relationship()
    players: Mapped[list[LivePlayer]] = relationship(
        back_populates="game",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="LivePlayer.joined_at",
    )

    @property
    def total(self) -> int:
        return len(self.question_ids)

    @property
    def active(self) -> bool:
        return self.status is not LiveStatus.FINISHED


class LivePlayer(db.Model):  # type: ignore[name-defined,misc]
    __tablename__ = "live_player"
    __table_args__ = (UniqueConstraint("game_id", "nickname_key", name="pseudo_unique"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    game_id: Mapped[int] = mapped_column(
        ForeignKey("live_game.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("user.id", ondelete="SET NULL"), nullable=True
    )
    nickname: Mapped[str] = mapped_column(String(20), nullable=False)
    # Pseudo normalisé (minuscules) : « Alice » et « alice » ne peuvent coexister.
    nickname_key: Mapped[str] = mapped_column(String(20), nullable=False)
    # Secret du joueur (cookie de session) : permet de revenir après une coupure.
    token: Mapped[str] = mapped_column(String(43), unique=True, nullable=False)
    score: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    kicked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    joined_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)

    game: Mapped[LiveGame] = relationship(back_populates="players")


class LiveAnswer(db.Model):  # type: ignore[name-defined,misc]
    __tablename__ = "live_answer"
    __table_args__ = (UniqueConstraint("player_id", "position", name="une_reponse_par_question"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    game_id: Mapped[int] = mapped_column(
        ForeignKey("live_game.id", ondelete="CASCADE"), nullable=False, index=True
    )
    player_id: Mapped[int] = mapped_column(
        ForeignKey("live_player.id", ondelete="CASCADE"), nullable=False
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    question_id: Mapped[int | None] = mapped_column(
        ForeignKey("question.id", ondelete="SET NULL"), nullable=True
    )
    selected_ids: Mapped[list[int]] = mapped_column(JSON, nullable=False)
    is_correct: Mapped[bool] = mapped_column(Boolean, nullable=False)
    points: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    elapsed_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    answered_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
