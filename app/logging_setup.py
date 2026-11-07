"""Journal applicatif structuré : une ligne JSON par événement, avec l'identifiant de requête.

Ne jamais y écrire de mot de passe, de jeton ni de contenu d'e-mail en production.
"""

from __future__ import annotations

import json
import logging
import secrets
import sys
from datetime import UTC, datetime

from flask import Flask, g, has_request_context, request
from werkzeug.wrappers import Response


class FormatJson(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        donnees: dict[str, object] = {
            "date": datetime.fromtimestamp(record.created, UTC).isoformat(timespec="milliseconds"),
            "niveau": record.levelname,
            "source": record.name,
            "message": record.getMessage(),
        }
        if has_request_context():
            donnees["requete"] = g.get("request_id")
            donnees["chemin"] = request.path
        if record.exc_info:
            donnees["exception"] = self.formatException(record.exc_info)
        return json.dumps(donnees, ensure_ascii=False)


def installer(app: Flask) -> None:
    racine = logging.getLogger()
    if not any(getattr(h, "_cyberhoot", False) for h in racine.handlers):
        sortie = logging.StreamHandler(sys.stdout)
        sortie.setFormatter(FormatJson())
        sortie._cyberhoot = True  # type: ignore[attr-defined]
        racine.addHandler(sortie)
    racine.setLevel(logging.DEBUG if app.debug else logging.INFO)

    @app.before_request
    def identifiant() -> None:
        # L'identifiant posé par Nginx est repris s'il a une forme saine, sinon on en crée un.
        recu = request.headers.get("X-Request-ID", "")
        valide = 8 <= len(recu) <= 64 and recu.replace("-", "").isalnum()
        g.request_id = recu if valide else secrets.token_hex(8)

    @app.after_request
    def renvoyer(reponse: Response) -> Response:
        reponse.headers["X-Request-ID"] = g.get("request_id", "")
        return reponse
