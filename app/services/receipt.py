"""
Montagem do cupom como lista de linhas (texto puro, 32 colunas por padrao).

FUNCAO PURA: nao toca em banco, nao toca em hardware. Recebe dados ja
carregados. O chamador passa a venda, os itens, os pagamentos e o dict
de settings da padaria.

Fase 4: usada pelo Dummy printer para teste.
Fase 5: Win32Raw envia as mesmas linhas para a impressora real.

Cupom traz "DOCUMENTO SEM VALOR FISCAL" (decisao 1 do cliente).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Iterable, Optional

from app.money import format_brl, format_qty

DEFAULT_COLUMNS = 32


def _settings_as_dict(settings_rows: Iterable[Any]) -> dict[str, str]:
    """Converte uma iteracao de Setting (ou dict) em dict simples."""
    result: dict[str, str] = {}
    for row in settings_rows or []:
        if hasattr(row, "key") and hasattr(row, "value"):
            result[row.key] = row.value
        elif isinstance(row, dict):
            k = row.get("key")
            if k:
                result[k] = str(row.get("value", ""))
    return result


def _center(text: str, width: int) -> str:
    text = text[:width]
    pad = max(0, (width - len(text)) // 2)
    return (" " * pad) + text


def _left_right(left: str, right: str, width: int) -> str:
    """Mantem `right` sempre completo; recorta `left` se preciso."""
    right = right[:width]
    max_left = max(0, width - len(right) - 1)
    left = left[:max_left]
    pad = max(1, width - len(left) - len(right))
    return left + (" " * pad) + right


def _divider(width: int, char: str = "-") -> str:
    return char * width


def _wrap(text: str, width: int) -> list[str]:
    """Quebra texto longo em multiplas linhas respeitando o width."""
    text = text or ""
    lines: list[str] = []
    while len(text) > width:
        lines.append(text[:width])
        text = text[width:]
    if text:
        lines.append(text)
    return lines


def _format_dt(dt: Optional[datetime]) -> str:
    if dt is None:
        return ""
    return dt.strftime("%d/%m/%Y %H:%M")


def build_receipt_lines(
    sale: Any,
    items: Iterable[Any],
    payments: Iterable[Any],
    settings: Iterable[Any] | dict[str, str],
    *,
    is_reprint: bool = False,
    operator_name: Optional[str] = None,
) -> list[str]:
    """
    Monta as linhas do cupom.

    Parametros:
        sale: objeto com id, number, status, subtotal_cents, discount_cents,
              total_cents, finalized_at.
        items: iteravel com product_name, unit, unit_price_cents, qty_milli,
               line_total_cents.
        payments: iteravel com method, amount_cents, change_cents.
        settings: lista de Setting (ou dict). Chaves usadas:
            store_name, store_cnpj, store_address, store_phone,
            receipt_header_extra, receipt_footer, receipt_disclaimer,
            receipt_columns.
        is_reprint: se True, acrescenta "** 2a VIA **" no cabecalho.
        operator_name: opcional; aparece abaixo do numero da venda.
    """
    s = settings if isinstance(settings, dict) else _settings_as_dict(settings)

    try:
        width = int(s.get("receipt_columns") or DEFAULT_COLUMNS)
    except (TypeError, ValueError):
        width = DEFAULT_COLUMNS
    if width < 20:
        width = DEFAULT_COLUMNS

    store_name = s.get("store_name") or "PADARIA"
    store_cnpj = s.get("store_cnpj") or ""
    store_address = s.get("store_address") or ""
    store_phone = s.get("store_phone") or ""
    header_extra = s.get("receipt_header_extra") or ""
    footer = s.get("receipt_footer") or "Obrigado e volte sempre!"
    disclaimer = s.get("receipt_disclaimer") or "DOCUMENTO SEM VALOR FISCAL"

    lines: list[str] = []
    # ---------- cabecalho da loja ----------
    lines.append(_center(store_name.upper(), width))
    if store_address:
        for ln in _wrap(store_address, width):
            lines.append(_center(ln, width))
    if store_cnpj:
        lines.append(_center(f"CNPJ: {store_cnpj}", width))
    if store_phone:
        lines.append(_center(f"Tel: {store_phone}", width))
    if header_extra:
        for ln in _wrap(header_extra, width):
            lines.append(_center(ln, width))

    lines.append(_divider(width))
    lines.append(_center(f"*** {disclaimer} ***", width))
    lines.append(_divider(width))

    if is_reprint:
        lines.append(_center("** 2a VIA **", width))
        lines.append(_divider(width))

    # ---------- dados da venda ----------
    number_fmt = f"Venda: {sale.number:06d}"
    date_fmt = _format_dt(sale.finalized_at or sale.created_at)
    lines.append(_left_right(number_fmt, date_fmt, width))
    if operator_name:
        lines.append(f"Operador: {operator_name[:width - 10]}")

    lines.append(_divider(width))

    # ---------- itens ----------
    lines.append("ITEM DESCRICAO")
    item_list = list(items)
    for idx, it in enumerate(item_list, start=1):
        name = it.product_name if hasattr(it, "product_name") else it["product_name"]
        unit = it.unit if hasattr(it, "unit") else it["unit"]
        price = it.unit_price_cents if hasattr(it, "unit_price_cents") else it["unit_price_cents"]
        qty = it.qty_milli if hasattr(it, "qty_milli") else it["qty_milli"]
        total = it.line_total_cents if hasattr(it, "line_total_cents") else it["line_total_cents"]

        # Linha 1: numero + nome
        header = f"{idx:03d} {name}"
        for ln in _wrap(header, width):
            lines.append(ln)
        # Linha 2: qtd x preco ................ total
        qty_label = format_qty(qty, unit)
        if unit != "UN":
            qty_label = f"{qty_label} {unit.lower()}"
        detail_left = f"  {qty_label} x {format_brl(price).replace('R$ ', '')}"
        total_fmt = format_brl(total).replace("R$ ", "")
        lines.append(_left_right(detail_left, total_fmt, width))

    lines.append(_divider(width))

    # ---------- totais ----------
    lines.append(_left_right("SUBTOTAL", format_brl(sale.subtotal_cents), width))
    if sale.discount_cents and sale.discount_cents > 0:
        lines.append(
            _left_right(f"DESCONTO", "-" + format_brl(sale.discount_cents), width)
        )
    lines.append(_left_right("TOTAL", format_brl(sale.total_cents), width))

    # ---------- pagamentos ----------
    pay_list = list(payments)
    if pay_list:
        lines.append(_divider(width))
        for p in pay_list:
            method = p.method if hasattr(p, "method") else p["method"]
            amount = p.amount_cents if hasattr(p, "amount_cents") else p["amount_cents"]
            change = p.change_cents if hasattr(p, "change_cents") else p.get("change_cents", 0)
            lines.append(
                _left_right(method.capitalize(), format_brl(amount), width)
            )
            if change and change > 0:
                lines.append(_left_right("  Troco", format_brl(change), width))

    # ---------- rodape ----------
    lines.append(_divider(width))
    for ln in _wrap(footer, width):
        lines.append(_center(ln, width))
    # linhas em branco para avanco de papel
    lines.append("")
    lines.append("")

    return lines
