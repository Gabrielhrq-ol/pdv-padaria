"""
Schemas Pydantic v2 do PDV.

Regras de validacao (CLAUDE.md secao Seguranca):
- extra="forbid" em todos os schemas (rejeita campos extras).
- Limites de tamanho em todos os textos.
- Precos e estoques nao-negativos, com teto maximo.
- Unidade so UN / KG / L.
- Codigos (barcode, internal_code) somente ASCII sem espaco.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

from app.money import MAX_CENTS, MAX_MILLI, VALID_UNITS

Unit = Literal["UN", "KG", "L"]
Role = Literal["admin", "caixa"]

# Barcode: 1 a 20 digitos (EAN-8, EAN-13, UPC...). So digitos.
BarcodeStr = Annotated[
    str,
    StringConstraints(min_length=1, max_length=20, pattern=r"^\d+$"),
]
# Codigo interno: 1 a 10 chars, letras/digitos, sem espaco.
InternalCodeStr = Annotated[
    str,
    StringConstraints(min_length=1, max_length=10, pattern=r"^[A-Za-z0-9]+$"),
]
# Nome do produto: 1 a 120, sem controle, sem leading/trailing space.
ProductNameStr = Annotated[
    str,
    StringConstraints(min_length=1, max_length=120, strip_whitespace=True),
]
# Nome de categoria: 1 a 60.
CategoryNameStr = Annotated[
    str,
    StringConstraints(min_length=1, max_length=60, strip_whitespace=True),
]


class StrictBase(BaseModel):
    """Base com rejeicao de campos extras e strip de whitespace."""

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        from_attributes=True,
    )


# ---------- Category ----------


class CategoryOut(StrictBase):
    id: int
    name: CategoryNameStr


# ---------- Product ----------


class ProductBase(StrictBase):
    name: ProductNameStr
    barcode: Optional[BarcodeStr] = None
    internal_code: Optional[InternalCodeStr] = None
    category_id: Optional[int] = Field(default=None, ge=1)
    unit: Unit
    price_cents: int = Field(..., ge=0, le=MAX_CENTS)
    cost_cents: Optional[int] = Field(default=None, ge=0, le=MAX_CENTS)
    stock_milli: int = Field(default=0, ge=0, le=MAX_MILLI)
    min_stock_milli: int = Field(default=0, ge=0, le=MAX_MILLI)
    favorite: bool = False

    @field_validator("unit")
    @classmethod
    def _unit_valid(cls, v: str) -> str:
        if v not in VALID_UNITS:
            raise ValueError(f"unidade invalida: {v}")
        return v

    @field_validator("barcode", "internal_code")
    @classmethod
    def _empty_string_as_none(cls, v: Optional[str]) -> Optional[str]:
        # Garantia extra: um "" acidental vira None (campo opcional).
        if v is None:
            return None
        v = v.strip()
        return v or None


class ProductCreate(ProductBase):
    """Payload para criar produto. active sempre True no create."""


class ProductUpdate(StrictBase):
    """Edicao parcial. Todos os campos opcionais."""

    name: Optional[ProductNameStr] = None
    barcode: Optional[BarcodeStr] = None
    internal_code: Optional[InternalCodeStr] = None
    category_id: Optional[int] = Field(default=None, ge=1)
    unit: Optional[Unit] = None
    price_cents: Optional[int] = Field(default=None, ge=0, le=MAX_CENTS)
    cost_cents: Optional[int] = Field(default=None, ge=0, le=MAX_CENTS)
    stock_milli: Optional[int] = Field(default=None, ge=0, le=MAX_MILLI)
    min_stock_milli: Optional[int] = Field(default=None, ge=0, le=MAX_MILLI)
    favorite: Optional[bool] = None

    @field_validator("unit")
    @classmethod
    def _unit_valid(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        if v not in VALID_UNITS:
            raise ValueError(f"unidade invalida: {v}")
        return v

    @field_validator("barcode", "internal_code")
    @classmethod
    def _empty_string_as_none(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        v = v.strip()
        return v or None


class ActiveUpdate(StrictBase):
    active: bool


# ---------- Auth ----------


UsernameStr = Annotated[
    str,
    StringConstraints(min_length=3, max_length=50, pattern=r"^[A-Za-z0-9._-]+$"),
]


class LoginRequest(StrictBase):
    username: UsernameStr
    password: Annotated[str, StringConstraints(min_length=1, max_length=200)]


class UserOut(StrictBase):
    id: int
    name: str
    username: str
    role: Role
    active: bool


class LoginResponse(StrictBase):
    user: UserOut
    csrf_token: str


# ---------- Product ----------


class ProductOut(StrictBase):
    id: int
    name: str
    barcode: Optional[str]
    internal_code: Optional[str]
    category_id: Optional[int]
    unit: Unit
    price_cents: int
    cost_cents: Optional[int]
    stock_milli: int
    min_stock_milli: int
    favorite: bool
    active: bool
    created_at: datetime
    updated_at: datetime


class ByCodeResult(StrictBase):
    """Resposta de GET /api/products/by-code/{code}."""

    product: ProductOut
    qty_multiplier: int = Field(default=1, ge=1, le=1000)


# ---------- Sales ----------

SaleStatus = Literal["open", "completed", "cancelled"]


class SaleItemAdd(StrictBase):
    """
    Adiciona um item. Fornece OU `product_id` OU `code`.
    `code` aceita "N*codigo" para multiplicar.
    `qty_milli` sobrescreve o multiplicador (ex: para peso digitado).
    """

    product_id: Optional[int] = Field(default=None, ge=1)
    code: Optional[Annotated[str, StringConstraints(min_length=1, max_length=30)]] = None
    qty_milli: Optional[int] = Field(default=None, ge=1, le=1_000_000_000)


class SaleItemUpdate(StrictBase):
    qty_milli: int = Field(..., ge=1, le=1_000_000_000)


class SaleCancel(StrictBase):
    reason: Annotated[str, StringConstraints(min_length=1, max_length=200)]


class SaleItemOut(StrictBase):
    id: int
    product_id: int
    product_name: str
    barcode: Optional[str]
    internal_code: Optional[str]
    unit: Unit
    unit_price_cents: int
    qty_milli: int
    line_total_cents: int


class PaymentOut(StrictBase):
    id: int
    method: str
    amount_cents: int
    change_cents: int


class SaleOut(StrictBase):
    id: int
    number: int
    user_id: int
    status: SaleStatus
    subtotal_cents: int
    discount_cents: int
    total_cents: int
    created_at: datetime
    finalized_at: Optional[datetime]
    cancel_reason: Optional[str]
    discount_reason: Optional[str] = None
    items: list[SaleItemOut] = Field(default_factory=list)
    payments: list[PaymentOut] = Field(default_factory=list)


# ---------- Finalize / Reverse / Reprint ----------


MethodStr = Annotated[
    str,
    StringConstraints(min_length=1, max_length=20, strip_whitespace=True, pattern=r"^[A-Za-z0-9_-]+$"),
]


class PaymentInput(StrictBase):
    method: MethodStr
    amount_cents: int = Field(..., ge=0, le=100_000_000)


class FinalizeRequest(StrictBase):
    payments: list[PaymentInput] = Field(..., min_length=1, max_length=10)
    discount_cents: int = Field(default=0, ge=0, le=100_000_000)
    discount_reason: Optional[
        Annotated[str, StringConstraints(min_length=1, max_length=200)]
    ] = None
    print_receipt: bool = Field(default=True)


class ReverseRequest(StrictBase):
    reason: Annotated[str, StringConstraints(min_length=1, max_length=200)]


class FinalizeResult(StrictBase):
    sale: SaleOut
    receipt_lines: list[str] = Field(default_factory=list)
    printed: bool
    print_error: Optional[str] = None
