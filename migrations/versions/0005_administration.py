"""Administration : journal d'audit, signalements, double authentification.

Révision : 0005
Précédente : 0004
Créée le : 2026-11-07
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = '0005'
down_revision: str | None = '0004'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table('audit_log',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=True),
    sa.Column('username', sa.String(length=32), nullable=True),
    sa.Column('ip', sa.String(length=45), nullable=True),
    sa.Column('action', sa.String(length=40), nullable=False),
    sa.Column('target', sa.String(length=120), nullable=True),
    sa.Column('details', sa.JSON(), nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['user.id'], name=op.f('fk_audit_log_user_id_user'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_audit_log'))
    )
    with op.batch_alter_table('audit_log', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_audit_log_action'), ['action'], unique=False)
        batch_op.create_index(batch_op.f('ix_audit_log_created_at'), ['created_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_audit_log_user_id'), ['user_id'], unique=False)

    op.create_table('recovery_code',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('code_hash', sa.String(length=64), nullable=False),
    sa.Column('used_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['user.id'], name=op.f('fk_recovery_code_user_id_user'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_recovery_code')),
    sa.UniqueConstraint('code_hash', name=op.f('uq_recovery_code_code_hash'))
    )
    with op.batch_alter_table('recovery_code', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_recovery_code_user_id'), ['user_id'], unique=False)

    op.create_table('report',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('reporter_id', sa.Integer(), nullable=True),
    sa.Column('quiz_id', sa.Integer(), nullable=True),
    sa.Column('review_id', sa.Integer(), nullable=True),
    sa.Column('reason', sa.String(length=500), nullable=False),
    sa.Column('status', sa.Enum('open', 'closed', name='report_status'), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('handled_at', sa.DateTime(), nullable=True),
    sa.Column('handled_by_id', sa.Integer(), nullable=True),
    sa.Column('resolution', sa.String(length=255), nullable=True),
    sa.ForeignKeyConstraint(['handled_by_id'], ['user.id'], name=op.f('fk_report_handled_by_id_user'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['quiz_id'], ['quiz.id'], name=op.f('fk_report_quiz_id_quiz'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['reporter_id'], ['user.id'], name=op.f('fk_report_reporter_id_user'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['review_id'], ['review.id'], name=op.f('fk_report_review_id_review'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_report'))
    )
    with op.batch_alter_table('report', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_report_quiz_id'), ['quiz_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_report_status'), ['status'], unique=False)

    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.add_column(sa.Column('totp_secret', sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column('totp_enabled_at', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column('totp_last_step', sa.Integer(), nullable=True))



def downgrade() -> None:
    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.drop_column('totp_last_step')
        batch_op.drop_column('totp_enabled_at')
        batch_op.drop_column('totp_secret')

    with op.batch_alter_table('report', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_report_status'))
        batch_op.drop_index(batch_op.f('ix_report_quiz_id'))

    op.drop_table('report')
    with op.batch_alter_table('recovery_code', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_recovery_code_user_id'))

    op.drop_table('recovery_code')
    with op.batch_alter_table('audit_log', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_audit_log_user_id'))
        batch_op.drop_index(batch_op.f('ix_audit_log_created_at'))
        batch_op.drop_index(batch_op.f('ix_audit_log_action'))

    op.drop_table('audit_log')
