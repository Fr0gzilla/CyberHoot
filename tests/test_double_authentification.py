"""v2.2 : double authentification (activation, connexion en deux étapes, codes de secours)."""

from __future__ import annotations

import re

import pyotp
from flask import Flask
from flask.testing import FlaskClient
from sqlalchemy import update

from app.extensions import db
from app.models import (
    RoleName,
    User,
)
from app.services import twofa
from tests.conftest import (
    MOT_DE_PASSE,
    SECRET_TOTP,
    actions,
    activer_2fa,
    code_totp,
    connecter,
    creer_compte,
    jeton_csrf,
    poster,
)


class TestDoubleAuthentification:
    def test_activation(self, app: Flask, client: FlaskClient) -> None:
        joueur = creer_compte(app, "prudent")
        connecter(client, "prudent@example.org")
        page = client.get("/profil/double-authentification").get_data(as_text=True)
        secret = re.search(r"break-all[^>]*>([A-Z2-7]{32})<", page).group(1)  # type: ignore[union-attr]
        assert "<svg" in page
        refus = poster(
            client,
            "/profil/double-authentification/activer",
            "/profil/double-authentification",
            code="000000",
        )
        assert refus.status_code == 302
        codes = poster(
            client,
            "/profil/double-authentification/activer",
            "/profil/double-authentification",
            code=pyotp.TOTP(secret).now(),
        )
        html = codes.get_data(as_text=True)
        assert len(re.findall(r"[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}", html)) == 10
        db.session.refresh(joueur)
        assert joueur.totp_enabled
        assert joueur.totp_secret is not None
        assert secret not in joueur.totp_secret  # stocké chiffré
        assert twofa.dechiffrer(joueur.totp_secret) == secret
        assert "2fa_activee" in actions(joueur)

    def test_connexion_en_deux_etapes(self, app: Flask, client: FlaskClient) -> None:
        user = creer_compte(app, "protege")
        activer_2fa(user)
        jeton = jeton_csrf(client, "/compte/connexion")
        reponse = client.post(
            "/compte/connexion",
            data={
                "email": "protege@example.org",
                "password": MOT_DE_PASSE,
                "csrf_token": jeton,
            },
        )
        assert reponse.headers["Location"].endswith("/compte/verification")
        assert client.get("/profil/").status_code == 302  # pas encore connecté
        mauvais = poster(client, "/compte/verification", "/compte/verification", code="123456")
        assert "Code incorrect" in mauvais.get_data(as_text=True)
        bon = poster(client, "/compte/verification", "/compte/verification", code=code_totp())
        assert bon.status_code == 302
        assert client.get("/profil/").status_code == 200
        assert actions(user)[-2:] == ["connexion_2fa_echec", "connexion"]

    def test_un_code_ne_sert_qu_une_fois(self, app: Flask) -> None:
        user = creer_compte(app, "rejeu")
        activer_2fa(user)
        code = code_totp()
        assert twofa.verifier(user, code) == "totp"
        assert twofa.verifier(user, code) is None

    def test_code_de_secours_a_usage_unique(self, app: Flask, client: FlaskClient) -> None:
        user = creer_compte(app, "secours")
        activer_2fa(user)
        codes = twofa.regenerer_codes(user)
        assert twofa.verifier(user, codes[0].upper()) == "secours"
        assert twofa.verifier(user, codes[0]) is None
        assert twofa.codes_restants(user) == 9

    def test_verification_expiree(self, app: Flask, client: FlaskClient) -> None:
        user = creer_compte(app, "lent")
        activer_2fa(user)
        jeton = jeton_csrf(client, "/compte/connexion")
        client.post(
            "/compte/connexion",
            data={
                "email": "lent@example.org",
                "password": MOT_DE_PASSE,
                "csrf_token": jeton,
            },
        )
        with client.session_transaction() as session:
            attente = dict(session["connexion_2fa"])
            attente["t"] -= 301
            session["connexion_2fa"] = attente
        assert client.get("/compte/verification").headers["Location"].endswith("/compte/connexion")

    def test_cinq_codes_faux_verrouillent(self, app: Flask, client: FlaskClient) -> None:
        user = creer_compte(app, "cible")
        activer_2fa(user)
        jeton = jeton_csrf(client, "/compte/connexion")
        client.post(
            "/compte/connexion",
            data={
                "email": "cible@example.org",
                "password": MOT_DE_PASSE,
                "csrf_token": jeton,
            },
        )
        for _ in range(5):
            poster(client, "/compte/verification", "/compte/verification", code="000000")
        db.session.refresh(user)
        assert user.is_locked()

    def test_administration_exige_la_double_authentification(
        self, app: Flask, client: FlaskClient
    ) -> None:
        creer_compte(app, "chefsans2fa", RoleName.ADMIN)
        connecter(client, "chefsans2fa@example.org")
        assert client.get("/admin/").headers["Location"].endswith("/profil/double-authentification")

    def test_un_admin_ne_peut_pas_la_desactiver(self, client: FlaskClient, admin: User) -> None:
        connecter(client, "chef@example.org")
        db.session.execute(update(User).values(totp_last_step=None))
        db.session.commit()
        poster(
            client,
            "/profil/double-authentification/desactiver",
            "/profil/double-authentification",
            code=code_totp(),
        )
        db.session.refresh(admin)
        assert admin.totp_enabled

    def test_un_joueur_peut_la_desactiver(self, app: Flask, client: FlaskClient) -> None:
        user = creer_compte(app, "change")
        activer_2fa(user)
        connecter(client, "change@example.org")
        db.session.execute(update(User).values(totp_last_step=None))
        db.session.commit()
        poster(
            client,
            "/profil/double-authentification/desactiver",
            "/profil/double-authentification",
            code=pyotp.TOTP(SECRET_TOTP).now(),
        )
        db.session.refresh(user)
        assert not user.totp_enabled
