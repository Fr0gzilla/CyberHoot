"""Commandes d'administration : `flask --app wsgi <commande>`."""

from __future__ import annotations

import click
from flask import Flask

from app.services import accounts


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

    @app.cli.command("purger-comptes")
    def purger_comptes() -> None:
        """Supprime les comptes jamais activés depuis plus de 30 jours."""
        click.echo(f"Comptes supprimés : {accounts.purger_comptes_non_actives()}")
