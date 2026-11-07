"""Quiz : catégories, quiz, questions, réponses, médias, parties en solo, avis.

Révision : 0002
Précédente : 0001
Créée le : 2026-11-07
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = '0002'
down_revision: str | None = '0001'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    category = op.create_table('category',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('slug', sa.String(length=40), nullable=False),
    sa.Column('name', sa.String(length=80), nullable=False),
    sa.Column('description', sa.String(length=255), nullable=False),
    sa.Column('position', sa.Integer(), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_category')),
    sa.UniqueConstraint('slug', name=op.f('uq_category_slug'))
    )
    op.create_table('media',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('uid', sa.String(length=32), nullable=False),
    sa.Column('owner_id', sa.Integer(), nullable=True),
    sa.Column('mime_type', sa.String(length=30), nullable=False),
    sa.Column('size', sa.Integer(), nullable=False),
    sa.Column('sha256', sa.String(length=64), nullable=False),
    sa.Column('status', sa.Enum('pending', 'clean', 'rejected', name='media_status'), nullable=False),
    sa.Column('scan_detail', sa.String(length=255), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('scanned_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['owner_id'], ['user.id'], name=op.f('fk_media_owner_id_user'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_media')),
    sa.UniqueConstraint('uid', name=op.f('uq_media_uid'))
    )
    with op.batch_alter_table('media', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_media_owner_id'), ['owner_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_media_sha256'), ['sha256'], unique=False)
        batch_op.create_index(batch_op.f('ix_media_status'), ['status'], unique=False)

    op.create_table('quiz',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('creator_id', sa.Integer(), nullable=True),
    sa.Column('category_id', sa.Integer(), nullable=False),
    sa.Column('title', sa.String(length=120), nullable=False),
    sa.Column('description', sa.String(length=500), nullable=False),
    sa.Column('difficulty', sa.Enum('easy', 'medium', 'hard', name='difficulty'), nullable=False),
    sa.Column('status', sa.Enum('draft', 'pending', 'published', 'rejected', name='quiz_status'), nullable=False),
    sa.Column('rejection_reason', sa.String(length=500), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.Column('submitted_at', sa.DateTime(), nullable=True),
    sa.Column('published_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['category_id'], ['category.id'], name=op.f('fk_quiz_category_id_category'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['creator_id'], ['user.id'], name=op.f('fk_quiz_creator_id_user'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_quiz'))
    )
    with op.batch_alter_table('quiz', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_quiz_category_id'), ['category_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_quiz_creator_id'), ['creator_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_quiz_status'), ['status'], unique=False)

    op.create_table('play_session',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('token', sa.String(length=43), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=True),
    sa.Column('quiz_id', sa.Integer(), nullable=False),
    sa.Column('question_ids', sa.JSON(), nullable=False),
    sa.Column('current_index', sa.Integer(), nullable=False),
    sa.Column('score', sa.Integer(), nullable=False),
    sa.Column('total', sa.Integer(), nullable=False),
    sa.Column('started_at', sa.DateTime(), nullable=False),
    sa.Column('finished_at', sa.DateTime(), nullable=True),
    sa.CheckConstraint('current_index >= 0', name=op.f('ck_play_session_index_positif')),
    sa.CheckConstraint('score >= 0', name=op.f('ck_play_session_score_positif')),
    sa.ForeignKeyConstraint(['quiz_id'], ['quiz.id'], name=op.f('fk_play_session_quiz_id_quiz'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['user.id'], name=op.f('fk_play_session_user_id_user'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_play_session')),
    sa.UniqueConstraint('token', name=op.f('uq_play_session_token'))
    )
    with op.batch_alter_table('play_session', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_play_session_quiz_id'), ['quiz_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_play_session_user_id'), ['user_id'], unique=False)

    op.create_table('question',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('quiz_id', sa.Integer(), nullable=False),
    sa.Column('position', sa.Integer(), nullable=False),
    sa.Column('text', sa.String(length=500), nullable=False),
    sa.Column('explanation', sa.Text(), nullable=False),
    sa.Column('media_id', sa.Integer(), nullable=True),
    sa.Column('media_alt', sa.String(length=200), nullable=True),
    sa.ForeignKeyConstraint(['media_id'], ['media.id'], name=op.f('fk_question_media_id_media'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['quiz_id'], ['quiz.id'], name=op.f('fk_question_quiz_id_quiz'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_question')),
    sa.UniqueConstraint('quiz_id', 'position', name='quiz_position')
    )
    op.create_table('review',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('quiz_id', sa.Integer(), nullable=False),
    sa.Column('rating', sa.Integer(), nullable=False),
    sa.Column('comment', sa.String(length=1000), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.CheckConstraint('rating BETWEEN 1 AND 5', name=op.f('ck_review_note_1_a_5')),
    sa.ForeignKeyConstraint(['quiz_id'], ['quiz.id'], name=op.f('fk_review_quiz_id_quiz'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['user.id'], name=op.f('fk_review_user_id_user'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_review')),
    sa.UniqueConstraint('user_id', 'quiz_id', name='un_avis_par_joueur')
    )
    with op.batch_alter_table('review', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_review_quiz_id'), ['quiz_id'], unique=False)

    op.create_table('answer_option',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('question_id', sa.Integer(), nullable=False),
    sa.Column('position', sa.Integer(), nullable=False),
    sa.Column('text', sa.String(length=300), nullable=False),
    sa.Column('is_correct', sa.Boolean(), nullable=False),
    sa.ForeignKeyConstraint(['question_id'], ['question.id'], name=op.f('fk_answer_option_question_id_question'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_answer_option')),
    sa.UniqueConstraint('question_id', 'position', name='question_position')
    )
    op.create_table('play_answer',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('session_id', sa.Integer(), nullable=False),
    sa.Column('position', sa.Integer(), nullable=False),
    sa.Column('question_id', sa.Integer(), nullable=True),
    sa.Column('selected_ids', sa.JSON(), nullable=False),
    sa.Column('is_correct', sa.Boolean(), nullable=False),
    sa.Column('answered_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['question_id'], ['question.id'], name=op.f('fk_play_answer_question_id_question'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['session_id'], ['play_session.id'], name=op.f('fk_play_answer_session_id_play_session'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_play_answer')),
    sa.UniqueConstraint('session_id', 'position', name='session_position')
    )
    with op.batch_alter_table('play_answer', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_play_answer_question_id'), ['question_id'], unique=False)

    # Données de référence : les catégories de la plateforme.
    op.bulk_insert(
        category,
        [
            {"id": 1, "slug": "hameconnage", "name": "Hameçonnage et ingénierie sociale", "position": 1,
             "description": "Repérer les faux messages, appels et sites qui cherchent à vous manipuler."},
            {"id": 2, "slug": "mots-de-passe", "name": "Mots de passe et authentification", "position": 2,
             "description": "Choisir, retenir et protéger ses mots de passe ; la double authentification."},
            {"id": 3, "slug": "securite-web", "name": "Sécurité web", "position": 3,
             "description": "Naviguer prudemment : HTTPS, téléchargements, extensions, failles courantes."},
            {"id": 4, "slug": "logiciels-malveillants", "name": "Logiciels malveillants", "position": 4,
             "description": "Virus, rançongiciels, chevaux de Troie : comment ils arrivent et comment s'en protéger."},
            {"id": 5, "slug": "reseaux-wifi", "name": "Réseaux et Wi-Fi", "position": 5,
             "description": "Wi-Fi public, box, VPN : sécuriser ses connexions."},
            {"id": 6, "slug": "donnees-rgpd", "name": "Données personnelles et RGPD", "position": 6,
             "description": "Protéger sa vie privée et connaître ses droits."},
            {"id": 7, "slug": "cryptographie", "name": "Cryptographie", "position": 7,
             "description": "Chiffrement, signatures, certificats : les bases expliquées simplement."},
            {"id": 8, "slug": "bonnes-pratiques", "name": "Bonnes pratiques au quotidien", "position": 8,
             "description": "Mises à jour, sauvegardes, verrouillage : les gestes qui protègent."},
        ],
    )


def downgrade() -> None:
    with op.batch_alter_table('play_answer', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_play_answer_question_id'))

    op.drop_table('play_answer')
    op.drop_table('answer_option')
    with op.batch_alter_table('review', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_review_quiz_id'))

    op.drop_table('review')
    op.drop_table('question')
    with op.batch_alter_table('play_session', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_play_session_user_id'))
        batch_op.drop_index(batch_op.f('ix_play_session_quiz_id'))

    op.drop_table('play_session')
    with op.batch_alter_table('quiz', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_quiz_status'))
        batch_op.drop_index(batch_op.f('ix_quiz_creator_id'))
        batch_op.drop_index(batch_op.f('ix_quiz_category_id'))

    op.drop_table('quiz')
    with op.batch_alter_table('media', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_media_status'))
        batch_op.drop_index(batch_op.f('ix_media_sha256'))
        batch_op.drop_index(batch_op.f('ix_media_owner_id'))

    op.drop_table('media')
    op.drop_table('category')
