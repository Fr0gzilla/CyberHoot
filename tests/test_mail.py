"""Modes d'envoi des e-mails : console, mémoire, SMTP."""

from __future__ import annotations

import logging
import smtplib
from typing import Any, ClassVar

import pytest
from flask import Flask

from app.services import mail


class FauxSMTP:
    envoyes: ClassVar[list[Any]] = []
    echec = False

    def __init__(self, hote: str, port: int, timeout: int) -> None:
        self.hote, self.port = hote, port
        self.tls = False
        self.identifiants: tuple[str, str] | None = None

    def __enter__(self) -> FauxSMTP:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def starttls(self, context: object) -> None:
        self.tls = True

    def login(self, utilisateur: str, mot_de_passe: str) -> None:
        self.identifiants = (utilisateur, mot_de_passe)

    def send_message(self, message: Any) -> None:
        if FauxSMTP.echec:
            raise smtplib.SMTPException("serveur indisponible")
        FauxSMTP.envoyes.append((self, message))


def _envoyer(app: Flask) -> None:
    with app.test_request_context():
        mail.envoyer("dest@example.org", "Sujet", "mot_de_passe_modifie", user={"username": "x"})


def test_mode_smtp_avec_starttls_et_identifiants(
    app: Flask, monkeypatch: pytest.MonkeyPatch
) -> None:
    FauxSMTP.envoyes, FauxSMTP.echec = [], False
    monkeypatch.setattr(mail.smtplib, "SMTP", FauxSMTP)
    app.config.update(MAIL_BACKEND="smtp", SMTP_USER="robot", SMTP_PASSWORD="secret-smtp")
    _envoyer(app)
    serveur, message = FauxSMTP.envoyes[-1]
    assert serveur.tls is True
    assert serveur.identifiants == ("robot", "secret-smtp")
    assert message["To"] == "dest@example.org"
    assert message["Subject"] == "Sujet"


def test_echec_smtp_ne_fait_pas_planter(
    app: Flask, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    FauxSMTP.envoyes, FauxSMTP.echec = [], True
    monkeypatch.setattr(mail.smtplib, "SMTP", FauxSMTP)
    app.config.update(MAIL_BACKEND="smtp")
    _envoyer(app)
    assert "échec d'envoi SMTP" in caplog.text


def test_mode_console_n_ecrit_pas_le_contenu_hors_developpement(
    app: Flask, caplog: pytest.LogCaptureFixture
) -> None:
    app.config.update(MAIL_BACKEND="console")
    with caplog.at_level(logging.INFO):
        _envoyer(app)
    assert "e-mail (console) à dest@example.org : Sujet" in caplog.text
    assert "vient d'être modifié" not in caplog.text


def test_mode_console_ecrit_le_contenu_en_developpement(
    app: Flask, caplog: pytest.LogCaptureFixture
) -> None:
    app.config.update(MAIL_BACKEND="console")
    app.debug = True
    with caplog.at_level(logging.INFO):
        _envoyer(app)
    assert "vient d'être modifié" in caplog.text
