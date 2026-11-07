"""Envoi d'e-mails.

Trois modes, choisis par MAIL_BACKEND :
- « console » : le message est écrit dans le journal (développement et recette, aucun envoi) ;
- « memoire » : le message est gardé dans une liste (tests) ;
- « smtp » : envoi réel par SMTP avec STARTTLS.
"""

from __future__ import annotations

import logging
import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage

from flask import current_app, render_template

journal = logging.getLogger(__name__)


@dataclass(frozen=True)
class Message:
    destinataire: str
    sujet: str
    texte: str


# Boîte d'envoi du mode « memoire », lue par les tests.
boite_envoi: list[Message] = []


def envoyer(destinataire: str, sujet: str, gabarit: str, **contexte: object) -> None:
    """Rend le gabarit texte `mail/<gabarit>.txt` et l'envoie selon le mode configuré."""
    texte = render_template(f"mail/{gabarit}.txt", **contexte)
    message = Message(destinataire=destinataire, sujet=sujet, texte=texte)
    mode = current_app.config["MAIL_BACKEND"]
    if mode == "memoire":
        boite_envoi.append(message)
    elif mode == "console":
        # Le contenu (qui peut porter un lien à usage unique) ne sort qu'en développement.
        if current_app.debug:
            journal.info("e-mail (console) à %s : %s\n%s", destinataire, sujet, texte)
        else:
            journal.info("e-mail (console) à %s : %s", destinataire, sujet)
    else:
        _envoyer_smtp(message)


def _envoyer_smtp(message: Message) -> None:
    config = current_app.config
    courriel = EmailMessage()
    courriel["From"] = config["MAIL_FROM"]
    courriel["To"] = message.destinataire
    courriel["Subject"] = message.sujet
    courriel.set_content(message.texte)
    try:
        with smtplib.SMTP(config["SMTP_HOST"], config["SMTP_PORT"], timeout=10) as serveur:
            if config["SMTP_STARTTLS"]:
                serveur.starttls(context=ssl.create_default_context())
            if config["SMTP_USER"]:
                serveur.login(config["SMTP_USER"], config["SMTP_PASSWORD"] or "")
            serveur.send_message(courriel)
    except (OSError, smtplib.SMTPException):
        # Un e-mail perdu ne doit ni planter la requête ni révéler l'existence d'un compte.
        journal.exception("échec d'envoi SMTP vers %s", message.destinataire)
