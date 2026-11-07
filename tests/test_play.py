"""Catalogue, parties en solo (corrigées côté serveur), avis."""

from __future__ import annotations

import re

from flask import Flask
from flask.testing import FlaskClient

from app.extensions import db
from app.models import PlaySession, Quiz, QuizStatus, User
from tests.conftest import connecter, creer_compte, jeton_csrf
from tests.fabrique import creer_quiz


def demarrer(client: FlaskClient, quiz: Quiz) -> str:
    jeton = jeton_csrf(client, f"/quiz/{quiz.id}")
    reponse = client.post(f"/quiz/{quiz.id}/jouer", data={"csrf_token": jeton})
    assert reponse.status_code == 302, reponse.status_code
    return reponse.headers["Location"].rsplit("/", 1)[1]


def page_question(client: FlaskClient, token: str) -> tuple[int, dict[str, int], str]:
    """Identifiant de la question en cours et identifiants de ses réponses par texte."""
    html = client.get(f"/partie/{token}").get_data(as_text=True)
    question = int(re.search(r'name="question" value="(\d+)"', html).group(1))  # type: ignore[union-attr]
    options = {
        texte.strip(): int(valeur)
        for valeur, texte in re.findall(
            r'name="choix" value="(\d+)"[^>]*>\s*'
            r'<span aria-hidden="true">[^<]*</span>\s*<span>([^<]+)</span>',
            html,
        )
    }
    return question, options, html


def repondre(client: FlaskClient, token: str, question: int, choix: list[int]):  # type: ignore[no-untyped-def]
    jeton = jeton_csrf(client, f"/partie/{token}")
    return client.post(
        f"/partie/{token}",
        data={"csrf_token": jeton, "question": str(question), "choix": [str(c) for c in choix]},
    )


def partie(token: str) -> PlaySession:
    db.session.expire_all()
    trouvee = db.session.scalar(db.select(PlaySession).where(PlaySession.token == token))
    assert trouvee is not None
    return trouvee


class TestCatalogue:
    def test_seuls_les_quiz_publies_apparaissent(
        self, app: Flask, client: FlaskClient, createur: User
    ) -> None:
        creer_quiz(app, createur, titre="Publié visible")
        creer_quiz(app, createur, QuizStatus.DRAFT, titre="Brouillon caché")
        creer_quiz(app, createur, QuizStatus.PENDING, titre="En attente caché")
        html = client.get("/quiz").get_data(as_text=True)
        assert "Publié visible" in html
        assert "caché" not in html

    def test_recherche_et_filtres(self, app: Flask, client: FlaskClient, createur: User) -> None:
        creer_quiz(app, createur, titre="Wi-Fi public")
        creer_quiz(app, createur, titre="Gestion des secrets")
        html = client.get("/quiz?q=wi-fi").get_data(as_text=True)
        assert "Wi-Fi public" in html
        assert "Gestion des secrets" not in html
        assert "Wi-Fi public" not in client.get("/quiz?categorie=2").get_data(as_text=True)
        assert "Wi-Fi public" not in client.get("/quiz?niveau=hard").get_data(as_text=True)

    def test_recherche_avec_caracteres_speciaux(self, client: FlaskClient) -> None:
        for texte in ("%", "_", "\\", "' OR 1=1 --"):
            assert client.get("/quiz", query_string={"q": texte}).status_code == 200

    def test_brouillon_introuvable_pour_les_autres(
        self, app: Flask, client: FlaskClient, createur: User
    ) -> None:
        quiz = creer_quiz(app, createur, QuizStatus.DRAFT)
        assert client.get(f"/quiz/{quiz.id}").status_code == 404
        creer_compte(app, "curieux")
        connecter(client, "curieux@example.org")
        assert client.get(f"/quiz/{quiz.id}").status_code == 404

    def test_apercu_du_brouillon_pour_son_createur(
        self, app: Flask, client: FlaskClient, createur: User
    ) -> None:
        quiz = creer_quiz(app, createur, QuizStatus.DRAFT)
        connecter(client, "createur@example.org")
        html = client.get(f"/quiz/{quiz.id}").get_data(as_text=True)
        assert "Aperçu" in html


class TestPartie:
    def test_jouer_exige_une_connexion(
        self, app: Flask, client: FlaskClient, createur: User
    ) -> None:
        quiz = creer_quiz(app, createur)
        jeton = jeton_csrf(client, "/compte/connexion")
        reponse = client.post(f"/quiz/{quiz.id}/jouer", data={"csrf_token": jeton})
        assert "/compte/connexion" in reponse.headers["Location"]

    def test_partie_complete_score_calcule_par_le_serveur(
        self, app: Flask, client: FlaskClient, createur: User
    ) -> None:
        quiz = creer_quiz(app, createur, n=3)
        connecter(client, "createur@example.org")
        token = demarrer(client, quiz)
        # Q1 : deux bonnes réponses (A0 et B0) → juste. Q2 : faux. Q3 : juste.
        q, opts, html = page_question(client, token)
        assert 'type="checkbox"' in html
        assert (
            repondre(client, token, q, [opts["Réponse A0"], opts["Réponse B0"]]).status_code == 302
        )
        q, opts, html = page_question(client, token)
        assert 'type="radio"' in html
        repondre(client, token, q, [opts["Réponse C1"]])
        q, opts, _ = page_question(client, token)
        reponse = repondre(client, token, q, [opts["Réponse A2"]])
        assert partie(token).score == 2
        assert partie(token).finished
        assert reponse.headers["Location"].endswith("/correction/2")
        resultat = client.get(f"/partie/{token}/resultat").get_data(as_text=True)
        assert "2 / 3" in resultat
        assert "Explication détaillée numéro 2." in resultat

    def test_reponse_incomplete_comptee_fausse(
        self, app: Flask, client: FlaskClient, createur: User
    ) -> None:
        quiz = creer_quiz(app, createur)
        connecter(client, "createur@example.org")
        token = demarrer(client, quiz)
        q, opts, _ = page_question(client, token)
        repondre(client, token, q, [opts["Réponse A0"]])  # il manquait B0
        assert partie(token).score == 0

    def test_la_page_de_question_ne_revele_pas_les_bonnes_reponses(
        self, app: Flask, client: FlaskClient, createur: User
    ) -> None:
        quiz = creer_quiz(app, createur)
        connecter(client, "createur@example.org")
        token = demarrer(client, quiz)
        _, _, html = page_question(client, token)
        assert "bonne réponse" not in html.lower()
        assert "correct" not in html.lower()
        assert "Explication détaillée" not in html

    def test_pas_de_score_envoye_par_le_client(
        self, app: Flask, client: FlaskClient, createur: User
    ) -> None:
        quiz = creer_quiz(app, createur)
        connecter(client, "createur@example.org")
        token = demarrer(client, quiz)
        q, opts, _ = page_question(client, token)
        jeton = jeton_csrf(client, f"/partie/{token}")
        client.post(
            f"/partie/{token}",
            data={
                "csrf_token": jeton,
                "question": str(q),
                "choix": [str(opts["Réponse C0"])],
                "score": "100",
                "totalQuestions": "1",
            },
        )
        assert partie(token).score == 0

    def test_impossible_de_repondre_deux_fois_ou_a_une_autre_question(
        self, app: Flask, client: FlaskClient, createur: User
    ) -> None:
        quiz = creer_quiz(app, createur)
        connecter(client, "createur@example.org")
        token = demarrer(client, quiz)
        q1, opts1, _ = page_question(client, token)
        repondre(client, token, q1, [opts1["Réponse C0"]])
        # Rejouer la même question (pour corriger une erreur) : refusé.
        html = repondre(client, token, q1, [opts1["Réponse A0"], opts1["Réponse B0"]]).get_data(
            as_text=True
        )
        assert "plus la question en cours" in html
        assert partie(token).score == 0
        assert partie(token).current_index == 1

    def test_choix_d_une_autre_question_refuse(
        self, app: Flask, client: FlaskClient, createur: User
    ) -> None:
        quiz = creer_quiz(app, createur)
        connecter(client, "createur@example.org")
        token = demarrer(client, quiz)
        q, _, _ = page_question(client, token)
        autre = quiz.questions[1].options[0].id
        html = repondre(client, token, q, [autre]).get_data(as_text=True)
        assert "Réponse invalide." in html
        assert partie(token).current_index == 0

    def test_un_seul_choix_pour_une_question_simple(
        self, app: Flask, client: FlaskClient, createur: User
    ) -> None:
        quiz = creer_quiz(app, createur)
        connecter(client, "createur@example.org")
        token = demarrer(client, quiz)
        q, opts, _ = page_question(client, token)
        repondre(client, token, q, [opts["Réponse A0"], opts["Réponse B0"]])
        q, opts, _ = page_question(client, token)
        html = repondre(client, token, q, [opts["Réponse A1"], opts["Réponse C1"]]).get_data(
            as_text=True
        )
        assert "Une seule réponse" in html

    def test_aucun_choix_refuse(self, app: Flask, client: FlaskClient, createur: User) -> None:
        quiz = creer_quiz(app, createur)
        connecter(client, "createur@example.org")
        token = demarrer(client, quiz)
        q, _, _ = page_question(client, token)
        assert "Choisissez au moins une réponse." in repondre(client, token, q, []).get_data(
            as_text=True
        )

    def test_partie_d_un_autre_joueur_introuvable(self, app: Flask, createur: User) -> None:
        quiz = creer_quiz(app, createur)
        creer_compte(app, "intrus")
        proprietaire, intrus = app.test_client(), app.test_client()
        connecter(proprietaire, "createur@example.org")
        token = demarrer(proprietaire, quiz)
        connecter(intrus, "intrus@example.org")
        assert intrus.get(f"/partie/{token}").status_code == 404
        assert intrus.get(f"/partie/{token}/resultat").status_code == 404
        assert intrus.get(f"/partie/{token}/correction/0").status_code == 404

    def test_reprise_de_la_partie_en_cours(
        self, app: Flask, client: FlaskClient, createur: User
    ) -> None:
        quiz = creer_quiz(app, createur)
        connecter(client, "createur@example.org")
        assert demarrer(client, quiz) == demarrer(client, quiz)

    def test_correction_d_une_question_pas_encore_jouee(
        self, app: Flask, client: FlaskClient, createur: User
    ) -> None:
        quiz = creer_quiz(app, createur)
        connecter(client, "createur@example.org")
        token = demarrer(client, quiz)
        assert client.get(f"/partie/{token}/correction/0").status_code == 404
        assert client.get(f"/partie/{token}/resultat").headers["Location"].endswith(token)

    def test_brouillon_non_jouable(self, app: Flask, client: FlaskClient, createur: User) -> None:
        quiz = creer_quiz(app, createur, QuizStatus.DRAFT)
        connecter(client, "createur@example.org")
        reponse = client.post(
            f"/quiz/{quiz.id}/jouer", data={"csrf_token": jeton_csrf(client, "/")}
        )
        assert reponse.headers["Location"].endswith(f"/quiz/{quiz.id}")

    def test_historique_sur_le_profil(
        self, app: Flask, client: FlaskClient, createur: User
    ) -> None:
        quiz = creer_quiz(app, createur, n=1, titre="Quiz express")
        connecter(client, "createur@example.org")
        token = demarrer(client, quiz)
        q, opts, _ = page_question(client, token)
        repondre(client, token, q, [opts["Réponse A0"], opts["Réponse B0"]])
        html = client.get("/profil/").get_data(as_text=True)
        assert "Quiz express" in html
        assert "1 / 1" in html


class TestAvis:
    def noter(self, client: FlaskClient, quiz: Quiz, note: str, commentaire: str = ""):  # type: ignore[no-untyped-def]
        jeton = jeton_csrf(client, f"/quiz/{quiz.id}")
        return client.post(
            f"/quiz/{quiz.id}/avis",
            data={"csrf_token": jeton, "rating": note, "comment": commentaire},
        )

    def finir(self, client: FlaskClient, quiz: Quiz) -> None:
        token = demarrer(client, quiz)
        while not partie(token).finished:
            q, opts, _ = page_question(client, token)
            repondre(client, token, q, [next(iter(opts.values()))])

    def test_avis_apres_une_partie_terminee_seulement(
        self, app: Flask, client: FlaskClient, createur: User
    ) -> None:
        quiz = creer_quiz(app, createur, n=1)
        connecter(client, "createur@example.org")
        self.noter(client, quiz, "5")
        assert "Merci" not in client.get(f"/quiz/{quiz.id}").get_data(as_text=True)
        self.finir(client, quiz)
        self.noter(client, quiz, "4", "Très clair")
        html = client.get(f"/quiz/{quiz.id}").get_data(as_text=True)
        assert "Très clair" in html
        assert "4.0" in html

    def test_un_seul_avis_par_joueur_mis_a_jour(
        self, app: Flask, client: FlaskClient, createur: User
    ) -> None:
        quiz = creer_quiz(app, createur, n=1)
        connecter(client, "createur@example.org")
        self.finir(client, quiz)
        self.noter(client, quiz, "2", "Bof")
        self.noter(client, quiz, "5", "Finalement top")
        html = client.get(f"/quiz/{quiz.id}").get_data(as_text=True)
        assert "Bof" not in html
        assert "(1)" in html

    def test_note_hors_bornes_refusee(
        self, app: Flask, client: FlaskClient, createur: User
    ) -> None:
        quiz = creer_quiz(app, createur, n=1)
        connecter(client, "createur@example.org")
        self.finir(client, quiz)
        self.noter(client, quiz, "9")
        assert "Pas encore d'avis" in client.get(f"/quiz/{quiz.id}").get_data(as_text=True)

    def test_commentaire_echappe(self, app: Flask, client: FlaskClient, createur: User) -> None:
        quiz = creer_quiz(app, createur, n=1)
        connecter(client, "createur@example.org")
        self.finir(client, quiz)
        self.noter(client, quiz, "3", "<script>alert(1)</script>")
        html = client.get(f"/quiz/{quiz.id}").get_data(as_text=True)
        assert "<script>alert(1)</script>" not in html
        assert "&lt;script&gt;" in html
