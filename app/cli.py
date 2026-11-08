"""Commandes d'administration : `flask --app wsgi <commande>`."""

from __future__ import annotations

import json
from importlib import resources

import click
from flask import Flask
from sqlalchemy import select

from app.extensions import db
from app.models import Category, Quiz, Role, RoleName, User
from app.services import accounts, moderation, quizzes, scan


def charger_demo(auteur: User) -> list[str]:
    """Crée et publie les quiz de démonstration absents (app/data/demo/*.json)."""
    crees: list[str] = []
    dossier = resources.files("app.data").joinpath("demo")
    for fichier in sorted(dossier.iterdir(), key=lambda f: f.name):
        if not fichier.name.endswith(".json"):
            continue
        donnees = json.loads(fichier.read_text("utf-8"))
        deja = db.session.scalar(select(Quiz).where(Quiz.title == donnees["title"]))
        if deja is not None:
            continue
        categorie = db.session.scalar(select(Category).where(Category.slug == donnees["category"]))
        brouillon = quizzes.Brouillon(
            title=donnees["title"],
            description=donnees["description"],
            category_id=categorie.id if categorie else None,
            difficulty=donnees["difficulty"],
            questions=[
                quizzes.BrouillonQuestion(
                    text=q["text"],
                    explanation=q["explanation"],
                    options=[
                        quizzes.BrouillonOption(o["text"], o.get("correct", False))
                        for o in q["options"]
                    ],
                    kind=q.get("kind", "choice"),
                    canal=q.get("message", {}).get("canal", "email"),
                    expediteur=q.get("message", {}).get("expediteur", ""),
                    objet=q.get("message", {}).get("objet", ""),
                )
                for q in donnees["questions"]
            ],
        )
        erreurs = quizzes.valider(brouillon, set(), soumission=True)
        if erreurs:
            raise click.ClickException(f"{fichier.name} invalide : {erreurs}")
        quiz = quizzes.enregistrer(None, brouillon, auteur)
        quizzes.soumettre(quiz)
        moderation.publier(quiz)
        crees.append(quiz.title)
    return crees


def installer(app: Flask) -> None:
    @app.cli.command("creer-admin")
    @click.option("--pseudo", prompt="Pseudo")
    @click.option("--email", prompt="Adresse e-mail")
    @click.password_option("--mot-de-passe", prompt="Mot de passe")
    def creer_admin(pseudo: str, email: str, mot_de_passe: str) -> None:
        """Crée un compte administrateur déjà activé."""
        try:
            user = accounts.creer_admin(pseudo, email, mot_de_passe)
        except ValueError as erreur:
            raise click.ClickException(str(erreur)) from erreur
        click.echo(f"Administrateur créé : {user.username}")

    @app.cli.command("donner-role")
    @click.option("--email", required=True)
    @click.option("--role", type=click.Choice([r.value for r in RoleName]), required=True)
    @click.option("--retirer", is_flag=True, help="Retire le rôle au lieu de l'ajouter.")
    def donner_role(email: str, role: str, retirer: bool) -> None:
        """Ajoute (ou retire) un rôle à un compte."""
        user = accounts.trouver_par_email(email)
        if user is None:
            raise click.ClickException("Aucun compte avec cette adresse.")
        cible = db.session.scalar(select(Role).where(Role.name == role))
        if cible is None:
            raise click.ClickException("Rôle inconnu : migrations non appliquées ?")
        if retirer and cible in user.roles:
            user.roles.remove(cible)
        elif not retirer and cible not in user.roles:
            user.roles.append(cible)
        db.session.commit()
        click.echo(f"{user.username} : {', '.join(user.role_names)}")

    @app.cli.command("purger-comptes")
    def purger_comptes() -> None:
        """Supprime les comptes jamais activés depuis plus de 30 jours."""
        click.echo(f"Comptes supprimés : {accounts.purger_comptes_non_actives()}")

    @app.cli.command("analyser-medias")
    @click.option("--boucle", is_flag=True, help="Tourne en continu (conteneur worker).")
    def analyser_medias(boucle: bool) -> None:
        """Analyse les images en attente (VirusTotal ou mode simulé)."""
        if boucle:  # pragma: no cover
            scan.boucle()
        click.echo(f"Verdicts rendus : {scan.analyser_en_attente()}")

    @app.cli.command("charger-demo")
    @click.option("--email", required=True, help="Compte auteur des quiz (créateur ou admin).")
    def charger_demo_cmd(email: str) -> None:
        """Ajoute et publie les quiz de démonstration absents."""
        auteur = accounts.trouver_par_email(email)
        if auteur is None:
            raise click.ClickException("Aucun compte avec cette adresse.")
        # Les e-mails de publication construisent des liens : il faut un contexte de requête.
        with app.test_request_context():
            crees = charger_demo(auteur)
        click.echo(f"Quiz ajoutés : {len(crees)}")
        for titre in crees:
            click.echo(f"  - {titre}")
