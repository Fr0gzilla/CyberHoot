"""Création, édition, soumission et validation des quiz.

Un seul service lit et enregistre un quiz, que l'auteur soit le créateur ou un
administrateur (l'ancienne version répétait trois fois ce code).

L'éditeur fonctionne sans JavaScript : les boutons « ajouter une question », « retirer
cette réponse »… renvoient le formulaire, que le serveur relit (`lire_formulaire`), modifie
(`appliquer_action`) et réaffiche. Seul « Enregistrer » écrit en base.

Cycle de vie : brouillon → en attente (soumis) → publié ou refusé (motif obligatoire).
Un quiz publié modifié par son créateur repasse en attente.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

from flask import current_app, url_for
from sqlalchemy import delete, select
from werkzeug.datastructures import FileStorage, ImmutableMultiDict, MultiDict

from app.extensions import db
from app.models import (
    AnswerOption,
    Category,
    Difficulty,
    Media,
    PlaySession,
    Question,
    Quiz,
    QuizStatus,
    User,
    utcnow,
)
from app.services import mail
from app.services import media as medias

journal = logging.getLogger(__name__)

QUESTIONS_MAX = 50
QUESTIONS_MIN_SOUMISSION = 3
OPTIONS_MIN = 2
OPTIONS_MAX = 6
CLE_QUESTION = re.compile(r"^q-(\d{1,2})-text$")
CLE_OPTION = re.compile(r"^q-(\d{1,2})-o-(\d{1,2})-text$")


@dataclass
class BrouillonOption:
    text: str = ""
    correct: bool = False


@dataclass
class BrouillonQuestion:
    text: str = ""
    explanation: str = ""
    media_uid: str = ""
    media_alt: str = ""
    options: list[BrouillonOption] = field(
        default_factory=lambda: [BrouillonOption(), BrouillonOption()]
    )


@dataclass
class Brouillon:
    """Contenu d'un quiz tel qu'édité, avant enregistrement."""

    title: str = ""
    description: str = ""
    category_id: int | None = None
    difficulty: str = Difficulty.EASY.value
    questions: list[BrouillonQuestion] = field(default_factory=lambda: [BrouillonQuestion()])


Erreurs = dict[str, list[str]]


# --- Lecture et modification du formulaire ------------------------------------------------


def _texte(form: MultiDict[str, str], cle: str, longueur: int) -> str:
    return (form.get(cle) or "").strip()[: longueur + 1]


def lire_formulaire(form: MultiDict[str, str]) -> Brouillon:
    """Reconstruit le brouillon depuis les champs envoyés (sans rien écrire en base)."""
    try:
        categorie: int | None = int(form.get("category", ""))
    except ValueError:
        categorie = None
    brouillon = Brouillon(
        title=_texte(form, "title", 120),
        description=_texte(form, "description", 500),
        category_id=categorie,
        difficulty=form.get("difficulty", Difficulty.EASY.value),
        questions=[],
    )
    indices_q = sorted({int(m.group(1)) for cle in form if (m := CLE_QUESTION.match(cle))})
    for i in indices_q[:QUESTIONS_MAX]:
        indices_o = sorted(
            {
                int(m.group(2))
                for cle in form
                if (m := CLE_OPTION.match(cle)) and int(m.group(1)) == i
            }
        )
        brouillon.questions.append(
            BrouillonQuestion(
                text=_texte(form, f"q-{i}-text", 500),
                explanation=_texte(form, f"q-{i}-explanation", 2000),
                media_uid=(form.get(f"q-{i}-media") or "").strip()[:32],
                media_alt=_texte(form, f"q-{i}-alt", 200),
                options=[
                    BrouillonOption(
                        text=_texte(form, f"q-{i}-o-{j}-text", 300),
                        correct=form.get(f"q-{i}-o-{j}-correct") == "1",
                    )
                    for j in indices_o[:OPTIONS_MAX]
                ],
            )
        )
    return brouillon


def appliquer_action(brouillon: Brouillon, action: str) -> None:
    """Applique un bouton de l'éditeur (ajout, retrait, déplacement) au brouillon."""
    nom, _, cible = action.partition(":")
    parties = [int(p) for p in cible.split(":") if p.isdigit()]
    questions = brouillon.questions
    if nom == "ajouter-question" and len(questions) < QUESTIONS_MAX:
        questions.append(BrouillonQuestion())
        return
    if not parties or parties[0] >= len(questions):
        return
    i = parties[0]
    question = questions[i]
    if nom == "retirer-question" and len(questions) > 1:
        questions.pop(i)
    elif nom == "monter-question" and i > 0:
        questions[i - 1], questions[i] = questions[i], questions[i - 1]
    elif nom == "descendre-question" and i < len(questions) - 1:
        questions[i + 1], questions[i] = questions[i], questions[i + 1]
    elif nom == "ajouter-reponse" and len(question.options) < OPTIONS_MAX:
        question.options.append(BrouillonOption())
    elif nom == "retirer-reponse" and len(parties) == 2 and len(question.options) > OPTIONS_MIN:
        if parties[1] < len(question.options):
            question.options.pop(parties[1])
    elif nom == "retirer-image":
        question.media_uid = ""
        question.media_alt = ""


def brouillon_depuis(quiz: Quiz) -> Brouillon:
    return Brouillon(
        title=quiz.title,
        description=quiz.description,
        category_id=quiz.category_id,
        difficulty=quiz.difficulty.value,
        questions=[
            BrouillonQuestion(
                text=q.text,
                explanation=q.explanation,
                media_uid=q.media.uid if q.media else "",
                media_alt=q.media_alt or "",
                options=[BrouillonOption(o.text, o.is_correct) for o in q.options],
            )
            for q in quiz.questions
        ],
    )


# --- Images --------------------------------------------------------------------------------


def medias_autorises(auteur: User, quiz: Quiz | None) -> set[str]:
    """Images qu'un brouillon a le droit de référencer : celles de l'auteur et du quiz édité."""
    uids = set(db.session.scalars(select(Media.uid).where(Media.owner_id == auteur.id)))
    if quiz is not None:
        uids |= {q.media.uid for q in quiz.questions if q.media}
    return uids


def recevoir_images(
    brouillon: Brouillon, fichiers: ImmutableMultiDict[str, FileStorage], auteur: User
) -> Erreurs:
    """Enregistre les images envoyées et les rattache aux questions du brouillon."""
    erreurs: Erreurs = {}
    for i, question in enumerate(brouillon.questions):
        fichier = fichiers.get(f"q-{i}-image")
        if fichier is None or not fichier.filename:
            continue
        try:
            question.media_uid = medias.enregistrer(fichier, auteur).uid
        except medias.MediaInvalideError as erreur:
            erreurs[f"q-{i}-image"] = [str(erreur)]
    return erreurs


# --- Validation -----------------------------------------------------------------------------


def valider(brouillon: Brouillon, medias_permis: set[str], soumission: bool = False) -> Erreurs:
    erreurs: Erreurs = {}

    def ajouter(cle: str, message: str) -> None:
        erreurs.setdefault(cle, []).append(message)

    if not 3 <= len(brouillon.title) <= 120:
        ajouter("title", "Le titre doit faire entre 3 et 120 caractères.")
    if len(brouillon.description) > 500:
        ajouter("description", "La description ne doit pas dépasser 500 caractères.")
    if brouillon.category_id is None or db.session.get(Category, brouillon.category_id) is None:
        ajouter("category", "Choisissez une catégorie.")
    if brouillon.difficulty not in {d.value for d in Difficulty}:
        ajouter("difficulty", "Choisissez un niveau.")
    if not brouillon.questions:
        ajouter("questions", "Ajoutez au moins une question.")
    if soumission and len(brouillon.questions) < QUESTIONS_MIN_SOUMISSION:
        ajouter(
            "questions",
            f"Un quiz soumis à validation compte au moins {QUESTIONS_MIN_SOUMISSION} questions.",
        )

    for i, question in enumerate(brouillon.questions):
        if not 5 <= len(question.text) <= 500:
            ajouter(f"q-{i}-text", "L'intitulé doit faire entre 5 et 500 caractères.")
        if not 10 <= len(question.explanation) <= 2000:
            ajouter(f"q-{i}-explanation", "L'explication doit faire entre 10 et 2000 caractères.")
        if question.media_uid:
            if question.media_uid not in medias_permis:
                ajouter(f"q-{i}-image", "Image inconnue.")
            if not 3 <= len(question.media_alt) <= 200:
                ajouter(f"q-{i}-alt", "Décrivez l'image en 3 à 200 caractères (accessibilité).")
        if not OPTIONS_MIN <= len(question.options) <= OPTIONS_MAX:
            ajouter(f"q-{i}-options", f"Entre {OPTIONS_MIN} et {OPTIONS_MAX} réponses.")
        for j, option in enumerate(question.options):
            if not 1 <= len(option.text) <= 300:
                ajouter(f"q-{i}-o-{j}-text", "Réponse vide ou trop longue (300 caractères).")
        textes = [o.text.lower() for o in question.options if o.text]
        if len(set(textes)) != len(textes):
            ajouter(f"q-{i}-options", "Deux réponses sont identiques.")
        if not any(o.correct for o in question.options):
            ajouter(f"q-{i}-options", "Cochez au moins une bonne réponse.")
    return erreurs


# --- Enregistrement ------------------------------------------------------------------------


def _remplacer_questions(quiz: Quiz, brouillon: Brouillon) -> None:
    # Les parties en cours suivent l'ancienne version : on les arrête.
    db.session.execute(
        delete(PlaySession).where(PlaySession.quiz_id == quiz.id, PlaySession.finished_at.is_(None))
    )
    quiz.questions.clear()
    db.session.flush()
    uids = [q.media_uid for q in brouillon.questions if q.media_uid]
    par_uid = {m.uid: m for m in db.session.scalars(select(Media).where(Media.uid.in_(uids)))}
    for position, bq in enumerate(brouillon.questions):
        quiz.questions.append(
            Question(
                position=position,
                text=bq.text,
                explanation=bq.explanation,
                media=par_uid.get(bq.media_uid),
                media_alt=bq.media_alt or None,
                options=[
                    AnswerOption(position=j, text=o.text, is_correct=o.correct)
                    for j, o in enumerate(bq.options)
                ],
            )
        )


def enregistrer(quiz: Quiz | None, brouillon: Brouillon, auteur: User) -> Quiz:
    """Crée ou met à jour un quiz validé au préalable (`valider`)."""
    if quiz is None:
        quiz = Quiz(creator_id=auteur.id, status=QuizStatus.DRAFT)
        db.session.add(quiz)
    quiz.title = brouillon.title
    quiz.description = brouillon.description
    quiz.category_id = brouillon.category_id or 0
    quiz.difficulty = Difficulty(brouillon.difficulty)
    db.session.flush()
    _remplacer_questions(quiz, brouillon)

    est_createur = quiz.creator_id == auteur.id
    if est_createur and quiz.status is QuizStatus.PUBLISHED:
        # Le contenu publié a changé : il doit être revalidé avant de réapparaître.
        quiz.status = QuizStatus.PENDING
        quiz.submitted_at = utcnow()
    elif est_createur and quiz.status is QuizStatus.REJECTED:
        quiz.status = QuizStatus.DRAFT
    db.session.commit()
    journal.info("quiz %s enregistré par le compte %s", quiz.id, auteur.id)
    return quiz


def soumettre(quiz: Quiz) -> Erreurs:
    erreurs = valider(brouillon_depuis(quiz), medias_autorises_quiz(quiz), soumission=True)
    if erreurs:
        return erreurs
    if quiz.status in {QuizStatus.DRAFT, QuizStatus.REJECTED}:
        quiz.status = QuizStatus.PENDING
        quiz.submitted_at = utcnow()
        quiz.rejection_reason = None
        db.session.commit()
    return {}


def medias_autorises_quiz(quiz: Quiz) -> set[str]:
    return {q.media.uid for q in quiz.questions if q.media}


def supprimer(quiz: Quiz) -> None:
    images = [q.media for q in quiz.questions if q.media]
    db.session.delete(quiz)
    db.session.commit()
    for image in images:
        encore_utilisee = db.session.scalar(
            select(Question.id).where(Question.media_id == image.id)
        )
        if encore_utilisee is None:
            medias.supprimer_fichier(image)
            db.session.delete(image)
    db.session.commit()


# --- Validation par un administrateur -------------------------------------------------------


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
    return True


def refuser(quiz: Quiz, motif: str) -> bool:
    if quiz.status not in {QuizStatus.PENDING, QuizStatus.PUBLISHED}:
        return False
    quiz.status = QuizStatus.REJECTED
    quiz.rejection_reason = motif.strip()[:500]
    db.session.commit()
    _prevenir_createur(quiz, f"Votre quiz « {quiz.title} » doit être revu", "quiz_refuse")
    return True


def categories() -> list[Category]:
    return list(db.session.scalars(select(Category).order_by(Category.position)))
