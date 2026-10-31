"""Testes do relatorio de fechamento (funcao pura, sem banco)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from app.services.close_report import build_close_report_lines


@dataclass
class P:
    method: str
    amount_cents: int
    change_cents: int = 0


@dataclass
class V:
    number: int
    total_cents: int
    payments: list = field(default_factory=list)
    status: str = "completed"
    created_at: datetime = datetime(2026, 10, 31, 17, 0)
    finalized_at: Optional[datetime] = datetime(2026, 10, 31, 17, 5)


@dataclass
class C:
    id: int = 7
    opening_cash_cents: int = 16710
    opened_at: datetime = datetime(2026, 10, 31, 12, 0)
    closed_at: datetime = datetime(2026, 10, 31, 21, 0)
    closing_cash_declared_cents: int = 18000
    closing_cash_expected_cents: int = 18459
    closing_difference_cents: int = -459


SETTINGS = {"store_name": "Joao & Maria - Confeitaria", "receipt_columns": "32"}


def _texto(sales, sessao=None, **kw):
    return build_close_report_lines(sessao or C(), sales, SETTINGS, **kw)


def test_lista_cada_venda_com_valor_e_forma() -> None:
    lines = _texto([
        V(1, 1799, [P("dinheiro", 2000, 201)]),
        V(2, 750, [P("pix", 750)]),
        V(3, 1000, [P("dinheiro", 500), P("debito", 500)]),
    ])
    linhas = {ln[:6]: ln for ln in lines}
    assert "Dinheiro" in linhas["000001"] and linhas["000001"].endswith("17,99")
    assert "PIX" in linhas["000002"] and linhas["000002"].endswith("7,50")
    assert "Misto" in linhas["000003"]


def test_cabe_em_32_colunas() -> None:
    lines = _texto(
        [V(123456, 123456789, [P("credito", 123456789)])],
        opened_by_name="Nome Bem Comprido De Operador Da Padaria",
    )
    assert all(len(ln) <= 32 for ln in lines)


def test_totais_descontam_troco_e_ignoram_canceladas() -> None:
    lines = _texto([
        V(1, 1799, [P("dinheiro", 2000, 201)]),
        V(2, 750, [P("pix", 750)]),
        V(3, 5000, [P("dinheiro", 5000)], status="cancelled"),
    ])
    texto = "\n".join(lines)
    assert any(ln.startswith("TOTAL VENDAS") and ln.endswith("R$ 25,49") for ln in lines)
    assert any(ln.startswith("Qtd de vendas") and ln.endswith("2") for ln in lines)
    assert any(ln.startswith("Dinheiro") and ln.endswith("R$ 17,99") for ln in lines)
    assert "CANCELADAS" in texto
    pos = texto.index("CANCELADAS")
    assert "50,00" in texto[pos:]


def test_cancelada_antes_de_finalizar_nao_aparece() -> None:
    lines = _texto([V(9, 700, status="cancelled", finalized_at=None)])
    assert "CANCELADAS" not in "\n".join(lines)


def test_sobra_falta_e_sem_motivo() -> None:
    falta = "\n".join(_texto([]))
    assert "FALTA" in falta and "R$ 4,59" in falta
    assert "otivo" not in falta

    sessao = C(closing_cash_declared_cents=18500, closing_difference_cents=41)
    assert "SOBRA" in "\n".join(_texto([], sessao))

    igual = C(closing_cash_declared_cents=18459, closing_difference_cents=0)
    texto = "\n".join(_texto([], igual))
    assert "SOBRA" not in texto and "FALTA" not in texto


def test_sem_vendas() -> None:
    assert "Nenhuma venda" in "\n".join(_texto([]))


def test_total_por_forma_lista_todas_inclusive_zeradas() -> None:
    lines = _texto([
        V(1, 1000, [P("dinheiro", 1000)]),
        V(2, 2500, [P("credito", 2500)]),
    ])
    pos = lines.index("POR FORMA DE PAGAMENTO")
    bloco = lines[pos + 1:pos + 6]
    esperado = [
        ("Dinheiro", "R$ 10,00"),
        ("Debito", None),
        ("Cartao de credito", "R$ 25,00"),
        ("PIX", "R$ 0,00"),
        ("Outros", "R$ 0,00"),
    ]
    assert bloco[0].startswith("Dinheiro") and bloco[0].endswith("R$ 10,00")
    assert bloco[1].startswith("Cartao de debito") and bloco[1].endswith("R$ 0,00")
    assert bloco[2].startswith("Cartao de credito") and bloco[2].endswith("R$ 25,00")
    assert bloco[3].startswith("PIX") and bloco[3].endswith("R$ 0,00")
    assert bloco[4].startswith("Outros") and bloco[4].endswith("R$ 0,00")
    assert len(esperado) == 5
