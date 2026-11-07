"""Inscription, activation, connexion, verrouillage, mot de passe oublié."""

from __future__ import annotations

from datetime import timedelta

from flask import Flask
from flask.testing import FlaskClient
from sqlalchemy import update

from app.extensions import db
from app.models import AccountToken, User, utcnow
from app.services import accounts, mail
from tests.conftest import MOT_DE_PASSE, chemin, connecter, jeton_csrf, lien_du_dernier_mail


def inscrire(client: FlaskClient, **champs: str):  # type: ignore[no-untyped-def]
    donnees = {
        "username": "bob",
        "email": "bob@example.org",
        "password": MOT_DE_PASSE,
        "password_confirm": MOT_DE_PASSE,
        "csrf_token": jeton_csrf(client, "/compte/inscription"),
    }
    donnees.update(champs)
    return client.post("/compte/inscription", data=donnees)


class TestInscription:
    def test_cree_un_compte_inactif_et_envoie_l_activation(self, client: FlaskClient) -> None:
        reponse = inscrire(client)
        assert reponse.status_code == 302
        user = accounts.trouver_par_email("bob@example.org")
        assert user is not None
        assert user.email_verified_at is None
        assert user.role_names == ["player"]
        assert user.password_hash.startswith("$argon2id$")
        assert "/compte/activation/" in lien_du_dernier_mail()

    def test_adresse_deja_prise_meme_reponse_et_aucun_nouveau_compte(
        self, client: FlaskClient, compte_actif: User
    ) -> None:
        premiere = inscrire(client, username="autre", email="nouvelle@example.org")
        seconde = inscrire(client, username="autre2", email="ALICE@example.org")
        assert premiere.status_code == seconde.status_code == 302
        assert premiere.headers["Location"] == seconde.headers["Location"]
        assert accounts.pseudo_pris("autre2") is False
        # Le titulaire est prévenu, sans lien d'activation.
        assert mail.boite_envoi[-1].destinataire == "alice@example.org"
        assert "activation" not in mail.boite_envoi[-1].texte

    def test_pseudo_deja_pris_refuse_sans_tenir_compte_de_la_casse(
        self, client: FlaskClient, compte_actif: User
    ) -> None:
        reponse = inscrire(client, username="ALICE", email="x@example.org")
        assert reponse.status_code == 200
        assert "déjà pris" in reponse.get_data(as_text=True)
        assert accounts.trouver_par_email("x@example.org") is None

    def test_mot_de_passe_trop_court_refuse(self, client: FlaskClient) -> None:
        reponse = inscrire(client, password="court1!", password_confirm="court1!")
        assert reponse.status_code == 200
        assert accounts.trouver_par_email("bob@example.org") is None

    def test_mot_de_passe_courant_refuse(self, client: FlaskClient) -> None:
        reponse = inscrire(client, password="azertyuiop123", password_confirm="azertyuiop123")
        assert "plus utilisés" in reponse.get_data(as_text=True)
        assert accounts.trouver_par_email("bob@example.org") is None

    def test_mot_de_passe_contenant_le_pseudo_refuse(self, client: FlaskClient) -> None:
        mdp = "bobbybob-est-la-2026"
        reponse = inscrire(client, username="bobbybob", password=mdp, password_confirm=mdp)
        assert "pseudo" in reponse.get_data(as_text=True)
        assert accounts.trouver_par_email("bob@example.org") is None

    def test_confirmation_differente_refusee(self, client: FlaskClient) -> None:
        inscrire(client, password_confirm=MOT_DE_PASSE + "x")
        assert accounts.trouver_par_email("bob@example.org") is None

    def test_pseudo_avec_caracteres_interdits_refuse(self, client: FlaskClient) -> None:
        inscrire(client, username="<script>")
        assert accounts.trouver_par_email("bob@example.org") is None

    def test_purge_des_comptes_jamais_actives_apres_30_jours(self, client: FlaskClient) -> None:
        inscrire(client)
        user = accounts.trouver_par_email("bob@example.org")
        assert user is not None
        user.created_at = utcnow() - timedelta(days=31)
        db.session.commit()
        assert accounts.purger_comptes_non_actives() == 1
        assert accounts.trouver_par_email("bob@example.org") is None


class TestActivation:
    def test_lien_active_le_compte_une_seule_fois(self, client: FlaskClient) -> None:
        inscrire(client)
        lien = chemin(lien_du_dernier_mail())
        assert client.get(lien).headers["Location"].endswith("/compte/connexion")
        user = accounts.trouver_par_email("bob@example.org")
        assert user is not None
        assert user.email_verified_at is not None
        assert client.get(lien).headers["Location"].endswith("/compte/activation")

    def test_lien_invalide_refuse(self, client: FlaskClient) -> None:
        reponse = client.get("/compte/activation/jeton-bidon")
        assert reponse.headers["Location"].endswith("/compte/activation")

    def test_connexion_avant_activation_refusee_et_lien_renvoye(self, client: FlaskClient) -> None:
        inscrire(client)
        mail.boite_envoi.clear()
        reponse = connecter(client, "bob@example.org")
        assert reponse.status_code == 200
        assert "pas encore activé" in reponse.get_data(as_text=True)
        assert "/compte/activation/" in lien_du_dernier_mail()

    def test_renvoi_d_activation_neutre(self, client: FlaskClient) -> None:
        jeton = jeton_csrf(client, "/compte/activation")
        reponse = client.post(
            "/compte/activation", data={"email": "inconnu@example.org", "csrf_token": jeton}
        )
        assert reponse.status_code == 302
        assert mail.boite_envoi == []


class TestConnexion:
    def test_connexion_reussie(self, client: FlaskClient, compte_actif: User) -> None:
        reponse = connecter(client)
        assert reponse.status_code == 302
        assert client.get("/profil/").status_code == 200

    def test_meme_message_compte_inconnu_ou_mauvais_mot_de_passe(
        self, client: FlaskClient, compte_actif: User
    ) -> None:
        inconnu = connecter(client, "personne@example.org").get_data(as_text=True)
        mauvais = connecter(client, mdp="mauvais mot de passe").get_data(as_text=True)
        assert "Adresse e-mail ou mot de passe incorrect." in inconnu
        assert "Adresse e-mail ou mot de passe incorrect." in mauvais

    def test_verrouillage_apres_cinq_echecs(self, client: FlaskClient, compte_actif: User) -> None:
        for _ in range(5):
            connecter(client, mdp="mauvais mot de passe")
        db.session.refresh(compte_actif)
        assert compte_actif.is_locked()
        # Même le bon mot de passe est refusé pendant le verrou.
        reponse = connecter(client)
        assert "temporairement bloqué" in reponse.get_data(as_text=True)
        assert client.get("/profil/").status_code == 302

    def test_verrou_levee_apres_expiration(self, client: FlaskClient, compte_actif: User) -> None:
        compte_actif.locked_until = utcnow() - timedelta(seconds=1)
        db.session.commit()
        assert connecter(client).status_code == 302

    def test_compte_desactive_refuse(self, client: FlaskClient, compte_actif: User) -> None:
        compte_actif.is_enabled = False
        db.session.commit()
        assert "désactivé" in connecter(client).get_data(as_text=True)

    def test_redirection_externe_refusee(self, client: FlaskClient, compte_actif: User) -> None:
        for cible in ("https://evil.example", "//evil.example", "/\\evil.example"):
            jeton = jeton_csrf(client, "/compte/connexion")
            reponse = client.post(
                f"/compte/connexion?next={cible}",
                data={"email": "alice@example.org", "password": MOT_DE_PASSE, "csrf_token": jeton},
            )
            assert reponse.headers["Location"] == "/profil/"
            client.post("/compte/deconnexion", data={"csrf_token": jeton_csrf(client, "/")})

    def test_redirection_interne_acceptee(self, client: FlaskClient, compte_actif: User) -> None:
        jeton = jeton_csrf(client, "/compte/connexion")
        reponse = client.post(
            "/compte/connexion?next=/confidentialite",
            data={"email": "alice@example.org", "password": MOT_DE_PASSE, "csrf_token": jeton},
        )
        assert reponse.headers["Location"] == "/confidentialite"

    def test_deconnexion_exige_post_et_csrf(self, client: FlaskClient, compte_actif: User) -> None:
        connecter(client)
        assert client.get("/compte/deconnexion").status_code == 405
        assert client.post("/compte/deconnexion").status_code == 400
        assert client.get("/profil/").status_code == 200
        client.post("/compte/deconnexion", data={"csrf_token": jeton_csrf(client, "/")})
        assert client.get("/profil/").status_code == 302

    def test_limitation_de_debit_sur_la_connexion(self, client: FlaskClient) -> None:
        jeton = jeton_csrf(client, "/compte/connexion")
        codes = [
            client.post(
                "/compte/connexion",
                data={"email": "x@example.org", "password": "y" * 12, "csrf_token": jeton},
            ).status_code
            for _ in range(31)
        ]
        assert codes[-1] == 429


class TestMotDePasseOublie:
    def demander(self, client: FlaskClient, email: str = "alice@example.org"):  # type: ignore[no-untyped-def]
        jeton = jeton_csrf(client, "/compte/mot-de-passe-oublie")
        return client.post(
            "/compte/mot-de-passe-oublie", data={"email": email, "csrf_token": jeton}
        )

    def reinitialiser(self, client: FlaskClient, lien: str, mdp: str):  # type: ignore[no-untyped-def]
        jeton = jeton_csrf(client, lien)
        return client.post(
            lien, data={"password": mdp, "password_confirm": mdp, "csrf_token": jeton}
        )

    def test_reponse_identique_compte_ou_non(self, client: FlaskClient, compte_actif: User) -> None:
        connu = self.demander(client)
        inconnu = self.demander(client, "inconnu@example.org")
        assert connu.status_code == inconnu.status_code == 302
        assert len(mail.boite_envoi) == 1

    def test_lien_a_usage_unique(self, client: FlaskClient, compte_actif: User) -> None:
        self.demander(client)
        lien = chemin(lien_du_dernier_mail())
        nouveau = "Une toute nouvelle phrase 2026"
        assert (
            self.reinitialiser(client, lien, nouveau)
            .headers["Location"]
            .endswith("/compte/connexion")
        )
        assert connecter(client, mdp=nouveau).status_code == 302
        # Deuxième usage du même lien : refusé.
        assert client.get(lien).headers["Location"].endswith("/compte/mot-de-passe-oublie")

    def test_nouveau_lien_annule_le_precedent(
        self, client: FlaskClient, compte_actif: User
    ) -> None:
        self.demander(client)
        ancien = chemin(lien_du_dernier_mail())
        self.demander(client)
        assert client.get(ancien).headers["Location"].endswith("/compte/mot-de-passe-oublie")

    def test_lien_expire(self, client: FlaskClient, compte_actif: User) -> None:
        self.demander(client)
        lien = chemin(lien_du_dernier_mail())
        db.session.execute(update(AccountToken).values(expires_at=utcnow() - timedelta(seconds=1)))
        db.session.commit()
        assert client.get(lien).headers["Location"].endswith("/compte/mot-de-passe-oublie")

    def test_lien_d_activation_ne_sert_pas_a_reinitialiser(self, client: FlaskClient) -> None:
        inscrire(client)
        jeton = chemin(lien_du_dernier_mail()).rsplit("/", 1)[1]
        reponse = client.get(f"/compte/reinitialisation/{jeton}")
        assert reponse.headers["Location"].endswith("/compte/mot-de-passe-oublie")

    def test_reinitialisation_deverrouille_le_compte(
        self, client: FlaskClient, compte_actif: User
    ) -> None:
        compte_actif.locked_until = utcnow() + timedelta(minutes=10)
        db.session.commit()
        self.demander(client)
        nouveau = "Une toute nouvelle phrase 2026"
        self.reinitialiser(client, chemin(lien_du_dernier_mail()), nouveau)
        assert connecter(client, mdp=nouveau).status_code == 302

    def test_lien_construit_depuis_l_url_publique(self, app: Flask, compte_actif: User) -> None:
        # Un en-tête Host forgé ne doit pas changer le domaine du lien envoyé.
        with app.test_request_context(base_url="http://evil.example"):
            accounts.demander_reinitialisation("alice@example.org")
        assert lien_du_dernier_mail().startswith(app.config["PUBLIC_URL"] + "/")
