"""Testes do modulo app.money."""

from __future__ import annotations

import pytest

from app.money import (
    MAX_CENTS,
    MAX_MILLI,
    format_brl,
    format_qty,
    line_total_cents,
    parse_brl,
    parse_qty,
)


class TestLineTotalCents:
    """Funcao unica de arredondamento. CLAUDE.md regra 2."""

    def test_pao_frances_meio_kilo(self) -> None:
        # 0,350 kg x R$ 18,00 = R$ 6,30
        assert line_total_cents(1800, 350) == 630

    def test_tres_x_tres_trinta_e_tres(self) -> None:
        # 3 x R$ 3,33 = R$ 9,99
        assert line_total_cents(333, 3000) == 999

    def test_um_x_dez_reais(self) -> None:
        # 1 x R$ 10,00 = R$ 10,00
        assert line_total_cents(1000, 1000) == 1000

    def test_qty_zero_resulta_zero(self) -> None:
        assert line_total_cents(1800, 0) == 0

    def test_preco_zero_resulta_zero(self) -> None:
        assert line_total_cents(0, 1000) == 0

    def test_arredondamento_meia_casa_para_cima(self) -> None:
        # price=1 centavo, qty=500 milesimos (meio) -> (500+500)//1000 = 1
        assert line_total_cents(1, 500) == 1

    def test_arredondamento_abaixo_meia_casa(self) -> None:
        # 499 milesimos -> abaixo da meia, arredonda para baixo
        assert line_total_cents(1, 499) == 0

    def test_arredondamento_acima_meia_casa(self) -> None:
        # 501 milesimos -> acima da meia, arredonda para cima
        assert line_total_cents(1, 501) == 1

    def test_valor_grande(self) -> None:
        # 100 x R$ 100,00 = R$ 10.000,00
        assert line_total_cents(10000, 100000) == 1000000

    def test_rejeita_float_no_preco(self) -> None:
        with pytest.raises(TypeError):
            line_total_cents(18.0, 350)  # type: ignore[arg-type]

    def test_rejeita_float_na_qty(self) -> None:
        with pytest.raises(TypeError):
            line_total_cents(1800, 0.35)  # type: ignore[arg-type]

    def test_rejeita_bool(self) -> None:
        # bool e subclasse de int, mas False/True virariam 0/1 silenciosamente.
        with pytest.raises(TypeError):
            line_total_cents(True, 1000)  # type: ignore[arg-type]

    def test_rejeita_preco_negativo(self) -> None:
        with pytest.raises(ValueError):
            line_total_cents(-100, 1000)

    def test_rejeita_qty_negativa(self) -> None:
        with pytest.raises(ValueError):
            line_total_cents(1000, -100)

    def test_rejeita_preco_acima_do_teto(self) -> None:
        with pytest.raises(ValueError):
            line_total_cents(MAX_CENTS + 1, 1000)

    def test_rejeita_qty_acima_do_teto(self) -> None:
        with pytest.raises(ValueError):
            line_total_cents(1000, MAX_MILLI + 1)


class TestFormatBRL:
    """Formatacao de centavos para string com separadores brasileiros."""

    def test_sem_centavos(self) -> None:
        assert format_brl(1800) == "R$ 18,00"

    def test_zero(self) -> None:
        assert format_brl(0) == "R$ 0,00"

    def test_com_centavos(self) -> None:
        assert format_brl(999) == "R$ 9,99"

    def test_mil_reais_tem_separador_de_milhar(self) -> None:
        assert format_brl(100000) == "R$ 1.000,00"

    def test_cem_mil_reais(self) -> None:
        assert format_brl(10000000) == "R$ 100.000,00"

    def test_milhao(self) -> None:
        assert format_brl(100000000) == "R$ 1.000.000,00"

    def test_apenas_centavos(self) -> None:
        assert format_brl(5) == "R$ 0,05"

    def test_rejeita_float(self) -> None:
        with pytest.raises(TypeError):
            format_brl(18.0)  # type: ignore[arg-type]


class TestParseBRL:
    """Converte texto para centavos."""

    def test_formato_brasileiro(self) -> None:
        assert parse_brl("18,00") == 1800

    def test_formato_americano(self) -> None:
        assert parse_brl("18.00") == 1800

    def test_com_prefixo_rs(self) -> None:
        assert parse_brl("R$ 18,00") == 1800

    def test_com_milhar_brasileiro(self) -> None:
        assert parse_brl("1.234,56") == 123456

    def test_com_milhar_americano(self) -> None:
        assert parse_brl("1,234.56") == 123456

    def test_so_inteiro(self) -> None:
        assert parse_brl("18") == 1800

    def test_centavos_pequenos(self) -> None:
        assert parse_brl("0,05") == 5

    def test_uma_casa_decimal(self) -> None:
        assert parse_brl("1,5") == 150

    def test_rejeita_vazio(self) -> None:
        with pytest.raises(ValueError):
            parse_brl("   ")

    def test_rejeita_negativo(self) -> None:
        with pytest.raises(ValueError):
            parse_brl("-10,00")

    def test_rejeita_tres_casas_decimais(self) -> None:
        with pytest.raises(ValueError):
            parse_brl("18,000")

    def test_rejeita_lixo(self) -> None:
        with pytest.raises(ValueError):
            parse_brl("abc")


class TestFormatQty:
    """Formatacao de quantidade conforme a unidade."""

    def test_un_inteiro(self) -> None:
        assert format_qty(3000, "UN") == "3"

    def test_un_zero(self) -> None:
        assert format_qty(0, "UN") == "0"

    def test_kg_fracionario(self) -> None:
        assert format_qty(350, "KG") == "0,350"

    def test_kg_um_quilo(self) -> None:
        assert format_qty(1000, "KG") == "1,000"

    def test_l_um_e_meio(self) -> None:
        assert format_qty(1500, "L") == "1,500"

    def test_rejeita_unidade_invalida(self) -> None:
        with pytest.raises(ValueError):
            format_qty(1000, "ML")  # type: ignore[arg-type]

    def test_rejeita_float(self) -> None:
        with pytest.raises(TypeError):
            format_qty(1.5, "KG")  # type: ignore[arg-type]


class TestParseQty:
    """Converte texto para milesimos conforme a unidade."""

    def test_un_inteiro(self) -> None:
        assert parse_qty("3", "UN") == 3000

    def test_un_com_virgula(self) -> None:
        assert parse_qty("3,000", "UN") == 3000

    def test_kg_fracionario_virgula(self) -> None:
        assert parse_qty("0,350", "KG") == 350

    def test_kg_fracionario_ponto(self) -> None:
        assert parse_qty("0.350", "KG") == 350

    def test_kg_inteiro(self) -> None:
        assert parse_qty("1", "KG") == 1000

    def test_l_meio_litro(self) -> None:
        assert parse_qty("0,500", "L") == 500

    def test_rejeita_vazio(self) -> None:
        with pytest.raises(ValueError):
            parse_qty("", "KG")

    def test_rejeita_negativo(self) -> None:
        with pytest.raises(ValueError):
            parse_qty("-1,000", "KG")

    def test_rejeita_quatro_casas_decimais(self) -> None:
        with pytest.raises(ValueError):
            parse_qty("1,0000", "KG")

    def test_rejeita_unidade_invalida(self) -> None:
        with pytest.raises(ValueError):
            parse_qty("1", "ML")  # type: ignore[arg-type]

    def test_rejeita_lixo(self) -> None:
        with pytest.raises(ValueError):
            parse_qty("abc", "KG")

    def test_rejeita_qty_acima_teto(self) -> None:
        with pytest.raises(ValueError):
            parse_qty(f"{MAX_MILLI // 1000 + 1}", "UN")
