"""Testes unitarios do stock_service (sem HTTP)."""

from __future__ import annotations

import pytest

from app.models import AuditLog, Product, StockMovement, User
from app.security import hash_password
from app.services.stock_service import (
    StockError,
    list_low_stock,
    list_movements,
    register_adjustment,
    register_entry,
    register_loss,
)


# ---------- fixtures ----------


@pytest.fixture
def admin_db(session):
    u = User(
        name="Admin",
        username="adm",
        password_hash=hash_password("Senha1234"),
        role="admin",
        active=True,
    )
    session.add(u)
    session.commit()
    session.refresh(u)
    return u


@pytest.fixture
def produto_un(session):
    p = Product(
        name="Refrigerante",
        barcode="7891111111117",
        unit="UN",
        price_cents=1200,
        stock_milli=10_000,  # 10 unidades
        min_stock_milli=0,
        favorite=False,
        active=True,
    )
    session.add(p)
    session.commit()
    session.refresh(p)
    return p


@pytest.fixture
def produto_kg(session):
    p = Product(
        name="Pao frances",
        internal_code="101",
        unit="KG",
        price_cents=1800,
        stock_milli=5_000,  # 5 kg
        min_stock_milli=2_000,  # 2 kg minimo
        favorite=False,
        active=True,
    )
    session.add(p)
    session.commit()
    session.refresh(p)
    return p


@pytest.fixture
def produto_inativo(session):
    p = Product(
        name="Descontinuado",
        internal_code="999",
        unit="UN",
        price_cents=500,
        stock_milli=3_000,
        min_stock_milli=0,
        favorite=False,
        active=False,
    )
    session.add(p)
    session.commit()
    session.refresh(p)
    return p


# ---------- entrada ----------


def test_entrada_sem_motivo_atualiza_estoque(session, admin_db, produto_un):
    estoque_antes = produto_un.stock_milli
    mv = register_entry(
        session, user=admin_db, product_id=produto_un.id, qty_milli=5_000
    )
    session.refresh(produto_un)
    assert produto_un.stock_milli == estoque_antes + 5_000
    assert mv.type == "entrada"
    assert mv.qty_milli == 5_000
    assert mv.reason is None
    assert mv.user_id == admin_db.id


def test_entrada_com_motivo_salva_reason(session, admin_db, produto_un):
    mv = register_entry(
        session,
        user=admin_db,
        product_id=produto_un.id,
        qty_milli=1_000,
        reason="Nota 1234 Fornecedor X",
    )
    assert mv.reason == "Nota 1234 Fornecedor X"


def test_entrada_motivo_vazio_fica_none(session, admin_db, produto_un):
    mv = register_entry(
        session, user=admin_db, product_id=produto_un.id, qty_milli=1_000, reason="   "
    )
    assert mv.reason is None


def test_entrada_qty_zero_falha(session, admin_db, produto_un):
    with pytest.raises(StockError) as exc:
        register_entry(session, user=admin_db, product_id=produto_un.id, qty_milli=0)
    assert exc.value.status_code == 422


def test_entrada_qty_negativa_falha(session, admin_db, produto_un):
    with pytest.raises(StockError):
        register_entry(session, user=admin_db, product_id=produto_un.id, qty_milli=-5)


def test_entrada_produto_inexistente_falha(session, admin_db):
    with pytest.raises(StockError) as exc:
        register_entry(session, user=admin_db, product_id=99999, qty_milli=1_000)
    assert exc.value.status_code == 404


def test_entrada_produto_inativo_falha(session, admin_db, produto_inativo):
    with pytest.raises(StockError) as exc:
        register_entry(
            session, user=admin_db, product_id=produto_inativo.id, qty_milli=1_000
        )
    assert exc.value.status_code == 400


def test_entrada_grava_audit_log(session, admin_db, produto_un):
    register_entry(session, user=admin_db, product_id=produto_un.id, qty_milli=1_000)
    audits = session.query(AuditLog).filter_by(action="stock_entry").all()
    assert len(audits) == 1
    assert audits[0].entity == "product"
    assert audits[0].entity_id == produto_un.id
    assert audits[0].user_id == admin_db.id


# ---------- perda ----------


def test_perda_atualiza_estoque_para_negativo(session, admin_db, produto_un):
    # Padaria pode ter estoque negativo (CLAUDE.md decisao 9)
    estoque_antes = produto_un.stock_milli
    mv = register_loss(
        session,
        user=admin_db,
        product_id=produto_un.id,
        qty_milli=3_000,
        reason="Vencimento",
    )
    session.refresh(produto_un)
    assert produto_un.stock_milli == estoque_antes - 3_000
    assert mv.type == "perda"
    assert mv.qty_milli == -3_000
    assert mv.reason == "Vencimento"


def test_perda_motivo_obrigatorio_vazio_falha(session, admin_db, produto_un):
    with pytest.raises(StockError) as exc:
        register_loss(
            session, user=admin_db, product_id=produto_un.id, qty_milli=1_000, reason=""
        )
    assert exc.value.status_code == 422
    assert "motivo" in exc.value.message.lower()


def test_perda_motivo_whitespace_falha(session, admin_db, produto_un):
    with pytest.raises(StockError):
        register_loss(
            session,
            user=admin_db,
            product_id=produto_un.id,
            qty_milli=1_000,
            reason="   ",
        )


def test_perda_motivo_curto_falha(session, admin_db, produto_un):
    with pytest.raises(StockError):
        register_loss(
            session,
            user=admin_db,
            product_id=produto_un.id,
            qty_milli=1_000,
            reason="ab",
        )


def test_perda_motivo_muito_longo_falha(session, admin_db, produto_un):
    with pytest.raises(StockError):
        register_loss(
            session,
            user=admin_db,
            product_id=produto_un.id,
            qty_milli=1_000,
            reason="x" * 201,
        )


def test_perda_qty_invalida_falha(session, admin_db, produto_un):
    with pytest.raises(StockError):
        register_loss(
            session,
            user=admin_db,
            product_id=produto_un.id,
            qty_milli=0,
            reason="Teste",
        )


def test_perda_produto_inativo_falha(session, admin_db, produto_inativo):
    with pytest.raises(StockError):
        register_loss(
            session,
            user=admin_db,
            product_id=produto_inativo.id,
            qty_milli=1_000,
            reason="Teste",
        )


def test_perda_grava_audit_log(session, admin_db, produto_un):
    register_loss(
        session,
        user=admin_db,
        product_id=produto_un.id,
        qty_milli=1_000,
        reason="Vencimento lote XY",
    )
    audits = session.query(AuditLog).filter_by(action="stock_loss").all()
    assert len(audits) == 1


# ---------- ajuste ----------


def test_ajuste_delta_positivo(session, admin_db, produto_un):
    # saldo era 10, novo 15 -> delta +5
    mv = register_adjustment(
        session,
        user=admin_db,
        product_id=produto_un.id,
        new_stock_milli=15_000,
        reason="Inventario mensal",
    )
    session.refresh(produto_un)
    assert produto_un.stock_milli == 15_000
    assert mv.qty_milli == 5_000
    assert mv.type == "ajuste"


def test_ajuste_delta_negativo(session, admin_db, produto_un):
    # saldo era 10, novo 7 -> delta -3
    mv = register_adjustment(
        session,
        user=admin_db,
        product_id=produto_un.id,
        new_stock_milli=7_000,
        reason="Divergencia encontrada",
    )
    session.refresh(produto_un)
    assert produto_un.stock_milli == 7_000
    assert mv.qty_milli == -3_000


def test_ajuste_delta_zero_falha(session, admin_db, produto_un):
    # saldo era 10, novo 10 -> delta 0 -> erro
    with pytest.raises(StockError) as exc:
        register_adjustment(
            session,
            user=admin_db,
            product_id=produto_un.id,
            new_stock_milli=produto_un.stock_milli,
            reason="Teste",
        )
    assert exc.value.status_code == 422


def test_ajuste_novo_negativo_falha(session, admin_db, produto_un):
    with pytest.raises(StockError):
        register_adjustment(
            session,
            user=admin_db,
            product_id=produto_un.id,
            new_stock_milli=-100,
            reason="Teste",
        )


def test_ajuste_motivo_obrigatorio(session, admin_db, produto_un):
    with pytest.raises(StockError):
        register_adjustment(
            session,
            user=admin_db,
            product_id=produto_un.id,
            new_stock_milli=5_000,
            reason="",
        )


def test_ajuste_motivo_curto_falha(session, admin_db, produto_un):
    with pytest.raises(StockError):
        register_adjustment(
            session,
            user=admin_db,
            product_id=produto_un.id,
            new_stock_milli=5_000,
            reason="xy",
        )


def test_ajuste_produto_inativo_rejeitado(session, admin_db, produto_inativo):
    """Decisao do dono 2026-10-14: nao permitir ajuste em produto inativo."""
    with pytest.raises(StockError) as exc:
        register_adjustment(
            session,
            user=admin_db,
            product_id=produto_inativo.id,
            new_stock_milli=0,
            reason="Zerar saldo",
        )
    assert exc.value.status_code == 400


def test_ajuste_grava_audit_log(session, admin_db, produto_un):
    register_adjustment(
        session,
        user=admin_db,
        product_id=produto_un.id,
        new_stock_milli=20_000,
        reason="Correcao de contagem",
    )
    audits = session.query(AuditLog).filter_by(action="stock_adjustment").all()
    assert len(audits) == 1


def test_ajuste_para_zero_funciona(session, admin_db, produto_un):
    mv = register_adjustment(
        session,
        user=admin_db,
        product_id=produto_un.id,
        new_stock_milli=0,
        reason="Esgotou e nao tem reposicao",
    )
    session.refresh(produto_un)
    assert produto_un.stock_milli == 0
    assert mv.qty_milli == -10_000  # delta: 0 - 10_000


# ---------- invariante soma(movements) == stock ----------


def test_invariante_soma_igual_a_stock(session, admin_db, produto_un):
    """Entrada 5, perda 2, ajuste pra 15 => stock=15, soma=10+5-2+2=15."""
    register_entry(
        session, user=admin_db, product_id=produto_un.id, qty_milli=5_000
    )
    register_loss(
        session,
        user=admin_db,
        product_id=produto_un.id,
        qty_milli=2_000,
        reason="Quebra",
    )
    # saldo agora = 10 + 5 - 2 = 13
    register_adjustment(
        session,
        user=admin_db,
        product_id=produto_un.id,
        new_stock_milli=15_000,
        reason="Correcao",
    )
    session.refresh(produto_un)
    assert produto_un.stock_milli == 15_000

    movements = (
        session.query(StockMovement)
        .filter_by(product_id=produto_un.id)
        .all()
    )
    soma = sum(m.qty_milli for m in movements)
    # saldo inicial era 10_000, soma dos movements deve ser +5_000
    assert soma == 15_000 - 10_000


# ---------- list_movements ----------


def test_list_movements_vazio(session):
    assert list_movements(session) == []


def test_list_movements_filtro_tipo(session, admin_db, produto_un, produto_kg):
    register_entry(session, user=admin_db, product_id=produto_un.id, qty_milli=1_000)
    register_loss(
        session,
        user=admin_db,
        product_id=produto_un.id,
        qty_milli=500,
        reason="Teste perda",
    )
    rows = list_movements(session, type_="entrada")
    assert len(rows) == 1
    assert rows[0].type == "entrada"


def test_list_movements_filtro_produto(session, admin_db, produto_un, produto_kg):
    register_entry(session, user=admin_db, product_id=produto_un.id, qty_milli=1_000)
    register_entry(session, user=admin_db, product_id=produto_kg.id, qty_milli=2_000)
    rows = list_movements(session, product_id=produto_kg.id)
    assert len(rows) == 1
    assert rows[0].product_id == produto_kg.id
    assert rows[0].product_name == "Pao frances"
    assert rows[0].product_unit == "KG"


def test_list_movements_ordena_decrescente(session, admin_db, produto_un):
    register_entry(session, user=admin_db, product_id=produto_un.id, qty_milli=100)
    register_entry(session, user=admin_db, product_id=produto_un.id, qty_milli=200)
    register_entry(session, user=admin_db, product_id=produto_un.id, qty_milli=300)
    rows = list_movements(session)
    # mais recente primeiro: 300, 200, 100
    assert [r.qty_milli for r in rows] == [300, 200, 100]


# ---------- list_low_stock ----------


def test_low_stock_vazio_quando_nenhum_configurado(session, admin_db, produto_un):
    # produto_un tem min_stock_milli=0 -> nao aparece
    rows = list_low_stock(session)
    assert rows == []


def test_low_stock_detecta_abaixo_do_minimo(session, admin_db, produto_kg):
    # produto_kg: stock=5, min=2 -> acima, nao aparece
    assert list_low_stock(session) == []
    # Baixa pra 1
    register_loss(
        session,
        user=admin_db,
        product_id=produto_kg.id,
        qty_milli=4_000,
        reason="Quebra total",
    )
    rows = list_low_stock(session)
    assert len(rows) == 1
    assert rows[0].product_id == produto_kg.id
    assert rows[0].stock_milli == 1_000
    assert rows[0].min_stock_milli == 2_000


def test_low_stock_igual_ao_minimo_aparece(session, admin_db, produto_kg):
    # Baixa pra 2 (igual ao min)
    register_loss(
        session,
        user=admin_db,
        product_id=produto_kg.id,
        qty_milli=3_000,
        reason="Perda",
    )
    rows = list_low_stock(session)
    assert len(rows) == 1


def test_low_stock_ignora_inativos(session, admin_db, produto_kg):
    produto_kg.active = False
    produto_kg.min_stock_milli = 10_000  # bem acima
    session.commit()
    rows = list_low_stock(session)
    assert rows == []
