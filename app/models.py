"""
Modelos SQLAlchemy 2.x do PDV.

Fase 1: User, Category, Product, Setting.
Outras tabelas (sales, sale_items, payments, stock_movements, cash_*,
audit_log) entram nas Fases 4+ via migrations incrementais.

Convencoes:
- Dinheiro em centavos (int). Quantidade em milesimos (int).
- Produto nunca e apagado: active=False.
- created_at / updated_at com timezone UTC.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def utc_now() -> datetime:
    """Naive UTC. Alinhado com app.security.utc_now."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class User(Base):
    """Usuario do sistema. Fase 2 implementa autenticacao + bloqueio."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    username: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(10), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    # Fase 2: controle de tentativas de login
    failed_login_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    locked_until: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_login_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    __table_args__ = (
        CheckConstraint("role IN ('admin', 'caixa')", name="ck_users_role"),
        CheckConstraint(
            "failed_login_count >= 0", name="ck_users_failed_count_non_negative"
        ),
    )


class Category(Base):
    """Categoria de produto (padaria, bebida, salgado, bolo etc.)."""

    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(60), nullable=False, unique=True)

    products: Mapped[list["Product"]] = relationship(back_populates="category")


class Product(Base):
    """
    Produto vendido na padaria.

    - Dinheiro em centavos (int).
    - Estoque em milesimos (int).
    - Produto nunca e apagado: active=False desativa.
    """

    __tablename__ = "products"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    barcode: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    internal_code: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    category_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("categories.id"), nullable=True
    )
    unit: Mapped[str] = mapped_column(String(3), nullable=False)
    price_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    cost_cents: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    stock_milli: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    min_stock_milli: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    favorite: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )

    category: Mapped[Optional["Category"]] = relationship(back_populates="products")

    __table_args__ = (
        UniqueConstraint("barcode", name="uq_products_barcode"),
        UniqueConstraint("internal_code", name="uq_products_internal_code"),
        CheckConstraint("unit IN ('UN', 'KG', 'L')", name="ck_products_unit"),
        CheckConstraint("price_cents >= 0", name="ck_products_price_non_negative"),
        CheckConstraint(
            "cost_cents IS NULL OR cost_cents >= 0",
            name="ck_products_cost_non_negative",
        ),
        CheckConstraint("stock_milli >= 0", name="ck_products_stock_non_negative"),
        CheckConstraint(
            "min_stock_milli >= 0", name="ck_products_min_stock_non_negative"
        ),
        Index("ix_products_barcode", "barcode"),
        Index("ix_products_internal_code", "internal_code"),
        Index("ix_products_name", "name"),
        Index("ix_products_active", "active"),
    )


class AuditLog(Base):
    """
    Registro de acoes sensiveis (CLAUDE.md regra 11).

    Nunca contem senha, token ou dado sensivel em `details`.
    """

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    action: Mapped[str] = mapped_column(String(60), nullable=False)
    entity: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    entity_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    details: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    ip: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )

    __table_args__ = (
        Index("ix_audit_log_user_id", "user_id"),
        Index("ix_audit_log_action", "action"),
        Index("ix_audit_log_created_at", "created_at"),
    )


class Setting(Base):
    """
    Configuracoes chave/valor (nome da padaria, endereco, CNPJ, rodape do
    cupom, nome da impressora, largura em colunas etc.).

    Dados REAIS do cliente NAO vem de seed_demo.py. Vem de
    scripts/seed_cliente.py lendo data/cliente.json (gitignored).
    """

    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(50), primary_key=True)
    value: Mapped[str] = mapped_column(String(500), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )
