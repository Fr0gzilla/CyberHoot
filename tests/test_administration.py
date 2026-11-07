"""v2.2 : double authentification, journal d'audit, comptes, signalements, export RGPD."""

from __future__ import annotations

import json
import re
from datetime import timedelta

import pyotp
from flask import Flask
from flask.testing import FlaskClient
from sqlalchemy import func, select, update

from app.extensions import db
from app.models import (
    AuditLog,
    Badge,
    Category,
    Quiz,
    QuizStatus,
    Report,
    Review,
    RoleName,
    User,
    utcnow,
)
from app.services import audit, twofa
from tests.conftest import (
    MOT_DE_PASSE,
    SECRET_TOTP,
    activer_2fa,
    code_totp,
    connecter,
    creer_compte,
    jeton_csrf,
)
from tests.fabrique import creer_quiz


def actions(user: User | None = None) -> list[str]:
    requete = select(AuditLog.action).order_by(AuditLog.id)
    if user is not None:
        requete = requete.where(AuditLog.user_id == user.id)
    return list(db.session.scalars(requete))


def poster(client: FlaskClient, url: str, page: str, **champs: str):  # type: ignore[no-untyped-def]
    return client.post(url, data={"csrf_token": jeton_csrf(client, page), **champs})


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


class TestJournal:
    def test_connexions_journalisees_avec_l_adresse(
        self, client: FlaskClient, compte_actif: User
    ) -> None:
        connecter(client, mdp="mauvais mot de passe")
        connecter(client)
        lignes = db.session.scalars(select(AuditLog).order_by(AuditLog.id)).all()
        assert [ligne.action for ligne in lignes] == ["connexion_echec", "connexion"]
        assert lignes[0].target == "alice@example.org"
        assert lignes[1].ip == "127.0.0.1"
        assert lignes[1].username == "alice"

    def test_page_du_journal_et_filtres(
        self, client: FlaskClient, admin: User, compte_actif: User
    ) -> None:
        connecter(client, "alice@example.org", "faux mot de passe")
        connecter(client, "chef@example.org")
        html = client.get("/admin/journal?action=connexion_echec").get_data(as_text=True)
        assert "alice@example.org" in html
        assert "Connexion réussie" not in html.split("<tbody>")[1]

    def test_purge_apres_douze_mois(self, app: Flask) -> None:
        audit.journaliser("connexion")
        db.session.execute(update(AuditLog).values(created_at=utcnow() - timedelta(days=400)))
        audit.journaliser("connexion")
        assert audit.purger() == 1
        assert db.session.scalar(select(func.count(AuditLog.id))) == 1


class TestComptes:
    def test_donner_le_role_createur(self, app: Flask, client: FlaskClient, admin: User) -> None:
        futur = creer_compte(app, "futur")
        connecter(client, "chef@example.org")
        assert "futur@example.org" in client.get("/admin/comptes?q=futur").get_data(as_text=True)
        poster(
            client,
            f"/admin/comptes/{futur.id}/role",
            "/admin/comptes",
            role="creator",
            operation="ajouter",
        )
        db.session.refresh(futur)
        assert futur.has_role("creator")
        assert "admin_role" in actions(admin)

    def test_pas_de_modification_de_ses_propres_droits(
        self, client: FlaskClient, admin: User
    ) -> None:
        connecter(client, "chef@example.org")
        poster(
            client,
            f"/admin/comptes/{admin.id}/role",
            "/admin/comptes",
            role="admin",
            operation="retirer",
        )
        poster(client, f"/admin/comptes/{admin.id}/activation", "/admin/comptes", actif="0")
        db.session.refresh(admin)
        assert admin.has_role("admin")
        assert admin.is_enabled

    def test_il_reste_toujours_un_administrateur(
        self, app: Flask, client: FlaskClient, admin: User
    ) -> None:
        from app.services import admin as service_admin

        autre = creer_compte(app, "autreadmin", RoleName.ADMIN)
        assert service_admin.changer_role(autre, admin, "admin", ajouter=False) is None
        assert (
            service_admin.changer_role(admin, autre, "admin", ajouter=False)
            is service_admin.Refus.DERNIER_ADMIN
        )

    def test_desactiver_un_compte_coupe_sa_session(
        self, app: Flask, admin: User, compte_actif: User
    ) -> None:
        joueur, chef = app.test_client(), app.test_client()
        connecter(joueur)
        connecter(chef, "chef@example.org")
        poster(chef, f"/admin/comptes/{compte_actif.id}/activation", "/admin/comptes", actif="0")
        assert joueur.get("/profil/").status_code == 302
        assert "désactivé" in connecter(joueur).get_data(as_text=True)

    def test_un_joueur_n_entre_pas_dans_l_administration(
        self, client: FlaskClient, compte_actif: User
    ) -> None:
        connecter(client)
        for url in ("/admin/", "/admin/comptes", "/admin/journal", "/admin/badges"):
            assert client.get(url).status_code == 403, url


class TestReferentiels:
    def test_modifier_une_categorie(self, client: FlaskClient, admin: User) -> None:
        categorie = db.session.get(Category, 1)
        assert categorie is not None
        origine = (categorie.name, categorie.description)
        try:
            self._modifier_categorie(client)
        finally:  # données de référence : on les remet en état pour les autres tests
            categorie.name, categorie.description = origine
            db.session.commit()

    def _modifier_categorie(self, client: FlaskClient) -> None:
        connecter(client, "chef@example.org")
        poster(
            client,
            "/admin/categories",
            "/admin/categories",
            id="1",
            name="Hameçonnage",
            description="Faux messages et arnaques.",
        )
        assert db.session.get(Category, 1).name == "Hameçonnage"  # type: ignore[union-attr]
        poster(client, "/admin/categories", "/admin/categories", id="1", name="x", description="")
        assert db.session.get(Category, 1).name == "Hameçonnage"  # type: ignore[union-attr]

    def test_modifier_un_badge(self, client: FlaskClient, admin: User) -> None:
        badge = db.session.get(Badge, 2)
        assert badge is not None
        origine = (badge.name, badge.description, badge.icon, badge.threshold)
        try:
            self._modifier_badge(client)
        finally:
            badge.name, badge.description, badge.icon, badge.threshold = origine
            db.session.commit()

    def _modifier_badge(self, client: FlaskClient) -> None:
        connecter(client, "chef@example.org")
        poster(
            client,
            "/admin/badges",
            "/admin/badges",
            id="2",
            name="Fidèle",
            description="Terminer 20 parties.",
            icon="🎯",
            threshold="20",
        )
        badge = db.session.get(Badge, 2)
        assert badge is not None
        assert (badge.name, badge.threshold) == ("Fidèle", 20)
        poster(
            client,
            "/admin/badges",
            "/admin/badges",
            id="2",
            name="Fidèle",
            description="Terminer 20 parties.",
            icon="🎯",
            threshold="0",
        )
        db.session.refresh(badge)
        assert badge.threshold == 20


class TestSignalements:
    def test_signaler_puis_depublier(
        self, app: Flask, client: FlaskClient, createur: User, admin: User, compte_actif: User
    ) -> None:
        quiz = creer_quiz(app, createur, titre="Douteux")
        joueur, chef = app.test_client(), app.test_client()
        connecter(joueur)
        poster(
            joueur,
            f"/quiz/{quiz.id}/signaler",
            f"/quiz/{quiz.id}",
            reason="La réponse 2 est fausse.",
        )
        poster(joueur, f"/quiz/{quiz.id}/signaler", f"/quiz/{quiz.id}", reason="Encore moi.")
        assert db.session.scalar(select(func.count(Report.id))) == 1
        connecter(chef, "chef@example.org")
        assert "La réponse 2 est fausse." in chef.get("/admin/signalements").get_data(as_text=True)
        signalement = db.session.scalar(select(Report))
        assert signalement is not None
        poster(
            chef, f"/admin/signalements/{signalement.id}", "/admin/signalements", action="depublier"
        )
        db.session.expire_all()
        assert db.session.get(Quiz, quiz.id).status is QuizStatus.REJECTED  # type: ignore[union-attr]
        assert "Aucun signalement" in chef.get("/admin/signalements").get_data(as_text=True)

    def test_signaler_un_avis_puis_le_supprimer(
        self, app: Flask, createur: User, admin: User, compte_actif: User
    ) -> None:
        quiz = creer_quiz(app, createur)
        avis = Review(user_id=createur.id, quiz_id=quiz.id, rating=1, comment="insulte")
        db.session.add(avis)
        db.session.commit()
        joueur, chef = app.test_client(), app.test_client()
        connecter(joueur)
        poster(joueur, f"/avis/{avis.id}/signaler", f"/quiz/{quiz.id}", reason="Propos injurieux")
        connecter(chef, "chef@example.org")
        signalement = db.session.scalar(select(Report))
        assert signalement is not None
        identifiant = avis.id
        poster(
            chef,
            f"/admin/signalements/{signalement.id}",
            "/admin/signalements",
            action="supprimer-avis",
        )
        db.session.expire_all()
        assert db.session.get(Review, identifiant) is None
        assert "admin_avis_supprime" in actions(admin)

    def test_motif_obligatoire(
        self, app: Flask, client: FlaskClient, createur: User, compte_actif: User
    ) -> None:
        quiz = creer_quiz(app, createur)
        connecter(client)
        poster(client, f"/quiz/{quiz.id}/signaler", f"/quiz/{quiz.id}", reason="")
        assert db.session.scalar(select(func.count(Report.id))) == 0


class TestTableauDeBordEtDonnees:
    def test_tableau_de_bord(
        self, app: Flask, client: FlaskClient, admin: User, createur: User
    ) -> None:
        creer_quiz(app, createur)
        connecter(client, "chef@example.org")
        html = client.get("/admin/").get_data(as_text=True)
        assert "Joueurs actifs (30 j)" in html
        assert "Parties terminées par jour" in html

    def test_export_de_mes_donnees(
        self, app: Flask, client: FlaskClient, createur: User, compte_actif: User
    ) -> None:
        connecter(client)
        reponse = client.get("/profil/mes-donnees.json")
        assert reponse.mimetype == "application/json"
        assert "attachment" in reponse.headers["Content-Disposition"]
        donnees = json.loads(reponse.get_data(as_text=True))
        assert donnees["compte"]["email"] == "alice@example.org"
        assert donnees["compte"]["pseudo"] == "alice"
        assert any(
            ligne["action"] == "Connexion réussie" for ligne in donnees["journal_de_securite"]
        )
        assert "donnees_exportees" in actions(compte_actif)

    def test_suppression_de_compte_journalisee(
        self, client: FlaskClient, compte_actif: User
    ) -> None:
        connecter(client)
        champs = {
            "suppr-password": MOT_DE_PASSE,
            "suppr-confirm": "y",
            "suppr-csrf_token": jeton_csrf(client, "/profil/"),
        }
        client.post("/profil/suppression", data=champs)
        ligne = db.session.scalar(select(AuditLog).where(AuditLog.action == "compte_supprime"))
        assert ligne is not None
        assert ligne.username == "alice"
        assert ligne.user_id is None  # compte supprimé : la ligne reste, anonymisée
