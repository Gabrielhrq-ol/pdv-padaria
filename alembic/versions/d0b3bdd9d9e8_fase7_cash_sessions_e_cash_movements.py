"""fase7 cash_sessions e cash_movements

Revision ID: d0b3bdd9d9e8
Revises: 85a0a006e786
Create Date: 2026-10-14 20:45:36.076065

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd0b3bdd9d9e8'
down_revision: Union[str, None] = '85a0a006e786'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'cash_sessions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(length=10), nullable=False, server_default='open'),
        sa.Column('opened_by', sa.Integer(), nullable=False),
        sa.Column('opened_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('opening_cash_cents', sa.Integer(), nullable=False),
        sa.Column('closed_by', sa.Integer(), nullable=True),
        sa.Column('closed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('closing_cash_declared_cents', sa.Integer(), nullable=True),
        sa.Column('closing_cash_expected_cents', sa.Integer(), nullable=True),
        sa.Column('closing_difference_cents', sa.Integer(), nullable=True),
        sa.Column('difference_reason', sa.String(length=200), nullable=True),
        sa.Column('notes', sa.String(length=500), nullable=True),
        sa.CheckConstraint("status IN ('open', 'closed')", name='ck_cash_sessions_status'),
        sa.CheckConstraint('opening_cash_cents >= 0', name='ck_cash_sessions_opening_non_negative'),
        sa.CheckConstraint(
            'closing_cash_declared_cents IS NULL OR closing_cash_declared_cents >= 0',
            name='ck_cash_sessions_declared_non_negative',
        ),
        sa.ForeignKeyConstraint(['opened_by'], ['users.id']),
        sa.ForeignKeyConstraint(['closed_by'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('cash_sessions', schema=None) as batch_op:
        batch_op.create_index('ix_cash_sessions_status', ['status'], unique=False)
        batch_op.create_index('ix_cash_sessions_opened_at', ['opened_at'], unique=False)

    op.create_table(
        'cash_movements',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('cash_session_id', sa.Integer(), nullable=False),
        sa.Column('type', sa.String(length=12), nullable=False),
        sa.Column('amount_cents', sa.Integer(), nullable=False),
        sa.Column('reason', sa.String(length=200), nullable=True),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("type IN ('sangria', 'suprimento')", name='ck_cash_movements_type'),
        sa.CheckConstraint('amount_cents > 0', name='ck_cash_movements_amount_positive'),
        sa.ForeignKeyConstraint(['cash_session_id'], ['cash_sessions.id']),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('cash_movements', schema=None) as batch_op:
        batch_op.create_index(
            'ix_cash_movements_session_created',
            ['cash_session_id', 'created_at'],
            unique=False,
        )

    # Setting: cash_session_required default true em producao.
    # (Testes sobrescrevem via fixture no conftest.)
    op.execute(
        "INSERT INTO settings (key, value, updated_at) "
        "VALUES ('cash_session_required', 'true', CURRENT_TIMESTAMP) "
        "ON CONFLICT(key) DO NOTHING"
    )


def downgrade() -> None:
    op.execute("DELETE FROM settings WHERE key = 'cash_session_required'")
    with op.batch_alter_table('cash_movements', schema=None) as batch_op:
        batch_op.drop_index('ix_cash_movements_session_created')
    op.drop_table('cash_movements')
    with op.batch_alter_table('cash_sessions', schema=None) as batch_op:
        batch_op.drop_index('ix_cash_sessions_opened_at')
        batch_op.drop_index('ix_cash_sessions_status')
    op.drop_table('cash_sessions')
