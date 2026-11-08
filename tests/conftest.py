"""Fixtures communes.

La base de test est construite par les migrations Alembic, comme en production (jamais par
create_all) : un écart entre modèles et migrations casse donc les tests. Par défaut SQLite
dans un fichier temporaire ; en CI, TEST_DATABASE_URL pointe vers un vrai MySQL.
"""

from __future__ import annotations

import os
import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from alembic import command
from alembic.config import Config as AlembicConfig
from flask import Flask
from flask.testing import FlaskClient
from sqlalchemy import create_engine, delete, select, text

from app import create_app
from app.config import charger_config
from app.extensions import db, limiter
from app.models import AuditLog, LiveGame, Quiz, RoleName, User
from app.services import accounts, mail

RACINE = Path(__file__).resolve().parent.parent
MOT_DE_PASSE = "Phrase de passe solide 42"


def alembic_config(url: str) -> AlembicConfig:
    config = AlembicConfig(str(RACINE / "alembic.ini"))
    config.set_main_option("script_location", str(RACINE / "migrations"))
    config.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    return config


@pytest.fixture(scope="session", autouse=True)
def horloge_sans_recul() -> Iterator[None]:
    """Horodatage des jetons signés (session, CSRF) qui ne recule jamais.

    L'horloge des machines virtuelles Docker sur Mac recule parfois de quelques
    centaines de millisecondes ; un jeton paraît alors « venir du futur » et itsdangerous
    le refuse, ce qui fait échouer un test au hasard. Ce n'est pas un défaut de
    l'application (un serveur Linux à l'heure n'a pas ce problème), seulement des tests.
    """
    from itsdangerous import timed

    origine = timed.TimestampSigner.get_timestamp
    dernier = 0

    def get_timestamp(self: timed.TimestampSigner) -> int:
        nonlocal dernier
        dernier = max(dernier, origine(self))
        return dernier

    timed.TimestampSigner.get_timestamp = get_timestamp  # type: ignore[method-assign]
    yield
    timed.TimestampSigner.get_timestamp = origine  # type: ignore[method-assign]


@pytest.fixture(scope="session")
def database_url(tmp_path_factory: pytest.TempPathFactory) -> Iterator[str]:
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        url = f"sqlite:///{tmp_path_factory.mktemp('db') / 'test.db'}"
    moteur = create_engine(url)
    with moteur.begin() as connexion:
        if moteur.dialect.name == "mysql":
            connexion.execute(text("SET FOREIGN_KEY_CHECKS = 0"))
            for (table,) in connexion.execute(text("SHOW TABLES")).all():
                connexion.execute(text(f"DROP TABLE `{table}`"))
            connexion.execute(text("SET FOREIGN_KEY_CHECKS = 1"))
    moteur.dispose()
    command.upgrade(alembic_config(url), "head")
    return url


@pytest.fixture
def app(database_url: str, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[Flask]:
    monkeypatch.setenv("TEST_DATABASE_URL", database_url)
    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path / "uploads"))
    application = create_app(charger_config("testing"))
    application.test_client_class = ClientIsole
    with application.app_context():
        limiter.reset()
        mail.boite_envoi.clear()
        yield application
        db.session.remove()
        # Nettoyage : tout sauf les données de référence (rôles, catégories, badges).
        for table in reversed(db.metadata.sorted_tables):
            if table.name not in {"role", "category", "badge"}:
                db.session.execute(delete(table))
        db.session.commit()


class ClientIsole(FlaskClient):
    """Chaque requête a son propre contexte d'application, comme en service.

    Sans cela, les requêtes du test partageraient le `g` du contexte ouvert par la fixture
    `app` (jeton CSRF, nonce de la CSP...), ce qui fausserait les vérifications.
    """

    def open(self, *args: Any, **kwargs: Any) -> Any:  # type: ignore[override]
        with self.application.app_context():
            reponse = super().open(*args, **kwargs)
        # Termine la transaction du test : sous MySQL (REPEATABLE READ), elle garderait sinon
        # une image figée de la base et ne verrait pas ce que la requête vient d'enregistrer.
        db.session.rollback()
        return reponse


@pytest.fixture
def client(app: Flask) -> FlaskClient:
    return app.test_client()


def jeton_csrf(client: FlaskClient, url: str) -> str:
    page = client.get(url).get_data(as_text=True)
    trouve = re.search(r'name="(?:\w+-)?csrf_token" type="hidden" value="([^"]+)"', page)
    if trouve is None:
        trouve = re.search(r'name="csrf_token" value="([^"]+)"', page)
    assert trouve, f"pas de jeton CSRF sur {url}"
    return trouve.group(1)


def lien_du_dernier_mail() -> str:
    assert mail.boite_envoi, "aucun e-mail envoyé"
    trouve = re.search(r"https?://\S+", mail.boite_envoi[-1].texte)
    assert trouve
    return trouve.group(0)


def chemin(lien: str) -> str:
    return "/" + lien.split("/", 3)[3]


@pytest.fixture
def compte_actif(app: Flask) -> User:
    """Un joueur activé, prêt à se connecter."""
    with app.test_request_context():
        accounts.inscrire("alice", "alice@example.org", MOT_DE_PASSE)
    accounts.activer(chemin(lien_du_dernier_mail()).rsplit("/", 1)[1])
    user = accounts.trouver_par_email("alice@example.org")
    assert user is not None
    mail.boite_envoi.clear()
    return user


SECRET_TOTP = "JBSWY3DPEHPK3PXPJBSWY3DPEHPK3PXP"


def code_totp(secret: str = SECRET_TOTP) -> str:
    import pyotp

    return pyotp.TOTP(secret).now()


def connecter(client: FlaskClient, email: str = "alice@example.org", mdp: str = MOT_DE_PASSE):  # type: ignore[no-untyped-def]
    """Connexion complète ; passe la double authentification si le compte l'a activée."""
    jeton = jeton_csrf(client, "/compte/connexion")
    reponse = client.post(
        "/compte/connexion",
        data={"email": email, "password": mdp, "csrf_token": jeton},
    )
    if reponse.headers.get("Location", "").endswith("/compte/verification"):
        # Un code ne sert qu'une fois : on oublie le dernier pas pour les connexions répétées.
        from sqlalchemy import update

        db.session.execute(update(User).where(User.email == email).values(totp_last_step=None))
        db.session.commit()
        jeton = jeton_csrf(client, "/compte/verification")
        reponse = client.post(
            "/compte/verification", data={"code": code_totp(), "csrf_token": jeton}
        )
    return reponse


def creer_compte(app: Flask, pseudo: str, *roles: RoleName) -> User:
    """Compte activé avec les rôles donnés (en plus de joueur)."""
    from sqlalchemy import select

    from app.models import Role, utcnow

    user = User(
        username=pseudo,
        email=f"{pseudo}@example.org",
        password_hash=accounts.passwords.hacher(MOT_DE_PASSE),
        email_verified_at=utcnow(),
    )
    noms = {RoleName.PLAYER.value, *(r.value for r in roles)}
    user.roles.extend(db.session.scalars(select(Role).where(Role.name.in_(noms))))
    db.session.add(user)
    db.session.commit()
    return user


@pytest.fixture
def createur(app: Flask) -> User:
    return creer_compte(app, "createur", RoleName.CREATOR)


def activer_2fa(user: User) -> None:
    from app.models import utcnow
    from app.services import twofa

    user.totp_secret = twofa.chiffrer(SECRET_TOTP)
    user.totp_enabled_at = utcnow()
    db.session.commit()


@pytest.fixture
def admin(app: Flask) -> User:
    """Administrateur, double authentification activée (obligatoire pour l'administration)."""
    user = creer_compte(app, "chef", RoleName.CREATOR, RoleName.ADMIN)
    with app.test_request_context():
        activer_2fa(user)
    return user


@pytest.fixture
def salle(app: Flask, createur: User) -> tuple[FlaskClient, LiveGame, Quiz]:
    """Partie en direct lancée par le créateur (quiz de 3 questions), encore en salle d'attente."""
    from tests.direct import lancer
    from tests.fabrique import creer_quiz

    quiz = creer_quiz(app, createur, n=3)
    animateur = app.test_client()
    connecter(animateur, "createur@example.org")
    return animateur, lancer(animateur, quiz), quiz


def actions(user: User | None = None) -> list[str]:
    """Actions inscrites au journal d'audit, dans l'ordre (pour un compte, ou toutes)."""
    requete = select(AuditLog.action).order_by(AuditLog.id)
    if user is not None:
        requete = requete.where(AuditLog.user_id == user.id)
    return list(db.session.scalars(requete))


def poster(client: FlaskClient, url: str, page: str, **champs: str):  # type: ignore[no-untyped-def]
    return client.post(url, data={"csrf_token": jeton_csrf(client, page), **champs})
