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


# ---------- Admin / Printer settings ----------

PrinterBackend = Literal["dummy", "win32raw"]
PrinterCodepage = Literal["", "CP437", "CP850", "CP858", "CP860"]


class PrinterSettingsOut(StrictBase):
    printer_backend: PrinterBackend
    printer_name: str = ""
    printer_codepage: PrinterCodepage = ""
    printer_auto_cut: bool = False
    active_label: str  # texto legivel do backend atual (ex "Win32Raw (POS-58)")


class PrinterSettingsUpdate(StrictBase):
    printer_backend: PrinterBackend
    printer_name: Annotated[str, StringConstraints(max_length=120, strip_whitespace=True)] = ""
    printer_codepage: PrinterCodepage = ""
    printer_auto_cut: bool = False


class PrinterTestResult(StrictBase):
    backend: str
    printed: bool
    print_error: Optional[str] = None
    lines: list[str] = Field(default_factory=list)


# ---------- Stock (Fase 6) ----------

StockMovementType = Literal["entrada", "venda", "ajuste", "perda", "estorno"]

# Reason obrigatorio em perda/ajuste: min 3 chars util, max 200.
ReasonRequired = Annotated[
    str,
    StringConstraints(min_length=3, max_length=200, strip_whitespace=True),
]
# Reason opcional em entrada: ate 200 chars; vazio vira None.
ReasonOptional = Annotated[
    str,
    StringConstraints(max_length=200, strip_whitespace=True),
]


class StockEntryIn(StrictBase):
    """
    Entrada de mercadoria (chegada de fornecedor, producao propria etc).
    Motivo e OPCIONAL (decisao do dono 2026-10-14).
    """

    product_id: int = Field(..., ge=1)
    qty_milli: int = Field(..., ge=1, le=MAX_MILLI)
    reason: Optional[ReasonOptional] = None

    @field_validator("reason")
    @classmethod
    def _empty_reason_as_none(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        v = v.strip()
        return v or None


class StockLossIn(StrictBase):
    """
    Perda de mercadoria (quebra, vencimento, furto). Motivo OBRIGATORIO
    (CLAUDE.md decisao 9 do cliente + regra 11 de auditoria).
    """

    product_id: int = Field(..., ge=1)
    qty_milli: int = Field(..., ge=1, le=MAX_MILLI)
    reason: ReasonRequired


class StockAdjustmentIn(StrictBase):
    """
    Ajuste de inventario: define um NOVO saldo absoluto e grava o delta
    como stock_movement tipo 'ajuste'. Produto deve estar ATIVO (decisao
    do dono 2026-10-14). Motivo OBRIGATORIO.
    """

    product_id: int = Field(..., ge=1)
    new_stock_milli: int = Field(..., ge=0, le=MAX_MILLI)
    reason: ReasonRequired


class StockMovementOut(StrictBase):
    """Linha do historico de movimentacoes."""

    id: int
    product_id: int
    product_name: str
    product_unit: Unit
    type: StockMovementType
    qty_milli: int  # SIGNED
    reason: Optional[str]
    sale_id: Optional[int]
    user_id: int
    user_name: Optional[str]
    created_at: datetime


class LowStockOut(StrictBase):
    """Produto com estoque <= minimo configurado."""

    product_id: int
    product_name: str
    unit: Unit
    stock_milli: int
    min_stock_milli: int


# ---------- Cash (Fase 7) ----------

CashSessionStatus = Literal["open", "closed"]
CashMovementType = Literal["sangria", "suprimento"]

CashReasonRequired = Annotated[
    str,
    StringConstraints(min_length=3, max_length=200, strip_whitespace=True),
]
CashReasonOptional = Annotated[
    str,
    StringConstraints(max_length=200, strip_whitespace=True),
]
CashNotes = Annotated[
    str,
    StringConstraints(max_length=500, strip_whitespace=True),
]


class CashOpenIn(StrictBase):
    """Abre uma sessao de caixa."""

    opening_cash_cents: int = Field(..., ge=0, le=100_000_000)
    notes: Optional[CashNotes] = None


class CashSangriaIn(StrictBase):
    """Sangria: saida de dinheiro manual. Motivo OBRIGATORIO."""

    amount_cents: int = Field(..., ge=1, le=100_000_000)
    reason: CashReasonRequired


class CashSuprimentoIn(StrictBase):
    """Suprimento: entrada de dinheiro manual. Motivo OPCIONAL."""

    amount_cents: int = Field(..., ge=1, le=100_000_000)
    reason: Optional[CashReasonOptional] = None

    @field_validator("reason")
    @classmethod
    def _empty_reason_as_none(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        s = v.strip()
        return s or None


class CashCloseIn(StrictBase):
    """
    Fecha a sessao atual.
    - declared_cash_cents: dinheiro contado fisicamente.
    - difference_reason: obrigatorio se declared != esperado.
    """

    declared_cash_cents: int = Field(..., ge=0, le=100_000_000)
    difference_reason: Optional[CashReasonOptional] = None

    @field_validator("difference_reason")
    @classmethod
    def _empty_reason_as_none(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        s = v.strip()
        return s or None


class CashRequiredToggle(StrictBase):
    """Liga/desliga o setting cash_session_required."""

    enabled: bool


class CashMovementOut(StrictBase):
    id: int
    cash_session_id: int
    type: CashMovementType
    amount_cents: int
    reason: Optional[str]
    user_id: int
    user_name: Optional[str]
    created_at: datetime


class CashPaymentTotal(StrictBase):
    method: str
    total_cents: int
    count: int


class CashSessionOut(StrictBase):
    id: int
    status: CashSessionStatus
    opened_by: int
    opened_by_name: Optional[str] = None
    opened_at: datetime
    opening_cash_cents: int
    closed_by: Optional[int]
    closed_by_name: Optional[str] = None
    closed_at: Optional[datetime]
    closing_cash_declared_cents: Optional[int]
    closing_cash_expected_cents: Optional[int]
    closing_difference_cents: Optional[int]
    difference_reason: Optional[str]
    notes: Optional[str]


class CashSessionSummaryOut(StrictBase):
    """Preview em tempo real para a UI de fechamento."""

    session: CashSessionOut
    movements: list[CashMovementOut] = Field(default_factory=list)
    payments_by_method: list[CashPaymentTotal] = Field(default_factory=list)
    sales_cash_cents: int  # dinheiro recebido em vendas finalizadas
    sales_count: int
    expected_cash_cents: int  # opening + suprimentos - sangrias + sales_cash


# ---------- Reports (Fase 8) ----------


class DashboardOut(StrictBase):
    today_sales_count: int
    today_revenue_cents: int
    today_avg_ticket_cents: int
    open_cash_session_id: Optional[int]
    low_stock_count: int


class SalesPeriodDayOut(StrictBase):
    day: str
    sales_count: int
    revenue_cents: int
    avg_ticket_cents: int


class SalesPeriodOut(StrictBase):
    days: list[SalesPeriodDayOut] = Field(default_factory=list)
    total_count: int
    total_revenue_cents: int
    total_avg_ticket_cents: int


class ClosedCashRowOut(StrictBase):
    id: int
    opened_by_name: Optional[str]
    opened_at: datetime
    closed_by_name: Optional[str]
    closed_at: Optional[datetime]
    opening_cash_cents: int
    expected_cash_cents: Optional[int]
    declared_cash_cents: Optional[int]
    difference_cents: Optional[int]
    difference_reason: Optional[str]


class OperatorStatsOut(StrictBase):
    user_id: int
    user_name: str
    sales_count: int
    revenue_cents: int
    discount_total_cents: int
    cancelled_count: int


class MethodStatsOut(StrictBase):
    method: str
    sales_count: int
    total_cents: int


class TopProductRowOut(StrictBase):
    product_id: int
    product_name: str
    unit: Unit
    qty_milli: int
    revenue_cents: int


class DiscountRowOut(StrictBase):
    sale_id: int
    sale_number: int
    kind: Literal["desconto", "cancelamento"]
    user_name: Optional[str]
    occurred_at: Optional[datetime]
    total_cents: int
    discount_cents: int
    reason: Optional[str]


# ---------- Backup (Fase 9) ----------

BackupDirPath = Annotated[
    str,
    StringConstraints(max_length=260, strip_whitespace=True),
]


class BackupSettingsIn(StrictBase):
    backup_dir_1: Optional[BackupDirPath] = None
    backup_dir_2: Optional[BackupDirPath] = None
    backup_keep: int = Field(default=30, ge=1, le=1000)
    backup_on_cash_close: bool = True
    backup_compress: bool = True

    @field_validator("backup_dir_1", "backup_dir_2")
    @classmethod
    def _empty_as_none(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        s = v.strip()
        return s or None


class BackupSettingsOut(StrictBase):
    backup_dir_1: Optional[str]
    backup_dir_2: Optional[str]
    backup_keep: int
    backup_on_cash_close: bool
    backup_compress: bool


class BackupDestinationOut(StrictBase):
    destination: str
    status: Literal["ok", "fail"]
    bytes_written: int = 0
    file_name: Optional[str] = None
    error: Optional[str] = None


class BackupRunOut(StrictBase):
    started_at: datetime
    finished_at: datetime
    source_bytes: int
    compressed: bool
    ok_count: int
    fail_count: int
    results: list[BackupDestinationOut] = Field(default_factory=list)


class BackupHistoryEntry(StrictBase):
    created_at: datetime
    user_name: Optional[str]
    action: str  # "backup_run" | "backup_skipped" | "backup_failed"
    details: Optional[str]
