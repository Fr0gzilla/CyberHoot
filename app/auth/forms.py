"""Formulaires des comptes. Flask-WTF ajoute et vérifie le jeton CSRF de chacun."""

from __future__ import annotations

import re
from typing import Any

from flask_wtf import FlaskForm
from wtforms import BooleanField, EmailField, PasswordField, StringField
from wtforms.validators import DataRequired, Email, EqualTo, Length, ValidationError

from app.services import accounts, passwords

MOTIF_PSEUDO = re.compile(r"^[A-Za-z0-9_-]{3,32}$")


def _pseudo_valide(_form: Any, field: Any) -> None:
    if not MOTIF_PSEUDO.fullmatch(field.data or ""):
        raise ValidationError(
            "3 à 32 caractères : lettres sans accent, chiffres, tiret ou tiret bas."
        )


class _AvecMotDePasse(FlaskForm):  # type: ignore[misc]
    """Vérifie la robustesse du champ `password` contre la politique commune."""

    def _verifier_robustesse(self, username: str, email: str) -> bool:
        erreurs = passwords.problemes(self.password.data or "", username, email)
        if erreurs:
            self.password.errors = [*self.password.errors, *erreurs]
            return False
        return True


class RegisterForm(_AvecMotDePasse):
    username = StringField("Pseudo", validators=[DataRequired(), _pseudo_valide])
    email = EmailField(
        "Adresse e-mail",
        validators=[DataRequired(), Email(check_deliverability=False), Length(max=254)],
    )
    password = PasswordField(
        "Mot de passe", validators=[DataRequired(), Length(max=passwords.LONGUEUR_MAX)]
    )
    password_confirm = PasswordField(
        "Confirmer le mot de passe",
        validators=[DataRequired(), EqualTo("password", "Les mots de passe ne correspondent pas.")],
    )

    def validate_username(self, field: Any) -> None:
        if accounts.pseudo_pris(field.data or ""):
            raise ValidationError("Ce pseudo est déjà pris.")

    def validate(self, extra_validators: Any = None) -> bool:
        valide: bool = super().validate(extra_validators)
        return self._verifier_robustesse(self.username.data or "", self.email.data or "") and valide


class LoginForm(FlaskForm):  # type: ignore[misc]
    email = EmailField("Adresse e-mail", validators=[DataRequired(), Length(max=254)])
    password = PasswordField(
        "Mot de passe", validators=[DataRequired(), Length(max=passwords.LONGUEUR_MAX)]
    )
    remember = BooleanField("Rester connecté sur cet appareil")


class EmailForm(FlaskForm):  # type: ignore[misc]
    email = EmailField(
        "Adresse e-mail",
        validators=[DataRequired(), Email(check_deliverability=False), Length(max=254)],
    )


class ResetPasswordForm(_AvecMotDePasse):
    password = PasswordField(
        "Nouveau mot de passe", validators=[DataRequired(), Length(max=passwords.LONGUEUR_MAX)]
    )
    password_confirm = PasswordField(
        "Confirmer le mot de passe",
        validators=[DataRequired(), EqualTo("password", "Les mots de passe ne correspondent pas.")],
    )

    def validate(self, extra_validators: Any = None) -> bool:
        valide: bool = super().validate(extra_validators)
        return self._verifier_robustesse("", "") and valide


class ChangePasswordForm(_AvecMotDePasse):
    current_password = PasswordField("Mot de passe actuel", validators=[DataRequired()])
    password = PasswordField(
        "Nouveau mot de passe", validators=[DataRequired(), Length(max=passwords.LONGUEUR_MAX)]
    )
    password_confirm = PasswordField(
        "Confirmer le nouveau mot de passe",
        validators=[DataRequired(), EqualTo("password", "Les mots de passe ne correspondent pas.")],
    )

    def __init__(self, *args: Any, user_username: str = "", user_email: str = "", **kwargs: Any):
        super().__init__(*args, **kwargs)
        self._username = user_username
        self._email = user_email

    def validate(self, extra_validators: Any = None) -> bool:
        valide: bool = super().validate(extra_validators)
        return self._verifier_robustesse(self._username, self._email) and valide


class UsernameForm(FlaskForm):  # type: ignore[misc]
    username = StringField("Nouveau pseudo", validators=[DataRequired(), _pseudo_valide])

    def validate_username(self, field: Any) -> None:
        if accounts.pseudo_pris(field.data or ""):
            raise ValidationError("Ce pseudo est déjà pris.")


class DeleteAccountForm(FlaskForm):  # type: ignore[misc]
    password = PasswordField("Mot de passe", validators=[DataRequired()])
    confirm = BooleanField(
        "Je comprends que la suppression est définitive.", validators=[DataRequired()]
    )


class ConfirmForm(FlaskForm):  # type: ignore[misc]
    """Formulaire vide : seulement le jeton CSRF (déconnexion, actions à un bouton)."""


class CodeForm(FlaskForm):  # type: ignore[misc]
    code = StringField(
        "Code à 6 chiffres (ou code de secours)",
        validators=[DataRequired(), Length(min=6, max=20)],
    )
