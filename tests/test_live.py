"""Parties en direct : PIN, salle d'attente, chrono, points, classement, animation."""

from __future__ import annotations

import re
from datetime import timedelta

import pytest
from flask import Flask
from flask.testing import FlaskClient
from sqlalchemy import select, update

from app.extensions import db
from app.models import LiveGame, LivePlayer, LiveStatus, PlaySession, Quiz, User, utcnow
from app.services import live
from tests.conftest import connecter, creer_compte, jeton_csrf
from tests.fabrique import creer_quiz


def recharger(partie: LiveGame) -> LiveGame:
    db.session.expire_all()
    trouvee = db.session.get(LiveGame, partie.id)
    assert trouvee is not None
    return trouvee


def lancer(client: FlaskClient, quiz: Quiz, chrono: str = "20") -> LiveGame:
    jeton = jeton_csrf(client, f"/quiz/{quiz.id}")
    reponse = client.post(f"/direct/lancer/{quiz.id}", data={"csrf_token": jeton, "chrono": chrono})
    assert reponse.status_code == 302, reponse.status_code
    game_id = int(reponse.headers["Location"].rsplit("/", 1)[1])
    partie = db.session.get(LiveGame, game_id)
    assert partie is not None
    return partie


def rejoindre(client: FlaskClient, pin: str, pseudo: str):  # type: ignore[no-untyped-def]
    jeton = jeton_csrf(client, "/direct/")
    return client.post("/direct/", data={"csrf_token": jeton, "pin": pin, "pseudo": pseudo})


def agir(client: FlaskClient, partie: LiveGame, action: str, **champs: str):  # type: ignore[no-untyped-def]
    jeton = jeton_csrf(client, f"/direct/animer/{partie.id}")
    return client.post(f"/direct/animer/{partie.id}/{action}", data={"csrf_token": jeton, **champs})


def repondre(client: FlaskClient, partie: LiveGame, choix: list[int], position: int | None = None):  # type: ignore[no-untyped-def]
    partie = recharger(partie)
    # Le jeton se lit sur la page « Rejoindre » : l'écran du joueur n'a pas toujours de formulaire.
    jeton = jeton_csrf(client, "/direct/")
    return client.post(
        f"/direct/jouer/{partie.id}",
        data={
            "csrf_token": jeton,
            "position": str(partie.current_index if position is None else position),
            "choix": [str(c) for c in choix],
        },
    )


def bonnes(partie: LiveGame) -> list[int]:
    question = live.question_courante(recharger(partie))
    assert question is not None
    return sorted(question.correct_ids)


def mauvaise(partie: LiveGame) -> list[int]:
    question = live.question_courante(recharger(partie))
    assert question is not None
    return [next(o.id for o in question.options if not o.is_correct)]


@pytest.fixture
def salle(app: Flask, createur: User) -> tuple[FlaskClient, LiveGame, Quiz]:
    quiz = creer_quiz(app, createur, n=3)
    animateur = app.test_client()
    connecter(animateur, "createur@example.org")
    return animateur, lancer(animateur, quiz), quiz


class TestLancement:
    def test_seul_un_createur_lance_une_partie(
        self, app: Flask, client: FlaskClient, createur: User
    ) -> None:
        quiz = creer_quiz(app, createur)
        creer_compte(app, "joueur")
        connecter(client, "joueur@example.org")
        jeton = jeton_csrf(client, f"/quiz/{quiz.id}")
        assert (
            client.post(f"/direct/lancer/{quiz.id}", data={"csrf_token": jeton}).status_code == 403
        )

    def test_brouillon_non_lancable(self, app: Flask, client: FlaskClient, createur: User) -> None:
        from app.models import QuizStatus

        quiz = creer_quiz(app, createur, QuizStatus.DRAFT)
        connecter(client, "createur@example.org")
        jeton = jeton_csrf(client, "/createur/")
        assert (
            client.post(f"/direct/lancer/{quiz.id}", data={"csrf_token": jeton}).status_code == 404
        )

    def test_pin_qr_et_chrono_borne(self, app: Flask, createur: User) -> None:
        quiz = creer_quiz(app, createur)
        animateur = app.test_client()
        connecter(animateur, "createur@example.org")
        partie = lancer(animateur, quiz, chrono="999")
        assert re.fullmatch(r"\d{6}", partie.pin or "")
        assert partie.time_limit == live.CHRONO_MAX
        html = animateur.get(f"/direct/animer/{partie.id}").get_data(as_text=True)
        assert partie.pin in html
        assert "<svg" in html

    def test_l_ecran_d_animation_est_reserve_a_l_animateur(
        self, app: Flask, salle: tuple[FlaskClient, LiveGame, Quiz]
    ) -> None:
        _, partie, _ = salle
        creer_compte(app, "curieux")
        curieux = app.test_client()
        connecter(curieux, "curieux@example.org")
        assert curieux.get(f"/direct/animer/{partie.id}").status_code == 404
        assert agir(curieux, partie, "terminer").status_code == 404
        assert curieux.get(f"/direct/{partie.id}/etat").status_code == 404
        assert recharger(partie).active


class TestSalleDAttente:
    def test_rejoindre_sans_compte(
        self, app: Flask, salle: tuple[FlaskClient, LiveGame, Quiz]
    ) -> None:
        animateur, partie, _ = salle
        joueur = app.test_client()
        reponse = rejoindre(joueur, partie.pin or "", "Alice")
        assert reponse.headers["Location"].endswith(f"/direct/jouer/{partie.id}")
        assert "Vous êtes dans la partie" in joueur.get(f"/direct/jouer/{partie.id}").get_data(
            as_text=True
        )
        assert "Alice" in animateur.get(f"/direct/animer/{partie.id}").get_data(as_text=True)
        etat = joueur.get(f"/direct/{partie.id}/etat").get_json()
        assert etat["joueurs"] == 1
        assert etat["statut"] == "lobby"

    def test_mauvais_pin(
        self, client: FlaskClient, salle: tuple[FlaskClient, LiveGame, Quiz]
    ) -> None:
        for pin in ("000000", "abc", "1234567890", ""):
            reponse = rejoindre(client, pin, "Bob")
            assert reponse.status_code == 404
            assert "Aucune partie ouverte avec ce code." in reponse.get_data(as_text=True)

    @pytest.mark.parametrize(
        ("pseudo", "message"),
        [
            ("", "Pseudo de 1 à 20"),
            ("<script>", "Pseudo de 1 à 20"),
            ("x" * 21, "Pseudo de 1 à 20"),
            ("Admin", "pas accepté"),
            ("gros connard", "pas accepté"),
            ("H i t l e r", "pas accepté"),
        ],
    )
    def test_pseudos_refuses(
        self,
        client: FlaskClient,
        salle: tuple[FlaskClient, LiveGame, Quiz],
        pseudo: str,
        message: str,
    ) -> None:
        _, partie, _ = salle
        reponse = rejoindre(client, partie.pin or "", pseudo)
        assert reponse.status_code == 422
        assert message in reponse.get_data(as_text=True)

    def test_pseudo_unique_sans_tenir_compte_de_la_casse_ni_des_accents(
        self, app: Flask, salle: tuple[FlaskClient, LiveGame, Quiz]
    ) -> None:
        _, partie, _ = salle
        rejoindre(app.test_client(), partie.pin or "", "Éloïse")
        reponse = rejoindre(app.test_client(), partie.pin or "", "eloise")
        assert "déjà pris" in reponse.get_data(as_text=True)
        assert rejoindre(app.test_client(), partie.pin or "", "Badminton").status_code == 302

    def test_partie_complete(self, app: Flask, salle: tuple[FlaskClient, LiveGame, Quiz]) -> None:
        _, partie, _ = salle
        partie.max_players = 2
        db.session.commit()
        rejoindre(app.test_client(), partie.pin or "", "Un")
        rejoindre(app.test_client(), partie.pin or "", "Deux")
        assert "complète" in rejoindre(app.test_client(), partie.pin or "", "Trois").get_data(
            as_text=True
        )

    def test_reconnexion_avec_la_meme_session(
        self, app: Flask, salle: tuple[FlaskClient, LiveGame, Quiz]
    ) -> None:
        _, partie, _ = salle
        joueur = app.test_client()
        rejoindre(joueur, partie.pin or "", "Fidèle")
        # Revenir avec le code ne crée pas de doublon.
        assert (
            rejoindre(joueur, partie.pin or "", "Autre")
            .headers["Location"]
            .endswith(f"/jouer/{partie.id}")
        )
        assert len(live.joueurs_actifs(recharger(partie))) == 1

    def test_ecran_joueur_sans_avoir_rejoint(
        self, client: FlaskClient, salle: tuple[FlaskClient, LiveGame, Quiz]
    ) -> None:
        _, partie, _ = salle
        assert f"pin={partie.pin}" in client.get(f"/direct/jouer/{partie.id}").headers["Location"]

    def test_lancer_exige_un_joueur(self, salle: tuple[FlaskClient, LiveGame, Quiz]) -> None:
        animateur, partie, _ = salle
        agir(animateur, partie, "demarrer")
        assert recharger(partie).status is LiveStatus.LOBBY

    def test_exclure_un_joueur(self, app: Flask, salle: tuple[FlaskClient, LiveGame, Quiz]) -> None:
        animateur, partie, _ = salle
        joueur = app.test_client()
        rejoindre(joueur, partie.pin or "", "Perturbateur")
        cible = db.session.scalar(select(LivePlayer).where(LivePlayer.nickname == "Perturbateur"))
        assert cible is not None
        agir(animateur, partie, "exclure", joueur=str(cible.id))
        assert joueur.get(f"/direct/jouer/{partie.id}").status_code == 302
        assert live.classement(recharger(partie)) == []


class TestDeroulement:
    @pytest.fixture
    def en_jeu(
        self, app: Flask, salle: tuple[FlaskClient, LiveGame, Quiz]
    ) -> tuple[FlaskClient, LiveGame, FlaskClient, FlaskClient]:
        animateur, partie, _ = salle
        alice, bob = app.test_client(), app.test_client()
        rejoindre(alice, partie.pin or "", "Alice")
        rejoindre(bob, partie.pin or "", "Bob")
        agir(animateur, partie, "demarrer")
        return animateur, recharger(partie), alice, bob

    def test_la_question_n_affiche_pas_la_bonne_reponse(self, en_jeu) -> None:  # type: ignore[no-untyped-def]
        _, partie, alice, _ = en_jeu
        html = alice.get(f"/direct/jouer/{partie.id}").get_data(as_text=True)
        assert "Question numéro 1 ?" in html
        assert "Explication" not in html
        etat = alice.get(f"/direct/{partie.id}/etat").get_json()
        assert set(etat) == {
            "version",
            "statut",
            "question",
            "total",
            "reste_ms",
            "chrono_s",
            "reponses",
            "joueurs",
        }

    def test_points_selon_justesse_et_rapidite(self, en_jeu) -> None:  # type: ignore[no-untyped-def]
        _, partie, alice, bob = en_jeu
        repondre(alice, partie, bonnes(partie))
        repondre(bob, partie, mauvaise(partie))
        scores = {j.nickname: j.score for j in live.classement(recharger(partie))}
        assert 900 <= scores["Alice"] <= 1000
        assert scores["Bob"] == 0
        # Tout le monde a répondu : correction affichée sans attendre la fin du chrono.
        assert recharger(partie).status is LiveStatus.REVEAL
        assert "Bonne réponse" in alice.get(f"/direct/jouer/{partie.id}").get_data(as_text=True)

    def test_une_seule_reponse_par_question(self, en_jeu) -> None:  # type: ignore[no-untyped-def]
        _, partie, alice, _ = en_jeu
        repondre(alice, partie, mauvaise(partie))
        repondre(alice, partie, bonnes(partie))
        assert live.classement(recharger(partie))[0].score == 0

    def test_reponse_hors_delai_refusee(self, en_jeu) -> None:  # type: ignore[no-untyped-def]
        _, partie, alice, _ = en_jeu
        db.session.execute(
            update(LiveGame)
            .where(LiveGame.id == partie.id)
            .values(question_deadline=utcnow() - timedelta(seconds=1))
        )
        db.session.commit()
        repondre(alice, partie, bonnes(partie))
        partie = recharger(partie)
        assert partie.status is LiveStatus.REVEAL
        assert all(j.score == 0 for j in live.classement(partie))

    def test_reponse_a_une_ancienne_question_refusee(self, en_jeu) -> None:  # type: ignore[no-untyped-def]
        animateur, partie, alice, _ = en_jeu
        agir(animateur, partie, "suivant")  # correction
        agir(animateur, partie, "suivant")  # question 2
        html = repondre(alice, partie, bonnes(partie), position=0).get_data(as_text=True)
        assert "Cette question est terminée." in html

    def test_choix_invalide_refuse(self, en_jeu) -> None:  # type: ignore[no-untyped-def]
        _, partie, alice, _ = en_jeu
        assert "Réponse invalide." in repondre(alice, partie, [999999]).get_data(as_text=True)
        question = live.question_courante(recharger(partie))
        assert question is not None
        assert question.multiple
        assert "Réponse invalide." not in repondre(
            alice, partie, [o.id for o in question.options]
        ).get_data(as_text=True)

    def test_pause_et_reprise(self, en_jeu) -> None:  # type: ignore[no-untyped-def]
        animateur, partie, alice, _ = en_jeu
        agir(animateur, partie, "pause")
        partie = recharger(partie)
        assert partie.status is LiveStatus.PAUSED
        assert partie.paused_remaining_ms is not None
        assert "Aucune question" in repondre(alice, partie, bonnes(partie)).get_data(as_text=True)
        agir(animateur, partie, "reprendre")
        partie = recharger(partie)
        assert partie.status is LiveStatus.QUESTION
        repondre(alice, partie, bonnes(partie))
        assert live.classement(recharger(partie))[0].score > 0

    def test_partie_complete_jusqu_au_podium(self, app: Flask, en_jeu) -> None:  # type: ignore[no-untyped-def]
        animateur, partie, alice, bob = en_jeu
        for _ in range(partie.total):
            repondre(alice, partie, bonnes(partie))
            repondre(bob, partie, mauvaise(partie))
            agir(animateur, partie, "suivant")
            if recharger(partie).status is LiveStatus.REVEAL:
                agir(animateur, partie, "suivant")
        partie = recharger(partie)
        assert partie.status is LiveStatus.FINISHED
        assert partie.pin is None
        html = animateur.get(f"/direct/animer/{partie.id}").get_data(as_text=True)
        assert "Podium" in html
        csv = animateur.get(f"/direct/animer/{partie.id}/classement.csv").get_data(as_text=True)
        assert "1;Alice;" in csv
        assert "2;Bob;0;0" in csv
        assert "1<sup" in alice.get(f"/direct/jouer/{partie.id}").get_data(as_text=True)

    def test_double_clic_de_l_animateur_n_avance_qu_une_fois(self, en_jeu) -> None:  # type: ignore[no-untyped-def]
        _, partie, _, _ = en_jeu
        perime = recharger(partie)
        version = perime.version
        assert live.suivant(perime)
        perime.version = version  # comme une seconde requête partie de la même page
        assert not live._transition(perime, {LiveStatus.QUESTION}, status=LiveStatus.REVEAL)

    def test_resultats_enregistres_pour_les_joueurs_connectes(
        self, app: Flask, salle: tuple[FlaskClient, LiveGame, Quiz]
    ) -> None:
        animateur, partie, _ = salle
        creer_compte(app, "inscrit")
        inscrit, anonyme = app.test_client(), app.test_client()
        connecter(inscrit, "inscrit@example.org")
        rejoindre(inscrit, partie.pin or "", "Inscrit")
        rejoindre(anonyme, partie.pin or "", "Anonyme")
        agir(animateur, partie, "demarrer")
        repondre(inscrit, partie, bonnes(partie))
        agir(animateur, partie, "terminer")
        sessions = db.session.scalars(select(PlaySession)).all()
        assert len(sessions) == 1
        assert sessions[0].score == 1
        assert sessions[0].total == 3
        assert "1 / 3" in inscrit.get("/profil/").get_data(as_text=True)


class TestService:
    def test_bareme(self) -> None:
        assert live.points(False, 0, 20) == 0
        assert live.points(True, 0, 20) == 1000
        assert live.points(True, 10_000, 20) == 750
        assert live.points(True, 25_000, 20) == 500

    def test_export_csv_neutralise_les_formules(
        self, app: Flask, salle: tuple[FlaskClient, LiveGame, Quiz]
    ) -> None:
        _, partie, _ = salle
        db.session.add(
            LivePlayer(game_id=partie.id, nickname="=1+1", nickname_key="x", token="t" * 43)
        )
        db.session.commit()
        assert "'=1+1" in live.export_csv(recharger(partie))

    def test_purge(self, app: Flask, salle: tuple[FlaskClient, LiveGame, Quiz]) -> None:
        _, partie, _ = salle
        partie.last_activity_at = utcnow() - timedelta(hours=4)
        db.session.commit()
        assert live.purger() == (1, 0)
        partie = recharger(partie)
        assert partie.status is LiveStatus.FINISHED
        partie.ended_at = utcnow() - timedelta(hours=25)
        db.session.commit()
        identifiant = partie.id
        assert live.purger() == (0, 1)
        db.session.expire_all()
        assert db.session.get(LiveGame, identifiant) is None

    def test_actions_inconnues_ou_hors_etat(
        self, salle: tuple[FlaskClient, LiveGame, Quiz]
    ) -> None:
        animateur, partie, _ = salle
        assert agir(animateur, partie, "inconnue").status_code == 404
        assert not live.pause(partie)
        assert not live.reprendre(partie)
        assert not live.suivant(partie)
        assert not live.exclure(partie, 123456)
        assert live.terminer(partie)
        assert not live.terminer(partie)


def test_essais_de_pin_limites_mais_pas_les_arrivees(
    app: Flask, salle: tuple[FlaskClient, LiveGame, Quiz]
) -> None:
    _, partie, _ = salle
    client = app.test_client()
    for i in range(35):
        assert rejoindre(app.test_client(), partie.pin or "", f"Eleve {i}").status_code == 302
    codes = [rejoindre(client, "000000", "Devin").status_code for _ in range(31)]
    assert codes[-1] == 429
    assert set(codes[:30]) == {404}
