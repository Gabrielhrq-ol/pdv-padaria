"""
Servico de gestao de estoque (Fase 6).

Operacoes manuais (fora do fluxo de venda):
- register_entry: entrada de mercadoria. Motivo OPCIONAL (decisao do
  dono 2026-10-14; evolui a decisao 9 do CLAUDE.md).
- register_loss: perda. Motivo OBRIGATORIO.
- register_adjustment: ajuste de inventario para um novo saldo absoluto.
  Produto deve estar ATIVO. Motivo OBRIGATORIO.
- list_movements: historico filtravel.
- list_low_stock: produtos ativos abaixo do minimo.

Cada operacao mutante:
1. Grava em stock_movements (livro-razao).
2. Atualiza products.stock_milli (snapshot).
3. Grava audit_log.
4. Faz commit atomico (ou raise -> rollback).

Invariante preservada:
    product.stock_milli == soma(stock_movements[product].qty_milli)
    (sob a hipotese que stock_milli inicial e 0 em todo produto novo,
    o que e verdade pelos defaults do modelo).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AuditLog, Product, StockMovement, User


class StockError(Exception):
    """Erro de regra de negocio em estoque."""

    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


# ---------- helpers ----------


def _get_active_product(db: Session, product_id: int) -> Product:
    product = db.get(Product, product_id)
    if product is None:
        raise StockError(f"Produto nao encontrado: {product_id}", 404)
    if not product.active:
        raise StockError(f"Produto inativo: {product.name}", 400)
    return product


def _audit(
    db: Session,
    *,
    user_id: int,
    action: str,
    entity_id: Optional[int],
    details: Optional[str] = None,
) -> None:
    db.add(
        AuditLog(
            user_id=user_id,
            action=action,
            entity="product",
            entity_id=entity_id,
            details=details,
        )
    )


# ---------- operacoes ----------


def register_entry(
    db: Session,
    *,
    user: User,
    product_id: int,
    qty_milli: int,
    reason: Optional[str] = None,
) -> StockMovement:
    """
    Entrada de mercadoria. qty_milli > 0 obrigatorio. reason opcional.
    """
    if type(qty_milli) is not int:
        raise StockError("qty_milli deve ser int.", 422)
    if qty_milli <= 0:
        raise StockError("qty_milli deve ser > 0.", 422)

    product = _get_active_product(db, product_id)

    clean_reason: Optional[str] = None
    if reason is not None:
        s = reason.strip()
        if s:
            if len(s) > 200:
                raise StockError("Motivo acima de 200 caracteres.", 422)
            clean_reason = s

    movement = StockMovement(
        product_id=product.id,
        type="entrada",
        qty_milli=qty_milli,
        reason=clean_reason,
        sale_id=None,
        user_id=user.id,
    )
    db.add(movement)
    product.stock_milli = product.stock_milli + qty_milli

    _audit(
        db,
        user_id=user.id,
        action="stock_entry",
        entity_id=product.id,
        details=f"product={product.name[:40]} qty={qty_milli}",
    )
    db.commit()
    db.refresh(movement)
    return movement


def register_loss(
    db: Session,
    *,
    user: User,
    product_id: int,
    qty_milli: int,
    reason: str,
) -> StockMovement:
    """
    Perda de mercadoria. qty_milli > 0 obrigatorio; e armazenado como
    negativo (saida). reason OBRIGATORIO (min 3 chars uteis).
    """
    if type(qty_milli) is not int:
        raise StockError("qty_milli deve ser int.", 422)
    if qty_milli <= 0:
        raise StockError("qty_milli deve ser > 0.", 422)
    if not isinstance(reason, str) or not reason.strip() or len(reason.strip()) < 3:
        raise StockError("Motivo obrigatorio (min 3 caracteres).", 422)
    clean_reason = reason.strip()
    if len(clean_reason) > 200:
        raise StockError("Motivo acima de 200 caracteres.", 422)

    product = _get_active_product(db, product_id)

    movement = StockMovement(
        product_id=product.id,
        type="perda",
        qty_milli=-qty_milli,
        reason=clean_reason,
        sale_id=None,
        user_id=user.id,
    )
    db.add(movement)
    product.stock_milli = product.stock_milli - qty_milli

    _audit(
        db,
        user_id=user.id,
        action="stock_loss",
        entity_id=product.id,
        details=f"product={product.name[:40]} qty={qty_milli} reason={clean_reason[:60]}",
    )
    db.commit()
    db.refresh(movement)
    return movement


def register_adjustment(
    db: Session,
    *,
    user: User,
    product_id: int,
    new_stock_milli: int,
    reason: str,
) -> StockMovement:
    """
    Ajuste de inventario. Define novo saldo absoluto >= 0. Produto deve
    estar ATIVO (decisao do dono 2026-10-14: para ajustar produto
    descontinuado, admin reativa primeiro). Motivo OBRIGATORIO.
    Erro se delta == 0 (nada a ajustar).
    """
    if type(new_stock_milli) is not int:
        raise StockError("new_stock_milli deve ser int.", 422)
    if new_stock_milli < 0:
        raise StockError("new_stock_milli nao pode ser negativo.", 422)
    if not isinstance(reason, str) or not reason.strip() or len(reason.strip()) < 3:
        raise StockError("Motivo obrigatorio (min 3 caracteres).", 422)
    clean_reason = reason.strip()
    if len(clean_reason) > 200:
        raise StockError("Motivo acima de 200 caracteres.", 422)

    product = _get_active_product(db, product_id)
    delta = new_stock_milli - product.stock_milli
    if delta == 0:
        raise StockError("Novo saldo igual ao atual. Nada a ajustar.", 422)

    movement = StockMovement(
        product_id=product.id,
        type="ajuste",
        qty_milli=delta,  # signed
        reason=clean_reason,
        sale_id=None,
        user_id=user.id,
    )
    db.add(movement)
    product.stock_milli = new_stock_milli

    _audit(
        db,
        user_id=user.id,
        action="stock_adjustment",
        entity_id=product.id,
        details=(
            f"product={product.name[:40]} delta={delta} "
            f"new={new_stock_milli} reason={clean_reason[:60]}"
        ),
    )
    db.commit()
    db.refresh(movement)
    return movement


# ---------- consultas ----------


@dataclass
class MovementRow:
    """Linha serializavel para StockMovementOut."""

    id: int
    product_id: int
    product_name: str
    product_unit: str
    type: str
    qty_milli: int
    reason: Optional[str]
    sale_id: Optional[int]
    user_id: int
    user_name: Optional[str]
    created_at: datetime


def list_movements(
    db: Session,
    *,
    product_id: Optional[int] = None,
    type_: Optional[str] = None,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    limit: int = 100,
    offset: int = 0,
) -> list[MovementRow]:
    """
    Historico paginado, mais recentes primeiro. Filtros opcionais:
    product_id, type (ex 'entrada'), date_from/date_to (UTC naive).
    """
    if limit <= 0 or limit > 500:
        limit = 100
    if offset < 0:
        offset = 0

    stmt = (
        select(StockMovement, Product, User)
        .join(Product, Product.id == StockMovement.product_id)
        .join(User, User.id == StockMovement.user_id)
        .order_by(StockMovement.created_at.desc(), StockMovement.id.desc())
    )
    if product_id is not None:
        stmt = stmt.where(StockMovement.product_id == product_id)
    if type_ is not None:
        stmt = stmt.where(StockMovement.type == type_)
    if date_from is not None:
        stmt = stmt.where(StockMovement.created_at >= date_from)
    if date_to is not None:
        stmt = stmt.where(StockMovement.created_at <= date_to)
    stmt = stmt.limit(limit).offset(offset)

    rows: list[MovementRow] = []
    for mv, product, user in db.execute(stmt).all():
        rows.append(
            MovementRow(
                id=mv.id,
                product_id=product.id,
                product_name=product.name,
                product_unit=product.unit,
                type=mv.type,
                qty_milli=mv.qty_milli,
                reason=mv.reason,
                sale_id=mv.sale_id,
                user_id=user.id,
                user_name=user.name,
                created_at=mv.created_at,
            )
        )
    return rows


@dataclass
class LowStockRow:
    product_id: int
    product_name: str
    unit: str
    stock_milli: int
    min_stock_milli: int


def list_low_stock(db: Session) -> list[LowStockRow]:
    """
    Produtos ATIVOS onde stock_milli <= min_stock_milli AND
    min_stock_milli > 0 (so alerta quem configurou um minimo). Ordena
    pela "profundidade" do deficit (menor saldo primeiro).
    """
    stmt = (
        select(Product)
        .where(Product.active.is_(True))
        .where(Product.min_stock_milli > 0)
        .where(Product.stock_milli <= Product.min_stock_milli)
        .order_by(Product.stock_milli.asc(), Product.name.asc())
    )
    rows: list[LowStockRow] = []
    for product in db.execute(stmt).scalars().all():
        rows.append(
            LowStockRow(
                product_id=product.id,
                product_name=product.name,
                unit=product.unit,
                stock_milli=product.stock_milli,
                min_stock_milli=product.min_stock_milli,
            )
        )
    return rows
