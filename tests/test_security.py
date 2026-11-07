"""En-têtes, CSP, pages d'erreur, contrôle d'accès par rôle, sonde de santé."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from flask import Flask
from flask.testing import FlaskClient

from app.auth import role_required
from app.models import User
from tests.conftest import connecter

GABARITS = Path(__file__).resolve().parent.parent / "app" / "templates"


def test_entetes_de_securite(client: FlaskClient) -> None:
    entetes = client.get("/").headers
    csp = entetes["Content-Security-Policy"]
    assert "unsafe-inline" not in csp
    assert "unsafe-eval" not in csp
    assert "frame-ancestors 'none'" in csp
    assert "object-src 'none'" in csp
    assert entetes["X-Content-Type-Options"] == "nosniff"
    assert entetes["X-Frame-Options"] == "DENY"
    assert entetes["Referrer-Policy"] == "strict-origin-when-cross-origin"
    assert entetes["Cache-Control"] == "no-store"
    assert len(entetes["X-Request-ID"]) >= 8


def test_nonce_change_a_chaque_requete_et_correspond_aux_scripts(client: FlaskClient) -> None:
    nonces = []
    for _ in range(2):
        reponse = client.get("/")
        nonce = re.search(r"'nonce-([^']+)'", reponse.headers["Content-Security-Policy"])
        assert nonce
        assert f'nonce="{nonce.group(1)}"' in reponse.get_data(as_text=True)
        nonces.append(nonce.group(1))
    assert nonces[0] != nonces[1]


def test_aucun_javascript_en_ligne_dans_les_gabarits() -> None:
    """La CSP stricte bloquerait tout gestionnaire on*= ou script sans source."""
    for gabarit in GABARITS.rglob("*.html"):
        contenu = gabarit.read_text(encoding="utf-8")
        assert not re.search(r"\son[a-z]+\s*=", contenu, re.IGNORECASE), gabarit
        assert not re.search(r"<script(?![^>]*\ssrc=)[^>]*>", contenu), gabarit
        assert "style=" not in contenu, gabarit
        assert "|safe" not in contenu, gabarit


def test_identifiant_de_requete_repris_s_il_est_sain(client: FlaskClient) -> None:
    sain = client.get("/", headers={"X-Request-ID": "abcdef12-3456"})
    assert sain.headers["X-Request-ID"] == "abcdef12-3456"
    douteux = client.get("/", headers={"X-Request-ID": "<script>alert(1)</script>"})
    assert "<" not in douteux.headers["X-Request-ID"]


def test_page_404_sans_detail_technique(client: FlaskClient) -> None:
    reponse = client.get("/n-existe-pas")
    assert reponse.status_code == 404
    assert "Page introuvable" in reponse.get_data(as_text=True)


def test_erreur_interne_masquee(app: Flask) -> None:
    @app.get("/test-plantage")
    def plantage() -> str:
        raise RuntimeError("détail secret de la base")

    reponse = app.test_client().get("/test-plantage")
    assert reponse.status_code == 500
    assert "détail secret" not in reponse.get_data(as_text=True)


def test_reponse_json_pour_un_client_api(client: FlaskClient) -> None:
    reponse = client.get("/n-existe-pas", headers={"Accept": "application/json"})
    assert reponse.status_code == 404
    assert reponse.get_json() == {"erreur": "Page introuvable"}


def test_sonde_de_sante(client: FlaskClient) -> None:
    reponse = client.get("/health")
    assert reponse.status_code == 200
    assert reponse.get_json() == {"status": "ok"}


def test_sonde_de_sante_base_injoignable(app: Flask, monkeypatch: pytest.MonkeyPatch) -> None:
    from sqlalchemy.exc import OperationalError

    from app.extensions import db

    def panne(*_args: object, **_kwargs: object) -> None:
        raise OperationalError("SELECT 1", {}, Exception("base arrêtée"))

    with monkeypatch.context() as patch:
        patch.setattr(db.session, "execute", panne)
        reponse = app.test_client().get("/health")
    assert reponse.status_code == 503
    assert reponse.get_json() == {"status": "degrade"}


@pytest.fixture
def route_admin(app: Flask) -> str:
    @app.get("/test-admin")
    @role_required("admin")
    def zone_admin() -> str:
        return "zone admin"

    return "/test-admin"


def test_role_requis_anonyme_redirige(client: FlaskClient, route_admin: str) -> None:
    reponse = client.get(route_admin)
    assert reponse.status_code == 302
    assert "/compte/connexion" in reponse.headers["Location"]


def test_role_requis_joueur_refuse(
    client: FlaskClient, compte_actif: User, route_admin: str
) -> None:
    connecter(client)
    assert client.get(route_admin).status_code == 403


def test_role_requis_admin_accepte(app: Flask, route_admin: str) -> None:
    from tests.conftest import MOT_DE_PASSE

    app.test_cli_runner().invoke(
        args=[
            "creer-admin",
            "--pseudo",
            "chef",
            "--email",
            "chef@example.org",
            "--mot-de-passe",
            MOT_DE_PASSE,
        ],
    )
    client = app.test_client()
    connecter(client, "chef@example.org")
    reponse = client.get(route_admin)
    assert reponse.status_code == 200
    assert reponse.get_data(as_text=True) == "zone admin"


def test_pages_publiques_accessibles(client: FlaskClient) -> None:
    for url in (
        "/",
        "/confidentialite",
        "/compte/connexion",
        "/compte/inscription",
        "/compte/mot-de-passe-oublie",
        "/compte/activation",
    ):
        assert client.get(url).status_code == 200, url


def test_fichiers_statiques_sans_limite_de_debit(client: FlaskClient) -> None:
    """Une page charge plusieurs fichiers : ils ne doivent jamais épuiser une limite."""
    codes = set()
    for _ in range(400):
        reponse = client.get("/static/js/app.js")
        codes.add(reponse.status_code)
        reponse.close()
    assert codes == {200}
