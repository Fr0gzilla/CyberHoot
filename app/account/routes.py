"""Espace personnel : profil, pseudo, mot de passe, suppression du compte."""

from __future__ import annotations

from flask import Blueprint, abort, flash, redirect, render_template, session, url_for
from flask_login import current_user, login_required, login_user, logout_user
from werkzeug.wrappers import Response

from app.auth.forms import (
    ChangePasswordForm,
    CodeForm,
    ConfirmForm,
    DeleteAccountForm,
    UsernameForm,
)
from app.extensions import limiter
from app.models import RoleName
from app.services import accounts, audit, play, progression, rgpd, twofa

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


@bp.get("/progression")
@login_required
def progress() -> str:
    en_cours, meilleure = progression.series(current_user)
    return render_template(
        "account/progression.html",
        themes=progression.par_theme(current_user),
        parties=progression.parties_terminees(current_user),
        serie=en_cours,
        meilleure_serie=meilleure,
        badges=progression.badges_de(current_user),
        nb_badges=len(progression.tous_les_badges()),
    )


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
            audit.journaliser("mot_de_passe_change")
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
        if accounts.verifier_mot_de_passe(user, form.password.data):
            audit.journaliser("compte_supprime", user=user)
        if accounts.supprimer_compte(user, form.password.data):
            logout_user()
            session.clear()
            flash("Votre compte et vos données ont été supprimés.", "info")
            return redirect(url_for("main.index"))
        form.password.errors = ["Mot de passe incorrect."]
    return _page(formulaires, 422)


# --- Double authentification ---------------------------------------------------------------

# Nom de clé de session (pas un secret).
CLE_SECRET = "2fa_secret_en_attente"  # noqa: S105  # nosec B105


@bp.get("/double-authentification")
@login_required
def twofa_page() -> str:
    user = current_user._get_current_object()
    contexte: dict[str, object] = {"form": CodeForm(), "confirm": ConfirmForm()}
    if user.totp_enabled:
        contexte["restants"] = twofa.codes_restants(user)
    else:
        # Secret proposé, gardé dans la session (signée) jusqu'à la confirmation par un code.
        secret = session.get(CLE_SECRET) or twofa.nouveau_secret()
        session[CLE_SECRET] = secret
        contexte |= {"qr": twofa.qr(user, secret), "secret": secret}
    return render_template("account/twofa.html", **contexte)


def _afficher_codes(codes: list[str]) -> str:
    return render_template("account/twofa_codes.html", codes=codes)


@bp.post("/double-authentification/activer")
@login_required
@limiter.limit("10 per hour")
def twofa_enable() -> str | Response:
    form = CodeForm()
    secret = session.get(CLE_SECRET)
    if not form.validate_on_submit() or not secret:
        abort(400)
    codes = twofa.activer(current_user._get_current_object(), secret, form.code.data)
    if codes is None:
        flash("Code incorrect : vérifiez l'heure de votre téléphone et réessayez.", "error")
        return redirect(url_for("account.twofa_page"))
    session.pop(CLE_SECRET, None)
    audit.journaliser("2fa_activee")
    return _afficher_codes(codes)


@bp.post("/double-authentification/codes")
@login_required
@limiter.limit("10 per hour")
def twofa_codes() -> str | Response:
    form = CodeForm()
    user = current_user._get_current_object()
    if not form.validate_on_submit() or not user.totp_enabled:
        abort(400)
    if twofa.verifier(user, form.code.data) != "totp":
        flash("Code incorrect.", "error")
        return redirect(url_for("account.twofa_page"))
    audit.journaliser("2fa_codes_regeneres")
    return _afficher_codes(twofa.regenerer_codes(user))


@bp.post("/double-authentification/desactiver")
@login_required
@limiter.limit("10 per hour")
def twofa_disable() -> Response:
    form = CodeForm()
    user = current_user._get_current_object()
    if not form.validate_on_submit() or not user.totp_enabled:
        abort(400)
    if user.has_role(RoleName.ADMIN):
        flash("La double authentification est obligatoire pour les administrateurs.", "error")
        return redirect(url_for("account.twofa_page"))
    if twofa.verifier(user, form.code.data) is None:
        flash("Code incorrect.", "error")
        return redirect(url_for("account.twofa_page"))
    twofa.desactiver(user)
    audit.journaliser("2fa_desactivee")
    flash("Double authentification désactivée.", "info")
    return redirect(url_for("account.twofa_page"))


# --- Données personnelles ------------------------------------------------------------------


@bp.get("/mes-donnees.json")
@login_required
@limiter.limit("10 per hour")
def export() -> Response:
    """Droit d'accès et à la portabilité (RGPD, articles 15 et 20) : tout, en JSON."""
    user = current_user._get_current_object()
    audit.journaliser("donnees_exportees")
    reponse = Response(rgpd.export_json(user), mimetype="application/json")
    reponse.headers["Content-Disposition"] = 'attachment; filename="cyberhoot-mes-donnees.json"'
    return reponse
