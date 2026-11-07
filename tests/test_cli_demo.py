"""Commandes : rôles, quiz de démonstration, analyse des médias."""

from __future__ import annotations

from flask import Flask
from sqlalchemy import func, select

from app.extensions import db
from app.models import Quiz, QuizStatus, User
from app.services import accounts
from tests.conftest import creer_compte


def test_donner_et_retirer_un_role(app: Flask) -> None:
    creer_compte(app, "futur")
    cli = app.test_cli_runner()
    resultat = cli.invoke(args=["donner-role", "--email", "futur@example.org", "--role", "creator"])
    assert resultat.exit_code == 0, resultat.output
    user = accounts.trouver_par_email("futur@example.org")
    assert user is not None
    assert user.has_role("creator")
    cli.invoke(
        args=["donner-role", "--email", "futur@example.org", "--role", "creator", "--retirer"]
    )
    db.session.expire_all()
    assert not user.has_role("creator")


def test_donner_role_compte_inconnu(app: Flask) -> None:
    resultat = app.test_cli_runner().invoke(
        args=["donner-role", "--email", "personne@example.org", "--role", "admin"]
    )
    assert resultat.exit_code != 0


def test_charger_la_demo_une_seule_fois(app: Flask, admin: User) -> None:
    cli = app.test_cli_runner()
    premier = cli.invoke(args=["charger-demo", "--email", "chef@example.org"])
    assert premier.exit_code == 0, premier.output
    assert "Quiz ajoutés : 2" in premier.output
    second = cli.invoke(args=["charger-demo", "--email", "chef@example.org"])
    assert "Quiz ajoutés : 0" in second.output
    publies = db.session.scalar(
        select(func.count()).select_from(Quiz).where(Quiz.status == QuizStatus.PUBLISHED)
    )
    assert publies == 2


def test_charger_demo_compte_inconnu(app: Flask) -> None:
    resultat = app.test_cli_runner().invoke(args=["charger-demo", "--email", "x@example.org"])
    assert resultat.exit_code != 0


def test_analyser_les_medias(app: Flask) -> None:
    resultat = app.test_cli_runner().invoke(args=["analyser-medias"])
    assert resultat.exit_code == 0
    assert "Verdicts rendus : 0" in resultat.output
