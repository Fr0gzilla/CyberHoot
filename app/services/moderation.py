"""Décision d'un administrateur sur un quiz soumis : publication ou refus (avec motif).

Le créateur est prévenu par e-mail dans les deux cas ; une publication peut lui valoir un badge.
"""

from __future__ import annotations

from flask import current_app, url_for

from app.extensions import db
from app.models import Quiz, QuizStatus, utcnow
from app.services import mail, progression


def _prevenir_createur(quiz: Quiz, sujet: str, gabarit: str) -> None:
    if quiz.creator is None:
        return
    lien = f"{current_app.config['PUBLIC_URL']}{url_for('creator.dashboard')}"
    mail.envoyer(quiz.creator.email, sujet, gabarit, user=quiz.creator, quiz=quiz, lien=lien)


def publier(quiz: Quiz) -> bool:
    if quiz.status is not QuizStatus.PENDING:
        return False
    images_non_saines = [
        q.media for q in quiz.questions if q.media and q.media.status.value != "clean"
    ]
    if images_non_saines:
        return False
    quiz.status = QuizStatus.PUBLISHED
    quiz.published_at = utcnow()
    quiz.rejection_reason = None
    db.session.commit()
    _prevenir_createur(quiz, f"Votre quiz « {quiz.title} » est publié", "quiz_publie")
    if quiz.creator is not None:
        progression.attribuer(quiz.creator)
    return True


def refuser(quiz: Quiz, motif: str) -> bool:
    if quiz.status not in {QuizStatus.PENDING, QuizStatus.PUBLISHED}:
        return False
    quiz.status = QuizStatus.REJECTED
    quiz.rejection_reason = motif.strip()[:500]
    db.session.commit()
    _prevenir_createur(quiz, f"Votre quiz « {quiz.title} » doit être revu", "quiz_refuse")
    return True
