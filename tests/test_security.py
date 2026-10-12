"""Testes do app.security."""

from __future__ import annotations

import time

import pytest

from app.security import (
    MIN_PASSWORD_LENGTH,
    compare_csrf_tokens,
    create_session_token,
    generate_csrf_token,
    hash_password,
    needs_rehash,
    validate_password_strength,
    verify_password,
    verify_session_token,
)


class TestHashPassword:
    def test_gera_hash(self) -> None:
        h = hash_password("MinhaSenha123")
        assert h.startswith("$argon2id$")
        assert "MinhaSenha123" not in h

    def test_hashes_sao_diferentes_mesmo_input(self) -> None:
        h1 = hash_password("MinhaSenha123")
        h2 = hash_password("MinhaSenha123")
        assert h1 != h2  # salt aleatorio

    def test_rejeita_vazio(self) -> None:
        with pytest.raises(ValueError):
            hash_password("")

    def test_rejeita_nao_str(self) -> None:
        with pytest.raises(TypeError):
            hash_password(12345)  # type: ignore[arg-type]


class TestVerifyPassword:
    def test_aceita_senha_correta(self) -> None:
        h = hash_password("MinhaSenha123")
        assert verify_password("MinhaSenha123", h) is True

    def test_rejeita_senha_errada(self) -> None:
        h = hash_password("MinhaSenha123")
        assert verify_password("Errada123", h) is False

    def test_rejeita_vazio(self) -> None:
        h = hash_password("MinhaSenha123")
        assert verify_password("", h) is False
        assert verify_password("x", "") is False

    def test_rejeita_hash_invalido(self) -> None:
        assert verify_password("x", "nao-e-hash") is False

    def test_nao_lanca_em_nenhum_caso(self) -> None:
        # Entradas estranhas nao podem derrubar o processo.
        assert verify_password("x", "$argon2id$corrompido") is False


class TestNeedsRehash:
    def test_hash_novo_nao_precisa(self) -> None:
        h = hash_password("MinhaSenha123")
        assert needs_rehash(h) is False

    def test_hash_invalido_sinaliza_rehash(self) -> None:
        assert needs_rehash("nao-e-hash") is True


class TestValidatePasswordStrength:
    def test_aceita_senha_forte(self) -> None:
        assert validate_password_strength("MinhaSenha123") is None

    def test_rejeita_curta(self) -> None:
        msg = validate_password_strength("ab1")
        assert msg and "caracteres" in msg

    def test_rejeita_sem_letra(self) -> None:
        msg = validate_password_strength("12345678")
        assert msg and "letra" in msg

    def test_rejeita_sem_numero(self) -> None:
        msg = validate_password_strength("abcdefgh")
        assert msg and "numero" in msg

    def test_minimo_conhecido(self) -> None:
        assert MIN_PASSWORD_LENGTH == 8


class TestSessionToken:
    def test_roundtrip(self) -> None:
        tok = create_session_token(42)
        uid = verify_session_token(tok, max_age_seconds=3600)
        assert uid == 42

    def test_rejeita_user_id_zero(self) -> None:
        with pytest.raises(ValueError):
            create_session_token(0)

    def test_rejeita_user_id_negativo(self) -> None:
        with pytest.raises(ValueError):
            create_session_token(-1)

    def test_rejeita_user_id_float(self) -> None:
        with pytest.raises(TypeError):
            create_session_token(1.5)  # type: ignore[arg-type]

    def test_token_adulterado_retorna_none(self) -> None:
        tok = create_session_token(42)
        adulterado = tok[:-5] + "AAAAA"
        assert verify_session_token(adulterado, 3600) is None

    def test_token_vazio_retorna_none(self) -> None:
        assert verify_session_token("", 3600) is None

    def test_token_nao_str_retorna_none(self) -> None:
        assert verify_session_token(None, 3600) is None  # type: ignore[arg-type]
        assert verify_session_token(123, 3600) is None  # type: ignore[arg-type]

    def test_max_age_invalido_retorna_none(self) -> None:
        tok = create_session_token(42)
        assert verify_session_token(tok, 0) is None
        assert verify_session_token(tok, -1) is None

    def test_token_expirado_retorna_none(self) -> None:
        tok = create_session_token(42)
        time.sleep(2.5)  # itsdangerous usa int(time.time()); 2.5s garante expiracao
        assert verify_session_token(tok, max_age_seconds=1) is None


class TestCSRF:
    def test_gera_token_url_safe(self) -> None:
        t = generate_csrf_token()
        assert isinstance(t, str)
        assert len(t) >= 32
        # URL-safe: letras, digitos, '-' e '_'
        assert all(c.isalnum() or c in "-_" for c in t)

    def test_tokens_sao_unicos(self) -> None:
        a = generate_csrf_token()
        b = generate_csrf_token()
        assert a != b

    def test_compare_aceita_iguais(self) -> None:
        t = generate_csrf_token()
        assert compare_csrf_tokens(t, t) is True

    def test_compare_rejeita_diferentes(self) -> None:
        a = generate_csrf_token()
        b = generate_csrf_token()
        assert compare_csrf_tokens(a, b) is False

    def test_compare_rejeita_vazios(self) -> None:
        assert compare_csrf_tokens("", "") is False
        assert compare_csrf_tokens("x", "") is False
        assert compare_csrf_tokens("", "x") is False

    def test_compare_rejeita_tamanhos_diferentes(self) -> None:
        assert compare_csrf_tokens("abc", "abcd") is False

    def test_compare_rejeita_nao_str(self) -> None:
        assert compare_csrf_tokens(None, "x") is False  # type: ignore[arg-type]
        assert compare_csrf_tokens("x", None) is False  # type: ignore[arg-type]
