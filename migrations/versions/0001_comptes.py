"""Comptes : utilisateurs, rôles, jetons à usage unique.

Révision : 0001
Précédente :
Créée le : 2026-11-07
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    role = op.create_table(
        "role",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=20), nullable=False),
        sa.Column("label", sa.String(length=50), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_role")),
        sa.UniqueConstraint("name", name=op.f("uq_role_name")),
    )
    op.create_table(
        "user",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("username", sa.String(length=32), nullable=False),
        sa.Column("email", sa.String(length=254), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("is_enabled", sa.Boolean(), nullable=False),
        sa.Column("email_verified_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("last_login_at", sa.DateTime(), nullable=True),
        sa.Column("failed_logins", sa.Integer(), nullable=False),
        sa.Column("locked_until", sa.DateTime(), nullable=True),
        sa.Column("session_token", sa.String(length=32), nullable=False),
        sa.CheckConstraint("failed_logins >= 0", name=op.f("ck_user_failed_logins_positif")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_user")),
        sa.UniqueConstraint("email", name=op.f("uq_user_email")),
        sa.UniqueConstraint("username", name=op.f("uq_user_username")),
    )
    op.create_table(
        "account_token",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column(
            "purpose", sa.Enum("activation", "reset", name="token_purpose"), nullable=False
        ),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("used_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"], ["user.id"], name=op.f("fk_account_token_user_id_user"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_account_token")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_account_token_token_hash")),
    )
    op.create_index(
        op.f("ix_account_token_user_id"), "account_token", ["user_id"], unique=False
    )
    op.create_table(
        "user_role",
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("role_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["role_id"], ["role.id"], name=op.f("fk_user_role_role_id_role"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["user.id"], name=op.f("fk_user_role_user_id_user"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("user_id", "role_id", name=op.f("pk_user_role")),
    )

    # Données de référence : les trois rôles de l'application.
    op.bulk_insert(
        role,
        [
            {"id": 1, "name": "player", "label": "Joueur"},
            {"id": 2, "name": "creator", "label": "Créateur"},
            {"id": 3, "name": "admin", "label": "Administrateur"},
        ],
    )


def downgrade() -> None:
    op.drop_table("user_role")
    op.drop_index(op.f("ix_account_token_user_id"), table_name="account_token")
    op.drop_table("account_token")
    op.drop_table("user")
    op.drop_table("role")
