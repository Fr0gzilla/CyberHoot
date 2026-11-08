"""Espace créateur (éditeur, soumission, statistiques) et validation par un administrateur."""

from __future__ import annotations

from flask import Flask
from flask.testing import FlaskClient
from sqlalchemy import select

from app.extensions import db
from app.models import Quiz, QuizStatus, RoleName, User
from app.services import catalog, mail, moderation, quizzes
from tests.conftest import connecter, creer_compte, jeton_csrf
from tests.fabrique import brouillon, creer_quiz, formulaire


def editer(client: FlaskClient, url: str, champs: dict[str, str]):  # type: ignore[no-untyped-def]
    champs = {**champs, "csrf_token": jeton_csrf(client, url)}
    return client.post(url, data=champs, content_type="multipart/form-data")


def recharger(quiz_id: int) -> Quiz:
    db.session.expire_all()
    quiz = db.session.get(Quiz, quiz_id)
    assert quiz is not None
    return quiz


class TestAcces:
    def test_un_joueur_n_a_pas_acces_a_l_espace_createur(
        self, app: Flask, client: FlaskClient
    ) -> None:
        creer_compte(app, "joueur")
        connecter(client, "joueur@example.org")
        assert client.get("/createur/").status_code == 403
        assert client.get("/createur/quiz/nouveau").status_code == 403

    def test_un_createur_ne_touche_pas_au_quiz_d_un_autre(
        self, app: Flask, client: FlaskClient, createur: User
    ) -> None:
        autre = creer_compte(app, "autre", RoleName.CREATOR)
        quiz = creer_quiz(app, autre, QuizStatus.DRAFT)
        connecter(client, "createur@example.org")
        assert client.get(f"/createur/quiz/{quiz.id}/modifier").status_code == 404
        assert client.get(f"/createur/quiz/{quiz.id}/statistiques").status_code == 404
        jeton = jeton_csrf(client, "/createur/")
        assert (
            client.post(
                f"/createur/quiz/{quiz.id}/supprimer", data={"csrf_token": jeton}
            ).status_code
            == 404
        )
        assert recharger(quiz.id).status is QuizStatus.DRAFT

    def test_un_joueur_n_a_pas_acces_a_l_administration(
        self, app: Flask, client: FlaskClient, createur: User
    ) -> None:
        connecter(client, "createur@example.org")
        assert client.get("/admin/").status_code == 403


class TestEditeur:
    def test_creer_un_brouillon(self, client: FlaskClient, createur: User) -> None:
        connecter(client, "createur@example.org")
        reponse = editer(client, "/createur/quiz/nouveau", formulaire(brouillon(2, "Mon quiz")))
        assert reponse.status_code == 302
        quiz = db.session.scalar(select(Quiz).where(Quiz.title == "Mon quiz"))
        assert quiz is not None
        assert quiz.status is QuizStatus.DRAFT
        assert quiz.creator_id == createur.id
        assert [len(q.options) for q in quiz.questions] == [3, 3]
        assert quiz.questions[0].correct_ids == {
            quiz.questions[0].options[0].id,
            quiz.questions[0].options[1].id,
        }

    def test_les_boutons_modifient_le_formulaire_sans_rien_enregistrer(
        self, client: FlaskClient, createur: User
    ) -> None:
        connecter(client, "createur@example.org")
        b = brouillon(1, "Pas encore enregistré")
        html = editer(client, "/createur/quiz/nouveau", formulaire(b, "ajouter-question")).get_data(
            as_text=True
        )
        assert 'name="q-1-text"' in html
        html = editer(
            client, "/createur/quiz/nouveau", formulaire(b, "ajouter-reponse:0")
        ).get_data(as_text=True)
        assert 'name="q-0-o-3-text"' in html
        html = editer(
            client, "/createur/quiz/nouveau", formulaire(b, "retirer-reponse:0:2")
        ).get_data(as_text=True)
        assert 'name="q-0-o-2-text"' not in html
        assert db.session.scalar(select(Quiz).where(Quiz.title == "Pas encore enregistré")) is None

    def test_deplacer_et_retirer_des_questions(self) -> None:
        b = brouillon(3)
        quizzes.appliquer_action(b, "descendre-question:0")
        assert b.questions[1].text == "Question numéro 1 ?"
        quizzes.appliquer_action(b, "monter-question:1")
        assert b.questions[0].text == "Question numéro 1 ?"
        quizzes.appliquer_action(b, "retirer-question:2")
        assert len(b.questions) == 2
        quizzes.appliquer_action(b, "retirer-question:99")
        quizzes.appliquer_action(b, "action-inconnue:0")
        assert len(b.questions) == 2

    def test_erreurs_de_validation_affichees(self, client: FlaskClient, createur: User) -> None:
        connecter(client, "createur@example.org")
        b = brouillon(1)
        b.title = "x"
        b.questions[0].options = [
            quizzes.BrouillonOption("Seule", False),
            quizzes.BrouillonOption("Seule", False),
        ]
        b.questions[0].explanation = ""
        reponse = editer(client, "/createur/quiz/nouveau", formulaire(b))
        html = reponse.get_data(as_text=True)
        assert reponse.status_code == 422
        assert "Le titre doit faire entre 3 et 120 caractères." in html
        assert "Cochez au moins une bonne réponse." in html
        assert "Deux réponses sont identiques." in html
        assert "L&#39;explication doit faire" in html
        assert db.session.scalar(select(Quiz)) is None

    def test_categorie_inexistante_refusee(self, app: Flask) -> None:
        b = brouillon(1)
        b.category_id = 999
        assert "category" in quizzes.valider(b, set())

    def test_soumission_exige_trois_questions(self, client: FlaskClient, createur: User) -> None:
        connecter(client, "createur@example.org")
        html = editer(
            client, "/createur/quiz/nouveau", formulaire(brouillon(2), "soumettre")
        ).get_data(as_text=True)
        assert "au moins 3 questions" in html
        editer(client, "/createur/quiz/nouveau", formulaire(brouillon(3, "Complet"), "soumettre"))
        quiz = db.session.scalar(select(Quiz).where(Quiz.title == "Complet"))
        assert quiz is not None
        assert quiz.status is QuizStatus.PENDING

    def test_modifier_un_quiz_publie_le_renvoie_en_validation(
        self, app: Flask, client: FlaskClient, createur: User
    ) -> None:
        quiz = creer_quiz(app, createur)
        connecter(client, "createur@example.org")
        b = brouillon(3, "Titre corrigé")
        editer(client, f"/createur/quiz/{quiz.id}/modifier", formulaire(b))
        quiz = recharger(quiz.id)
        assert quiz.title == "Titre corrigé"
        assert quiz.status is QuizStatus.PENDING
        assert "Titre corrigé" not in client.get("/quiz").get_data(as_text=True)

    def test_modifier_un_quiz_refuse_le_remet_en_brouillon(
        self, app: Flask, client: FlaskClient, createur: User
    ) -> None:
        quiz = creer_quiz(app, createur, QuizStatus.REJECTED)
        connecter(client, "createur@example.org")
        assert "À revoir" in client.get(f"/createur/quiz/{quiz.id}/modifier").get_data(as_text=True)
        editer(client, f"/createur/quiz/{quiz.id}/modifier", formulaire(brouillon(3)))
        assert recharger(quiz.id).status is QuizStatus.DRAFT

    def test_soumettre_depuis_le_tableau_de_bord(
        self, app: Flask, client: FlaskClient, createur: User
    ) -> None:
        petit = creer_quiz(app, createur, QuizStatus.DRAFT, n=1, titre="Petit")
        complet = creer_quiz(app, createur, QuizStatus.DRAFT, n=3, titre="Complet")
        connecter(client, "createur@example.org")
        jeton = jeton_csrf(client, "/createur/")
        client.post(f"/createur/quiz/{petit.id}/soumettre", data={"csrf_token": jeton})
        client.post(f"/createur/quiz/{complet.id}/soumettre", data={"csrf_token": jeton})
        assert recharger(petit.id).status is QuizStatus.DRAFT
        assert recharger(complet.id).status is QuizStatus.PENDING

    def test_supprimer_son_quiz(self, app: Flask, client: FlaskClient, createur: User) -> None:
        quiz = creer_quiz(app, createur)
        connecter(client, "createur@example.org")
        jeton = jeton_csrf(client, "/createur/")
        identifiant = quiz.id
        client.post(f"/createur/quiz/{identifiant}/supprimer", data={"csrf_token": jeton})
        db.session.expire_all()
        assert db.session.get(Quiz, identifiant) is None

    def test_statistiques(self, app: Flask, client: FlaskClient, createur: User) -> None:
        from tests.test_play import demarrer, page_question, repondre

        quiz = creer_quiz(app, createur, n=3)
        connecter(client, "createur@example.org")
        token = demarrer(client, quiz)
        for texte in (["Réponse A0", "Réponse B0"], ["Réponse C1"], ["Réponse A2"]):
            q, opts, _ = page_question(client, token)
            repondre(client, token, q, [opts[t] for t in texte])
        stats = catalog.statistiques(recharger(quiz.id))
        assert stats.parties == 1
        assert stats.score_moyen == 67
        assert [ligne.reussite for ligne in stats.questions] == [100, 0, 100]
        assert stats.plus_ratee is not None
        assert stats.plus_ratee.question.position == 1
        html = client.get(f"/createur/quiz/{quiz.id}/statistiques").get_data(as_text=True)
        assert "67 %" in html


class TestValidation:
    def test_publier_un_quiz_en_attente(
        self, app: Flask, client: FlaskClient, createur: User, admin: User
    ) -> None:
        quiz = creer_quiz(app, createur, QuizStatus.PENDING, titre="À relire")
        connecter(client, "chef@example.org")
        assert "À relire" in client.get("/admin/").get_data(as_text=True)
        assert "Réponse A0" in client.get(f"/admin/quiz/{quiz.id}").get_data(as_text=True)
        jeton = jeton_csrf(client, f"/admin/quiz/{quiz.id}")
        client.post(f"/admin/quiz/{quiz.id}/publier", data={"csrf_token": jeton})
        assert recharger(quiz.id).status is QuizStatus.PUBLISHED
        assert mail.boite_envoi[-1].destinataire == "createur@example.org"
        assert "publié" in mail.boite_envoi[-1].sujet

    def test_refuser_exige_un_motif_envoye_au_createur(
        self, app: Flask, client: FlaskClient, createur: User, admin: User
    ) -> None:
        quiz = creer_quiz(app, createur, QuizStatus.PENDING)
        connecter(client, "chef@example.org")
        jeton = jeton_csrf(client, f"/admin/quiz/{quiz.id}")
        reponse = client.post(
            f"/admin/quiz/{quiz.id}/refuser", data={"csrf_token": jeton, "reason": ""}
        )
        assert reponse.status_code == 422
        assert recharger(quiz.id).status is QuizStatus.PENDING
        client.post(
            f"/admin/quiz/{quiz.id}/refuser",
            data={"csrf_token": jeton, "reason": "La question 2 est ambiguë."},
        )
        quiz = recharger(quiz.id)
        assert quiz.status is QuizStatus.REJECTED
        assert quiz.rejection_reason == "La question 2 est ambiguë."
        assert "La question 2 est ambiguë." in mail.boite_envoi[-1].texte

    def test_depublier_un_quiz(
        self, app: Flask, client: FlaskClient, createur: User, admin: User
    ) -> None:
        quiz = creer_quiz(app, createur, titre="Obsolète")
        connecter(client, "chef@example.org")
        jeton = jeton_csrf(client, f"/admin/quiz/{quiz.id}")
        client.post(
            f"/admin/quiz/{quiz.id}/refuser",
            data={"csrf_token": jeton, "reason": "Contenu dépassé."},
        )
        assert recharger(quiz.id).status is QuizStatus.REJECTED
        client.get("/admin/")  # consomme le message flash qui cite le titre
        assert "Obsolète" not in client.get("/quiz").get_data(as_text=True)

    def test_publier_un_brouillon_impossible(self, app: Flask, createur: User) -> None:
        quiz = creer_quiz(app, createur, QuizStatus.DRAFT)
        assert not moderation.publier(quiz)
        assert not moderation.refuser(quiz, "motif")

    def test_un_admin_peut_corriger_sans_changer_le_statut(
        self, app: Flask, client: FlaskClient, createur: User, admin: User
    ) -> None:
        quiz = creer_quiz(app, createur, QuizStatus.PENDING)
        connecter(client, "chef@example.org")
        editer(client, f"/createur/quiz/{quiz.id}/modifier", formulaire(brouillon(3, "Corrigé")))
        quiz = recharger(quiz.id)
        assert quiz.title == "Corrigé"
        assert quiz.status is QuizStatus.PENDING
        assert quiz.creator_id == createur.id
