"""
Popula o banco com dados FICTICIOS para teste local.

NUNCA inclui dados reais do cliente. Para os dados reais, use
scripts/seed_cliente.py lendo data/cliente.json (que esta no .gitignore).

Uso:
    python scripts/seed_demo.py          # idempotente (ignora duplicatas)
    python scripts/seed_demo.py --reset  # limpa e re-popula
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Permite rodar fora da raiz do projeto.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy import delete, select  # noqa: E402

from app.db import SessionLocal  # noqa: E402
from app.models import Category, Product, Setting  # noqa: E402


DEMO_SETTINGS: dict[str, str] = {
    "store_name": "PADARIA DEMO",
    "store_cnpj": "00.000.000/0000-00",
    "store_address": "Rua Exemplo, 123 - Cidade/UF",
    "store_phone": "(00) 0000-0000",
    "receipt_header_extra": "",
    "receipt_footer": "Obrigado e volte sempre!",
    "receipt_columns": "32",
    "receipt_show_barcode": "false",
    "receipt_disclaimer": "DOCUMENTO SEM VALOR FISCAL",
    "printer_name": "",
    "printer_codepage": "",
    "printer_auto_cut": "false",
    "allow_negative_stock": "true",
    "default_print_after_sale": "true",
    "payment_methods": '["dinheiro","debito","credito","pix","outros"]',
}


DEMO_CATEGORIES: list[str] = [
    "Paes",
    "Doces",
    "Salgados",
    "Bebidas",
    "Mercearia",
]


# (nome, barcode, internal_code, categoria, unidade, preco_cents, estoque_milli, favorito)
DEMO_PRODUCTS: list[tuple] = [
    ("Pao frances", None, "101", "Paes", "KG", 1800, 10000, True),
    ("Pao de queijo", None, "102", "Paes", "UN", 350, 50000, True),
    ("Pao doce", None, "103", "Paes", "UN", 500, 30000, True),
    ("Bolo de chocolate (fatia)", None, "201", "Doces", "UN", 700, 10000, True),
    ("Sonho", None, "202", "Doces", "UN", 600, 20000, True),
    ("Coxinha", None, "301", "Salgados", "UN", 650, 20000, True),
    ("Esfiha", None, "302", "Salgados", "UN", 600, 20000, False),
    ("Cafe (xicara)", None, "401", "Bebidas", "UN", 400, 100000, True),
    ("Refrigerante 2L", "7891111111117", "402", "Bebidas", "UN", 1200, 24000, False),
    ("Agua mineral 500ml", "7891111111124", "403", "Bebidas", "UN", 400, 50000, False),
    ("Biscoito recheado", "7891111111131", "501", "Mercearia", "UN", 700, 30000, False),
    ("Leite integral 1L", "7891111111148", "502", "Mercearia", "L", 650, 15000, False),
]


def seed(reset: bool = False) -> None:
    session = SessionLocal()
    try:
        if reset:
            print("Reset: apagando dados...")
            session.execute(delete(Product))
            session.execute(delete(Category))
            session.execute(delete(Setting))
            session.commit()

        # Settings
        for key, value in DEMO_SETTINGS.items():
            existing = session.get(Setting, key)
            if existing is None:
                session.add(Setting(key=key, value=value))
        session.commit()
        print(f"Settings: {len(DEMO_SETTINGS)} chaves garantidas.")

        # Categorias (idempotente por nome)
        name_to_cat: dict[str, Category] = {}
        for name in DEMO_CATEGORIES:
            cat = session.execute(
                select(Category).where(Category.name == name)
            ).scalar_one_or_none()
            if cat is None:
                cat = Category(name=name)
                session.add(cat)
                session.flush()
            name_to_cat[name] = cat
        session.commit()
        print(f"Categorias: {len(name_to_cat)} garantidas.")

        # Produtos (idempotente por internal_code OU barcode)
        inserted = 0
        for row in DEMO_PRODUCTS:
            name, barcode, internal_code, cat_name, unit, price, stock, fav = row
            existing = None
            if internal_code:
                existing = session.execute(
                    select(Product).where(Product.internal_code == internal_code)
                ).scalar_one_or_none()
            if existing is None and barcode:
                existing = session.execute(
                    select(Product).where(Product.barcode == barcode)
                ).scalar_one_or_none()
            if existing is not None:
                continue
            session.add(
                Product(
                    name=name,
                    barcode=barcode,
                    internal_code=internal_code,
                    category_id=name_to_cat[cat_name].id,
                    unit=unit,
                    price_cents=price,
                    stock_milli=stock,
                    min_stock_milli=1000 if unit != "UN" else 10000,
                    favorite=fav,
                    active=True,
                )
            )
            inserted += 1
        session.commit()
        print(f"Produtos: {inserted} inseridos ({len(DEMO_PRODUCTS)} totais).")

        print("\nSeed demo concluido.")
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reset", action="store_true", help="Apaga tudo antes.")
    args = parser.parse_args()
    seed(reset=args.reset)
    return 0


if __name__ == "__main__":
    sys.exit(main())
