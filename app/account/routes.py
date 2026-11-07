"""Espace personnel : profil, pseudo, mot de passe, suppression du compte."""

from __future__ import annotations

from flask import Blueprint, flash, redirect, render_template, session, url_for
from flask_login import current_user, login_required, login_user, logout_user
from werkzeug.wrappers import Response

from app.auth.forms import ChangePasswordForm, DeleteAccountForm, UsernameForm
from app.extensions import limiter
from app.services import accounts, play

bp = Blueprint("account", __name__)


def _formulaires() -> tuple[UsernameForm, ChangePasswordForm, DeleteAccountForm]:
    return (
        UsernameForm(prefix="pseudo"),
        ChangePasswordForm(
            prefix="mdp", user_username=current_user.username, user_email=current_user.email
        ),
        DeleteAccountForm(prefix="suppr"),
    )


def _page(
    formulaires: tuple[UsernameForm, ChangePasswordForm, DeleteAccountForm], statut: int = 200
) -> tuple[str, int]:
    pseudo, mdp, suppr = formulaires
    page = render_template(
        "account/profile.html",
        username_form=pseudo,
        password_form=mdp,
        delete_form=suppr,
        parties=play.historique(current_user),
    )
    return page, statut


@bp.get("/")
@login_required
def profile() -> tuple[str, int]:
    return _page(_formulaires())


@bp.post("/pseudo")
@login_required
def change_username() -> tuple[str, int] | Response:
    formulaires = _formulaires()
    form = formulaires[0]
    if form.validate_on_submit():
        accounts.changer_pseudo(current_user, form.username.data)
        flash("Pseudo modifié.", "success")
        return redirect(url_for("account.profile"))
    return _page(formulaires, 422)


@bp.post("/mot-de-passe")
@login_required
@limiter.limit("10 per hour")
def change_password() -> tuple[str, int] | Response:
    formulaires = _formulaires()
    form = formulaires[1]
    if form.validate_on_submit():
        if accounts.changer_mot_de_passe(
            current_user, form.current_password.data, form.password.data
        ):
            # Le jeton de session a changé : on rouvre une session neuve pour cet appareil.
            user = current_user._get_current_object()
            session.clear()
            login_user(user)
            flash("Mot de passe modifié. Vos autres sessions ont été déconnectées.", "success")
            return redirect(url_for("account.profile"))
        form.current_password.errors = ["Mot de passe actuel incorrect."]
    return _page(formulaires, 422)


@bp.post("/suppression")
@login_required
@limiter.limit("10 per hour")
def delete_account() -> tuple[str, int] | Response:
    formulaires = _formulaires()
    form = formulaires[2]
    if form.validate_on_submit():
        user = current_user._get_current_object()
        if accounts.supprimer_compte(user, form.password.data):
            logout_user()
            session.clear()
            flash("Votre compte et vos données ont été supprimés.", "info")
            return redirect(url_for("main.index"))
        form.password.errors = ["Mot de passe incorrect."]
    return _page(formulaires, 422)
