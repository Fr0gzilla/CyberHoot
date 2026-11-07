"""Routes des comptes : inscription, activation, connexion, mot de passe oublié."""

from __future__ import annotations

from urllib.parse import urlsplit

from flask import Blueprint, abort, flash, redirect, render_template, request, session, url_for
from flask_login import current_user, login_required, login_user, logout_user
from werkzeug.wrappers import Response

from app.auth.forms import ConfirmForm, EmailForm, LoginForm, RegisterForm, ResetPasswordForm
from app.extensions import limiter
from app.services import accounts
from app.services.accounts import Echec

bp = Blueprint("auth", __name__)

# Limites par adresse IP : assez larges pour une classe entière derrière une même adresse
# (réseau d'établissement), assez basses pour freiner l'automatisation. Le verrouillage par
# compte (5 échecs) reste la protection principale contre le forçage d'un mot de passe.

MESSAGE_INSCRIPTION = (
    "Si cette adresse peut être utilisée, un e-mail vient d'y être envoyé : "
    "suivez le lien qu'il contient pour activer votre compte."
)
MESSAGE_OUBLI = (
    "Si un compte est associé à cette adresse, un lien de réinitialisation vient d'y être "
    "envoyé. Il est valable 30 minutes et ne sert qu'une fois."
)
MESSAGES_ECHEC = {
    Echec.IDENTIFIANTS: "Adresse e-mail ou mot de passe incorrect.",
    Echec.VERROUILLE: (
        "Trop de tentatives : ce compte est temporairement bloqué. Réessayez dans quelques "
        "minutes, ou réinitialisez votre mot de passe."
    ),
    Echec.NON_ACTIVE: (
        "Votre compte n'est pas encore activé : un nouveau lien d'activation vient de vous "
        "être envoyé."
    ),
    Echec.DESACTIVE: "Ce compte a été désactivé. Contactez un administrateur.",
}


def _destination_sure(cible: str | None) -> str:
    """N'accepte qu'un chemin local (pas de redirection vers un autre site)."""
    if cible:
        morceaux = urlsplit(cible)
        if (
            not morceaux.scheme
            and not morceaux.netloc
            and cible.startswith("/")
            and not cible.startswith("//")
            and "\\" not in cible
        ):
            return cible
    return url_for("account.profile")


@bp.route("/inscription", methods=["GET", "POST"])
@limiter.limit("30 per hour", methods=["POST"])
def register() -> str | Response:
    if current_user.is_authenticated:
        return redirect(url_for("account.profile"))
    form = RegisterForm()
    if form.validate_on_submit():
        accounts.inscrire(form.username.data, form.email.data, form.password.data)
        flash(MESSAGE_INSCRIPTION, "info")
        return redirect(url_for("auth.login"))
    return render_template("auth/register.html", form=form)


@bp.get("/activation/<token>")
@limiter.limit("60 per hour")
def activate(token: str) -> Response:
    if accounts.activer(token) is None:
        flash("Ce lien d'activation est invalide ou a expiré.", "error")
        return redirect(url_for("auth.resend_activation"))
    flash("Votre compte est activé : vous pouvez vous connecter.", "success")
    return redirect(url_for("auth.login"))


@bp.route("/activation", methods=["GET", "POST"])
@limiter.limit("20 per hour", methods=["POST"])
def resend_activation() -> str | Response:
    form = EmailForm()
    if form.validate_on_submit():
        accounts.renvoyer_activation(form.email.data)
        flash(
            "Si un compte non activé est associé à cette adresse, un nouveau lien vient d'y être "
            "envoyé.",
            "info",
        )
        return redirect(url_for("auth.login"))
    return render_template("auth/resend_activation.html", form=form)


@bp.route("/connexion", methods=["GET", "POST"])
@limiter.limit("30 per minute;300 per hour", methods=["POST"])
def login() -> str | Response:
    if current_user.is_authenticated:
        return redirect(url_for("account.profile"))
    form = LoginForm()
    if form.validate_on_submit():
        resultat = accounts.authentifier(form.email.data, form.password.data)
        if resultat.user is not None:
            # Nouvelle session : rien de l'ancienne n'est conservé (fixation de session).
            session.clear()
            login_user(resultat.user, remember=bool(form.remember.data))
            session.permanent = True
            flash(f"Bienvenue, {resultat.user.username} !", "success")
            return redirect(_destination_sure(request.args.get("next")))
        if resultat.echec is Echec.NON_ACTIVE:
            accounts.renvoyer_activation(form.email.data)
        flash(MESSAGES_ECHEC[resultat.echec or Echec.IDENTIFIANTS], "error")
    return render_template("auth/login.html", form=form)


@bp.post("/deconnexion")
@login_required
def logout() -> Response:
    form = ConfirmForm()
    if not form.validate_on_submit():
        abort(400)
    logout_user()
    session.clear()
    flash("Vous êtes déconnecté.", "info")
    return redirect(url_for("main.index"))


@bp.route("/mot-de-passe-oublie", methods=["GET", "POST"])
@limiter.limit("20 per hour", methods=["POST"])
def forgot_password() -> str | Response:
    form = EmailForm()
    if form.validate_on_submit():
        accounts.demander_reinitialisation(form.email.data)
        flash(MESSAGE_OUBLI, "info")
        return redirect(url_for("auth.login"))
    return render_template("auth/forgot_password.html", form=form)


@bp.route("/reinitialisation/<token>", methods=["GET", "POST"])
@limiter.limit("60 per hour")
def reset_password(token: str) -> str | Response:
    if not accounts.jeton_reinitialisation_valide(token):
        flash(
            "Ce lien est invalide, a expiré ou a déjà servi. Faites une nouvelle demande.", "error"
        )
        return redirect(url_for("auth.forgot_password"))
    form = ResetPasswordForm()
    if form.validate_on_submit():
        if accounts.reinitialiser(token, form.password.data) is None:
            flash("Ce lien n'est plus valable. Faites une nouvelle demande.", "error")
            return redirect(url_for("auth.forgot_password"))
        logout_user()
        session.clear()
        flash("Mot de passe modifié : vous pouvez vous connecter.", "success")
        return redirect(url_for("auth.login"))
    return render_template("auth/reset_password.html", form=form)
