"""Double authentification par code à usage unique (TOTP, RFC 6238).

- Obligatoire pour les administrateurs, possible pour tous les comptes.
- Le secret est chiffré en base (Fernet, clé dérivée de SECRET_KEY) : une copie de la base
  seule ne suffit pas à générer des codes.
- Un code ne sert qu'une fois (on retient le dernier pas de 30 s accepté) ; une dérive
  d'horloge d'un pas est tolérée.
- 10 codes de secours, à usage unique, stockés sous forme d'empreinte.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import time

import pyotp
import segno
from cryptography.fernet import Fernet, InvalidToken
from flask import current_app
from markupsafe import Markup
from sqlalchemy import delete, select

from app.extensions import db
from app.models import RecoveryCode, User, utcnow

EMETTEUR = "CyberHoot"
NB_CODES_SECOURS = 10
PAS = 30


def _fernet() -> Fernet:
    cle = hashlib.sha256(b"cyberhoot-totp:" + current_app.config["SECRET_KEY"].encode()).digest()
    return Fernet(base64.urlsafe_b64encode(cle))


def chiffrer(secret: str) -> str:
    return _fernet().encrypt(secret.encode()).decode()


def dechiffrer(chiffre: str) -> str | None:
    try:
        return _fernet().decrypt(chiffre.encode()).decode()
    except InvalidToken:
        return None


def nouveau_secret() -> str:
    return pyotp.random_base32()


def lien(user: User, secret: str) -> str:
    return pyotp.TOTP(secret).provisioning_uri(name=user.email, issuer_name=EMETTEUR)


def qr(user: User, secret: str) -> Markup:
    svg = segno.make(lien(user, secret), error="m").svg_inline(
        scale=5,
        dark="#07100a",
        light="#ffffff",
        omitsize=True,
        title="Code QR à scanner avec l'application d'authentification",
    )
    # Produit par segno à partir de données que nous générons : aucun contenu utilisateur.
    return Markup(svg)  # noqa: S704  # nosec B704


def _code_propre(code: str) -> str:
    return "".join(c for c in code if c.isalnum()).lower()


def _pas_valide(secret: str, code: str, dernier: int | None) -> int | None:
    """Pas de temps correspondant au code (dérive d'un pas tolérée), s'il n'a pas déjà servi."""
    if not (len(code) == 6 and code.isdigit()):
        return None
    totp = pyotp.TOTP(secret)
    maintenant = int(time.time()) // PAS
    for pas in (maintenant - 1, maintenant, maintenant + 1):
        if hmac.compare_digest(totp.at(pas * PAS), code) and (dernier is None or pas > dernier):
            return pas
    return None


def _hacher(code: str) -> str:
    return hashlib.sha256(_code_propre(code).encode()).hexdigest()


def _nouveaux_codes(user: User) -> list[str]:
    db.session.execute(delete(RecoveryCode).where(RecoveryCode.user_id == user.id))
    codes = [
        f"{secrets.token_hex(2)}-{secrets.token_hex(2)}-{secrets.token_hex(2)}"
        for _ in range(NB_CODES_SECOURS)
    ]
    for code in codes:
        db.session.add(RecoveryCode(user_id=user.id, code_hash=_hacher(code)))
    return codes


def activer(user: User, secret: str, code: str) -> list[str] | None:
    """Active la double authentification si le code est juste ; renvoie les codes de secours."""
    pas = _pas_valide(secret, _code_propre(code), None)
    if pas is None:
        return None
    user.totp_secret = chiffrer(secret)
    user.totp_enabled_at = utcnow()
    user.totp_last_step = pas
    codes = _nouveaux_codes(user)
    db.session.commit()
    return codes


def regenerer_codes(user: User) -> list[str]:
    codes = _nouveaux_codes(user)
    db.session.commit()
    return codes


def desactiver(user: User) -> None:
    user.totp_secret = None
    user.totp_enabled_at = None
    user.totp_last_step = None
    db.session.execute(delete(RecoveryCode).where(RecoveryCode.user_id == user.id))
    db.session.commit()


def verifier(user: User, saisie: str) -> str | None:
    """« totp » ou « secours » si la saisie est acceptée (et consommée), sinon None."""
    if not user.totp_enabled or not user.totp_secret:
        return None
    secret = dechiffrer(user.totp_secret)
    code = _code_propre(saisie)
    if secret:
        pas = _pas_valide(secret, code, user.totp_last_step)
        if pas is not None:
            user.totp_last_step = pas
            db.session.commit()
            return "totp"
    if len(code) == 12:
        trouve = db.session.scalar(
            select(RecoveryCode).where(
                RecoveryCode.user_id == user.id,
                RecoveryCode.code_hash == _hacher(code),
                RecoveryCode.used_at.is_(None),
            )
        )
        if trouve is not None:
            trouve.used_at = utcnow()
            db.session.commit()
            return "secours"
    return None


def codes_restants(user: User) -> int:
    return len(
        db.session.scalars(
            select(RecoveryCode.id).where(
                RecoveryCode.user_id == user.id, RecoveryCode.used_at.is_(None)
            )
        ).all()
    )
