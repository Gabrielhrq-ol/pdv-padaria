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
        # stock_milli pode ser negativo: decisao 9 do cliente diz pra NUNCA
        # bloquear venda por estoque. Padaria produz propria mercadoria.
        CheckConstraint(
            "min_stock_milli >= 0", name="ck_products_min_stock_non_negative"
        ),
        Index("ix_products_barcode", "barcode"),
        Index("ix_products_internal_code", "internal_code"),
        Index("ix_products_name", "name"),
        Index("ix_products_active", "active"),
    )


class Sale(Base):
    """
    Venda. Fase 3: cria em status=open; itens adicionados/removidos.
    Fase 4 adiciona payments e muda para completed na finalizacao atomica.

    cash_session_id fica nullable; Fase 7 ativa o setting que exige caixa aberto.
    """

    __tablename__ = "sales"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    number: Mapped[int] = mapped_column(Integer, nullable=False, unique=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    cash_session_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(10), nullable=False, default="open")
    subtotal_cents: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    discount_cents: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_cents: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    finalized_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    cancel_reason: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    cancelled_by: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    cancelled_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    discount_reason: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)

    items: Mapped[list["SaleItem"]] = relationship(
        back_populates="sale",
        cascade="all, delete-orphan",
        order_by="SaleItem.id",
    )
    payments: Mapped[list["Payment"]] = relationship(
        back_populates="sale",
        cascade="all, delete-orphan",
        order_by="Payment.id",
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('open', 'completed', 'cancelled')", name="ck_sales_status"
        ),
        CheckConstraint("subtotal_cents >= 0", name="ck_sales_subtotal_non_negative"),
        CheckConstraint("discount_cents >= 0", name="ck_sales_discount_non_negative"),
        CheckConstraint("total_cents >= 0", name="ck_sales_total_non_negative"),
        Index("ix_sales_status", "status"),
        Index("ix_sales_user_status", "user_id", "status"),
        Index("ix_sales_created_at", "created_at"),
    )


class SaleItem(Base):
    """
    Item de venda. Copia nome, barcode, unidade e preco do produto no
    momento da venda (CLAUDE.md regra 4).
    """

    __tablename__ = "sale_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    sale_id: Mapped[int] = mapped_column(
        ForeignKey("sales.id", ondelete="CASCADE"), nullable=False
    )
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), nullable=False)
    # Copias (snapshot do momento)
    product_name: Mapped[str] = mapped_column(String(120), nullable=False)
    barcode: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    internal_code: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    unit: Mapped[str] = mapped_column(String(3), nullable=False)
    unit_price_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    qty_milli: Mapped[int] = mapped_column(Integer, nullable=False)
    line_total_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )

    sale: Mapped["Sale"] = relationship(back_populates="items")

    __table_args__ = (
        CheckConstraint("qty_milli > 0", name="ck_sale_items_qty_positive"),
        CheckConstraint(
            "unit_price_cents >= 0", name="ck_sale_items_price_non_negative"
        ),
        CheckConstraint(
            "line_total_cents >= 0", name="ck_sale_items_total_non_negative"
        ),
        CheckConstraint("unit IN ('UN', 'KG', 'L')", name="ck_sale_items_unit"),
        Index("ix_sale_items_sale_id", "sale_id"),
    )


class Payment(Base):
    """
    Pagamento de uma venda. `method` validado contra setting
    `payment_methods` no servico (nao no banco).
    `change_cents` so eh > 0 em pagamento tipo dinheiro.
    """

    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    sale_id: Mapped[int] = mapped_column(
        ForeignKey("sales.id", ondelete="CASCADE"), nullable=False
    )
    method: Mapped[str] = mapped_column(String(20), nullable=False)
    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    change_cents: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )

    sale: Mapped["Sale"] = relationship(back_populates="payments")

    __table_args__ = (
        CheckConstraint("amount_cents >= 0", name="ck_payments_amount_non_negative"),
        CheckConstraint("change_cents >= 0", name="ck_payments_change_non_negative"),
        CheckConstraint("length(method) > 0", name="ck_payments_method_not_empty"),
        Index("ix_payments_sale_id", "sale_id"),
    )


class StockMovement(Base):
    """
    Livro-razao do estoque. qty_milli e SIGNED:
    - venda, perda: negativo
    - entrada, ajuste positivo, estorno: positivo
    - ajuste: qualquer sinal (motivo explica)

    Invariante: product.stock_milli = sum(movements.qty_milli) + saldo inicial.
    """

    __tablename__ = "stock_movements"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), nullable=False)
    type: Mapped[str] = mapped_column(String(10), nullable=False)
    qty_milli: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    sale_id: Mapped[Optional[int]] = mapped_column(ForeignKey("sales.id"), nullable=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )

    __table_args__ = (
        CheckConstraint(
            "type IN ('entrada', 'venda', 'ajuste', 'perda', 'estorno')",
            name="ck_stock_movements_type",
        ),
        CheckConstraint("qty_milli != 0", name="ck_stock_movements_qty_nonzero"),
        Index("ix_stock_movements_product_created", "product_id", "created_at"),
        Index("ix_stock_movements_sale_id", "sale_id"),
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
