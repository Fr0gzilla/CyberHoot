"""Comptes : utilisateurs, rôles et jetons à usage unique (activation, réinitialisation)."""

from __future__ import annotations

import enum
import secrets
from datetime import UTC, datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Table,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db


def utcnow() -> datetime:
    """Heure UTC sans fuseau (les colonnes DATETIME de MySQL n'en gardent pas)."""
    return datetime.now(UTC).replace(tzinfo=None)


def nouveau_jeton_session() -> str:
    return secrets.token_hex(16)


class RoleName(enum.StrEnum):
    PLAYER = "player"
    CREATOR = "creator"
    ADMIN = "admin"


user_role = Table(
    "user_role",
    db.metadata,
    Column("user_id", Integer, ForeignKey("user.id", ondelete="CASCADE"), primary_key=True),
    Column("role_id", Integer, ForeignKey("role.id", ondelete="CASCADE"), primary_key=True),
)


class Role(db.Model):  # type: ignore[name-defined,misc]
    __tablename__ = "role"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    label: Mapped[str] = mapped_column(String(50), nullable=False)

    def __repr__(self) -> str:
        return f"<Role {self.name}>"


class User(db.Model):  # type: ignore[name-defined,misc]
    __tablename__ = "user"
    __table_args__ = (CheckConstraint("failed_logins >= 0", name="failed_logins_positif"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    email: Mapped[str] = mapped_column(String(254), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=utcnow, onupdate=utcnow
    )
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    failed_logins: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # Change à chaque changement de mot de passe : toutes les autres sessions tombent.
    session_token: Mapped[str] = mapped_column(
        String(32), nullable=False, default=nouveau_jeton_session
    )

    roles: Mapped[list[Role]] = relationship(secondary=user_role, lazy="selectin")
    tokens: Mapped[list[AccountToken]] = relationship(
        back_populates="user", cascade="all, delete-orphan", passive_deletes=True
    )

    # Interface attendue par Flask-Login
    @property
    def is_authenticated(self) -> bool:
        return True

    @property
    def is_active(self) -> bool:
        return self.is_enabled and self.email_verified_at is not None

    @property
    def is_anonymous(self) -> bool:
        return False

    def get_id(self) -> str:
        # L'identifiant de session porte le jeton : il devient invalide quand le jeton change.
        return f"{self.id}:{self.session_token}"

    def has_role(self, name: str) -> bool:
        return any(role.name == name for role in self.roles)

    @property
    def role_names(self) -> list[str]:
        return sorted(role.name for role in self.roles)

    def is_locked(self, maintenant: datetime | None = None) -> bool:
        return self.locked_until is not None and self.locked_until > (maintenant or utcnow())

    def __repr__(self) -> str:
        return f"<User {self.username}>"


class TokenPurpose(enum.StrEnum):
    ACTIVATION = "activation"
    RESET = "reset"


class AccountToken(db.Model):  # type: ignore[name-defined,misc]
    """Jeton à usage unique. Seule son empreinte SHA-256 est stockée."""

    __tablename__ = "account_token"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("user.id", ondelete="CASCADE"), nullable=False, index=True
    )
    purpose: Mapped[TokenPurpose] = mapped_column(
        Enum(TokenPurpose, name="token_purpose", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    user: Mapped[User] = relationship(back_populates="tokens")
