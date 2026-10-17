"""fase11 unit_cost_cents em sale_items

Adiciona snapshot do custo unitario na linha da venda. Permite calcular
margem historica corretamente mesmo se o cost_cents do produto for
atualizado depois.

Nullable: produtos sem custo cadastrado nao travam a venda; linhas
anteriores a migracao ficam NULL e sao ignoradas no calculo de margem.

Revision ID: a29d4283435d
Revises: d0b3bdd9d9e8
Create Date: 2026-10-16 23:31:59.243656

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a29d4283435d'
down_revision: Union[str, None] = 'd0b3bdd9d9e8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('sale_items', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('unit_cost_cents', sa.Integer(), nullable=True)
        )
        batch_op.create_check_constraint(
            'ck_sale_items_cost_non_negative',
            'unit_cost_cents IS NULL OR unit_cost_cents >= 0',
        )


def downgrade() -> None:
    with op.batch_alter_table('sale_items', schema=None) as batch_op:
        batch_op.drop_constraint(
            'ck_sale_items_cost_non_negative', type_='check'
        )
        batch_op.drop_column('unit_cost_cents')
