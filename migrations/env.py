"""Environnement Alembic : la base cible vient de la configuration de l'application."""

from __future__ import annotations

import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

import app.models  # noqa: F401  (enregistre les tables dans la métadonnée)
from app.config import charger_config
from app.extensions import db

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

# Une URL passée par l'appelant (tests) ou par DATABASE_URL (génération du schéma) prime sur
# la configuration complète de l'application, qui exige aussi la clé secrète.
if not config.get_main_option("sqlalchemy.url"):
    url = os.environ.get("DATABASE_URL") or charger_config().SQLALCHEMY_DATABASE_URI
    config.set_main_option("sqlalchemy.url", url.replace("%", "%%"))

cible = db.metadata


def run_migrations_offline() -> None:
    """Produit le SQL sans base (make schema → docs/modele/schema.sql)."""
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=cible,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = config.attributes.get("connection")
    if connectable is None:
        moteur = engine_from_config(
            config.get_section(config.config_ini_section, {}),
            prefix="sqlalchemy.",
            poolclass=pool.NullPool,
        )
        with moteur.connect() as connexion:
            _executer(connexion)
    else:
        _executer(connectable)


def _executer(connexion: object) -> None:
    context.configure(
        connection=connexion,
        target_metadata=cible,
        compare_type=True,
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
