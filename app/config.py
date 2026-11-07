"""Configuration de l'application.

La configuration de production est celle par défaut : le mode développement ne s'obtient
qu'en posant explicitement APP_ENV=development. Les secrets se lisent dans une variable
d'environnement ou dans un fichier (secrets Docker, variable <NOM>_FILE) ; l'application
refuse de démarrer si un secret obligatoire manque ou garde une valeur d'exemple.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus

# Valeurs d'exemple qu'on ne doit jamais retrouver en service.
VALEURS_INTERDITES = frozenset(
    {
        "changeme",
        "change-me",
        "secret",
        "password",
        "motdepasse",
        "a-remplacer",
        "votre_cle_secrete_ici",
        "cle_secrete_a_changer_en_production",
    }
)
LONGUEUR_MIN_CLE = 32


class ConfigurationError(RuntimeError):
    """Configuration absente ou dangereuse : l'application ne doit pas démarrer."""


def lire_secret(nom: str, obligatoire: bool = True, longueur_min: int = 1) -> str | None:
    """Lit un secret dans <nom>_FILE (fichier) en priorité, sinon dans la variable <nom>."""
    valeur: str | None = None
    chemin = os.environ.get(f"{nom}_FILE")
    if chemin:
        try:
            valeur = Path(chemin).read_text(encoding="utf-8").strip()
        except OSError as exc:
            raise ConfigurationError(f"{nom}_FILE illisible : {chemin}") from exc
    else:
        valeur = os.environ.get(nom)

    if not valeur:
        if obligatoire:
            raise ConfigurationError(f"secret obligatoire absent : {nom} (ou {nom}_FILE)")
        return None
    if valeur.lower() in VALEURS_INTERDITES:
        raise ConfigurationError(f"{nom} garde une valeur d'exemple : choisissez un vrai secret")
    if len(valeur) < longueur_min:
        raise ConfigurationError(f"{nom} trop court ({longueur_min} caractères minimum)")
    return valeur


def _booleen(nom: str, defaut: bool) -> bool:
    brut = os.environ.get(nom)
    if brut is None:
        return defaut
    return brut.strip().lower() in {"1", "true", "oui", "yes", "on"}


def _url_base() -> str:
    """Construit l'URL MySQL depuis les variables, ou prend DATABASE_URL telle quelle."""
    url = os.environ.get("DATABASE_URL")
    if url:
        return url
    hote = os.environ.get("DB_HOST", "db")
    port = os.environ.get("DB_PORT", "3306")
    nom = os.environ.get("DB_NAME", "cyberhoot")
    utilisateur = os.environ.get("DB_USER", "cyberhoot")
    mot_de_passe = lire_secret("DB_PASSWORD") or ""
    return (
        f"mysql+pymysql://{quote_plus(utilisateur)}:{quote_plus(mot_de_passe)}"
        f"@{hote}:{port}/{nom}?charset=utf8mb4"
    )


@dataclass
class Config:
    """Réglages communs ; les classes filles ne changent que ce qui diffère."""

    APP_ENV: str = "production"
    DEBUG: bool = False
    TESTING: bool = False
    SECRET_KEY: str = ""
    SQLALCHEMY_DATABASE_URI: str = ""
    SQLALCHEMY_ENGINE_OPTIONS: dict[str, Any] = field(
        default_factory=lambda: {"pool_pre_ping": True, "pool_recycle": 280}
    )
    SQLALCHEMY_TRACK_MODIFICATIONS: bool = False

    # Session et cookies
    SESSION_COOKIE_NAME: str = "cyberhoot_session"
    SESSION_COOKIE_HTTPONLY: bool = True
    SESSION_COOKIE_SECURE: bool = True
    SESSION_COOKIE_SAMESITE: str = "Lax"
    REMEMBER_COOKIE_HTTPONLY: bool = True
    REMEMBER_COOKIE_SECURE: bool = True
    REMEMBER_COOKIE_SAMESITE: str = "Lax"
    REMEMBER_COOKIE_DURATION: int = 60 * 60 * 24 * 30
    PERMANENT_SESSION_LIFETIME: int = 60 * 60 * 8
    MAX_CONTENT_LENGTH: int = 4 * 1024 * 1024
    SEND_FILE_MAX_AGE_DEFAULT: int = 60 * 60

    # CSRF
    WTF_CSRF_ENABLED: bool = True
    WTF_CSRF_TIME_LIMIT: int = 60 * 60

    # Limitation de débit (Redis partagé entre les processus en service)
    RATELIMIT_STORAGE_URI: str = "memory://"
    RATELIMIT_HEADERS_ENABLED: bool = True
    RATELIMIT_ENABLED: bool = True

    # Comptes
    VERROU_ECHECS_MAX: int = 5
    VERROU_DUREE_MINUTES: int = 15
    JETON_DUREE_MINUTES: int = 30

    # Messagerie : "console" (journal), "memoire" (tests) ou "smtp"
    MAIL_BACKEND: str = "console"
    MAIL_FROM: str = "CyberHoot <no-reply@cyberhoot.local>"
    SMTP_HOST: str = "localhost"
    SMTP_PORT: int = 587
    SMTP_USER: str | None = None
    SMTP_PASSWORD: str | None = None
    SMTP_STARTTLS: bool = True

    # URL publique, utilisée dans les liens envoyés par e-mail
    PUBLIC_URL: str = "http://localhost:8080"

    # Derrière le proxy Nginx : nombre de proxys de confiance devant l'application
    PROXY_COUNT: int = 1


def charger_config(env: str | None = None) -> Config:
    """Construit la configuration de l'environnement demandé (production par défaut)."""
    env = (env or os.environ.get("APP_ENV") or "production").strip().lower()
    if env not in {"production", "development", "testing"}:
        raise ConfigurationError(f"APP_ENV inconnu : {env}")

    if env == "testing":
        return Config(
            APP_ENV="testing",
            TESTING=True,
            SECRET_KEY="cle-de-test-uniquement-" + "x" * 32,
            SQLALCHEMY_DATABASE_URI=os.environ.get("TEST_DATABASE_URL", "sqlite://"),
            SQLALCHEMY_ENGINE_OPTIONS={},
            SESSION_COOKIE_SECURE=False,
            REMEMBER_COOKIE_SECURE=False,
            MAIL_BACKEND="memoire",
            PROXY_COUNT=0,
        )

    config = Config(
        APP_ENV=env,
        SECRET_KEY=lire_secret("SECRET_KEY", longueur_min=LONGUEUR_MIN_CLE) or "",
        SQLALCHEMY_DATABASE_URI=_url_base(),
        RATELIMIT_STORAGE_URI=os.environ.get("REDIS_URL", "memory://"),
        MAIL_BACKEND=os.environ.get("MAIL_BACKEND", "console"),
        MAIL_FROM=os.environ.get("MAIL_FROM", Config.MAIL_FROM),
        SMTP_HOST=os.environ.get("SMTP_HOST", "localhost"),
        SMTP_PORT=int(os.environ.get("SMTP_PORT", "587")),
        SMTP_USER=os.environ.get("SMTP_USER"),
        SMTP_PASSWORD=lire_secret("SMTP_PASSWORD", obligatoire=False),
        SMTP_STARTTLS=_booleen("SMTP_STARTTLS", True),
        PUBLIC_URL=os.environ.get("PUBLIC_URL", Config.PUBLIC_URL).rstrip("/"),
        PROXY_COUNT=int(os.environ.get("PROXY_COUNT", "1")),
    )
    if env == "development":
        config.DEBUG = True
        config.SESSION_COOKIE_SECURE = False
        config.REMEMBER_COOKIE_SECURE = False
    else:
        # En production, les cookies ne passent qu'en HTTPS, sauf choix explicite pour un
        # essai local en HTTP (documenté dans le README).
        secure = _booleen("COOKIE_SECURE", True)
        config.SESSION_COOKIE_SECURE = secure
        config.REMEMBER_COOKIE_SECURE = secure
    if config.MAIL_BACKEND not in {"console", "memoire", "smtp"}:
        raise ConfigurationError(f"MAIL_BACKEND inconnu : {config.MAIL_BACKEND}")
    return config
