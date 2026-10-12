"""
Rotas de CRUD de produtos.

Fase 2: autorizacao ativa.
- Leitura (GET): require_authenticated (admin ou caixa).
- Mutacao (POST/PUT/PATCH): require_admin + require_csrf.
- Produto NUNCA e apagado: usa PATCH /{id}/active com {"active": false}.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import get_db
from app.dependencies import require_admin, require_authenticated, require_csrf
from app.models import AuditLog, Product, User
from app.schemas import (
    ActiveUpdate,
    ProductCreate,
    ProductOut,
    ProductUpdate,
)

router = APIRouter(prefix="/api/products", tags=["products"])


def _get_or_404(db: Session, product_id: int) -> Product:
    product = db.get(Product, product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="Produto nao encontrado.")
    return product


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
            entity="product",
            entity_id=entity_id,
            details=details,
            ip=ip,
        )
    )


def _ip(request: Request) -> Optional[str]:
    return request.client.host if request.client else None


# ---------- leitura (admin + caixa) ----------


@router.get("", response_model=list[ProductOut])
def list_products(
    include_inactive: bool = Query(default=False),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    _: User = Depends(require_authenticated),
) -> list[Product]:
    stmt = select(Product).order_by(Product.name).limit(limit).offset(offset)
    if not include_inactive:
        stmt = stmt.where(Product.active.is_(True))
    return list(db.execute(stmt).scalars())


@router.get("/search", response_model=list[ProductOut])
def search_products(
    q: str = Query(..., min_length=1, max_length=120),
    include_inactive: bool = Query(default=False),
    limit: int = Query(default=50, ge=1, le=500),
    db: Session = Depends(get_db),
    _: User = Depends(require_authenticated),
) -> list[Product]:
    q = q.strip()
    like = f"%{q}%"
    stmt = (
        select(Product)
        .where(
            or_(
                Product.barcode == q,
                Product.internal_code == q,
                Product.name.ilike(like),
            )
        )
        .order_by(Product.name)
        .limit(limit)
    )
    if not include_inactive:
        stmt = stmt.where(Product.active.is_(True))
    return list(db.execute(stmt).scalars())


@router.get("/{product_id}", response_model=ProductOut)
def get_product(
    product_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_authenticated),
) -> Product:
    return _get_or_404(db, product_id)


# ---------- mutacao (so admin + CSRF) ----------


@router.post(
    "",
    response_model=ProductOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_csrf)],
)
def create_product(
    payload: ProductCreate,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
) -> Product:
    product = Product(**payload.model_dump(exclude_none=False))
    db.add(product)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail=_integrity_message(exc, "criar"),
        ) from exc
    _audit(
        db,
        user_id=user.id,
        action="product_created",
        entity_id=product.id,
        details=product.name[:200],
        ip=_ip(request),
    )
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail=_integrity_message(exc, "criar"),
        ) from exc
    db.refresh(product)
    return product


@router.put(
    "/{product_id}",
    response_model=ProductOut,
    dependencies=[Depends(require_csrf)],
)
def update_product(
    product_id: int,
    payload: ProductUpdate,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
) -> Product:
    product = _get_or_404(db, product_id)
    data = payload.model_dump(exclude_unset=True)
    for key, value in data.items():
        setattr(product, key, value)
    _audit(
        db,
        user_id=user.id,
        action="product_updated",
        entity_id=product.id,
        details=", ".join(sorted(data.keys()))[:200],
        ip=_ip(request),
    )
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail=_integrity_message(exc, "atualizar"),
        ) from exc
    db.refresh(product)
    return product


@router.patch(
    "/{product_id}/active",
    response_model=ProductOut,
    dependencies=[Depends(require_csrf)],
)
def set_active(
    product_id: int,
    payload: ActiveUpdate,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
) -> Product:
    product = _get_or_404(db, product_id)
    product.active = payload.active
    _audit(
        db,
        user_id=user.id,
        action="product_reactivated" if payload.active else "product_deactivated",
        entity_id=product.id,
        details=product.name[:200],
        ip=_ip(request),
    )
    db.commit()
    db.refresh(product)
    return product


def _integrity_message(exc: IntegrityError, verb: str) -> str:
    text = str(exc.orig).lower() if exc.orig else ""
    if "barcode" in text or "uq_products_barcode" in text:
        return "Codigo de barras ja cadastrado em outro produto."
    if "internal_code" in text or "uq_products_internal_code" in text:
        return "Codigo interno ja cadastrado em outro produto."
    if "foreign key" in text:
        return "Categoria informada nao existe."
    return f"Nao foi possivel {verb} o produto: dados invalidos."
