"""Extensions Flask partagées, initialisées par la fabrique d'application."""

from __future__ import annotations

from typing import Any

from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_login import LoginManager
from flask_sqlalchemy import SQLAlchemy
from flask_wtf import CSRFProtect
from sqlalchemy import MetaData, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase

# Noms de contraintes stables : Alembic produit les mêmes noms sur MySQL et SQLite.
CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=CONVENTION)


db = SQLAlchemy(model_class=Base)
csrf = CSRFProtect()
login_manager = LoginManager()
# Pas de limite globale : Nginx limite le débit par adresse, et les routes sensibles
# (connexion, inscription, mot de passe) ont leurs propres limites. Une limite globale
# bloquerait une classe entière derrière une même adresse IP, fichiers statiques compris.
limiter = Limiter(key_func=get_remote_address)


@event.listens_for(Engine, "connect")
def _sqlite_cles_etrangeres(connexion: Any, _record: Any) -> None:
    """SQLite n'applique les clés étrangères (ON DELETE…) que sur demande, comme MySQL."""
    if type(connexion).__module__.startswith("sqlite3"):
        curseur = connexion.cursor()
        curseur.execute("PRAGMA foreign_keys=ON")
        curseur.close()
