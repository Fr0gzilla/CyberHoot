"""Logique métier des comptes, indépendante des routes.

Règles de sécurité appliquées ici :
- les réponses ne révèlent jamais si une adresse e-mail a un compte (inscription, oubli) ;
- la connexion coûte le même temps que le compte existe ou non ;
- après VERROU_ECHECS_MAX échecs, le compte est verrouillé VERROU_DUREE_MINUTES minutes ;
- changer de mot de passe annule les jetons en cours et déconnecte les autres sessions.
"""

from __future__ import annotations

import enum
import logging
from dataclasses import dataclass
from datetime import timedelta

from flask import current_app, url_for
from sqlalchemy import func, select

from app.extensions import db
from app.models import Role, RoleName, TokenPurpose, User, utcnow
from app.models.account import nouveau_jeton_session
from app.services import mail, passwords, tokens

journal = logging.getLogger(__name__)


def normaliser_email(email: str) -> str:
    return email.strip().lower()


def trouver_par_email(email: str) -> User | None:
    return db.session.scalar(select(User).where(User.email == normaliser_email(email)))


def pseudo_pris(username: str) -> bool:
    existe = db.session.scalar(
        select(func.count()).select_from(User).where(func.lower(User.username) == username.lower())
    )
    return bool(existe)


def _lien(endpoint: str, jeton: str) -> str:
    # Le lien part de l'URL publique configurée, jamais de l'en-tête Host de la requête
    # (sinon un attaquant pourrait faire envoyer un lien vers son propre domaine).
    chemin = url_for(endpoint, token=jeton, _external=False)
    return f"{current_app.config['PUBLIC_URL']}{chemin}"


def _role(nom: RoleName) -> Role:
    role: Role | None = db.session.scalar(select(Role).where(Role.name == nom.value))
    if role is None:
        raise RuntimeError(f"rôle {nom.value} absent : migrations non appliquées ?")
    return role


# --- Inscription et activation -------------------------------------------------------------

DELAI_ACTIVATION_JOURS = 30


def purger_comptes_non_actives() -> int:
    """Supprime les comptes jamais activés depuis 30 jours (politique de confidentialité)."""
    limite = utcnow() - timedelta(days=DELAI_ACTIVATION_JOURS)
    anciens = db.session.scalars(
        select(User).where(User.email_verified_at.is_(None), User.created_at < limite)
    ).all()
    for user in anciens:
        db.session.delete(user)
    db.session.commit()
    if anciens:
        journal.info("purge : %d compte(s) jamais activé(s) supprimé(s)", len(anciens))
    return len(anciens)


def inscrire(username: str, email: str, mot_de_passe: str) -> None:
    """Crée un compte inactif et envoie le lien d'activation.

    Si l'adresse a déjà un compte, rien n'est créé : le titulaire reçoit un e-mail qui le
    prévient, et la réponse affichée reste la même (pas d'énumération des comptes).
    Le pseudo, public, est vérifié avant l'appel par le formulaire.
    """
    purger_comptes_non_actives()
    email = normaliser_email(email)
    existant = trouver_par_email(email)
    if existant is not None:
        # Même coût qu'une création (hachage) : le temps de réponse ne trahit rien.
        passwords.verifier_factice(mot_de_passe)
        mail.envoyer(
            existant.email,
            "Tentative d'inscription avec votre adresse",
            "inscription_existante",
            user=existant,
            lien=f"{current_app.config['PUBLIC_URL']}{url_for('auth.forgot_password')}",
        )
        return

    user = User(
        username=username.strip(), email=email, password_hash=passwords.hacher(mot_de_passe)
    )
    user.roles.append(_role(RoleName.PLAYER))
    db.session.add(user)
    db.session.flush()
    jeton = tokens.emettre(
        user, TokenPurpose.ACTIVATION, current_app.config["JETON_DUREE_MINUTES"] * 48
    )
    db.session.commit()
    mail.envoyer(
        user.email,
        "Activez votre compte CyberHoot",
        "activation",
        user=user,
        lien=_lien("auth.activate", jeton),
    )
    journal.info("inscription : compte %s créé, activation envoyée", user.id)


def activer(jeton_clair: str) -> User | None:
    jeton = tokens.trouver_valide(jeton_clair, TokenPurpose.ACTIVATION)
    if jeton is None:
        return None
    tokens.consommer(jeton)
    user = jeton.user
    if user.email_verified_at is None:
        user.email_verified_at = utcnow()
    db.session.commit()
    journal.info("activation : compte %s", user.id)
    return user


# --- Connexion --------------------------------------------------------------------------


class Echec(enum.Enum):
    IDENTIFIANTS = "identifiants"
    VERROUILLE = "verrouille"
    NON_ACTIVE = "non_active"
    DESACTIVE = "desactive"


@dataclass(frozen=True)
class ResultatConnexion:
    user: User | None = None
    echec: Echec | None = None


def authentifier(email: str, mot_de_passe: str) -> ResultatConnexion:
    user = trouver_par_email(email)
    if user is None:
        passwords.verifier_factice(mot_de_passe)
        return ResultatConnexion(echec=Echec.IDENTIFIANTS)

    maintenant = utcnow()
    if user.is_locked(maintenant):
        # On ne vérifie même pas le mot de passe : le verrou ne doit pas servir d'oracle.
        passwords.verifier_factice(mot_de_passe)
        return ResultatConnexion(echec=Echec.VERROUILLE)

    if not passwords.verifier(user.password_hash, mot_de_passe):
        compter_echec(user)
        return ResultatConnexion(echec=Echec.IDENTIFIANTS)

    # Mot de passe juste : on peut dire pourquoi le compte ne s'ouvre pas.
    if not user.is_enabled:
        return ResultatConnexion(echec=Echec.DESACTIVE)
    if user.email_verified_at is None:
        return ResultatConnexion(echec=Echec.NON_ACTIVE)

    user.failed_logins = 0
    user.locked_until = None
    user.last_login_at = maintenant
    if passwords.doit_rehacher(user.password_hash):
        user.password_hash = passwords.hacher(mot_de_passe)
    db.session.commit()
    journal.info("connexion : compte %s", user.id)
    return ResultatConnexion(user=user)


def compter_echec(user: User) -> None:
    """Un échec de plus (mot de passe ou code de double authentification) ; verrou au 5e."""
    user.failed_logins += 1
    if user.failed_logins >= current_app.config["VERROU_ECHECS_MAX"]:
        user.locked_until = utcnow() + timedelta(minutes=current_app.config["VERROU_DUREE_MINUTES"])
        user.failed_logins = 0
        journal.warning("connexion : compte %s verrouillé après trop d'échecs", user.id)
    db.session.commit()


def renvoyer_activation(email: str) -> None:
    """Renvoie un lien d'activation si le compte existe et n'est pas activé (réponse neutre)."""
    user = trouver_par_email(email)
    if user is None or user.email_verified_at is not None:
        return
    jeton = tokens.emettre(
        user, TokenPurpose.ACTIVATION, current_app.config["JETON_DUREE_MINUTES"] * 48
    )
    db.session.commit()
    mail.envoyer(
        user.email,
        "Activez votre compte CyberHoot",
        "activation",
        user=user,
        lien=_lien("auth.activate", jeton),
    )


# --- Mot de passe oublié ----------------------------------------------------------------


def demander_reinitialisation(email: str) -> None:
    """Envoie un lien de réinitialisation si le compte existe ; réponse identique sinon."""
    user = trouver_par_email(email)
    if user is None or not user.is_enabled:
        return
    jeton = tokens.emettre(user, TokenPurpose.RESET, current_app.config["JETON_DUREE_MINUTES"])
    db.session.commit()
    mail.envoyer(
        user.email,
        "Réinitialisation de votre mot de passe CyberHoot",
        "reinitialisation",
        user=user,
        lien=_lien("auth.reset_password", jeton),
        duree=current_app.config["JETON_DUREE_MINUTES"],
    )
    journal.info("réinitialisation demandée : compte %s", user.id)


def jeton_reinitialisation_valide(jeton_clair: str) -> bool:
    return tokens.trouver_valide(jeton_clair, TokenPurpose.RESET) is not None


def reinitialiser(jeton_clair: str, nouveau: str) -> User | None:
    jeton = tokens.trouver_valide(jeton_clair, TokenPurpose.RESET)
    if jeton is None:
        return None
    user = jeton.user
    _changer_mot_de_passe(user, nouveau)
    # Le lien reçu par e-mail prouve aussi la possession de l'adresse.
    if user.email_verified_at is None:
        user.email_verified_at = utcnow()
    user.failed_logins = 0
    user.locked_until = None
    db.session.commit()
    mail.envoyer(user.email, "Votre mot de passe a été modifié", "mot_de_passe_modifie", user=user)
    journal.info("réinitialisation : compte %s", user.id)
    return user


# --- Profil -----------------------------------------------------------------------------


def _changer_mot_de_passe(user: User, nouveau: str) -> None:
    user.password_hash = passwords.hacher(nouveau)
    user.session_token = nouveau_jeton_session()
    tokens.annuler_tous(user)


def changer_mot_de_passe(user: User, actuel: str, nouveau: str) -> bool:
    if not passwords.verifier(user.password_hash, actuel):
        return False
    _changer_mot_de_passe(user, nouveau)
    db.session.commit()
    mail.envoyer(user.email, "Votre mot de passe a été modifié", "mot_de_passe_modifie", user=user)
    journal.info("mot de passe changé : compte %s", user.id)
    return True


def changer_pseudo(user: User, username: str) -> None:
    user.username = username.strip()
    db.session.commit()


def verifier_mot_de_passe(user: User, mot_de_passe: str) -> bool:
    return passwords.verifier(user.password_hash, mot_de_passe)


def supprimer_compte(user: User, mot_de_passe: str) -> bool:
    """Supprime le compte et ses données (droit à l'effacement), après confirmation."""
    if not passwords.verifier(user.password_hash, mot_de_passe):
        return False
    identifiant = user.id
    db.session.delete(user)
    db.session.commit()
    journal.info("compte %s supprimé à la demande de son titulaire", identifiant)
    return True


# --- Administration (ligne de commande) ---------------------------------------------------


def creer_admin(username: str, email: str, mot_de_passe: str) -> User:
    """Crée un administrateur déjà activé (commande `flask creer-admin`)."""
    erreurs = passwords.problemes(mot_de_passe, username, email)
    if erreurs:
        raise ValueError(" ".join(erreurs))
    if trouver_par_email(email) is not None or pseudo_pris(username):
        raise ValueError("Ce pseudo ou cette adresse e-mail a déjà un compte.")
    user = User(
        username=username.strip(),
        email=normaliser_email(email),
        password_hash=passwords.hacher(mot_de_passe),
        email_verified_at=utcnow(),
    )
    user.roles.extend([_role(RoleName.PLAYER), _role(RoleName.CREATOR), _role(RoleName.ADMIN)])
    db.session.add(user)
    db.session.commit()
    return user
