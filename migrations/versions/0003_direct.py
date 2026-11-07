"""Parties en direct : salles (PIN), joueurs, réponses.

Révision : 0003
Précédente : 0002
Créée le : 2026-11-07
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = '0003'
down_revision: str | None = '0002'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table('live_game',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('pin', sa.String(length=6), nullable=True),
    sa.Column('host_id', sa.Integer(), nullable=True),
    sa.Column('quiz_id', sa.Integer(), nullable=False),
    sa.Column('status', sa.Enum('lobby', 'question', 'paused', 'reveal', 'finished', name='live_status'), nullable=False),
    sa.Column('question_ids', sa.JSON(), nullable=False),
    sa.Column('current_index', sa.Integer(), nullable=False),
    sa.Column('time_limit', sa.Integer(), nullable=False),
    sa.Column('max_players', sa.Integer(), nullable=False),
    sa.Column('question_started_at', sa.DateTime(), nullable=True),
    sa.Column('question_deadline', sa.DateTime(), nullable=True),
    sa.Column('paused_remaining_ms', sa.Integer(), nullable=True),
    sa.Column('version', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('last_activity_at', sa.DateTime(), nullable=False),
    sa.Column('ended_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['host_id'], ['user.id'], name=op.f('fk_live_game_host_id_user'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['quiz_id'], ['quiz.id'], name=op.f('fk_live_game_quiz_id_quiz'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_live_game')),
    sa.UniqueConstraint('pin', name=op.f('uq_live_game_pin'))
    )
    with op.batch_alter_table('live_game', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_live_game_host_id'), ['host_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_live_game_quiz_id'), ['quiz_id'], unique=False)

    op.create_table('live_player',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('game_id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=True),
    sa.Column('nickname', sa.String(length=20), nullable=False),
    sa.Column('nickname_key', sa.String(length=20), nullable=False),
    sa.Column('token', sa.String(length=43), nullable=False),
    sa.Column('score', sa.Integer(), nullable=False),
    sa.Column('kicked', sa.Boolean(), nullable=False),
    sa.Column('joined_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['game_id'], ['live_game.id'], name=op.f('fk_live_player_game_id_live_game'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['user.id'], name=op.f('fk_live_player_user_id_user'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_live_player')),
    sa.UniqueConstraint('game_id', 'nickname_key', name='pseudo_unique'),
    sa.UniqueConstraint('token', name=op.f('uq_live_player_token'))
    )
    with op.batch_alter_table('live_player', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_live_player_game_id'), ['game_id'], unique=False)

    op.create_table('live_answer',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('game_id', sa.Integer(), nullable=False),
    sa.Column('player_id', sa.Integer(), nullable=False),
    sa.Column('position', sa.Integer(), nullable=False),
    sa.Column('question_id', sa.Integer(), nullable=True),
    sa.Column('selected_ids', sa.JSON(), nullable=False),
    sa.Column('is_correct', sa.Boolean(), nullable=False),
    sa.Column('points', sa.Integer(), nullable=False),
    sa.Column('elapsed_ms', sa.Integer(), nullable=False),
    sa.Column('answered_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['game_id'], ['live_game.id'], name=op.f('fk_live_answer_game_id_live_game'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['player_id'], ['live_player.id'], name=op.f('fk_live_answer_player_id_live_player'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['question_id'], ['question.id'], name=op.f('fk_live_answer_question_id_question'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_live_answer')),
    sa.UniqueConstraint('player_id', 'position', name='une_reponse_par_question')
    )
    with op.batch_alter_table('live_answer', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_live_answer_game_id'), ['game_id'], unique=False)



def downgrade() -> None:
    with op.batch_alter_table('live_answer', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_live_answer_game_id'))

    op.drop_table('live_answer')
    with op.batch_alter_table('live_player', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_live_player_game_id'))

    op.drop_table('live_player')
    with op.batch_alter_table('live_game', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_live_game_quiz_id'))
        batch_op.drop_index(batch_op.f('ix_live_game_host_id'))

    op.drop_table('live_game')
