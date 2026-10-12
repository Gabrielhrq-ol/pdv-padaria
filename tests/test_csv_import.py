"""Testes do servico de importacao CSV."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import select

from app.models import Category, Product
from app.services.csv_import import (
    MAX_ROWS,
    ImportResult,
    ParseResult,
    import_csv_file,
    import_rows,
    parse_csv_text,
)


# ---------- parser ----------


class TestParser:
    def test_cabecalho_valido(self) -> None:
        csv_text = (
            "name,unit,price\n"
            'Pao frances,KG,"18,00"\n'
        )
        r = parse_csv_text(csv_text)
        assert r.ok()
        assert len(r.rows) == 1
        assert r.rows[0].data.name == "Pao frances"
        assert r.rows[0].data.price_cents == 1800

    def test_formato_cents_puro_aceito(self) -> None:
        csv_text = "name,unit,price\nX,UN,999\n"
        r = parse_csv_text(csv_text)
        assert r.ok()
        assert r.rows[0].data.price_cents == 99900

    def test_formato_brl_com_rs(self) -> None:
        csv_text = 'name,unit,price\nX,UN,"R$ 12,50"\n'
        r = parse_csv_text(csv_text)
        assert r.ok()
        assert r.rows[0].data.price_cents == 1250

    def test_separador_ponto_virgula(self) -> None:
        csv_text = (
            "name;unit;price\n"
            'Pao;KG;"18,00"\n'
        )
        r = parse_csv_text(csv_text)
        assert r.ok(), r.errors
        assert r.rows[0].data.name == "Pao"

    def test_bom_removido(self) -> None:
        bom = "﻿"
        csv_text = bom + "name,unit,price\nX,UN,100\n"
        r = parse_csv_text(csv_text)
        assert r.ok(), r.errors
        assert r.rows[0].data.name == "X"

    def test_falta_coluna_obrigatoria(self) -> None:
        csv_text = "name,price\nX,100\n"
        r = parse_csv_text(csv_text)
        assert not r.ok()
        assert "unit" in r.errors[0].message

    def test_coluna_nao_reconhecida(self) -> None:
        csv_text = "name,unit,price,drop_table\nX,UN,100,yes\n"
        r = parse_csv_text(csv_text)
        assert not r.ok()
        assert "drop_table" in r.errors[0].message

    def test_arquivo_vazio(self) -> None:
        r = parse_csv_text("")
        assert not r.ok()
        assert "vazio" in r.errors[0].message

    def test_linha_vazia_e_pulada(self) -> None:
        csv_text = (
            "name,unit,price\n"
            ",,\n"
            'Pao,KG,"18,00"\n'
        )
        r = parse_csv_text(csv_text)
        assert r.ok()
        assert len(r.rows) == 1

    def test_favorite_aceita_variantes(self) -> None:
        csv_text = (
            "name,unit,price,favorite\n"
            "A,UN,100,true\n"
            "B,UN,100,1\n"
            "C,UN,100,sim\n"
            "D,UN,100,false\n"
            "E,UN,100,nao\n"
            "F,UN,100,0\n"
        )
        r = parse_csv_text(csv_text)
        assert r.ok(), r.errors
        favs = [row.data.favorite for row in r.rows]
        assert favs == [True, True, True, False, False, False]

    def test_favorite_invalido_erro(self) -> None:
        csv_text = "name,unit,price,favorite\nX,UN,100,talvez\n"
        r = parse_csv_text(csv_text)
        assert len(r.errors) == 1
        assert "favorite" in r.errors[0].message.lower()

    def test_barcode_so_digitos(self) -> None:
        csv_text = "name,unit,price,barcode\nX,UN,100,ABC\n"
        r = parse_csv_text(csv_text)
        assert len(r.errors) == 1

    def test_stock_formato_decimal_kg(self) -> None:
        csv_text = 'name,unit,price,stock\nPao,KG,"18,00","0,350"\n'
        r = parse_csv_text(csv_text)
        assert r.ok()
        assert r.rows[0].data.stock_milli == 350

    def test_category_opcional(self) -> None:
        csv_text = "name,unit,price,category\nX,UN,100,\n"
        r = parse_csv_text(csv_text)
        assert r.ok()
        assert r.rows[0].category_name is None

    def test_rejeita_mais_de_max_rows(self) -> None:
        linhas = ["name,unit,price"]
        for i in range(MAX_ROWS + 5):
            linhas.append(f"P{i},UN,100")
        csv_text = "\n".join(linhas)
        r = parse_csv_text(csv_text)
        assert any("limite" in e.message.lower() for e in r.errors)


# ---------- import ----------


class TestImport:
    def test_insere_produtos(self, session) -> None:
        text = (
            "name,unit,price,category\n"
            'Pao,KG,"18,00",Paes\n'
            "Cafe,UN,400,Bebidas\n"
        )
        pr = parse_csv_text(text)
        assert pr.ok()
        res = import_rows(session, pr.rows)
        assert res.inserted == 2
        assert res.skipped_existing == 0
        assert not res.errors
        # Confirma no banco
        count = len(session.execute(select(Product)).scalars().all())
        assert count == 2

    def test_cria_categorias_automaticamente(self, session) -> None:
        text = (
            "name,unit,price,category\n"
            "A,UN,100,Nova1\n"
            "B,UN,100,Nova1\n"
            "C,UN,100,Nova2\n"
        )
        pr = parse_csv_text(text)
        import_rows(session, pr.rows)
        cats = session.execute(select(Category)).scalars().all()
        assert {c.name for c in cats} == {"Nova1", "Nova2"}

    def test_idempotente_barcode(self, session) -> None:
        text = 'name,unit,price,barcode\nX,UN,100,"7891111111117"\n'
        pr = parse_csv_text(text)
        import_rows(session, pr.rows)
        # Segunda importacao do mesmo arquivo
        pr2 = parse_csv_text(text)
        res = import_rows(session, pr2.rows)
        assert res.inserted == 0
        assert res.skipped_existing == 1

    def test_idempotente_internal_code(self, session) -> None:
        text = "name,unit,price,internal_code\nX,UN,100,101\n"
        pr = parse_csv_text(text)
        import_rows(session, pr.rows)
        pr2 = parse_csv_text(text)
        res = import_rows(session, pr2.rows)
        assert res.inserted == 0
        assert res.skipped_existing == 1

    def test_dry_run_nao_grava(self, session) -> None:
        text = (
            "name,unit,price\n"
            "A,UN,100\n"
            "B,UN,200\n"
        )
        pr = parse_csv_text(text)
        res = import_rows(session, pr.rows, dry_run=True)
        assert res.inserted == 2
        assert res.dry_run
        count = len(session.execute(select(Product)).scalars().all())
        assert count == 0

    def test_strict_para_no_primeiro_duplicado(self, session) -> None:
        # Insere primeiro
        text1 = "name,unit,price,internal_code\nX,UN,100,101\n"
        pr1 = parse_csv_text(text1)
        import_rows(session, pr1.rows)

        # Tenta de novo com strict
        text2 = (
            "name,unit,price,internal_code\n"
            "X,UN,100,101\n"
            "Y,UN,200,102\n"
        )
        pr2 = parse_csv_text(text2)
        res = import_rows(session, pr2.rows, strict=True)
        assert res.errors
        # Nao deve ter inserido o Y
        count = len(session.execute(select(Product)).scalars().all())
        assert count == 1


# ---------- import_csv_file (end-to-end) ----------


class TestImportFile:
    def test_arquivo_exemplo_versionado_importa(self, session, tmp_path) -> None:
        """Garante que data/produtos.example.csv e um CSV valido."""
        example = Path(__file__).resolve().parent.parent / "data" / "produtos.example.csv"
        parse, result = import_csv_file(session, example, dry_run=True)
        assert parse.ok(), parse.errors
        assert result.inserted >= 10
        assert not result.errors

    def test_arquivo_nao_existe(self, session, tmp_path) -> None:
        bad = tmp_path / "nao_existe.csv"
        with pytest.raises(FileNotFoundError):
            import_csv_file(session, bad)
