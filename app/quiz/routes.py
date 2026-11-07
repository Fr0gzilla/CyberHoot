"""Catalogue, page d'un quiz, parties en solo, avis et images."""

from __future__ import annotations

from flask import (
    Blueprint,
    abort,
    flash,
    redirect,
    render_template,
    request,
    send_file,
    url_for,
)
from flask_login import current_user, login_required
from werkzeug.wrappers import Response

from app.auth.forms import ConfirmForm
from app.extensions import db, limiter
from app.models import Media, MediaStatus, Question, Quiz, RoleName
from app.quiz.forms import ReviewForm
from app.services import catalog, play, progression, quizzes
from app.services import correction as correcteur
from app.services import media as medias

bp = Blueprint("quiz", __name__)


def peut_voir(quiz: Quiz) -> bool:
    """Publié : tout le monde. Sinon : son créateur et les administrateurs seulement."""
    if quiz.is_published:
        return True
    if not current_user.is_authenticated:
        return False
    return bool(quiz.creator_id == current_user.id or current_user.has_role(RoleName.ADMIN))


def quiz_visible(quiz_id: int) -> Quiz:
    quiz = db.session.get(Quiz, quiz_id)
    # 404 aussi quand l'accès est refusé : on ne confirme pas l'existence d'un brouillon.
    if quiz is None or not peut_voir(quiz):
        abort(404)
    return quiz


@bp.get("/quiz")
def catalog_page() -> str:
    page = catalog.rechercher(
        texte=request.args.get("q", ""),
        categorie=request.args.get("categorie", type=int),
        niveau=request.args.get("niveau", ""),
        page=request.args.get("page", 1, type=int) or 1,
    )
    return render_template("quiz/catalog.html", resultats=page, categories=quizzes.categories())


@bp.get("/quiz/<int:quiz_id>")
def detail(quiz_id: int) -> str:
    quiz = quiz_visible(quiz_id)
    formulaire_avis = None
    if current_user.is_authenticated and play.a_termine(current_user, quiz):
        existant = catalog.avis_de(current_user, quiz)
        formulaire_avis = ReviewForm(obj=existant) if existant else ReviewForm()
    return render_template(
        "quiz/detail.html",
        quiz=quiz,
        note=catalog.notes([quiz.id])[quiz.id],
        avis=catalog.avis(quiz),
        formulaire_avis=formulaire_avis,
        jouable=play.jouable(quiz),
        form=ConfirmForm(),
    )


@bp.post("/quiz/<int:quiz_id>/jouer")
@login_required
def start(quiz_id: int) -> Response:
    quiz = quiz_visible(quiz_id)
    if not ConfirmForm().validate_on_submit():
        abort(400)
    if not play.jouable(quiz):
        flash("Ce quiz n'est pas encore jouable.", "error")
        return redirect(url_for("quiz.detail", quiz_id=quiz.id))
    partie = play.demarrer(current_user, quiz)
    return redirect(url_for("quiz.play_page", token=partie.token))


@bp.post("/quiz/<int:quiz_id>/avis")
@login_required
@limiter.limit("20 per hour")
def review(quiz_id: int) -> Response:
    quiz = quiz_visible(quiz_id)
    form = ReviewForm()
    if form.validate_on_submit() and catalog.donner_avis(
        current_user, quiz, form.rating.data, form.comment.data or ""
    ):
        flash("Merci pour votre avis !", "success")
    else:
        flash(
            "Avis refusé : terminez d'abord une partie, et choisissez une note de 1 à 5.", "error"
        )
    return redirect(url_for("quiz.detail", quiz_id=quiz.id) + "#avis")


@bp.route("/partie/<token>", methods=["GET", "POST"])
@login_required
def play_page(token: str) -> str | Response:
    partie = play.trouver(token, current_user)
    if partie is None:
        abort(404)
    if partie.finished:
        return redirect(url_for("quiz.result", token=token))
    question = play.question_courante(partie)
    if question is None:
        abort(404)
    form = ConfirmForm()
    erreur = None
    if request.method == "POST":
        if not form.validate_on_submit():
            abort(400)
        choix = correcteur.lire(question, request.form)
        corrigee = play.repondre(partie, request.form.get("question", type=int) or 0, choix)
        if corrigee.reponse is not None:
            if partie.finished:
                for badge in progression.attribuer(current_user):
                    flash(f"Nouveau badge : {badge.icon} {badge.name} !", "success")
            return redirect(
                url_for("quiz.correction", token=token, position=corrigee.reponse.position)
            )
        erreur = corrigee.refus.value if corrigee.refus else None
        question = play.question_courante(partie)
        if question is None:
            return redirect(url_for("quiz.result", token=token))
    return render_template(
        "quiz/play.html",
        partie=partie,
        question=question,
        options=correcteur.ordre_affiche(question, partie.token),
        form=form,
        erreur=erreur,
    )


@bp.get("/partie/<token>/correction/<int:position>")
@login_required
def correction(token: str, position: int) -> str:
    partie = play.trouver(token, current_user)
    reponse = play.reponse_a(partie, position) if partie else None
    if partie is None or reponse is None:
        abort(404)
    return render_template(
        "quiz/correction.html",
        partie=partie,
        reponse=reponse,
        question=reponse.question,
    )


@bp.get("/partie/<token>/resultat")
@login_required
def result(token: str) -> str | Response:
    partie = play.trouver(token, current_user)
    if partie is None:
        abort(404)
    if not partie.finished:
        return redirect(url_for("quiz.play_page", token=token))
    return render_template("quiz/result.html", partie=partie)


@bp.get("/media/<uid>")
def media_file(uid: str) -> Response:
    """Sert une image saine, si la question qui l'utilise est visible par le visiteur."""
    media = db.session.scalar(db.select(Media).where(Media.uid == uid[:32]))
    if media is None:
        abort(404)
    if media.status is MediaStatus.REJECTED:
        abort(404)
    proprietaire = current_user.is_authenticated and media.owner_id == current_user.id
    admin = current_user.is_authenticated and current_user.has_role(RoleName.ADMIN)
    # Avant analyse, seuls l'auteur et les administrateurs (pour la validation) la voient.
    if not (proprietaire or admin):
        if media.status is not MediaStatus.CLEAN:
            abort(404)
        questions = db.session.scalars(db.select(Question).where(Question.media_id == media.id))
        if not any(peut_voir(q.quiz) for q in questions):
            abort(404)
    chemin = medias.chemin(media)
    if not chemin.is_file():
        abort(404)
    reponse = send_file(chemin, mimetype=media.mime_type, max_age=3600, conditional=True)
    reponse.headers["Content-Disposition"] = "inline"
    return reponse


@bp.get("/badges")
def badges_page() -> str:
    possedes: set[int] = set()
    if current_user.is_authenticated:
        possedes = {ub.badge_id for ub in progression.badges_de(current_user)}
    return render_template(
        "quiz/badges.html", badges=progression.tous_les_badges(), possedes=possedes
    )
