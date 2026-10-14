"""Testes do receipt.py (funcao pura, sem banco)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from app.services.receipt import build_receipt_lines


@dataclass
class FakeSale:
    id: int = 1
    number: int = 42
    status: str = "completed"
    subtotal_cents: int = 2000
    discount_cents: int = 0
    total_cents: int = 2000
    created_at: datetime = datetime(2026, 10, 13, 14, 30)
    finalized_at: Optional[datetime] = datetime(2026, 10, 13, 14, 32)


@dataclass
class FakeItem:
    product_name: str
    unit: str
    unit_price_cents: int
    qty_milli: int
    line_total_cents: int


@dataclass
class FakePayment:
    method: str
    amount_cents: int
    change_cents: int = 0


SETTINGS = {
    "store_name": "Padaria Teste",
    "store_cnpj": "00.000.000/0000-00",
    "store_address": "Rua Teste 123",
    "store_phone": "(16) 0000-0000",
    "receipt_footer": "Obrigado!",
    "receipt_disclaimer": "DOCUMENTO SEM VALOR FISCAL",
    "receipt_columns": "32",
}


class TestEstruturaBasica:
    def test_contem_nome_loja(self) -> None:
        lines = build_receipt_lines(
            FakeSale(),
            [FakeItem("Pao", "KG", 1800, 350, 630)],
            [FakePayment("dinheiro", 630)],
            SETTINGS,
        )
        joined = "\n".join(lines)
        assert "PADARIA TESTE" in joined

    def test_contem_disclaimer(self) -> None:
        lines = build_receipt_lines(
            FakeSale(), [], [], SETTINGS,
        )
        joined = "\n".join(lines)
        assert "DOCUMENTO SEM VALOR FISCAL" in joined

    def test_cnpj_endereco_rodape(self) -> None:
        lines = build_receipt_lines(
            FakeSale(), [], [], SETTINGS,
        )
        joined = "\n".join(lines)
        assert "CNPJ: 00.000.000/0000-00" in joined
        assert "Rua Teste 123" in joined
        assert "Obrigado!" in joined

    def test_nenhuma_linha_passa_32_colunas(self) -> None:
        lines = build_receipt_lines(
            FakeSale(subtotal_cents=1500, total_cents=1500),
            [
                FakeItem("Produto com nome relativamente comprido para testar quebra", "UN", 500, 3000, 1500),
            ],
            [FakePayment("dinheiro", 1500)],
            SETTINGS,
        )
        for ln in lines:
            assert len(ln) <= 32, f"Linha com {len(ln)} chars: {ln!r}"


class TestItens:
    def test_item_un(self) -> None:
        lines = build_receipt_lines(
            FakeSale(subtotal_cents=1200, total_cents=1200),
            [FakeItem("Refri", "UN", 1200, 1000, 1200)],
            [FakePayment("dinheiro", 1200)],
            SETTINGS,
        )
        joined = "\n".join(lines)
        assert "Refri" in joined
        assert "1 x 12,00" in joined
        assert "12,00" in joined

    def test_item_kg(self) -> None:
        lines = build_receipt_lines(
            FakeSale(subtotal_cents=630, total_cents=630),
            [FakeItem("Pao", "KG", 1800, 350, 630)],
            [FakePayment("dinheiro", 630)],
            SETTINGS,
        )
        joined = "\n".join(lines)
        assert "0,350 kg x 18,00" in joined
        assert "6,30" in joined


class TestTotais:
    def test_subtotal_e_total(self) -> None:
        lines = build_receipt_lines(
            FakeSale(subtotal_cents=2000, total_cents=2000),
            [FakeItem("X", "UN", 2000, 1000, 2000)],
            [FakePayment("dinheiro", 2000)],
            SETTINGS,
        )
        joined = "\n".join(lines)
        assert "SUBTOTAL" in joined
        assert "TOTAL" in joined

    def test_desconto_aparece(self) -> None:
        lines = build_receipt_lines(
            FakeSale(subtotal_cents=2000, discount_cents=200, total_cents=1800),
            [FakeItem("X", "UN", 2000, 1000, 2000)],
            [FakePayment("dinheiro", 1800)],
            SETTINGS,
        )
        joined = "\n".join(lines)
        assert "DESCONTO" in joined


class TestPagamentoETroco:
    def test_dinheiro_exato(self) -> None:
        lines = build_receipt_lines(
            FakeSale(),
            [FakeItem("X", "UN", 2000, 1000, 2000)],
            [FakePayment("dinheiro", 2000, change_cents=0)],
            SETTINGS,
        )
        joined = "\n".join(lines)
        assert "Dinheiro" in joined
        assert "Troco" not in joined

    def test_com_troco(self) -> None:
        lines = build_receipt_lines(
            FakeSale(),
            [FakeItem("X", "UN", 2000, 1000, 2000)],
            [FakePayment("dinheiro", 3000, change_cents=1000)],
            SETTINGS,
        )
        joined = "\n".join(lines)
        assert "Troco" in joined
        assert "10,00" in joined

    def test_pagamento_misto(self) -> None:
        lines = build_receipt_lines(
            FakeSale(),
            [FakeItem("X", "UN", 2000, 1000, 2000)],
            [
                FakePayment("debito", 500),
                FakePayment("dinheiro", 1500, change_cents=0),
            ],
            SETTINGS,
        )
        joined = "\n".join(lines)
        assert "Debito" in joined
        assert "Dinheiro" in joined


class TestReprint:
    def test_marca_2a_via(self) -> None:
        lines = build_receipt_lines(
            FakeSale(),
            [FakeItem("X", "UN", 2000, 1000, 2000)],
            [FakePayment("dinheiro", 2000)],
            SETTINGS,
            is_reprint=True,
        )
        joined = "\n".join(lines)
        assert "2a VIA" in joined


class TestColunasPersonalizadas:
    def test_largura_42(self) -> None:
        s = dict(SETTINGS)
        s["receipt_columns"] = "42"
        lines = build_receipt_lines(
            FakeSale(),
            [FakeItem("Produto", "UN", 500, 1000, 500)],
            [FakePayment("dinheiro", 500)],
            s,
        )
        for ln in lines:
            assert len(ln) <= 42
