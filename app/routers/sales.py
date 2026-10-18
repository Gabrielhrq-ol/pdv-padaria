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

from datetime import datetime
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from sqlalchemy import select

from app.db import get_db
from app.dependencies import require_admin, require_authenticated, require_csrf
from app.models import AuditLog, Product, Sale, SaleItem, Setting, User
from app.schemas import (
    FinalizeRequest,
    FinalizeResult,
    ReverseRequest,
    SaleCancel,
    SaleItemAdd,
    SaleItemUpdate,
    SaleOut,
)
from app.services import sales_service
from app.services.printer import PrintJob, get_printer
from app.services.receipt import build_receipt_lines
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


# ---------- Historico de vendas (Fase 15, admin only) ----------


@router.get("", response_model=list[SaleOut])
def list_sales(
    date_from: Optional[datetime] = Query(default=None),
    date_to: Optional[datetime] = Query(default=None),
    status: Optional[Literal["open", "completed", "cancelled"]] = Query(default=None),
    user_id: Optional[int] = Query(default=None, ge=1),
    number: Optional[int] = Query(default=None, ge=1),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> list[Sale]:
    """
    Lista vendas com filtros (admin only). Serve a tela /admin/vendas.
    Ordem: numero decrescente (venda mais recente primeiro).
    """
    stmt = select(Sale)
    if number is not None:
        # busca por numero exato — ignora os outros filtros
        stmt = stmt.where(Sale.number == number)
    else:
        if status is not None:
            stmt = stmt.where(Sale.status == status)
        if user_id is not None:
            stmt = stmt.where(Sale.user_id == user_id)
        if date_from is not None:
            # usa finalized_at pra completed/cancelled, created_at pra open
            stmt = stmt.where(Sale.created_at >= date_from)
        if date_to is not None:
            stmt = stmt.where(Sale.created_at <= date_to)
    stmt = stmt.order_by(Sale.number.desc()).limit(limit).offset(offset)
    return list(db.execute(stmt).scalars())


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


@router.get("/last-completed", response_model=Optional[SaleOut])
def last_completed_route(
    db: Session = Depends(get_db),
    user: User = Depends(require_authenticated),
) -> Optional[Sale]:
    """Ultima venda completed do operador atual (para F10 reimprimir)."""
    return sales_service.get_last_completed(db, user.id)


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


def _settings_dict(db: Session) -> dict[str, str]:
    rows = db.execute(select(Setting)).scalars().all()
    return {r.key: r.value for r in rows}


@router.post(
    "/{sale_id}/finalize",
    response_model=FinalizeResult,
    dependencies=[Depends(require_csrf)],
)
def finalize(
    sale_id: int,
    payload: FinalizeRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_authenticated),
) -> FinalizeResult:
    sale = _get_sale_404(db, sale_id)
    if user.role != "admin" and sale.user_id != user.id:
        raise HTTPException(status_code=403, detail="Venda de outro operador.")
    pays = [(p.method, p.amount_cents) for p in payload.payments]
    try:
        sales_service.finalize_sale(
            db,
            sale,
            user,
            pays,
            discount_cents=payload.discount_cents,
            discount_reason=payload.discount_reason,
        )
    except SalesError as exc:
        db.rollback()
        _raise_sales_error(exc)

    _audit(
        db,
        user_id=user.id,
        action="sale_finalized",
        entity_id=sale.id,
        details=f"total={sale.total_cents} payments={len(sale.payments)}",
        ip=_ip(request),
    )
    db.commit()
    db.refresh(sale)

    # Imprimir (CLAUDE.md regra 6: falha de impressao NAO desfaz venda)
    receipt_lines: list[str] = []
    printed = False
    print_error: Optional[str] = None

    if payload.print_receipt:
        try:
            receipt_lines = build_receipt_lines(
                sale,
                sale.items,
                sale.payments,
                _settings_dict(db),
                operator_name=user.name,
            )
            get_printer(db).print_job(PrintJob(lines=receipt_lines))
            printed = True
        except Exception as exc:  # pragma: no cover - defensivo
            print_error = str(exc)

    return FinalizeResult(
        sale=SaleOut.model_validate(sale),
        receipt_lines=receipt_lines,
        printed=printed,
        print_error=print_error,
    )


@router.post(
    "/{sale_id}/reverse",
    response_model=SaleOut,
    dependencies=[Depends(require_csrf)],
)
def reverse(
    sale_id: int,
    payload: ReverseRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_authenticated),
) -> Sale:
    sale = _get_sale_404(db, sale_id)
    if user.role != "admin" and sale.user_id != user.id:
        raise HTTPException(status_code=403, detail="Venda de outro operador.")

    try:
        sales_service.reverse_sale(db, sale, user, payload.reason)
    except SalesError as exc:
        db.rollback()
        _raise_sales_error(exc)

    _audit(
        db,
        user_id=user.id,
        action="sale_reversed",
        entity_id=sale.id,
        details=payload.reason[:200],
        ip=_ip(request),
    )
    db.commit()
    db.refresh(sale)
    return sale


@router.post(
    "/{sale_id}/reprint",
    response_model=FinalizeResult,
    dependencies=[Depends(require_csrf)],
)
def reprint(
    sale_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_authenticated),
) -> FinalizeResult:
    sale = _get_sale_404(db, sale_id)
    if user.role != "admin" and sale.user_id != user.id:
        raise HTTPException(status_code=403, detail="Venda de outro operador.")
    if sale.status != "completed":
        raise HTTPException(
            status_code=400, detail="So e possivel reimprimir venda completed."
        )

    receipt_lines = build_receipt_lines(
        sale,
        sale.items,
        sale.payments,
        _settings_dict(db),
        is_reprint=True,
        operator_name=user.name,
    )
    printed = False
    print_error: Optional[str] = None
    try:
        get_printer(db).print_job(PrintJob(lines=receipt_lines))
        printed = True
    except Exception as exc:  # pragma: no cover
        print_error = str(exc)

    _audit(
        db,
        user_id=user.id,
        action="sale_reprinted",
        entity_id=sale.id,
        ip=_ip(request),
    )
    db.commit()

    return FinalizeResult(
        sale=SaleOut.model_validate(sale),
        receipt_lines=receipt_lines,
        printed=printed,
        print_error=print_error,
    )


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
