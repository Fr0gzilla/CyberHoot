"""Contenu cyber : types de questions (vrai/faux, phishing, ordre), badges.

Révision : 0004
Précédente : 0003
Créée le : 2026-11-07
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = '0004'
down_revision: str | None = '0003'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    badge = op.create_table('badge',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('code', sa.String(length=40), nullable=False),
    sa.Column('name', sa.String(length=80), nullable=False),
    sa.Column('description', sa.String(length=255), nullable=False),
    sa.Column('icon', sa.String(length=8), nullable=False),
    sa.Column('rule', sa.Enum('parties', 'sans_faute', 'zero', 'serie', 'expert', 'animateur', 'vainqueur', 'createur', name='badge_rule'), nullable=False),
    sa.Column('threshold', sa.Integer(), nullable=False),
    sa.Column('category_id', sa.Integer(), nullable=True),
    sa.Column('position', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['category_id'], ['category.id'], name=op.f('fk_badge_category_id_category'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_badge')),
    sa.UniqueConstraint('code', name=op.f('uq_badge_code'))
    )
    op.create_table('user_badge',
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('badge_id', sa.Integer(), nullable=False),
    sa.Column('obtained_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['badge_id'], ['badge.id'], name=op.f('fk_user_badge_badge_id_badge'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['user.id'], name=op.f('fk_user_badge_user_id_user'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('user_id', 'badge_id', name=op.f('pk_user_badge'))
    )
    with op.batch_alter_table('question', schema=None) as batch_op:
        # Les questions existantes sont des questions à choix : valeur par défaut le temps de
        # l'ajout, retirée ensuite (le modèle n'en a pas).
        batch_op.add_column(sa.Column('kind', sa.Enum('choice', 'true_false', 'phishing', 'order', name='question_kind'), nullable=False, server_default='choice'))
        batch_op.add_column(sa.Column('payload', sa.JSON(), nullable=True))
    with op.batch_alter_table('question', schema=None) as batch_op:
        batch_op.alter_column('kind', server_default=None, existing_type=sa.Enum('choice', 'true_false', 'phishing', 'order', name='question_kind'), existing_nullable=False)

    # Données de référence : les badges (définis ici, et nulle part ailleurs).
    badges = [
        ("premiere-partie", "Premier clic", "Terminer sa toute première partie.", "🐣", "parties", 1, None),
        ("habitue", "Habitué du quiz", "Terminer 10 parties.", "🎮", "parties", 10, None),
        ("accro", "Pare-feu humain", "Terminer 50 parties.", "🧱", "parties", 50, None),
        ("zero-faille", "Zéro faille", "Réussir sans aucune erreur une partie d'au moins 5 questions.", "🛡️", "sans_faute", 5, None),
        ("maillon-faible", "Maillon faible (pour l'instant)", "Finir une partie d'au moins 5 questions… sans une seule bonne réponse. Ça arrive aux meilleurs.", "🙈", "zero", 5, None),
        ("patch-du-jour", "Patch du jour", "Jouer 3 jours de suite.", "📅", "serie", 3, None),
        ("mise-a-jour-hebdo", "Mise à jour hebdomadaire", "Jouer 7 jours de suite.", "🔁", "serie", 7, None),
        ("expert-hameconnage", "Pêcheur repenti", "80 % de bonnes réponses sur au moins 20 questions d'hameçonnage.", "🎣", "expert", 20, 1),
        ("expert-mots-de-passe", "Coffre-fort ambulant", "80 % de bonnes réponses sur au moins 20 questions de mots de passe.", "🔐", "expert", 20, 2),
        ("expert-web", "Gardien du cadenas", "80 % de bonnes réponses sur au moins 20 questions de sécurité web.", "🌐", "expert", 20, 3),
        ("expert-malware", "Chasseur de rançongiciels", "80 % de bonnes réponses sur au moins 20 questions de logiciels malveillants.", "🦠", "expert", 20, 4),
        ("expert-reseaux", "Ondes maîtrisées", "80 % de bonnes réponses sur au moins 20 questions de réseaux et Wi-Fi.", "📶", "expert", 20, 5),
        ("expert-rgpd", "Délégué à la vie privée", "80 % de bonnes réponses sur au moins 20 questions de données personnelles.", "🕵️", "expert", 20, 6),
        ("expert-crypto", "Casseur de César", "80 % de bonnes réponses sur au moins 20 questions de cryptographie.", "🗝️", "expert", 20, 7),
        ("expert-pratiques", "Hygiène numérique", "80 % de bonnes réponses sur au moins 20 questions de bonnes pratiques.", "🧼", "expert", 20, 8),
        ("animateur", "Maître de cérémonie", "Animer une partie en direct d'au moins 3 joueurs.", "🎤", "animateur", 1, None),
        ("vainqueur", "Champion de la salle", "Finir premier d'une partie en direct d'au moins 3 joueurs.", "🏆", "vainqueur", 1, None),
        ("auteur", "Auteur publié", "Voir un de ses quiz publié.", "✍️", "createur", 1, None),
    ]
    op.bulk_insert(badge, [
        {"id": i, "code": code, "name": nom, "description": desc, "icon": icone, "rule": regle,
         "threshold": seuil, "category_id": categorie, "position": i}
        for i, (code, nom, desc, icone, regle, seuil, categorie) in enumerate(badges, start=1)
    ])


def downgrade() -> None:
    with op.batch_alter_table('question', schema=None) as batch_op:
        batch_op.drop_column('payload')
        batch_op.drop_column('kind')

    op.drop_table('user_badge')
    op.drop_table('badge')
