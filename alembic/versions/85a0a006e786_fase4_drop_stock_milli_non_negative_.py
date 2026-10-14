"""fase4 drop stock_milli non-negative constraint (decisao 9)

Revision ID: 85a0a006e786
Revises: 224a49b53db9
Create Date: 2026-10-13 20:59:02.670610

Decisao 9 do cliente: padaria produz propria mercadoria, NUNCA bloquear
venda por estoque zero/negativo. O constraint CHECK stock_milli >= 0
precisa sair.
"""
from typing import Sequence, Union

from alembic import op


revision: str = '85a0a006e786'
down_revision: Union[str, None] = '224a49b53db9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('products', schema=None) as batch_op:
        batch_op.drop_constraint(
            'ck_products_stock_non_negative', type_='check'
        )


def downgrade() -> None:
    with op.batch_alter_table('products', schema=None) as batch_op:
        batch_op.create_check_constraint(
            'ck_products_stock_non_negative', 'stock_milli >= 0'
        )
