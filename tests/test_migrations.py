"""Les migrations sont la seule source du schéma : elles doivent correspondre aux modèles."""

from __future__ import annotations

from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, inspect, select

from app.extensions import db
from app.models import Role


def test_migrations_identiques_aux_modeles(database_url: str) -> None:
    moteur = create_engine(database_url)
    with moteur.connect() as connexion:
        contexte = MigrationContext.configure(connexion, opts={"compare_type": True})
        ecarts = compare_metadata(contexte, db.metadata)
    moteur.dispose()
    assert ecarts == [], f"écarts entre modèles et migrations : {ecarts}"


def test_tables_attendues(database_url: str) -> None:
    moteur = create_engine(database_url)
    tables = set(inspect(moteur).get_table_names())
    moteur.dispose()
    assert {"user", "role", "user_role", "account_token", "alembic_version"} <= tables


def test_roles_de_reference(app: object) -> None:
    noms = set(db.session.scalars(select(Role.name)))
    assert noms == {"player", "creator", "admin"}
