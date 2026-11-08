"""Types de questions : choix, vrai/faux, phishing, remettre dans l'ordre."""

from __future__ import annotations

from flask import Flask
from flask.testing import FlaskClient
from sqlalchemy import select
from werkzeug.datastructures import MultiDict

from app.extensions import db
from app.models import PlaySession, Question, QuestionKind, Quiz, QuizStatus, User
from app.services import correction, moderation, quizzes
from tests.conftest import connecter, jeton_csrf
from tests.fabrique import brouillon_types, formulaire


def creer(app: Flask, auteur: User) -> Quiz:
    with app.test_request_context():
        quiz = quizzes.enregistrer(None, brouillon_types(), auteur)
        assert quizzes.soumettre(quiz) == {}
        assert moderation.publier(quiz)
    return quiz


def question(quiz: Quiz, type_: QuestionKind) -> Question:
    return next(q for q in quiz.questions if q.kind is type_)


class TestCorrection:
    def test_vrai_faux_et_choix(self, app: Flask, createur: User) -> None:
        quiz = creer(app, createur)
        vf = question(quiz, QuestionKind.TRUE_FALSE)
        faux = next(o.id for o in vf.options if o.text == "Faux")
        assert correction.corriger(vf, [faux]) is True
        assert correction.corriger(vf, [o.id for o in vf.options]) is correction.Refus.UN_SEUL_CHOIX
        assert correction.corriger(vf, []) is correction.Refus.AUCUN_CHOIX

    def test_phishing_exige_tous_les_indices_et_rien_d_autre(
        self, app: Flask, createur: User
    ) -> None:
        q = question(creer(app, createur), QuestionKind.PHISHING)
        indices = sorted(q.correct_ids)
        anodin = next(o.id for o in q.options if not o.is_correct)
        assert q.multiple
        assert correction.corriger(q, indices) is True
        assert correction.corriger(q, indices[:1]) is False
        assert correction.corriger(q, [*indices, anodin]) is False

    def test_ordre(self, app: Flask, createur: User) -> None:
        q = question(creer(app, createur), QuestionKind.ORDER)
        attendu = q.ordre_attendu
        assert correction.corriger(q, attendu) is True
        assert correction.corriger(q, list(reversed(attendu))) is False
        assert correction.corriger(q, attendu[:2]) is correction.Refus.ORDRE_INCOMPLET
        assert correction.a_enregistrer(q, list(reversed(attendu))) == list(reversed(attendu))

    def test_lecture_des_rangs(self, app: Flask, createur: User) -> None:
        q = question(creer(app, createur), QuestionKind.ORDER)
        a, b, c = q.ordre_attendu
        form = MultiDict({f"rang-{a}": "2", f"rang-{b}": "3", f"rang-{c}": "1"})
        assert correction.lire(q, form) == [c, a, b]
        doublon = MultiDict({f"rang-{a}": "1", f"rang-{b}": "1", f"rang-{c}": "2"})
        assert correction.lire(q, doublon) == []

    def test_ordre_affiche_melange_et_stable(self, app: Flask, createur: User) -> None:
        q = question(creer(app, createur), QuestionKind.ORDER)
        premier = [o.id for o in correction.ordre_affiche(q, "partie-1")]
        assert premier == [o.id for o in correction.ordre_affiche(q, "partie-1")]
        assert premier != q.ordre_attendu
        assert sorted(premier) == sorted(q.ordre_attendu)


class TestEditeur:
    def test_enregistrer_et_relire_tous_les_types(self, app: Flask, createur: User) -> None:
        quiz = creer(app, createur)
        assert [q.kind for q in quiz.questions] == [
            QuestionKind.CHOICE,
            QuestionKind.TRUE_FALSE,
            QuestionKind.PHISHING,
            QuestionKind.ORDER,
        ]
        phishing = question(quiz, QuestionKind.PHISHING)
        assert phishing.payload == {
            "canal": "email",
            "expediteur": "service@banque-horizon-securite.example",
            "objet": "Action requise",
        }
        relu = quizzes.brouillon_depuis(quiz)
        assert relu.questions[2].expediteur == "service@banque-horizon-securite.example"
        assert relu.questions[3].kind == "order"

    def test_passer_en_vrai_faux(self) -> None:
        b = brouillon_types()
        b.questions[0].kind = "true_false"
        quizzes.appliquer_action(b, "appliquer-type:0")
        assert [o.text for o in b.questions[0].options] == ["Vrai", "Faux"]
        assert sum(o.correct for o in b.questions[0].options) == 1

    def test_passer_en_ordre_ajoute_une_etape(self) -> None:
        b = brouillon_types()
        b.questions[1].kind = "order"
        quizzes.appliquer_action(b, "appliquer-type:1")
        assert len(b.questions[1].options) == quizzes.ORDRE_MIN

    def test_validations_par_type(self, app: Flask) -> None:
        b = brouillon_types()
        b.questions[1].options[0].text = "Peut-être"
        b.questions[2].expediteur = ""
        for option in b.questions[2].options:
            option.correct = True
        b.questions[3].options.pop()
        erreurs = quizzes.valider(b, set())
        assert "q-1-options" in erreurs
        assert "q-2-expediteur" in erreurs
        assert any("passage anodin" in m for m in erreurs["q-2-options"])
        assert "q-3-options" in erreurs

    def test_phishing_sans_indice(self, app: Flask) -> None:
        b = brouillon_types()
        for option in b.questions[2].options:
            option.correct = False
        assert "Cochez au moins un passage suspect." in quizzes.valider(b, set())["q-2-options"]

    def test_editeur_affiche_les_champs_du_type(self, client: FlaskClient, createur: User) -> None:
        connecter(client, "createur@example.org")
        champs = formulaire(brouillon_types(), "ajouter-question")
        champs["csrf_token"] = jeton_csrf(client, "/createur/quiz/nouveau")
        html = client.post("/createur/quiz/nouveau", data=champs).get_data(as_text=True)
        assert 'name="q-2-expediteur"' in html
        assert "Suspect" in html
        assert "Étapes, dans le bon ordre" in html


class TestPartie:
    def jouer_jusqu_a(
        self, client: FlaskClient, quiz: Quiz, type_: QuestionKind
    ) -> tuple[str, str]:
        """Démarre une partie et répond juste jusqu'à la première question du type voulu."""
        from tests.test_play import demarrer, repondre

        token = demarrer(client, quiz)
        for q in quiz.questions:
            if q.kind is type_:
                break
            repondre(client, token, q.id, sorted(q.correct_ids))
        return token, client.get(f"/partie/{token}").get_data(as_text=True)

    def test_phishing_en_solo(self, app: Flask, client: FlaskClient, createur: User) -> None:
        quiz = creer(app, createur)
        connecter(client, "createur@example.org")
        token, html = self.jouer_jusqu_a(client, quiz, QuestionKind.PHISHING)
        assert "service@banque-horizon-securite.example" in html
        assert html.count('class="indice') == 4
        q = question(quiz, QuestionKind.PHISHING)
        jeton = jeton_csrf(client, f"/partie/{token}")
        client.post(
            f"/partie/{token}",
            data={
                "csrf_token": jeton,
                "question": str(q.id),
                "choix": [str(i) for i in q.correct_ids],
            },
        )
        partie = db.session.scalar(select(PlaySession).where(PlaySession.token == token))
        assert partie is not None
        db.session.refresh(partie)
        assert partie.answers[-1].is_correct
        corrige = client.get(f"/partie/{token}/correction/{partie.answers[-1].position}")
        assert "<mark" in corrige.get_data(as_text=True)

    def test_ordre_en_solo(self, app: Flask, client: FlaskClient, createur: User) -> None:
        quiz = creer(app, createur)
        connecter(client, "createur@example.org")
        q = question(quiz, QuestionKind.ORDER)
        from tests.test_play import demarrer, repondre

        token = demarrer(client, quiz)
        for precedente in quiz.questions[:3]:
            repondre(client, token, precedente.id, sorted(precedente.correct_ids))
        html = client.get(f"/partie/{token}").get_data(as_text=True)
        assert f'name="rang-{q.ordre_attendu[0]}"' in html
        jeton = jeton_csrf(client, f"/partie/{token}")
        incomplet = client.post(
            f"/partie/{token}",
            data={
                "csrf_token": jeton,
                "question": str(q.id),
                f"rang-{q.ordre_attendu[0]}": "1",
            },
        )
        assert "Donnez un rang différent" in incomplet.get_data(as_text=True)
        rangs = {f"rang-{oid}": str(i + 1) for i, oid in enumerate(q.ordre_attendu)}
        client.post(f"/partie/{token}", data={"csrf_token": jeton, "question": str(q.id), **rangs})
        partie = db.session.scalar(select(PlaySession).where(PlaySession.token == token))
        assert partie is not None
        db.session.refresh(partie)
        assert partie.finished
        assert partie.answers[-1].is_correct
        assert partie.answers[-1].selected_ids == q.ordre_attendu
        assert "Ordre attendu" in client.get(f"/partie/{token}/resultat").get_data(as_text=True)


def test_chargement_de_la_demo_complete(app: Flask, admin: User) -> None:
    resultat = app.test_cli_runner().invoke(args=["charger-demo", "--email", "chef@example.org"])
    assert resultat.exit_code == 0, resultat.output
    quiz = db.session.scalars(select(Quiz).where(Quiz.status == QuizStatus.PUBLISHED)).all()
    assert len(quiz) >= 2
    types = {q.kind for z in quiz for q in z.questions}
    assert QuestionKind.CHOICE in types
