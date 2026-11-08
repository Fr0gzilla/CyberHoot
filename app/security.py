"""En-têtes de sécurité et politique de sécurité du contenu (CSP) à nonce.

La CSP n'autorise ni script ni style en ligne : tout le JavaScript et le CSS sont servis
en fichiers depuis l'application. Le nonce est disponible dans les gabarits (csp_nonce())
pour le cas exceptionnel d'une balise <script> qui en aurait besoin.

HSTS : envoyé seulement sur une requête arrivée en HTTPS (le proxy le signale par
X-Forwarded-Proto) ; le navigateur refusera ensuite tout accès en clair pendant un an.
"""

from __future__ import annotations

import secrets

from flask import Flask, g, request
from werkzeug.wrappers import Response

HSTS_DUREE = 365 * 24 * 60 * 60


def _nonce() -> str:
    if "csp_nonce" not in g:
        g.csp_nonce = secrets.token_urlsafe(16)
    nonce: str = g.csp_nonce
    return nonce


def politique(nonce: str) -> str:
    directives = {
        "default-src": "'self'",
        "script-src": f"'self' 'nonce-{nonce}'",
        "style-src": "'self'",
        "img-src": "'self' data:",
        "font-src": "'self'",
        "connect-src": "'self'",
        "object-src": "'none'",
        "base-uri": "'self'",
        "form-action": "'self'",
        "frame-ancestors": "'none'",
    }
    return "; ".join(f"{cle} {valeur}" for cle, valeur in directives.items())


def installer(app: Flask) -> None:
    app.jinja_env.globals["csp_nonce"] = _nonce

    @app.after_request
    def entetes(reponse: Response) -> Response:
        entetes = reponse.headers
        entetes["Content-Security-Policy"] = politique(_nonce())
        entetes["X-Content-Type-Options"] = "nosniff"
        entetes["X-Frame-Options"] = "DENY"
        entetes["Referrer-Policy"] = "strict-origin-when-cross-origin"
        entetes["Permissions-Policy"] = "camera=(), microphone=(), geolocation=(), payment=()"
        entetes["Cross-Origin-Opener-Policy"] = "same-origin"
        entetes["Cross-Origin-Resource-Policy"] = "same-origin"
        if request.is_secure:
            entetes["Strict-Transport-Security"] = f"max-age={HSTS_DUREE}; includeSubDomains"
        # Les pages d'un compte ne doivent pas rester dans un cache partagé.
        if "Cache-Control" not in entetes and reponse.mimetype == "text/html":
            entetes["Cache-Control"] = "no-store"
        return reponse
