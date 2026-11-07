"""Fabrique de l'application CyberHoot."""

from __future__ import annotations

from flask import Flask
from werkzeug.middleware.proxy_fix import ProxyFix

from app import cli, errors, logging_setup, security
from app.config import Config, charger_config
from app.extensions import csrf, db, limiter, login_manager


def create_app(config: Config | None = None) -> Flask:
    app = Flask(__name__)
    app.config.from_object(config or charger_config())

    if app.config["PROXY_COUNT"]:
        # Derrière Nginx : l'adresse du client et le schéma viennent des en-têtes du proxy,
        # seulement pour le nombre de proxys de confiance configuré.
        n = app.config["PROXY_COUNT"]
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=n, x_proto=n, x_host=n)  # type: ignore[method-assign]

    logging_setup.installer(app)
    db.init_app(app)
    csrf.init_app(app)
    limiter.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"
    login_manager.login_message = "Connectez-vous pour accéder à cette page."
    login_manager.login_message_category = "info"
    login_manager.session_protection = "basic"

    from app.models import User

    @login_manager.user_loader
    def charger_utilisateur(identifiant: str) -> User | None:
        # Format « id:jeton » : un jeton périmé (mot de passe changé) ferme la session.
        id_brut, _, jeton = identifiant.partition(":")
        if not id_brut.isdigit() or not jeton:
            return None
        user = db.session.get(User, int(id_brut))
        if user is None or user.session_token != jeton or not user.is_active:
            return None
        return user

    from app.account.routes import bp as account_bp
    from app.auth.routes import bp as auth_bp
    from app.main.routes import bp as main_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp, url_prefix="/compte")
    app.register_blueprint(account_bp, url_prefix="/profil")

    security.installer(app)
    errors.installer(app)
    cli.installer(app)
    return app
