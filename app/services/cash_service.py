"""
Servico de caixa (Fase 7).

Regras:
- Apenas UMA sessao com status='open' no sistema inteiro (padaria tem 1
  caixa fisico). Validacao no service, nao no banco.
- Fluxo:
    open_session -> (sangria|suprimento)* + vendas -> close_session
- Fechamento BLOQUEIA se houver venda com status='open' em qualquer
  usuario. Operador tem que finalizar ou cancelar antes.
- Diferenca no fechamento (declarado != esperado): permitido, mas exige
  motivo. Audit log registra tudo.

Setting cash_session_required:
- Em producao, default 'true' (seed na migracao da Fase 7).
- Quando true, create_open_sale exige sessao aberta (ver sales_service).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    AuditLog,
    CashMovement,
    CashSession,
    Payment,
    Sale,
    Setting,
    User,
)


DINHEIRO_METHOD = "dinheiro"


class CashError(Exception):
    """Erro de regra de negocio em caixa."""

    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


# ---------- settings ----------


def is_cash_required(db: Session) -> bool:
    row = db.get(Setting, "cash_session_required")
    if row is None:
        return False
    return row.value.strip().lower() == "true"


def set_cash_required(db: Session, user: User, enabled: bool) -> bool:
    row = db.get(Setting, "cash_session_required")
    value = "true" if enabled else "false"
    if row is None:
        db.add(Setting(key="cash_session_required", value=value))
    else:
        row.value = value
    db.add(
        AuditLog(
            user_id=user.id,
            action="cash_required_toggled",
            entity="setting",
            details=f"cash_session_required={value}",
        )
    )
    db.commit()
    return enabled


# ---------- sessao aberta ----------


def get_open_session(db: Session) -> Optional[CashSession]:
    return db.execute(
        select(CashSession).where(CashSession.status == "open")
    ).scalar_one_or_none()


def require_open_session(db: Session) -> CashSession:
    s = get_open_session(db)
    if s is None:
        raise CashError("Nenhum caixa esta aberto.", 409)
    return s


# ---------- abrir ----------


def open_session(
    db: Session,
    *,
    user: User,
    opening_cash_cents: int,
    notes: Optional[str] = None,
) -> CashSession:
    if type(opening_cash_cents) is not int:
        raise CashError("opening_cash_cents deve ser int.", 422)
    if opening_cash_cents < 0:
        raise CashError("opening_cash_cents nao pode ser negativo.", 422)
    if get_open_session(db) is not None:
        raise CashError("Ja existe um caixa aberto. Feche antes de abrir outro.", 409)

    clean_notes: Optional[str] = None
    if notes is not None:
        s = notes.strip()
        if s:
            clean_notes = s[:500]

    session_row = CashSession(
        status="open",
        opened_by=user.id,
        opening_cash_cents=opening_cash_cents,
        notes=clean_notes,
    )
    db.add(session_row)
    db.add(
        AuditLog(
            user_id=user.id,
            action="cash_opened",
            entity="cash_session",
            details=f"opening_cash={opening_cash_cents}",
        )
    )
    db.commit()
    db.refresh(session_row)
    return session_row


# ---------- sangria / suprimento ----------


def register_sangria(
    db: Session,
    *,
    user: User,
    amount_cents: int,
    reason: str,
) -> CashMovement:
    if type(amount_cents) is not int:
        raise CashError("amount_cents deve ser int.", 422)
    if amount_cents <= 0:
        raise CashError("amount_cents deve ser > 0.", 422)
    if not isinstance(reason, str) or len(reason.strip()) < 3:
        raise CashError("Motivo obrigatorio (min 3 caracteres).", 422)
    clean_reason = reason.strip()[:200]

    session_row = require_open_session(db)

    mv = CashMovement(
        cash_session_id=session_row.id,
        type="sangria",
        amount_cents=amount_cents,
        reason=clean_reason,
        user_id=user.id,
    )
    db.add(mv)
    db.add(
        AuditLog(
            user_id=user.id,
            action="cash_sangria",
            entity="cash_session",
            entity_id=session_row.id,
            details=f"amount={amount_cents} reason={clean_reason[:60]}",
        )
    )
    db.commit()
    db.refresh(mv)
    return mv


def register_suprimento(
    db: Session,
    *,
    user: User,
    amount_cents: int,
    reason: Optional[str] = None,
) -> CashMovement:
    if type(amount_cents) is not int:
        raise CashError("amount_cents deve ser int.", 422)
    if amount_cents <= 0:
        raise CashError("amount_cents deve ser > 0.", 422)

    clean_reason: Optional[str] = None
    if reason is not None:
        s = reason.strip()
        if s:
            clean_reason = s[:200]

    session_row = require_open_session(db)

    mv = CashMovement(
        cash_session_id=session_row.id,
        type="suprimento",
        amount_cents=amount_cents,
        reason=clean_reason,
        user_id=user.id,
    )
    db.add(mv)
    db.add(
        AuditLog(
            user_id=user.id,
            action="cash_suprimento",
            entity="cash_session",
            entity_id=session_row.id,
            details=f"amount={amount_cents}",
        )
    )
    db.commit()
    db.refresh(mv)
    return mv


# ---------- summary / expected cash ----------


@dataclass
class PaymentTotal:
    method: str
    total_cents: int
    count: int


@dataclass
class SessionSummary:
    session: CashSession
    movements: list[CashMovement]
    payments_by_method: list[PaymentTotal]
    sales_cash_cents: int
    sales_count: int
    expected_cash_cents: int


def _sum_movements_by_type(db: Session, session_id: int, type_: str) -> int:
    return (
        db.execute(
            select(func.coalesce(func.sum(CashMovement.amount_cents), 0)).where(
                CashMovement.cash_session_id == session_id,
                CashMovement.type == type_,
            )
        ).scalar_one()
    )


def _payments_by_method(db: Session, session_id: int) -> list[PaymentTotal]:
    rows = db.execute(
        select(
            Payment.method,
            func.sum(Payment.amount_cents).label("total"),
            func.count(Payment.id).label("count"),
        )
        .join(Sale, Sale.id == Payment.sale_id)
        .where(
            Sale.cash_session_id == session_id,
            Sale.status == "completed",
        )
        .group_by(Payment.method)
        .order_by(Payment.method)
    ).all()
    return [
        PaymentTotal(method=r.method, total_cents=int(r.total or 0), count=int(r.count))
        for r in rows
    ]


def _completed_sales_count(db: Session, session_id: int) -> int:
    return int(
        db.execute(
            select(func.count(Sale.id)).where(
                Sale.cash_session_id == session_id,
                Sale.status == "completed",
            )
        ).scalar_one()
    )


def calculate_expected_cash(db: Session, session: CashSession) -> int:
    """
    Dinheiro esperado em caixa:
      opening + suprimentos + Σ(payments.method='dinheiro' das vendas desta
      session) - Σ(sangrias) - Σ(change_cents em dinheiro)

    change_cents > 0 so em payments.method='dinheiro' (regra do sales_service),
    entao o saldo liquido de dinheiro recebido = sum(amount - change).
    """
    opening = session.opening_cash_cents
    suprimentos = _sum_movements_by_type(db, session.id, "suprimento")
    sangrias = _sum_movements_by_type(db, session.id, "sangria")

    row = db.execute(
        select(
            func.coalesce(
                func.sum(Payment.amount_cents - Payment.change_cents), 0
            )
        )
        .join(Sale, Sale.id == Payment.sale_id)
        .where(
            Sale.cash_session_id == session.id,
            Sale.status == "completed",
            Payment.method == DINHEIRO_METHOD,
        )
    ).scalar_one()
    sales_cash = int(row or 0)

    return opening + suprimentos + sales_cash - sangrias


def _sales_cash_net(db: Session, session_id: int) -> int:
    """Dinheiro liquido recebido em vendas desta sessao (amount - change)."""
    row = db.execute(
        select(
            func.coalesce(
                func.sum(Payment.amount_cents - Payment.change_cents), 0
            )
        )
        .join(Sale, Sale.id == Payment.sale_id)
        .where(
            Sale.cash_session_id == session_id,
            Sale.status == "completed",
            Payment.method == DINHEIRO_METHOD,
        )
    ).scalar_one()
    return int(row or 0)


def build_summary(db: Session, session: CashSession) -> SessionSummary:
    movements = list(
        db.execute(
            select(CashMovement)
            .where(CashMovement.cash_session_id == session.id)
            .order_by(CashMovement.created_at.asc(), CashMovement.id.asc())
        ).scalars()
    )
    payments = _payments_by_method(db, session.id)
    sales_count = _completed_sales_count(db, session.id)
    sales_cash = _sales_cash_net(db, session.id)
    suprimentos = _sum_movements_by_type(db, session.id, "suprimento")
    sangrias = _sum_movements_by_type(db, session.id, "sangria")
    expected = session.opening_cash_cents + suprimentos + sales_cash - sangrias
    return SessionSummary(
        session=session,
        movements=movements,
        payments_by_method=payments,
        sales_cash_cents=sales_cash,
        sales_count=sales_count,
        expected_cash_cents=expected,
    )


def close_report_lines(db: Session, session: CashSession) -> list[str]:
    """Monta o relatorio de fechamento de uma sessao ja fechada."""
    from app.models import Setting
    from app.services.close_report import build_close_report_lines

    sales = list(
        db.execute(
            select(Sale)
            .where(Sale.cash_session_id == session.id)
            .order_by(Sale.number.asc())
        ).scalars()
    )
    opener = db.get(User, session.opened_by)
    closer = db.get(User, session.closed_by) if session.closed_by else None
    return build_close_report_lines(
        session,
        sales,
        list(db.execute(select(Setting)).scalars()),
        suprimentos_cents=_sum_movements_by_type(db, session.id, "suprimento"),
        sangrias_cents=_sum_movements_by_type(db, session.id, "sangria"),
        opened_by_name=opener.name if opener else None,
        closed_by_name=closer.name if closer else None,
    )


# ---------- fechamento ----------


def _has_open_sales(db: Session) -> bool:
    row = db.execute(
        select(func.count(Sale.id)).where(Sale.status == "open")
    ).scalar_one()
    return int(row or 0) > 0


def close_session(
    db: Session,
    *,
    user: User,
    declared_cash_cents: int,
) -> CashSession:
    if type(declared_cash_cents) is not int:
        raise CashError("declared_cash_cents deve ser int.", 422)
    if declared_cash_cents < 0:
        raise CashError("declared_cash_cents nao pode ser negativo.", 422)

    session_row = require_open_session(db)

    if _has_open_sales(db):
        raise CashError(
            "Existem vendas em aberto. Finalize ou cancele antes de fechar o caixa.",
            409,
        )

    expected = calculate_expected_cash(db, session_row)
    difference = declared_cash_cents - expected

    session_row.status = "closed"
    session_row.closed_by = user.id
    from app.models import utc_now  # evita import circular no topo

    session_row.closed_at = utc_now()
    session_row.closing_cash_declared_cents = declared_cash_cents
    session_row.closing_cash_expected_cents = expected
    session_row.closing_difference_cents = difference

    db.add(
        AuditLog(
            user_id=user.id,
            action="cash_closed",
            entity="cash_session",
            entity_id=session_row.id,
            details=(
                f"declared={declared_cash_cents} expected={expected} "
                f"difference={difference}"
            ),
        )
    )
    db.commit()
    db.refresh(session_row)

    # Hook: dispara backup em background se setting on. Nao pode travar
    # nem reverter o fechamento se o backup falhar.
    try:
        from app.services.backup_hook import trigger_post_close_backup

        trigger_post_close_backup(db, user)
    except Exception:
        # Ultra-defensivo: nunca propagar erro de backup ao fechamento.
        pass

    return session_row
