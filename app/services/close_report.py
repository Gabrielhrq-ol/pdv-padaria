"""
Relatorio de fechamento de caixa como lista de linhas (texto puro).

FUNCAO PURA, como receipt.py: nao toca em banco nem em hardware. Lista cada
venda da sessao com hora, forma de pagamento e valor, as vendas canceladas,
os totais por forma e a conferencia do dinheiro.
"""

from __future__ import annotations

from typing import Any, Iterable, Optional

from app.money import format_brl
from app.services.receipt import (
    DEFAULT_COLUMNS,
    _center,
    _divider,
    _format_dt,
    _left_right,
    _settings_as_dict,
    _wrap_words,
)

METHOD_LABELS = {
    "dinheiro": "Dinheiro",
    "debito": "Debito",
    "credito": "Credito",
    "pix": "PIX",
    "outros": "Outros",
}
TOTAL_LABELS = {
    "debito": "Cartao de debito",
    "credito": "Cartao de credito",
}


def _label(method: str) -> str:
    return METHOD_LABELS.get(method, method.capitalize())


def _sale_method(sale: Any) -> str:
    methods = {p.method for p in sale.payments}
    if not methods:
        return "-"
    if len(methods) > 1:
        return "Misto"
    return _label(next(iter(methods)))


def _sale_line(sale: Any, width: int) -> str:
    hora = _format_dt(sale.finalized_at or sale.created_at)[-5:]
    left = f"{sale.number:06d} {hora} {_sale_method(sale)}"
    return _left_right(left, format_brl(sale.total_cents)[3:], width)


def build_close_report_lines(
    session: Any,
    sales: Iterable[Any],
    settings: Iterable[Any] | dict[str, str],
    *,
    suprimentos_cents: int = 0,
    sangrias_cents: int = 0,
    opened_by_name: Optional[str] = None,
    closed_by_name: Optional[str] = None,
) -> list[str]:
    s = settings if isinstance(settings, dict) else _settings_as_dict(settings)
    try:
        width = int(s.get("receipt_columns") or DEFAULT_COLUMNS)
    except (TypeError, ValueError):
        width = DEFAULT_COLUMNS
    if width < 20:
        width = DEFAULT_COLUMNS

    all_sales = list(sales)
    concluidas = [v for v in all_sales if v.status == "completed"]
    canceladas = [
        v for v in all_sales
        if v.status == "cancelled" and v.finalized_at is not None
    ]

    por_forma: dict[str, int] = {}
    for venda in concluidas:
        for p in venda.payments:
            liquido = p.amount_cents - p.change_cents
            por_forma[p.method] = por_forma.get(p.method, 0) + liquido
    dinheiro_vendas = por_forma.get("dinheiro", 0)
    total_vendas = sum(v.total_cents for v in concluidas)

    lines: list[str] = []
    for ln in _wrap_words((s.get("store_name") or "PADARIA").upper(), width):
        lines.append(_center(ln, width))
    lines.append(_center("FECHAMENTO DE CAIXA", width))
    lines.append(_divider(width))
    lines.append(_left_right("Caixa", f"{session.id:06d}", width))
    lines.append(_left_right("Aberto", _format_dt(session.opened_at), width))
    lines.append(_left_right("Fechado", _format_dt(session.closed_at), width))
    if opened_by_name:
        lines.append(f"Abriu: {opened_by_name}"[:width])
    if closed_by_name:
        lines.append(f"Fechou: {closed_by_name}"[:width])

    lines.append(_divider(width))
    lines.append("VENDAS")
    if concluidas:
        lines.extend(_sale_line(v, width) for v in concluidas)
    else:
        lines.append("Nenhuma venda")
    lines.append(_divider(width))
    lines.append(_left_right("Qtd de vendas", str(len(concluidas)), width))
    lines.append(_left_right("TOTAL VENDAS", format_brl(total_vendas), width))

    if canceladas:
        lines.append(_divider(width))
        lines.append("CANCELADAS")
        lines.extend(_sale_line(v, width) for v in canceladas)

    # Sempre lista todas as formas, inclusive zeradas, para conferencia.
    lines.append(_divider(width))
    lines.append("POR FORMA DE PAGAMENTO")
    for metodo in list(METHOD_LABELS) + sorted(set(por_forma) - set(METHOD_LABELS)):
        rotulo = TOTAL_LABELS.get(metodo, _label(metodo))
        lines.append(_left_right(rotulo, format_brl(por_forma.get(metodo, 0)), width))

    declarado = session.closing_cash_declared_cents or 0
    esperado = session.closing_cash_expected_cents or 0
    diferenca = session.closing_difference_cents or 0

    lines.append(_divider(width))
    lines.append("DINHEIRO NO CAIXA")
    lines.append(_left_right("Fundo inicial", format_brl(session.opening_cash_cents), width))
    lines.append(_left_right("+ Vendas", format_brl(dinheiro_vendas), width))
    lines.append(_left_right("+ Suprimentos", format_brl(suprimentos_cents), width))
    lines.append(_left_right("- Sangrias", format_brl(sangrias_cents), width))
    lines.append(_left_right("Esperado", format_brl(esperado), width))
    lines.append(_left_right("Contado", format_brl(declarado), width))
    if diferenca > 0:
        lines.append(_left_right("SOBRA", format_brl(diferenca), width))
    elif diferenca < 0:
        lines.append(_left_right("FALTA", format_brl(-diferenca), width))
    else:
        lines.append(_left_right("Diferenca", format_brl(0), width))

    lines.append(_divider(width))
    lines.append(_center("SEM VALOR FISCAL", width))
    lines.append("")
    lines.append("")
    return lines
