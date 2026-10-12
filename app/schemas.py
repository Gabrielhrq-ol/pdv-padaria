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
