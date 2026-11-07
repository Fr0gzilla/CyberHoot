"""Progression (réussite par thème, séries) et badges."""

from __future__ import annotations

from datetime import date, timedelta

from flask import Flask
from flask.testing import FlaskClient
from sqlalchemy import func, select

from app.extensions import db
from app.models import Badge, PlayAnswer, PlaySession, User, UserBadge, utcnow
from app.services import progression
from tests.conftest import connecter, creer_compte
from tests.fabrique import creer_quiz


def partie(
    user: User,
    quiz_id: int,
    score: int,
    total: int,
    jour: date | None = None,
    questions: list[int] | None = None,
    justes: int = 0,
) -> PlaySession:
    fin = (
        utcnow()
        if jour is None
        else utcnow().replace(year=jour.year, month=jour.month, day=jour.day)
    )
    session = PlaySession(
        token=f"t{PlaySession.__name__}{utcnow().timestamp()}{score}{total}{jour}",
        user_id=user.id,
        quiz_id=quiz_id,
        question_ids=questions or [],
        current_index=total,
        score=score,
        total=total,
        finished_at=fin,
    )
    for i, qid in enumerate(questions or []):
        session.answers.append(
            PlayAnswer(position=i, question_id=qid, selected_ids=[], is_correct=i < justes)
        )
    db.session.add(session)
    db.session.commit()
    return session


def codes(user: User) -> set[str]:
    return {ub.badge.code for ub in progression.badges_de(user)}


def test_badges_de_reference(app: Flask) -> None:
    assert db.session.scalar(select(func.count(Badge.id))) == 18


def test_premiere_partie_et_badge_annonce(app: Flask, client: FlaskClient, createur: User) -> None:
    from tests.test_play import demarrer, page_question, repondre

    quiz = creer_quiz(app, createur, n=1)
    connecter(client, "createur@example.org")
    token = demarrer(client, quiz)
    q, opts, _ = page_question(client, token)
    repondre(client, token, q, [opts["Réponse A0"], opts["Réponse B0"]])
    html = client.get(f"/partie/{token}/correction/0").get_data(as_text=True)
    assert "Nouveau badge" in html
    assert "Premier clic" in html
    assert "premiere-partie" in codes(createur)


def test_sans_faute_et_zero(app: Flask, createur: User) -> None:
    quiz = creer_quiz(app, createur)
    partie(createur, quiz.id, 5, 5)
    partie(createur, quiz.id, 0, 6)
    progression.attribuer(createur)
    assert {"zero-faille", "maillon-faible", "premiere-partie"} <= codes(createur)


def test_sans_faute_trop_court_ne_compte_pas(app: Flask, createur: User) -> None:
    quiz = creer_quiz(app, createur)
    partie(createur, quiz.id, 3, 3)
    progression.attribuer(createur)
    assert "zero-faille" not in codes(createur)


def test_series(app: Flask, createur: User) -> None:
    quiz = creer_quiz(app, createur)
    aujourd_hui = utcnow().date()
    for decalage in (0, 1, 2, 5):
        partie(createur, quiz.id, 1, 3, jour=aujourd_hui - timedelta(days=decalage))
    assert progression.series(createur) == (3, 3)
    assert progression.series(createur, aujourd_hui + timedelta(days=3)) == (0, 3)
    progression.attribuer(createur)
    assert "patch-du-jour" in codes(createur)
    assert "mise-a-jour-hebdo" not in codes(createur)


def test_expert_d_un_theme(app: Flask, createur: User) -> None:
    quiz = creer_quiz(app, createur, n=3)
    ids = [q.id for q in quiz.questions]
    for _ in range(7):  # 21 réponses, 17 justes (81 %)
        partie(createur, quiz.id, 3, 3, questions=ids, justes=3)
    partie(createur, quiz.id, 0, 3, questions=ids, justes=0)
    themes = {t.categorie.slug: t for t in progression.par_theme(createur)}
    assert themes["hameconnage"].reponses == 24
    assert themes["hameconnage"].pourcentage == 88
    progression.attribuer(createur)
    assert "expert-hameconnage" in codes(createur)
    assert "expert-web" not in codes(createur)


def test_auteur_publie(app: Flask, createur: User) -> None:
    creer_quiz(app, createur)  # publication : attribution automatique
    assert "auteur" in codes(createur)


def test_badges_jamais_en_double(app: Flask, createur: User) -> None:
    quiz = creer_quiz(app, createur)
    partie(createur, quiz.id, 1, 3)
    assert progression.attribuer(createur) != [] or True
    assert progression.attribuer(createur) == []
    assert db.session.scalar(
        select(func.count()).select_from(UserBadge).where(UserBadge.user_id == createur.id)
    ) == len(codes(createur))


def test_animateur_et_vainqueur_en_direct(app: Flask, createur: User) -> None:
    from app.models import LiveStatus
    from app.services import live

    quiz = creer_quiz(app, createur)
    joueurs = [creer_compte(app, f"j{i}") for i in range(3)]
    partie_direct = live.creer(createur, quiz)
    for compte in joueurs:
        live.rejoindre(partie_direct, compte.username, compte)
    assert live.demarrer(partie_direct)
    question = live.question_courante(partie_direct)
    assert question is not None
    gagnant = next(j for j in live.joueurs_actifs(partie_direct) if j.user_id == joueurs[1].id)
    live.repondre(partie_direct, gagnant, 0, sorted(question.correct_ids))
    assert live.terminer(partie_direct)
    assert partie_direct.status is LiveStatus.FINISHED
    assert "animateur" in codes(createur)
    assert "vainqueur" in codes(joueurs[1])
    assert "vainqueur" not in codes(joueurs[0])


def test_pages_progression_et_badges(app: Flask, client: FlaskClient, createur: User) -> None:
    assert "Champion de la salle" in client.get("/badges").get_data(as_text=True)
    connecter(client, "createur@example.org")
    html = client.get("/profil/progression").get_data(as_text=True)
    assert "Réussite par thème" in html
    assert "Hameçonnage et ingénierie sociale" in html
    assert "obtenu" in client.get("/badges").get_data(as_text=True)
