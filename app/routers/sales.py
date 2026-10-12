"""
Rotas de vendas (Fase 3).

- GET  /api/sales/open                  retomar venda em aberto
- POST /api/sales                       cria/retorna venda em aberto
- GET  /api/sales/{id}                  detalhes
- POST /api/sales/{id}/items            adiciona item (code ou product_id)
- PATCH /api/sales/{id}/items/{iid}     altera qty
- DELETE /api/sales/{id}/items/{iid}    remove item
- DELETE /api/sales/{id}                cancela venda em aberto (motivo obrigatorio)

Mutantes: require_authenticated (caixa ou admin) + require_csrf.
Rotas de leitura: require_authenticated.

Audit log registra: sale_opened, sale_item_added/changed/removed, sale_cancelled.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.dependencies import require_authenticated, require_csrf
from app.models import AuditLog, Product, Sale, SaleItem, User
from app.schemas import (
    SaleCancel,
    SaleItemAdd,
    SaleItemUpdate,
    SaleOut,
)
from app.services import sales_service
from app.services.sales_service import SalesError

router = APIRouter(prefix="/api/sales", tags=["sales"])


def _get_sale_404(db: Session, sale_id: int) -> Sale:
    sale = db.get(Sale, sale_id)
    if sale is None:
        raise HTTPException(status_code=404, detail="Venda nao encontrada.")
    return sale


def _audit(
    db: Session,
    *,
    user_id: int,
    action: str,
    entity_id: int,
    details: Optional[str] = None,
    ip: Optional[str] = None,
) -> None:
    db.add(
        AuditLog(
            user_id=user_id,
            action=action,
            entity="sale",
            entity_id=entity_id,
            details=details,
            ip=ip,
        )
    )


def _ip(request: Request) -> Optional[str]:
    return request.client.host if request.client else None


def _raise_sales_error(exc: SalesError) -> None:
    raise HTTPException(status_code=exc.status_code, detail=exc.message)


@router.get("/open", response_model=Optional[SaleOut])
def get_open(
    db: Session = Depends(get_db),
    user: User = Depends(require_authenticated),
) -> Optional[Sale]:
    """Retorna a venda em aberto do operador atual (ou null)."""
    return sales_service.get_open_sale(db, user.id)


@router.post(
    "",
    response_model=SaleOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_csrf)],
)
def open_sale(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_authenticated),
) -> Sale:
    sale = sales_service.create_open_sale(db, user)
    _audit(
        db,
        user_id=user.id,
        action="sale_opened",
        entity_id=sale.id,
        details=f"number={sale.number}",
        ip=_ip(request),
    )
    db.commit()
    db.refresh(sale)
    return sale


@router.get("/{sale_id}", response_model=SaleOut)
def get_sale(
    sale_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_authenticated),
) -> Sale:
    sale = _get_sale_404(db, sale_id)
    # Caixa so vê suas vendas; admin ve tudo.
    if user.role != "admin" and sale.user_id != user.id:
        raise HTTPException(status_code=403, detail="Venda de outro operador.")
    return sale


@router.post(
    "/{sale_id}/items",
    response_model=SaleOut,
    dependencies=[Depends(require_csrf)],
)
def add_item(
    sale_id: int,
    payload: SaleItemAdd,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_authenticated),
) -> Sale:
    sale = _get_sale_404(db, sale_id)
    if user.role != "admin" and sale.user_id != user.id:
        raise HTTPException(status_code=403, detail="Venda de outro operador.")

    # Resolve produto + qty
    product: Product
    qty_milli: int
    if payload.product_id is not None:
        p = db.get(Product, payload.product_id)
        if p is None:
            raise HTTPException(status_code=404, detail="Produto nao encontrado.")
        if not p.active:
            raise HTTPException(status_code=400, detail="Produto inativo.")
        product = p
        qty_milli = payload.qty_milli if payload.qty_milli is not None else 1000
    elif payload.code is not None:
        try:
            resolved = sales_service.resolve_code(db, payload.code)
        except SalesError as exc:
            _raise_sales_error(exc)
        product = resolved.product
        if payload.qty_milli is not None:
            qty_milli = payload.qty_milli
        else:
            # UN: multiplier vira unidades (3*cod = 3 UN = 3000 milesimos)
            # KG/L: multiplier vira unidades (3*cod = 3 kg = 3000 milesimos)
            qty_milli = resolved.qty_multiplier * 1000
    else:
        raise HTTPException(
            status_code=422, detail="Forneca product_id ou code."
        )

    try:
        item = sales_service.add_item(db, sale, product, qty_milli)
    except SalesError as exc:
        _raise_sales_error(exc)

    _audit(
        db,
        user_id=user.id,
        action="sale_item_added",
        entity_id=sale.id,
        details=f"product_id={product.id} qty_milli={qty_milli}",
        ip=_ip(request),
    )
    db.commit()
    db.refresh(sale)
    return sale


@router.patch(
    "/{sale_id}/items/{item_id}",
    response_model=SaleOut,
    dependencies=[Depends(require_csrf)],
)
def change_item(
    sale_id: int,
    item_id: int,
    payload: SaleItemUpdate,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_authenticated),
) -> Sale:
    sale = _get_sale_404(db, sale_id)
    if user.role != "admin" and sale.user_id != user.id:
        raise HTTPException(status_code=403, detail="Venda de outro operador.")

    item = db.get(SaleItem, item_id)
    if item is None or item.sale_id != sale.id:
        raise HTTPException(status_code=404, detail="Item nao encontrado.")

    try:
        sales_service.change_item_qty(db, sale, item, payload.qty_milli)
    except SalesError as exc:
        _raise_sales_error(exc)

    _audit(
        db,
        user_id=user.id,
        action="sale_item_changed",
        entity_id=sale.id,
        details=f"item_id={item_id} qty_milli={payload.qty_milli}",
        ip=_ip(request),
    )
    db.commit()
    db.refresh(sale)
    return sale


@router.delete(
    "/{sale_id}/items/{item_id}",
    response_model=SaleOut,
    dependencies=[Depends(require_csrf)],
)
def remove_item(
    sale_id: int,
    item_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_authenticated),
) -> Sale:
    sale = _get_sale_404(db, sale_id)
    if user.role != "admin" and sale.user_id != user.id:
        raise HTTPException(status_code=403, detail="Venda de outro operador.")
    item = db.get(SaleItem, item_id)
    if item is None or item.sale_id != sale.id:
        raise HTTPException(status_code=404, detail="Item nao encontrado.")

    try:
        sales_service.remove_item(db, sale, item)
    except SalesError as exc:
        _raise_sales_error(exc)

    _audit(
        db,
        user_id=user.id,
        action="sale_item_removed",
        entity_id=sale.id,
        details=f"item_id={item_id}",
        ip=_ip(request),
    )
    db.commit()
    db.refresh(sale)
    return sale


@router.delete(
    "/{sale_id}",
    response_model=SaleOut,
    dependencies=[Depends(require_csrf)],
)
def cancel_sale(
    sale_id: int,
    payload: SaleCancel,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_authenticated),
) -> Sale:
    sale = _get_sale_404(db, sale_id)
    if user.role != "admin" and sale.user_id != user.id:
        raise HTTPException(status_code=403, detail="Venda de outro operador.")

    try:
        sales_service.cancel_sale(db, sale, user, payload.reason)
    except SalesError as exc:
        _raise_sales_error(exc)

    _audit(
        db,
        user_id=user.id,
        action="sale_cancelled",
        entity_id=sale.id,
        details=payload.reason[:200],
        ip=_ip(request),
    )
    db.commit()
    db.refresh(sale)
    return sale
