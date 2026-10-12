"""
Logica central de vendas. Funcao pura testavel (recebe Session).

Fase 3: criar venda em open, adicionar/alterar/remover item, cancelar.
Agrupamento automatico de item (mesma product_id = soma qty).
Preco COPIADO do produto no momento do add (CLAUDE.md regra 4).

Fase 4 vai adicionar `finalize_sale` com transacao atomica
(itens, pagamentos, baixa de estoque, movimentos).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models import Product, Sale, SaleItem, User
from app.money import line_total_cents


class SalesError(Exception):
    """Erro de regra de negocio em vendas."""

    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


@dataclass
class ResolvedCode:
    product: Product
    qty_multiplier: int  # vezes 1 (default) ou N do "N*codigo"


# ---------- resolucao de codigo ----------

_CODE_RE = re.compile(r"^\s*(?:(\d{1,4})\s*\*\s*)?([A-Za-z0-9]+)\s*$")


def resolve_code(db: Session, code: str) -> ResolvedCode:
    """
    Resolve `barcode` ou `internal_code` ou `N*codigo`.
    - "7891111111117" -> product + qty_multiplier=1
    - "101" -> product + qty_multiplier=1
    - "3*101" -> product + qty_multiplier=3
    """
    if not isinstance(code, str) or not code.strip():
        raise SalesError("Codigo vazio.", 422)
    m = _CODE_RE.match(code)
    if not m:
        raise SalesError(f"Codigo invalido: {code!r}", 422)
    qty_str, body = m.groups()
    multiplier = int(qty_str) if qty_str else 1
    if multiplier < 1 or multiplier > 1000:
        raise SalesError("Multiplicador fora do intervalo 1..1000.", 422)

    product = db.execute(
        select(Product).where(
            or_(Product.barcode == body, Product.internal_code == body)
        )
    ).scalar_one_or_none()
    if product is None:
        raise SalesError(f"Produto nao encontrado: {body}", 404)
    if not product.active:
        raise SalesError(f"Produto inativo: {product.name}", 400)
    return ResolvedCode(product=product, qty_multiplier=multiplier)


# ---------- venda em aberto ----------


def get_open_sale(db: Session, user_id: int) -> Optional[Sale]:
    return db.execute(
        select(Sale).where(Sale.user_id == user_id, Sale.status == "open")
    ).scalar_one_or_none()


def _next_sale_number(db: Session) -> int:
    """Sequencial unico por ano. Simplificado: max+1 global."""
    max_number = db.execute(select(func.max(Sale.number))).scalar() or 0
    return max_number + 1


def create_open_sale(db: Session, user: User) -> Sale:
    """
    Cria venda nova em open. Se o operador ja tem uma aberta, devolve a
    existente (idempotente, 1 venda ativa por operador).
    """
    existing = get_open_sale(db, user.id)
    if existing is not None:
        return existing
    sale = Sale(
        number=_next_sale_number(db),
        user_id=user.id,
        status="open",
        subtotal_cents=0,
        discount_cents=0,
        total_cents=0,
    )
    db.add(sale)
    db.flush()
    return sale


# ---------- itens ----------


def _recalculate_totals(sale: Sale) -> None:
    subtotal = sum(item.line_total_cents for item in sale.items)
    sale.subtotal_cents = subtotal
    sale.total_cents = max(subtotal - sale.discount_cents, 0)


def _assert_open(sale: Sale) -> None:
    if sale.status != "open":
        raise SalesError(
            f"Venda nao esta aberta (status={sale.status}).", 409
        )


def _find_item(sale: Sale, product_id: int) -> Optional[SaleItem]:
    for it in sale.items:
        if it.product_id == product_id:
            return it
    return None


def add_item(
    db: Session,
    sale: Sale,
    product: Product,
    qty_milli: int,
) -> SaleItem:
    """
    Adiciona (ou agrupa) item na venda em aberto. Copia name/barcode/unit/price.
    """
    _assert_open(sale)
    if not product.active:
        raise SalesError(f"Produto inativo: {product.name}", 400)
    if type(qty_milli) is not int or qty_milli <= 0:
        raise SalesError("Quantidade deve ser inteiro positivo.", 422)

    existing = _find_item(sale, product.id)
    if existing is not None:
        new_qty = existing.qty_milli + qty_milli
        existing.qty_milli = new_qty
        existing.line_total_cents = line_total_cents(
            existing.unit_price_cents, new_qty
        )
        db.flush()
        _recalculate_totals(sale)
        db.flush()
        return existing

    item = SaleItem(
        sale_id=sale.id,
        product_id=product.id,
        product_name=product.name,
        barcode=product.barcode,
        internal_code=product.internal_code,
        unit=product.unit,
        unit_price_cents=product.price_cents,
        qty_milli=qty_milli,
        line_total_cents=line_total_cents(product.price_cents, qty_milli),
    )
    db.add(item)
    sale.items.append(item)
    db.flush()
    _recalculate_totals(sale)
    db.flush()
    return item


def change_item_qty(
    db: Session, sale: Sale, item: SaleItem, qty_milli: int
) -> SaleItem:
    _assert_open(sale)
    if type(qty_milli) is not int or qty_milli <= 0:
        raise SalesError("Quantidade deve ser inteiro positivo.", 422)
    item.qty_milli = qty_milli
    item.line_total_cents = line_total_cents(item.unit_price_cents, qty_milli)
    db.flush()
    _recalculate_totals(sale)
    db.flush()
    return item


def remove_item(db: Session, sale: Sale, item: SaleItem) -> None:
    _assert_open(sale)
    sale.items.remove(item)
    db.delete(item)
    db.flush()
    _recalculate_totals(sale)
    db.flush()


def cancel_sale(
    db: Session,
    sale: Sale,
    user: User,
    reason: str,
) -> Sale:
    _assert_open(sale)
    reason = reason.strip()
    if not reason:
        raise SalesError("Motivo obrigatorio.", 422)
    sale.status = "cancelled"
    sale.cancel_reason = reason[:200]
    sale.cancelled_by = user.id
    db.flush()
    return sale
