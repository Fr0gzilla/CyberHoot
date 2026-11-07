"""Jetons à usage unique (activation de compte, réinitialisation du mot de passe).

Le jeton envoyé par e-mail n'est jamais stocké : la base garde son empreinte SHA-256.
Un jeton sert une seule fois, expire, et tout nouveau jeton du même usage annule les
précédents.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import timedelta

from sqlalchemy import select, update

from app.extensions import db
from app.models import AccountToken, TokenPurpose, User, utcnow


def _empreinte(jeton: str) -> str:
    return hashlib.sha256(jeton.encode("utf-8")).hexdigest()


def emettre(user: User, usage: TokenPurpose, duree_minutes: int) -> str:
    """Crée un jeton, annule ceux du même usage encore valides, et renvoie le jeton en clair."""
    maintenant = utcnow()
    db.session.execute(
        update(AccountToken)
        .where(
            AccountToken.user_id == user.id,
            AccountToken.purpose == usage,
            AccountToken.used_at.is_(None),
        )
        .values(used_at=maintenant)
    )
    jeton = secrets.token_urlsafe(32)
    db.session.add(
        AccountToken(
            user_id=user.id,
            purpose=usage,
            token_hash=_empreinte(jeton),
            created_at=maintenant,
            expires_at=maintenant + timedelta(minutes=duree_minutes),
        )
    )
    return jeton


def trouver_valide(jeton: str, usage: TokenPurpose) -> AccountToken | None:
    """Le jeton s'il existe, correspond à l'usage, n'a pas servi et n'a pas expiré."""
    if not jeton or len(jeton) > 128:
        return None
    trouve: AccountToken | None = db.session.scalar(
        select(AccountToken).where(AccountToken.token_hash == _empreinte(jeton))
    )
    if trouve is None or trouve.purpose != usage or trouve.used_at is not None:
        return None
    if trouve.expires_at <= utcnow():
        return None
    return trouve


def consommer(jeton: AccountToken) -> None:
    jeton.used_at = utcnow()


def annuler_tous(user: User) -> None:
    """Annule tous les jetons en cours d'un compte (après un changement de mot de passe)."""
    db.session.execute(
        update(AccountToken)
        .where(AccountToken.user_id == user.id, AccountToken.used_at.is_(None))
        .values(used_at=utcnow())
    )
