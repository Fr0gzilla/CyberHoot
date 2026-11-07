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
from sqlalchemy import create_engine, delete, text

from app import create_app
from app.config import charger_config
from app.extensions import db, limiter
from app.models import AccountToken, User, user_role
from app.services import accounts, mail

RACINE = Path(__file__).resolve().parent.parent
MOT_DE_PASSE = "Phrase de passe solide 42"


def alembic_config(url: str) -> AlembicConfig:
    config = AlembicConfig(str(RACINE / "alembic.ini"))
    config.set_main_option("script_location", str(RACINE / "migrations"))
    config.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    return config


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
def app(database_url: str, monkeypatch: pytest.MonkeyPatch) -> Iterator[Flask]:
    monkeypatch.setenv("TEST_DATABASE_URL", database_url)
    application = create_app(charger_config("testing"))
    application.test_client_class = ClientIsole
    with application.app_context():
        limiter.reset()
        mail.boite_envoi.clear()
        yield application
        db.session.remove()
        # Nettoyage : tout sauf les données de référence (rôles).
        db.session.execute(delete(user_role))
        db.session.execute(delete(AccountToken))
        db.session.execute(delete(User))
        db.session.commit()


class ClientIsole(FlaskClient):
    """Chaque requête a son propre contexte d'application, comme en service.

    Sans cela, les requêtes du test partageraient le `g` du contexte ouvert par la fixture
    `app` (jeton CSRF, nonce de la CSP...), ce qui fausserait les vérifications.
    """

    def open(self, *args: Any, **kwargs: Any) -> Any:  # type: ignore[override]
        with self.application.app_context():
            return super().open(*args, **kwargs)


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


def connecter(client: FlaskClient, email: str = "alice@example.org", mdp: str = MOT_DE_PASSE):  # type: ignore[no-untyped-def]
    jeton = jeton_csrf(client, "/compte/connexion")
    return client.post(
        "/compte/connexion",
        data={"email": email, "password": mdp, "csrf_token": jeton},
    )
