"""Quiz : catégories, quiz, questions, réponses proposées, médias, parties en solo, avis."""

from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db
from app.models.account import User, utcnow


def _enum(classe: type[enum.Enum], nom: str) -> Enum:
    """Énumération stockée par valeur (« draft ») et non par nom (« DRAFT »)."""
    return Enum(classe, name=nom, values_callable=lambda e: [m.value for m in e])


class Difficulty(enum.StrEnum):
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"


DIFFICULTE_LIBELLES = {
    Difficulty.EASY: "Débutant",
    Difficulty.MEDIUM: "Intermédiaire",
    Difficulty.HARD: "Avancé",
}


class QuizStatus(enum.StrEnum):
    DRAFT = "draft"
    PENDING = "pending"
    PUBLISHED = "published"
    REJECTED = "rejected"


STATUT_LIBELLES = {
    QuizStatus.DRAFT: "Brouillon",
    QuizStatus.PENDING: "En attente de validation",
    QuizStatus.PUBLISHED: "Publié",
    QuizStatus.REJECTED: "Refusé",
}


class QuestionKind(enum.StrEnum):
    CHOICE = "choice"  # choix unique ou multiple (selon le nombre de bonnes réponses)
    TRUE_FALSE = "true_false"  # vrai ou faux
    PHISHING = "phishing"  # repérer les indices suspects d'un faux message
    ORDER = "order"  # remettre des étapes dans l'ordre


TYPE_LIBELLES = {
    QuestionKind.CHOICE: "Choix (une ou plusieurs bonnes réponses)",
    QuestionKind.TRUE_FALSE: "Vrai ou faux",
    QuestionKind.PHISHING: "Repérer le phishing",
    QuestionKind.ORDER: "Remettre dans l'ordre",
}


class MediaStatus(enum.StrEnum):
    PENDING = "pending"
    CLEAN = "clean"
    REJECTED = "rejected"


class Category(db.Model):  # type: ignore[name-defined,misc]
    __tablename__ = "category"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    slug: Mapped[str] = mapped_column(String(40), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    description: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class Quiz(db.Model):  # type: ignore[name-defined,misc]
    __tablename__ = "quiz"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    creator_id: Mapped[int | None] = mapped_column(
        ForeignKey("user.id", ondelete="SET NULL"), nullable=True, index=True
    )
    category_id: Mapped[int] = mapped_column(
        ForeignKey("category.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    difficulty: Mapped[Difficulty] = mapped_column(_enum(Difficulty, "difficulty"), nullable=False)
    status: Mapped[QuizStatus] = mapped_column(
        _enum(QuizStatus, "quiz_status"), nullable=False, default=QuizStatus.DRAFT, index=True
    )
    rejection_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=utcnow, onupdate=utcnow
    )
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    creator: Mapped[User | None] = relationship()
    category: Mapped[Category] = relationship(lazy="joined")
    questions: Mapped[list[Question]] = relationship(
        back_populates="quiz",
        order_by="Question.position",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    @property
    def difficulty_label(self) -> str:
        return DIFFICULTE_LIBELLES[self.difficulty]

    @property
    def status_label(self) -> str:
        return STATUT_LIBELLES[self.status]

    @property
    def is_published(self) -> bool:
        return self.status is QuizStatus.PUBLISHED


class Media(db.Model):  # type: ignore[name-defined,misc]
    """Image téléversée : ré-encodée, renommée, servie seulement après analyse."""

    __tablename__ = "media"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    uid: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    owner_id: Mapped[int | None] = mapped_column(
        ForeignKey("user.id", ondelete="SET NULL"), nullable=True, index=True
    )
    mime_type: Mapped[str] = mapped_column(String(30), nullable=False)
    size: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    status: Mapped[MediaStatus] = mapped_column(
        _enum(MediaStatus, "media_status"), nullable=False, default=MediaStatus.PENDING, index=True
    )
    scan_detail: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    scanned_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    @property
    def extension(self) -> str:
        return {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp"}[self.mime_type]

    @property
    def filename(self) -> str:
        return f"{self.uid}.{self.extension}"


class Question(db.Model):  # type: ignore[name-defined,misc]
    __tablename__ = "question"
    __table_args__ = (UniqueConstraint("quiz_id", "position", name="quiz_position"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    quiz_id: Mapped[int] = mapped_column(ForeignKey("quiz.id", ondelete="CASCADE"), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    kind: Mapped[QuestionKind] = mapped_column(
        _enum(QuestionKind, "question_kind"), nullable=False, default=QuestionKind.CHOICE
    )
    text: Mapped[str] = mapped_column(String(500), nullable=False)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    # Données propres au type : pour « phishing », l'en-tête du faux message
    # (canal, expéditeur, objet). Les morceaux du message sont les réponses proposées.
    payload: Mapped[dict[str, str] | None] = mapped_column(JSON, nullable=True)
    media_id: Mapped[int | None] = mapped_column(
        ForeignKey("media.id", ondelete="SET NULL"), nullable=True
    )
    media_alt: Mapped[str | None] = mapped_column(String(200), nullable=True)

    quiz: Mapped[Quiz] = relationship(back_populates="questions")
    media: Mapped[Media | None] = relationship(lazy="joined")
    options: Mapped[list[AnswerOption]] = relationship(
        back_populates="question",
        order_by="AnswerOption.position",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="selectin",
    )

    @property
    def correct_ids(self) -> set[int]:
        return {option.id for option in self.options if option.is_correct}

    @property
    def multiple(self) -> bool:
        """Plusieurs réponses à cocher (et non un seul choix)."""
        if self.kind is QuestionKind.PHISHING:
            return True
        return self.kind is QuestionKind.CHOICE and len(self.correct_ids) > 1

    @property
    def ordre_attendu(self) -> list[int]:
        """Pour « remettre dans l'ordre » : identifiants dans l'ordre correct (positions)."""
        return [option.id for option in self.options]


class AnswerOption(db.Model):  # type: ignore[name-defined,misc]
    __tablename__ = "answer_option"
    __table_args__ = (UniqueConstraint("question_id", "position", name="question_position"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    question_id: Mapped[int] = mapped_column(
        ForeignKey("question.id", ondelete="CASCADE"), nullable=False
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(String(300), nullable=False)
    is_correct: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    question: Mapped[Question] = relationship(back_populates="options")


class PlaySession(db.Model):  # type: ignore[name-defined,misc]
    """Partie en solo. Le serveur tient l'ordre des questions et corrige chaque réponse."""

    __tablename__ = "play_session"
    __table_args__ = (
        CheckConstraint("score >= 0", name="score_positif"),
        CheckConstraint("current_index >= 0", name="index_positif"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    token: Mapped[str] = mapped_column(String(43), unique=True, nullable=False)
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("user.id", ondelete="SET NULL"), nullable=True, index=True
    )
    quiz_id: Mapped[int] = mapped_column(
        ForeignKey("quiz.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Identifiants des questions dans l'ordre servi, figés au démarrage de la partie.
    question_ids: Mapped[list[int]] = mapped_column(JSON, nullable=False)
    current_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    score: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total: Mapped[int] = mapped_column(Integer, nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    quiz: Mapped[Quiz] = relationship()
    answers: Mapped[list[PlayAnswer]] = relationship(
        back_populates="session",
        order_by="PlayAnswer.position",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    @property
    def finished(self) -> bool:
        return self.finished_at is not None

    @property
    def percent(self) -> int:
        return round(100 * self.score / self.total) if self.total else 0


class PlayAnswer(db.Model):  # type: ignore[name-defined,misc]
    __tablename__ = "play_answer"
    __table_args__ = (UniqueConstraint("session_id", "position", name="session_position"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("play_session.id", ondelete="CASCADE"), nullable=False
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    question_id: Mapped[int | None] = mapped_column(
        ForeignKey("question.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # Identifiants des réponses choisies (JSON, jamais de repr Python).
    selected_ids: Mapped[list[int]] = mapped_column(JSON, nullable=False)
    is_correct: Mapped[bool] = mapped_column(Boolean, nullable=False)
    answered_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)

    session: Mapped[PlaySession] = relationship(back_populates="answers")
    question: Mapped[Question | None] = relationship()


class Review(db.Model):  # type: ignore[name-defined,misc]
    __tablename__ = "review"
    __table_args__ = (
        UniqueConstraint("user_id", "quiz_id", name="un_avis_par_joueur"),
        CheckConstraint("rating BETWEEN 1 AND 5", name="note_1_a_5"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id", ondelete="CASCADE"), nullable=False)
    quiz_id: Mapped[int] = mapped_column(
        ForeignKey("quiz.id", ondelete="CASCADE"), nullable=False, index=True
    )
    rating: Mapped[int] = mapped_column(Integer, nullable=False)
    comment: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=utcnow, onupdate=utcnow
    )

    user: Mapped[User] = relationship()


class BadgeRule(enum.StrEnum):
    PARTIES = "parties"  # nombre de parties terminées ≥ seuil
    SANS_FAUTE = "sans_faute"  # une partie sans faute (au moins `seuil` questions)
    ZERO = "zero"  # une partie à zéro (au moins `seuil` questions)
    SERIE = "serie"  # jours consécutifs avec une partie terminée ≥ seuil
    EXPERT = "expert"  # ≥ 80 % de réussite sur au moins `seuil` réponses d'une catégorie
    ANIMATEUR = "animateur"  # parties en direct animées (au moins 3 joueurs) ≥ seuil
    VAINQUEUR = "vainqueur"  # première place en direct (au moins 3 joueurs) ≥ seuil
    CREATEUR = "createur"  # quiz publiés ≥ seuil


class Badge(db.Model):  # type: ignore[name-defined,misc]
    """Badge : défini une seule fois, comme donnée de référence (migrations)."""

    __tablename__ = "badge"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(40), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    description: Mapped[str] = mapped_column(String(255), nullable=False)
    icon: Mapped[str] = mapped_column(String(8), nullable=False)
    rule: Mapped[BadgeRule] = mapped_column(_enum(BadgeRule, "badge_rule"), nullable=False)
    threshold: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    category_id: Mapped[int | None] = mapped_column(
        ForeignKey("category.id", ondelete="CASCADE"), nullable=True
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    category: Mapped[Category | None] = relationship(lazy="joined")


class UserBadge(db.Model):  # type: ignore[name-defined,misc]
    __tablename__ = "user_badge"

    user_id: Mapped[int] = mapped_column(
        ForeignKey("user.id", ondelete="CASCADE"), primary_key=True
    )
    badge_id: Mapped[int] = mapped_column(
        ForeignKey("badge.id", ondelete="CASCADE"), primary_key=True
    )
    obtained_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)

    badge: Mapped[Badge] = relationship(lazy="joined")
