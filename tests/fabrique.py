"""Fabrique de quiz pour les tests."""

from __future__ import annotations

from flask import Flask

from app.extensions import db
from app.models import Quiz, QuizStatus, User
from app.services import quizzes

CATEGORIE_HAMECONNAGE = 1


def brouillon(n: int = 3, titre: str = "Quiz de test") -> quizzes.Brouillon:
    """n questions ; la première a deux bonnes réponses (A et B), les autres une seule (A)."""
    questions = []
    for i in range(n):
        options = [
            quizzes.BrouillonOption(f"Réponse A{i}", True),
            quizzes.BrouillonOption(f"Réponse B{i}", i == 0),
            quizzes.BrouillonOption(f"Réponse C{i}", False),
        ]
        questions.append(
            quizzes.BrouillonQuestion(
                text=f"Question numéro {i + 1} ?",
                explanation=f"Explication détaillée numéro {i + 1}.",
                options=options,
            )
        )
    return quizzes.Brouillon(
        title=titre,
        description="Un quiz pour les tests.",
        category_id=CATEGORIE_HAMECONNAGE,
        difficulty="easy",
        questions=questions,
    )


def creer_quiz(
    app: Flask,
    auteur: User,
    statut: QuizStatus = QuizStatus.PUBLISHED,
    n: int = 3,
    titre: str = "Quiz de test",
) -> Quiz:
    with app.test_request_context():
        quiz = quizzes.enregistrer(None, brouillon(n, titre), auteur)
        if statut is not QuizStatus.DRAFT:
            if n >= quizzes.QUESTIONS_MIN_SOUMISSION:
                assert quizzes.soumettre(quiz) == {}
            else:  # quiz court des tests : soumis directement
                quiz.status = QuizStatus.PENDING
                db.session.commit()
        if statut is QuizStatus.PUBLISHED:
            assert quizzes.publier(quiz)
        if statut is QuizStatus.REJECTED:
            assert quizzes.refuser(quiz, "À revoir")
    return quiz


def formulaire(b: quizzes.Brouillon, action: str = "enregistrer") -> dict[str, str]:
    """Champs envoyés par l'éditeur pour ce brouillon."""
    champs = {
        "title": b.title,
        "description": b.description,
        "category": str(b.category_id or ""),
        "difficulty": b.difficulty,
        "action": action,
    }
    for i, q in enumerate(b.questions):
        champs[f"q-{i}-text"] = q.text
        champs[f"q-{i}-explanation"] = q.explanation
        champs[f"q-{i}-alt"] = q.media_alt
        if q.media_uid:
            champs[f"q-{i}-media"] = q.media_uid
        for j, o in enumerate(q.options):
            champs[f"q-{i}-o-{j}-text"] = o.text
            if o.correct:
                champs[f"q-{i}-o-{j}-correct"] = "1"
    return champs
