"""Pages d'erreur : jamais de détail technique côté client, tout part dans le journal."""

from __future__ import annotations

import logging

from flask import Flask, jsonify, render_template, request
from flask_wtf.csrf import CSRFError
from werkzeug.exceptions import HTTPException
from werkzeug.wrappers import Response

journal = logging.getLogger(__name__)

TITRES = {
    400: "Requête invalide",
    401: "Connexion requise",
    403: "Accès refusé",
    404: "Page introuvable",
    405: "Méthode non autorisée",
    413: "Fichier trop volumineux",
    422: "Données invalides",
    429: "Trop de requêtes",
    500: "Erreur interne",
}
TEXTES = {
    400: "La requête n'a pas pu être traitée.",
    401: "Connectez-vous pour accéder à cette page.",
    403: "Vous n'avez pas les droits nécessaires pour cette page.",
    404: "Cette page n'existe pas ou a été déplacée.",
    405: "Cette action n'est pas disponible ici.",
    413: "L'envoi dépasse la taille autorisée.",
    422: "Les données envoyées sont invalides.",
    429: "Vous avez fait trop de tentatives. Patientez un peu avant de réessayer.",
    500: "Un problème est survenu de notre côté. Réessayez dans un instant.",
}


def _reponse(code: int, texte: str | None = None) -> tuple[str | Response, int]:
    if request.accept_mimetypes.best == "application/json" or request.path == "/health":
        return jsonify(erreur=TITRES.get(code, "Erreur")), code
    page = render_template(
        "errors/error.html",
        code=code,
        titre=TITRES.get(code, "Erreur"),
        texte=texte or TEXTES.get(code, TEXTES[500]),
    )
    return page, code


def installer(app: Flask) -> None:
    @app.errorhandler(CSRFError)
    def csrf(erreur: CSRFError) -> tuple[str | Response, int]:
        journal.warning("jeton CSRF refusé sur %s : %s", request.path, erreur.description)
        return _reponse(
            400, "Le formulaire a expiré ou n'est pas valide. Rechargez la page et réessayez."
        )

    @app.errorhandler(HTTPException)
    def http(erreur: HTTPException) -> tuple[str | Response, int]:
        code = erreur.code or 500
        return _reponse(code)

    @app.errorhandler(Exception)
    def interne(_erreur: Exception) -> tuple[str | Response, int]:
        journal.exception("erreur non gérée sur %s %s", request.method, request.path)
        return _reponse(500)
