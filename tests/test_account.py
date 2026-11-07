"""Espace personnel : pseudo, mot de passe, suppression, sessions."""

from __future__ import annotations

from flask import Flask
from flask.testing import FlaskClient

from app.extensions import db
from app.models import AccountToken, User
from app.services import accounts, mail
from tests.conftest import MOT_DE_PASSE, connecter, jeton_csrf

NOUVEAU = "Une autre phrase de passe 77"


def poster(client: FlaskClient, url: str, prefixe: str, **champs: str):  # type: ignore[no-untyped-def]
    donnees = {f"{prefixe}-{cle}": valeur for cle, valeur in champs.items()}
    donnees[f"{prefixe}-csrf_token"] = jeton_csrf(client, "/profil/")
    return client.post(url, data=donnees)


def test_profil_exige_une_connexion(client: FlaskClient) -> None:
    reponse = client.get("/profil/")
    assert reponse.status_code == 302
    assert "/compte/connexion" in reponse.headers["Location"]


def test_changer_de_pseudo(client: FlaskClient, compte_actif: User) -> None:
    connecter(client)
    reponse = poster(client, "/profil/pseudo", "pseudo", username="alice2")
    assert reponse.status_code == 302
    db.session.refresh(compte_actif)
    assert compte_actif.username == "alice2"


def test_changer_de_pseudo_sans_csrf_refuse(client: FlaskClient, compte_actif: User) -> None:
    connecter(client)
    reponse = client.post("/profil/pseudo", data={"pseudo-username": "pirate"})
    assert reponse.status_code == 400
    db.session.refresh(compte_actif)
    assert compte_actif.username == "alice"


def test_changer_de_mot_de_passe_deconnecte_les_autres_sessions(
    app: Flask, compte_actif: User
) -> None:
    appareil_1 = app.test_client()
    appareil_2 = app.test_client()
    connecter(appareil_1)
    connecter(appareil_2)
    reponse = poster(
        appareil_1,
        "/profil/mot-de-passe",
        "mdp",
        current_password=MOT_DE_PASSE,
        password=NOUVEAU,
        password_confirm=NOUVEAU,
    )
    assert reponse.status_code == 302
    assert appareil_1.get("/profil/").status_code == 200
    assert appareil_2.get("/profil/").status_code == 302
    assert mail.boite_envoi[-1].sujet == "Votre mot de passe a été modifié"


def test_changer_de_mot_de_passe_annule_les_liens_en_cours(
    app: Flask, client: FlaskClient, compte_actif: User
) -> None:
    with app.test_request_context():
        accounts.demander_reinitialisation("alice@example.org")
    connecter(client)
    poster(
        client,
        "/profil/mot-de-passe",
        "mdp",
        current_password=MOT_DE_PASSE,
        password=NOUVEAU,
        password_confirm=NOUVEAU,
    )
    assert all(jeton.used_at is not None for jeton in db.session.query(AccountToken))


def test_mauvais_mot_de_passe_actuel_refuse(client: FlaskClient, compte_actif: User) -> None:
    connecter(client)
    reponse = poster(
        client,
        "/profil/mot-de-passe",
        "mdp",
        current_password="pas le bon du tout",
        password=NOUVEAU,
        password_confirm=NOUVEAU,
    )
    assert reponse.status_code == 422
    assert "Mot de passe actuel incorrect." in reponse.get_data(as_text=True)


def test_supprimer_son_compte(client: FlaskClient, compte_actif: User) -> None:
    connecter(client)
    reponse = poster(client, "/profil/suppression", "suppr", password=MOT_DE_PASSE, confirm="y")
    assert reponse.status_code == 302
    assert accounts.trouver_par_email("alice@example.org") is None
    assert client.get("/profil/").status_code == 302


def test_suppression_exige_le_mot_de_passe(client: FlaskClient, compte_actif: User) -> None:
    connecter(client)
    reponse = poster(client, "/profil/suppression", "suppr", password="mauvais", confirm="y")
    assert reponse.status_code == 422
    assert accounts.trouver_par_email("alice@example.org") is not None


def test_compte_desactive_perd_sa_session(client: FlaskClient, compte_actif: User) -> None:
    connecter(client)
    compte_actif.is_enabled = False
    db.session.commit()
    assert client.get("/profil/").status_code == 302


def test_creer_admin_en_ligne_de_commande(app: Flask) -> None:
    resultat = app.test_cli_runner().invoke(
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
    assert resultat.exit_code == 0, resultat.output
    user = accounts.trouver_par_email("chef@example.org")
    assert user is not None
    assert user.role_names == ["admin", "creator", "player"]
    assert user.is_active


def test_creer_admin_refuse_un_mot_de_passe_faible(app: Flask) -> None:
    resultat = app.test_cli_runner().invoke(
        args=[
            "creer-admin",
            "--pseudo",
            "chef",
            "--email",
            "chef@example.org",
            "--mot-de-passe",
            "azertyuiop123",
        ],
    )
    assert resultat.exit_code != 0
    assert accounts.trouver_par_email("chef@example.org") is None


def test_commande_de_purge(app: Flask) -> None:
    resultat = app.test_cli_runner().invoke(args=["purger-comptes"])
    assert resultat.exit_code == 0
    assert "Comptes supprimés : 0" in resultat.output
