"""Administration : tableau de bord, quiz, comptes, catégories, badges, signalements, journal.

Toutes les pages exigent le rôle administrateur ET la double authentification activée.
Chaque action modifiant quelque chose est inscrite au journal d'audit.
"""

from __future__ import annotations

from datetime import timedelta

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user
from sqlalchemy import select
from werkzeug.wrappers import Response

from app.auth import role_required
from app.auth.forms import ConfirmForm
from app.extensions import db
from app.models import (
    Badge,
    Category,
    MediaStatus,
    Quiz,
    QuizStatus,
    Report,
    RoleName,
    User,
    utcnow,
)
from app.quiz.forms import RejectForm
from app.services import admin, audit, catalog, moderation, reports

bp = Blueprint("admin", __name__)


@bp.before_request
def exiger_double_authentification() -> Response | None:
    if (
        current_user.is_authenticated
        and current_user.has_role(RoleName.ADMIN)
        and not current_user.totp_enabled
    ):
        flash("Activez la double authentification pour accéder à l'administration.", "info")
        return redirect(url_for("account.twofa_page"))
    return None


def _formulaire_valide() -> None:
    if not ConfirmForm().validate_on_submit():
        abort(400)


def _objet(modele: type, identifiant: int):  # type: ignore[no-untyped-def]
    objet = db.session.get(modele, identifiant)
    if objet is None:
        abort(404)
    return objet


# --- Tableau de bord -----------------------------------------------------------------------


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
        stats=admin.statistiques(),
        signalements=reports.nombre_ouverts(),
    )


# --- Quiz ----------------------------------------------------------------------------------


@bp.get("/quiz/<int:quiz_id>")
@role_required(RoleName.ADMIN)
def review(quiz_id: int) -> str:
    quiz = _objet(Quiz, quiz_id)
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
    quiz = _objet(Quiz, quiz_id)
    _formulaire_valide()
    if moderation.publier(quiz):
        audit.journaliser("admin_quiz_publie", cible=f"quiz {quiz.id} « {quiz.title} »")
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
    quiz = _objet(Quiz, quiz_id)
    form = RejectForm()
    if not form.validate_on_submit():
        return render_template(
            "admin/review.html",
            quiz=quiz,
            form=ConfirmForm(),
            reject_form=form,
            images_en_attente=[],
        ), 422
    if moderation.refuser(quiz, form.reason.data):
        audit.journaliser(
            "admin_quiz_refuse", cible=f"quiz {quiz.id} « {quiz.title} »", motif=form.reason.data
        )
        flash(f"« {quiz.title} » est renvoyé à son créateur.", "info")
    else:
        flash("Ce quiz ne peut pas être refusé dans son état actuel.", "error")
    return redirect(url_for("admin.dashboard"))


# --- Comptes -------------------------------------------------------------------------------


@bp.get("/comptes")
@role_required(RoleName.ADMIN)
def users() -> str:
    page = admin.comptes(
        request.args.get("q", ""),
        request.args.get("role", ""),
        request.args.get("page", 1, type=int) or 1,
    )
    return render_template("admin/users.html", resultats=page, form=ConfirmForm())


@bp.post("/comptes/<int:user_id>/role")
@role_required(RoleName.ADMIN)
def user_role(user_id: int) -> Response:
    cible = _objet(User, user_id)
    _formulaire_valide()
    role = request.form.get("role", "")
    ajouter = request.form.get("operation") == "ajouter"
    refus = admin.changer_role(current_user._get_current_object(), cible, role, ajouter)
    if refus:
        flash(refus.value, "error")
    else:
        audit.journaliser(
            "admin_role",
            cible=f"compte {cible.id} ({cible.username})",
            role=role,
            operation="ajout" if ajouter else "retrait",
        )
        flash(f"Rôles de {cible.username} : {', '.join(cible.role_names)}.", "success")
    return redirect(request.referrer or url_for("admin.users"))


@bp.post("/comptes/<int:user_id>/activation")
@role_required(RoleName.ADMIN)
def user_activation(user_id: int) -> Response:
    cible = _objet(User, user_id)
    _formulaire_valide()
    actif = request.form.get("actif") == "1"
    refus = admin.changer_activation(current_user._get_current_object(), cible, actif)
    if refus:
        flash(refus.value, "error")
    else:
        audit.journaliser(
            "admin_compte_active" if actif else "admin_compte_desactive",
            cible=f"compte {cible.id} ({cible.username})",
        )
        flash(f"Compte {cible.username} {'réactivé' if actif else 'désactivé'}.", "success")
    return redirect(request.referrer or url_for("admin.users"))


# --- Catégories et badges ------------------------------------------------------------------


@bp.route("/categories", methods=["GET", "POST"])
@role_required(RoleName.ADMIN)
def categories() -> str | Response:
    if request.method == "POST":
        _formulaire_valide()
        categorie = _objet(Category, request.form.get("id", 0, type=int) or 0)
        nom = request.form.get("name", "").strip()
        description = request.form.get("description", "").strip()
        if not 2 <= len(nom) <= 80 or len(description) > 255:
            flash("Nom de 2 à 80 caractères, description de 255 au plus.", "error")
        else:
            categorie.name, categorie.description = nom, description
            db.session.commit()
            audit.journaliser("admin_categorie", cible=f"catégorie {categorie.slug}")
            flash(f"Catégorie « {nom} » enregistrée.", "success")
        return redirect(url_for("admin.categories"))
    return render_template(
        "admin/categories.html", categories=catalog.categories(), form=ConfirmForm()
    )


@bp.route("/badges", methods=["GET", "POST"])
@role_required(RoleName.ADMIN)
def badges() -> str | Response:
    if request.method == "POST":
        _formulaire_valide()
        badge = _objet(Badge, request.form.get("id", 0, type=int) or 0)
        nom = request.form.get("name", "").strip()
        description = request.form.get("description", "").strip()
        icone = request.form.get("icon", "").strip()
        seuil = request.form.get("threshold", 0, type=int) or 0
        if not (
            2 <= len(nom) <= 80
            and 5 <= len(description) <= 255
            and 1 <= len(icone) <= 8
            and 1 <= seuil <= 1000
        ):
            flash(
                "Badge refusé : nom, description, icône (1 à 8 caractères), seuil 1 à 1000.",
                "error",
            )
        else:
            badge.name, badge.description, badge.icon, badge.threshold = (
                nom,
                description,
                icone,
                seuil,
            )
            db.session.commit()
            audit.journaliser("admin_badge", cible=f"badge {badge.code}", seuil=seuil)
            flash(f"Badge « {nom} » enregistré.", "success")
        return redirect(url_for("admin.badges"))
    return render_template("admin/badges.html", badges=admin.badges(), form=ConfirmForm())


# --- Signalements --------------------------------------------------------------------------


@bp.get("/signalements")
@role_required(RoleName.ADMIN)
def reports_page() -> str:
    return render_template("admin/reports.html", signalements=reports.ouverts(), form=ConfirmForm())


@bp.post("/signalements/<int:report_id>")
@role_required(RoleName.ADMIN)
def report_action(report_id: int) -> Response:
    signalement: Report = _objet(Report, report_id)
    _formulaire_valide()
    action = request.form.get("action", "")
    moi = current_user._get_current_object()
    if action == "supprimer-avis" and signalement.review is not None:
        avis = signalement.review
        audit.journaliser("admin_avis_supprime", cible=f"avis {avis.id}", texte=avis.comment)
        reports.clore(signalement, moi, "avis supprimé")
        db.session.delete(avis)
        db.session.commit()
    elif action == "depublier" and signalement.quiz is not None:
        quiz = signalement.quiz
        if moderation.refuser(quiz, f"Dépublié après signalement : {signalement.reason}"):
            audit.journaliser("admin_quiz_refuse", cible=f"quiz {quiz.id} « {quiz.title} »")
        reports.clore(signalement, moi, "quiz dépublié")
    elif action == "clore":
        reports.clore(signalement, moi, "sans suite")
    else:
        abort(400)
    audit.journaliser("admin_signalement", cible=f"signalement {signalement.id}", decision=action)
    flash("Signalement traité.", "success")
    return redirect(url_for("admin.reports_page"))


# --- Journal d'audit -----------------------------------------------------------------------


@bp.get("/journal")
@role_required(RoleName.ADMIN)
def audit_log() -> str:
    jours = request.args.get("jours", 0, type=int) or 0
    page = audit.lister(
        action=request.args.get("action", ""),
        pseudo=request.args.get("pseudo", ""),
        depuis=utcnow() - timedelta(days=jours) if jours > 0 else None,
        page=request.args.get("page", 1, type=int) or 1,
    )
    return render_template("admin/audit.html", resultats=page, actions=audit.ACTIONS)
