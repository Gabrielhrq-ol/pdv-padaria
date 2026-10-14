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

import json
from datetime import datetime

from app.models import Payment, Product, Sale, SaleItem, Setting, StockMovement, User
from app.money import line_total_cents
from app.security import utc_now


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

    Fase 7: se setting `cash_session_required` = true, exige sessao de
    caixa aberta e carimba cash_session_id na venda.
    """
    existing = get_open_sale(db, user.id)
    if existing is not None:
        return existing

    cash_session_id: Optional[int] = None
    from app.services.cash_service import get_open_session, is_cash_required

    if is_cash_required(db):
        open_cash = get_open_session(db)
        if open_cash is None:
            raise SalesError(
                "Abra o caixa antes de iniciar uma venda.", 409
            )
        cash_session_id = open_cash.id
    else:
        open_cash = get_open_session(db)
        if open_cash is not None:
            cash_session_id = open_cash.id

    sale = Sale(
        number=_next_sale_number(db),
        user_id=user.id,
        cash_session_id=cash_session_id,
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
    sale.cancelled_at = utc_now()
    db.flush()
    return sale


# ---------- Finalizacao e estorno (Fase 4) ----------


DEFAULT_PAYMENT_METHODS = ["dinheiro", "debito", "credito", "pix", "outros"]


def _load_payment_methods(db: Session) -> set[str]:
    s = db.get(Setting, "payment_methods")
    raw = s.value if s is not None else None
    if raw:
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list) and all(isinstance(x, str) for x in parsed):
                return {x.strip().lower() for x in parsed if x.strip()}
        except (ValueError, TypeError):
            pass
    return set(DEFAULT_PAYMENT_METHODS)


@dataclass
class ChangeResult:
    total_a_pagar_cents: int
    total_pago_cents: int
    change_cents: int
    change_payment_index: int  # posicao do payment que leva o troco (-1 se nao ha troco)


def calculate_change(
    payments: list[tuple[str, int]],  # [(method, amount_cents), ...]
    total_a_pagar: int,
) -> ChangeResult:
    """
    Funcao PURA. Calcula troco. Nao toca em banco.

    Regras (CLAUDE.md):
    - soma dos pagamentos >= total_a_pagar
    - cartao / pix / nao-dinheiro NAO podem ter excesso
    - troco so sai de pagamento tipo 'dinheiro'
    """
    if type(total_a_pagar) is not int or total_a_pagar < 0:
        raise SalesError("Total invalido.", 422)
    if not payments:
        raise SalesError("Pelo menos um pagamento e obrigatorio.", 422)

    total_pago = 0
    total_nao_dinheiro = 0
    last_dinheiro_idx = -1

    for idx, (method, amount) in enumerate(payments):
        if type(amount) is not int or amount < 0:
            raise SalesError("Valor de pagamento invalido.", 422)
        total_pago += amount
        if method.lower() == "dinheiro":
            last_dinheiro_idx = idx
        else:
            total_nao_dinheiro += amount

    if total_nao_dinheiro > total_a_pagar:
        raise SalesError(
            "Pagamento em cartao/PIX nao pode exceder o total.", 400
        )

    if total_pago < total_a_pagar:
        falta = total_a_pagar - total_pago
        raise SalesError(f"Valor insuficiente. Falta pagar.", 400)

    excesso = total_pago - total_a_pagar
    if excesso > 0 and last_dinheiro_idx == -1:
        # Impossivel na pratica (nao dinheiro nao pode exceder) mas defende.
        raise SalesError("Troco so pode sair de pagamento em dinheiro.", 400)

    return ChangeResult(
        total_a_pagar_cents=total_a_pagar,
        total_pago_cents=total_pago,
        change_cents=excesso,
        change_payment_index=last_dinheiro_idx if excesso > 0 else -1,
    )


def finalize_sale(
    db: Session,
    sale: Sale,
    user: User,
    payments_in: list[tuple[str, int]],  # [(method, amount_cents), ...]
    *,
    discount_cents: int = 0,
    discount_reason: Optional[str] = None,
) -> Sale:
    """
    Finalizacao atomica (CLAUDE.md regra 3): venda, itens ja existentes,
    pagamentos, baixa de estoque + stock_movements. Chamador deve dar
    commit no final (um unico commit).

    allow_negative_stock = true (decisao 9): NUNCA bloqueia por estoque.
    """
    _assert_open(sale)
    if not sale.items:
        raise SalesError("Venda sem itens.", 400)

    if type(discount_cents) is not int or discount_cents < 0:
        raise SalesError("Desconto invalido.", 422)
    if discount_cents > sale.subtotal_cents:
        raise SalesError("Desconto maior que o subtotal.", 422)
    if discount_cents > 0:
        if not discount_reason or not discount_reason.strip():
            raise SalesError("Motivo do desconto e obrigatorio.", 422)

    # Validacao de metodos contra o setting
    allowed = _load_payment_methods(db)
    for method, _ in payments_in:
        if method.lower() not in allowed:
            raise SalesError(
                f"Forma de pagamento nao permitida: {method}", 400
            )

    total_a_pagar = sale.subtotal_cents - discount_cents
    change_result = calculate_change(payments_in, total_a_pagar)

    # 1) Pagamentos
    pay_rows: list[Payment] = []
    for idx, (method, amount) in enumerate(payments_in):
        change = change_result.change_cents if idx == change_result.change_payment_index else 0
        p = Payment(
            sale_id=sale.id,
            method=method.lower(),
            amount_cents=amount,
            change_cents=change,
        )
        db.add(p)
        pay_rows.append(p)

    # 2) Baixa de estoque + movements (CLAUDE.md regra 3 - mesma transacao)
    for item in sale.items:
        product = db.get(Product, item.product_id)
        if product is None:
            raise SalesError("Produto do item nao encontrado.", 500)
        product.stock_milli = product.stock_milli - item.qty_milli
        db.add(
            StockMovement(
                product_id=product.id,
                type="venda",
                qty_milli=-item.qty_milli,
                sale_id=sale.id,
                user_id=user.id,
            )
        )

    # 3) Atualiza venda
    sale.discount_cents = discount_cents
    sale.discount_reason = (
        discount_reason.strip()[:200] if discount_cents > 0 and discount_reason else None
    )
    sale.total_cents = total_a_pagar
    sale.status = "completed"
    sale.finalized_at = utc_now()

    db.flush()
    return sale


def reverse_sale(
    db: Session,
    sale: Sale,
    user: User,
    reason: str,
) -> Sale:
    """
    Cancela uma venda ja FINALIZADA. Estorna estoque + grava movements.
    Decisao 3 do cliente: qualquer operador pode (com motivo + audit).
    """
    if sale.status != "completed":
        raise SalesError(
            f"So e possivel reverter venda completed (atual: {sale.status}).", 409
        )
    reason = (reason or "").strip()
    if not reason:
        raise SalesError("Motivo obrigatorio.", 422)

    for item in sale.items:
        product = db.get(Product, item.product_id)
        if product is None:
            continue  # inconsistencia; nao impede o estorno
        product.stock_milli = product.stock_milli + item.qty_milli
        db.add(
            StockMovement(
                product_id=product.id,
                type="estorno",
                qty_milli=item.qty_milli,
                sale_id=sale.id,
                user_id=user.id,
                reason=reason[:200],
            )
        )

    sale.status = "cancelled"
    sale.cancel_reason = reason[:200]
    sale.cancelled_by = user.id
    sale.cancelled_at = utc_now()
    db.flush()
    return sale


def get_last_completed(db: Session, user_id: int) -> Optional[Sale]:
    """Ultima venda COMPLETED do operador atual (para reimpressao F10)."""
    return db.execute(
        select(Sale)
        .where(Sale.user_id == user_id, Sale.status == "completed")
        .order_by(Sale.finalized_at.desc())
        .limit(1)
    ).scalar_one_or_none()
