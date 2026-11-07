"""Administration (v1.1) : relecture et validation des quiz."""

from __future__ import annotations

from flask import Blueprint, abort, flash, redirect, render_template, url_for
from sqlalchemy import select
from werkzeug.wrappers import Response

from app.auth import role_required
from app.auth.forms import ConfirmForm
from app.extensions import db
from app.models import MediaStatus, Quiz, QuizStatus, RoleName
from app.quiz.forms import RejectForm
from app.services import quizzes

bp = Blueprint("admin", __name__)


@bp.get("/")
@role_required(RoleName.ADMIN)
def dashboard() -> str:
    def par_statut(statut: QuizStatus) -> list[Quiz]:
        return list(
            db.session.scalars(
                select(Quiz).where(Quiz.status == statut).order_by(Quiz.updated_at.desc())
            )
        )

    return render_template(
        "admin/dashboard.html",
        en_attente=par_statut(QuizStatus.PENDING),
        publies=par_statut(QuizStatus.PUBLISHED),
    )


def _quiz(quiz_id: int) -> Quiz:
    quiz = db.session.get(Quiz, quiz_id)
    if quiz is None:
        abort(404)
    return quiz


@bp.get("/quiz/<int:quiz_id>")
@role_required(RoleName.ADMIN)
def review(quiz_id: int) -> str:
    quiz = _quiz(quiz_id)
    images_en_attente = [
        q for q in quiz.questions if q.media and q.media.status is not MediaStatus.CLEAN
    ]
    return render_template(
        "admin/review.html",
        quiz=quiz,
        form=ConfirmForm(),
        reject_form=RejectForm(),
        images_en_attente=images_en_attente,
    )


@bp.post("/quiz/<int:quiz_id>/publier")
@role_required(RoleName.ADMIN)
def publish(quiz_id: int) -> Response:
    quiz = _quiz(quiz_id)
    if not ConfirmForm().validate_on_submit():
        abort(400)
    if quizzes.publier(quiz):
        flash(f"« {quiz.title} » est publié.", "success")
    else:
        flash(
            "Publication impossible : le quiz doit être en attente et ses images analysées.",
            "error",
        )
    return redirect(url_for("admin.dashboard"))


@bp.post("/quiz/<int:quiz_id>/refuser")
@role_required(RoleName.ADMIN)
def reject(quiz_id: int) -> Response | str | tuple[str, int]:
    quiz = _quiz(quiz_id)
    form = RejectForm()
    if not form.validate_on_submit():
        return render_template(
            "admin/review.html",
            quiz=quiz,
            form=ConfirmForm(),
            reject_form=form,
            images_en_attente=[],
        ), 422
    if quizzes.refuser(quiz, form.reason.data):
        flash(f"« {quiz.title} » est renvoyé à son créateur.", "info")
    else:
        flash("Ce quiz ne peut pas être refusé dans son état actuel.", "error")
    return redirect(url_for("admin.dashboard"))
