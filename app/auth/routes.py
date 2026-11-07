"""Routes des comptes : inscription, activation, connexion, mot de passe oublié."""

from __future__ import annotations

import time
from urllib.parse import urlsplit

from flask import Blueprint, abort, flash, redirect, render_template, request, session, url_for
from flask_login import current_user, login_required, login_user, logout_user
from werkzeug.wrappers import Response

from app.auth.forms import (
    CodeForm,
    ConfirmForm,
    EmailForm,
    LoginForm,
    RegisterForm,
    ResetPasswordForm,
)
from app.extensions import db, limiter
from app.models import User
from app.services import accounts, audit, twofa
from app.services.accounts import Echec

bp = Blueprint("auth", __name__)

CLE_2FA = "connexion_2fa"
DELAI_2FA = 300  # secondes pour saisir le code après le mot de passe

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
        user = resultat.user
        if user is not None and user.totp_enabled:
            # Mot de passe juste : deuxième étape. Rien n'est ouvert tant que le code manque.
            session.clear()
            session[CLE_2FA] = {
                "uid": user.id,
                "jeton": user.session_token,
                "souvenir": bool(form.remember.data),
                "suite": _destination_sure(request.args.get("next")),
                "t": int(time.time()),
            }
            return redirect(url_for("auth.second_factor"))
        if user is not None:
            _ouvrir_session(user, bool(form.remember.data))
            flash(f"Bienvenue, {user.username} !", "success")
            return redirect(_destination_sure(request.args.get("next")))
        if resultat.echec is Echec.NON_ACTIVE:
            accounts.renvoyer_activation(form.email.data)
        audit.journaliser(
            "compte_verrouille" if resultat.echec is Echec.VERROUILLE else "connexion_echec",
            cible=accounts.normaliser_email(form.email.data or "")[:120],
        )
        flash(MESSAGES_ECHEC[resultat.echec or Echec.IDENTIFIANTS], "error")
    return render_template("auth/login.html", form=form)


def _ouvrir_session(user: User, souvenir: bool, methode: str = "mot de passe") -> None:
    # Nouvelle session : rien de l'ancienne n'est conservé (fixation de session).
    session.clear()
    login_user(user, remember=souvenir)
    session.permanent = True
    audit.journaliser("connexion", user=user, methode=methode)


@bp.route("/verification", methods=["GET", "POST"])
@limiter.limit("10 per minute;60 per hour", methods=["POST"])
def second_factor() -> str | Response:
    """Deuxième étape de la connexion : code de l'application ou code de secours."""
    attente = session.get(CLE_2FA)
    if not attente or int(time.time()) - int(attente.get("t", 0)) > DELAI_2FA:
        session.pop(CLE_2FA, None)
        flash("Reconnectez-vous : la vérification a expiré.", "info")
        return redirect(url_for("auth.login"))
    user = db.session.get(User, attente["uid"])
    if user is None or user.session_token != attente["jeton"] or not user.is_active:
        session.pop(CLE_2FA, None)
        return redirect(url_for("auth.login"))
    form = CodeForm()
    if form.validate_on_submit():
        if user.is_locked():
            flash(MESSAGES_ECHEC[Echec.VERROUILLE], "error")
            return redirect(url_for("auth.login"))
        methode = twofa.verifier(user, form.code.data)
        if methode is not None:
            suite = attente["suite"]
            _ouvrir_session(user, attente["souvenir"], methode)
            if methode == "secours":
                audit.journaliser("2fa_code_secours", user=user)
                flash(
                    f"Code de secours utilisé : il vous en reste {twofa.codes_restants(user)}.",
                    "info",
                )
            flash(f"Bienvenue, {user.username} !", "success")
            return redirect(suite)
        accounts.compter_echec(user)
        audit.journaliser("connexion_2fa_echec", user=user)
        form.code.errors = ["Code incorrect ou déjà utilisé."]
    return render_template("auth/second_factor.html", form=form)


@bp.post("/deconnexion")
@login_required
def logout() -> Response:
    form = ConfirmForm()
    if not form.validate_on_submit():
        abort(400)
    audit.journaliser("deconnexion")
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
        reinitialise = accounts.reinitialiser(token, form.password.data)
        if reinitialise is None:
            flash("Ce lien n'est plus valable. Faites une nouvelle demande.", "error")
            return redirect(url_for("auth.forgot_password"))
        audit.journaliser("mot_de_passe_reinitialise", user=reinitialise)
        logout_user()
        session.clear()
        flash("Mot de passe modifié : vous pouvez vous connecter.", "success")
        return redirect(url_for("auth.login"))
    return render_template("auth/reset_password.html", form=form)
