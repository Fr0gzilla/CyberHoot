"""Espace créateur : ses quiz, l'éditeur, la soumission, les statistiques.

Un administrateur peut aussi ouvrir l'éditeur d'un quiz qui n'est pas le sien (corrections
avant validation) ; un créateur ne voit et ne modifie que ses propres quiz.
"""

from __future__ import annotations

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user
from sqlalchemy import select
from werkzeug.wrappers import Response

from app.auth import role_required
from app.auth.forms import ConfirmForm
from app.extensions import db, limiter
from app.models import DIFFICULTE_LIBELLES, Quiz, QuizStatus, RoleName
from app.services import catalog, quizzes

bp = Blueprint("creator", __name__)


def quiz_modifiable(quiz_id: int) -> Quiz:
    quiz = db.session.get(Quiz, quiz_id)
    if quiz is None:
        abort(404)
    if quiz.creator_id != current_user.id and not current_user.has_role(RoleName.ADMIN):
        abort(404)
    return quiz


@bp.get("/")
@role_required(RoleName.CREATOR, RoleName.ADMIN)
def dashboard() -> str:
    mes_quiz = list(
        db.session.scalars(
            select(Quiz).where(Quiz.creator_id == current_user.id).order_by(Quiz.updated_at.desc())
        )
    )
    return render_template(
        "creator/dashboard.html",
        mes_quiz=mes_quiz,
        notes=catalog.notes([q.id for q in mes_quiz]),
        form=ConfirmForm(),
    )


def _editeur(quiz: Quiz | None) -> str | Response | tuple[str, int]:
    """GET : affiche l'éditeur. POST : applique un bouton, ou enregistre (et soumet)."""
    form = ConfirmForm()
    if request.method == "GET":
        brouillon = quizzes.brouillon_depuis(quiz) if quiz else quizzes.Brouillon()
        return _rendu(quiz, brouillon, {}, form)

    if not form.validate_on_submit():
        abort(400)
    brouillon = quizzes.lire_formulaire(request.form)
    erreurs = quizzes.recevoir_images(brouillon, request.files, current_user)
    action = request.form.get("action", "")
    if action not in {"enregistrer", "soumettre"}:
        db.session.commit()  # garde les images reçues entre deux allers-retours
        quizzes.appliquer_action(brouillon, action)
        return _rendu(quiz, brouillon, erreurs, form)

    permis = quizzes.medias_autorises(current_user, quiz)
    erreurs |= quizzes.valider(brouillon, permis, soumission=action == "soumettre")
    if erreurs:
        db.session.commit()
        flash("Le quiz n'a pas été enregistré : corrigez les champs signalés.", "error")
        return _rendu(quiz, brouillon, erreurs, form), 422
    quiz = quizzes.enregistrer(quiz, brouillon, current_user)
    if action == "soumettre" and quiz.creator_id == current_user.id:
        quizzes.soumettre(quiz)
        flash("Quiz envoyé en validation : un administrateur va le relire.", "success")
    else:
        flash(
            "Quiz enregistré."
            + (" Il repasse en validation." if quiz.status is QuizStatus.PENDING else ""),
            "success",
        )
    return redirect(url_for("creator.edit", quiz_id=quiz.id))


def _rendu(
    quiz: Quiz | None, brouillon: quizzes.Brouillon, erreurs: quizzes.Erreurs, form: ConfirmForm
) -> str:
    return render_template(
        "creator/editor.html",
        quiz=quiz,
        b=brouillon,
        erreurs=erreurs,
        form=form,
        categories=quizzes.categories(),
        niveaux=DIFFICULTE_LIBELLES,
        limites={
            "questions": quizzes.QUESTIONS_MAX,
            "options_min": quizzes.OPTIONS_MIN,
            "options_max": quizzes.OPTIONS_MAX,
        },
    )


@bp.route("/quiz/nouveau", methods=["GET", "POST"])
@role_required(RoleName.CREATOR, RoleName.ADMIN)
@limiter.limit("120 per hour", methods=["POST"])
def new() -> str | Response | tuple[str, int]:
    return _editeur(None)


@bp.route("/quiz/<int:quiz_id>/modifier", methods=["GET", "POST"])
@role_required(RoleName.CREATOR, RoleName.ADMIN)
@limiter.limit("120 per hour", methods=["POST"])
def edit(quiz_id: int) -> str | Response | tuple[str, int]:
    return _editeur(quiz_modifiable(quiz_id))


@bp.post("/quiz/<int:quiz_id>/soumettre")
@role_required(RoleName.CREATOR, RoleName.ADMIN)
def submit(quiz_id: int) -> Response:
    quiz = quiz_modifiable(quiz_id)
    if not ConfirmForm().validate_on_submit():
        abort(400)
    erreurs = quizzes.soumettre(quiz)
    if erreurs:
        messages = sorted({m for liste in erreurs.values() for m in liste})
        flash("Impossible de soumettre : " + " ".join(messages), "error")
    else:
        flash("Quiz envoyé en validation.", "success")
    return redirect(url_for("creator.dashboard"))


@bp.post("/quiz/<int:quiz_id>/supprimer")
@role_required(RoleName.CREATOR, RoleName.ADMIN)
def delete(quiz_id: int) -> Response:
    quiz = quiz_modifiable(quiz_id)
    if not ConfirmForm().validate_on_submit():
        abort(400)
    titre = quiz.title
    quizzes.supprimer(quiz)
    flash(f"Quiz « {titre} » supprimé.", "info")
    return redirect(url_for("creator.dashboard"))


@bp.get("/quiz/<int:quiz_id>/statistiques")
@role_required(RoleName.CREATOR, RoleName.ADMIN)
def stats(quiz_id: int) -> str:
    quiz = quiz_modifiable(quiz_id)
    return render_template("creator/stats.html", quiz=quiz, stats=catalog.statistiques(quiz))
