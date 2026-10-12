"""
Importacao de produtos a partir de CSV.

Projetado para rodar via `scripts/import_products.py`, SEM endpoint HTTP.
Validacao reusa `app.schemas.ProductCreate`, `app.money.parse_brl` e
`app.money.parse_qty` para que a logica fique consistente com a API.

Formato esperado (cabecalho obrigatorio):
    name,barcode,internal_code,category,unit,price,stock,min_stock,favorite

- Encoding: UTF-8 com ou sem BOM.
- Separador: virgula ou ponto-e-virgula (detectado automaticamente).
- `category` cria se nao existir.
- Produto existente (mesmo barcode OU internal_code) e PULADO (idempotente).
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from pydantic import ValidationError
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models import Category, Product
from app.money import parse_brl, parse_qty
from app.schemas import ProductCreate

# Limites de sanidade.
MAX_FILE_BYTES = 2 * 1024 * 1024  # 2 MB
MAX_ROWS = 2000

REQUIRED_HEADERS = {"name", "unit", "price"}
ALLOWED_HEADERS = {
    "name",
    "barcode",
    "internal_code",
    "category",
    "unit",
    "price",
    "stock",
    "min_stock",
    "favorite",
}

TRUE_VALUES = {"true", "1", "sim", "s", "yes", "y", "verdadeiro"}
FALSE_VALUES = {"false", "0", "nao", "n", "no", "", "falso"}


@dataclass
class ParsedRow:
    """Uma linha pronta pra virar Product."""

    line_number: int
    data: ProductCreate
    category_name: Optional[str]


@dataclass
class RowError:
    line_number: int
    message: str
    raw: dict[str, str]


@dataclass
class ParseResult:
    rows: list[ParsedRow] = field(default_factory=list)
    errors: list[RowError] = field(default_factory=list)

    def ok(self) -> bool:
        return not self.errors


@dataclass
class ImportResult:
    inserted: int = 0
    skipped_existing: int = 0
    errors: list[RowError] = field(default_factory=list)
    dry_run: bool = False

    def summary(self) -> str:
        parts = [
            f"inseridos={self.inserted}",
            f"pulados_existentes={self.skipped_existing}",
            f"erros={len(self.errors)}",
        ]
        if self.dry_run:
            parts.append("[DRY-RUN - nada foi gravado]")
        return " | ".join(parts)


# ---------- parsing ----------


def _parse_bool(value: str) -> Optional[bool]:
    v = (value or "").strip().lower()
    if v in TRUE_VALUES:
        return True
    if v in FALSE_VALUES:
        return False
    return None


def _strip_bom(text: str) -> str:
    if text.startswith("﻿"):
        return text[1:]
    return text


def _detect_dialect(sample: str) -> csv.Dialect:
    """
    Detecta separador. Fallback para virgula.
    Excel-BR costuma exportar com `;`.
    """
    try:
        return csv.Sniffer().sniff(sample, delimiters=",;")
    except csv.Error:
        class _Default(csv.Dialect):
            delimiter = ","
            quotechar = '"'
            doublequote = True
            skipinitialspace = True
            lineterminator = "\n"
            quoting = csv.QUOTE_MINIMAL

        return _Default()


def _validate_headers(fieldnames: Optional[list[str]]) -> Optional[str]:
    if not fieldnames:
        return "arquivo sem cabecalho"
    normalized = {f.strip().lower() for f in fieldnames}
    missing = REQUIRED_HEADERS - normalized
    if missing:
        return f"faltam colunas obrigatorias: {', '.join(sorted(missing))}"
    unknown = normalized - ALLOWED_HEADERS
    if unknown:
        return f"colunas nao reconhecidas: {', '.join(sorted(unknown))}"
    return None


def _row_to_create(raw: dict[str, str], line_number: int) -> ParsedRow:
    """Converte uma linha do CSV em ParsedRow ou lanca ValueError."""
    # Normaliza chaves (lowercase + strip)
    norm = {(k or "").strip().lower(): (v or "").strip() for k, v in raw.items()}

    name = norm.get("name", "")
    unit = norm.get("unit", "").upper()
    price_raw = norm.get("price", "")
    if not name or not unit or not price_raw:
        raise ValueError("name, unit e price sao obrigatorios")

    # Parse de preco: aceita BRL ("18,00", "R$ 18,00", "1.234,56") ou cents puro
    try:
        price_cents = parse_brl(price_raw)
    except (ValueError, TypeError) as exc:
        raise ValueError(f"price invalido ({price_raw!r}): {exc}") from exc

    cost_cents: Optional[int] = None
    cost_raw = norm.get("cost") or ""
    if cost_raw:
        try:
            cost_cents = parse_brl(cost_raw)
        except (ValueError, TypeError) as exc:
            raise ValueError(f"cost invalido ({cost_raw!r}): {exc}") from exc

    stock_raw = norm.get("stock") or ""
    if stock_raw:
        try:
            stock_milli = parse_qty(stock_raw, unit)  # type: ignore[arg-type]
        except (ValueError, TypeError) as exc:
            raise ValueError(f"stock invalido ({stock_raw!r}): {exc}") from exc
    else:
        stock_milli = 0

    min_stock_raw = norm.get("min_stock") or ""
    if min_stock_raw:
        try:
            min_stock_milli = parse_qty(min_stock_raw, unit)  # type: ignore[arg-type]
        except (ValueError, TypeError) as exc:
            raise ValueError(
                f"min_stock invalido ({min_stock_raw!r}): {exc}"
            ) from exc
    else:
        min_stock_milli = 0

    favorite_raw = norm.get("favorite") or ""
    fav = _parse_bool(favorite_raw)
    if fav is None:
        raise ValueError(f"favorite invalido ({favorite_raw!r})")

    barcode = norm.get("barcode") or None
    internal_code = norm.get("internal_code") or None
    category_name = norm.get("category") or None

    try:
        payload = ProductCreate(
            name=name,
            barcode=barcode,
            internal_code=internal_code,
            unit=unit,  # type: ignore[arg-type]
            price_cents=price_cents,
            cost_cents=cost_cents,
            stock_milli=stock_milli,
            min_stock_milli=min_stock_milli,
            favorite=fav,
        )
    except ValidationError as exc:
        msgs = "; ".join(e["msg"] for e in exc.errors())
        raise ValueError(msgs) from exc

    return ParsedRow(line_number=line_number, data=payload, category_name=category_name)


def parse_csv_text(text: str) -> ParseResult:
    """
    Parse o CSV completo e devolve linhas prontas + erros por linha.
    Nao toca no banco.
    """
    text = _strip_bom(text)
    if not text.strip():
        return ParseResult(errors=[RowError(0, "arquivo vazio", {})])

    # Usa so as primeiras linhas para detectar separador.
    sample = "\n".join(text.splitlines()[:5])
    dialect = _detect_dialect(sample)

    reader = csv.DictReader(io.StringIO(text), dialect=dialect)
    header_err = _validate_headers(reader.fieldnames)
    if header_err:
        return ParseResult(errors=[RowError(1, header_err, {})])

    result = ParseResult()
    for idx, raw in enumerate(reader, start=2):  # linha 1 = header
        if all((v or "").strip() == "" for v in raw.values()):
            continue  # linha vazia
        try:
            parsed = _row_to_create(raw, idx)
            result.rows.append(parsed)
        except ValueError as exc:
            result.errors.append(RowError(idx, str(exc), dict(raw)))
        if len(result.rows) + len(result.errors) > MAX_ROWS:
            result.errors.append(
                RowError(idx, f"limite de {MAX_ROWS} linhas excedido", {})
            )
            break
    return result


def read_csv_file(path: Path) -> str:
    """Le arquivo CSV com validacao de tamanho e encoding."""
    if not path.exists():
        raise FileNotFoundError(f"arquivo nao encontrado: {path}")
    size = path.stat().st_size
    if size > MAX_FILE_BYTES:
        raise ValueError(
            f"arquivo muito grande ({size} bytes). "
            f"Limite: {MAX_FILE_BYTES} bytes."
        )
    try:
        return path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError as exc:
        # tenta latin-1 como fallback com aviso
        raise ValueError(
            "arquivo nao esta em UTF-8. Salve o CSV como UTF-8 e tente de novo."
        ) from exc


# ---------- import no banco ----------


def _get_or_create_category(db: Session, name: str) -> Category:
    cat = db.execute(select(Category).where(Category.name == name)).scalar_one_or_none()
    if cat is None:
        cat = Category(name=name)
        db.add(cat)
        db.flush()
    return cat


def import_rows(
    db: Session,
    rows: list[ParsedRow],
    *,
    dry_run: bool = False,
    strict: bool = False,
) -> ImportResult:
    """
    Importa linhas ja parseadas. Transacao unica:
    - sem dry_run: commit no final
    - sem strict: linhas duplicadas apenas pulam
    - com strict: qualquer erro aborta e faz rollback
    """
    result = ImportResult(dry_run=dry_run)
    try:
        for pr in rows:
            payload = pr.data
            # Idempotencia por barcode OU internal_code
            existing = None
            if payload.barcode:
                existing = db.execute(
                    select(Product).where(Product.barcode == payload.barcode)
                ).scalar_one_or_none()
            if existing is None and payload.internal_code:
                existing = db.execute(
                    select(Product).where(
                        Product.internal_code == payload.internal_code
                    )
                ).scalar_one_or_none()
            if existing is not None:
                result.skipped_existing += 1
                if strict:
                    result.errors.append(
                        RowError(
                            pr.line_number,
                            f"produto ja existe (id={existing.id})",
                            {},
                        )
                    )
                    db.rollback()
                    return result
                continue

            category_id = None
            if pr.category_name:
                cat = _get_or_create_category(db, pr.category_name)
                category_id = cat.id

            product = Product(
                name=payload.name,
                barcode=payload.barcode,
                internal_code=payload.internal_code,
                category_id=category_id,
                unit=payload.unit,
                price_cents=payload.price_cents,
                cost_cents=payload.cost_cents,
                stock_milli=payload.stock_milli,
                min_stock_milli=payload.min_stock_milli,
                favorite=payload.favorite,
                active=True,
            )
            db.add(product)
            try:
                db.flush()
            except Exception as exc:
                db.rollback()
                result.errors.append(RowError(pr.line_number, str(exc), {}))
                if strict:
                    return result
                # Em modo nao-strict, nao conseguimos continuar com transacao
                # revertida; abortamos.
                return result
            result.inserted += 1

        if dry_run:
            db.rollback()
        else:
            db.commit()
    except Exception:
        db.rollback()
        raise
    return result


def import_csv_file(
    db: Session,
    path: Path,
    *,
    dry_run: bool = False,
    strict: bool = False,
) -> tuple[ParseResult, ImportResult]:
    text = read_csv_file(path)
    parse_result = parse_csv_text(text)
    if not parse_result.ok() and strict:
        return parse_result, ImportResult(dry_run=dry_run, errors=parse_result.errors)
    import_result = import_rows(
        db, parse_result.rows, dry_run=dry_run, strict=strict
    )
    # Erros de parse somam aos de import para o relatorio final.
    import_result.errors = parse_result.errors + import_result.errors
    return parse_result, import_result
