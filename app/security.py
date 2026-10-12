"""
Camada de seguranca do PDV: hash de senha, sessao assinada e CSRF.

Nunca armazena senha em texto. Nunca compara tokens com `==`
diretamente - sempre `secrets.compare_digest` (constant-time).
"""

from __future__ import annotations

import secrets
from datetime import datetime, timezone
from typing import Optional

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHash, VerifyMismatchError
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from app.config import get_settings


# ---------- hashing ----------

# Perfis argon2id com default seguro (OWASP 2026).
_hasher: PasswordHasher = PasswordHasher(
    time_cost=3,
    memory_cost=65536,  # 64 MiB
    parallelism=4,
    hash_len=32,
    salt_len=16,
)


def hash_password(plain: str) -> str:
    """
    Gera hash argon2id com salt aleatorio. Rejeita senha vazia.
    """
    if not isinstance(plain, str):
        raise TypeError("senha precisa ser str")
    if not plain:
        raise ValueError("senha vazia")
    return _hasher.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    """
    Confere senha. Retorna False em qualquer falha (nunca lanca).
    Nunca loga a senha.
    """
    if not isinstance(plain, str) or not isinstance(hashed, str):
        return False
    if not plain or not hashed:
        return False
    try:
        _hasher.verify(hashed, plain)
        return True
    except (VerifyMismatchError, InvalidHash):
        return False
    except Exception:
        # Hash corrompido / outro erro inesperado - nega acesso.
        return False


def needs_rehash(hashed: str) -> bool:
    """
    True se o hash foi feito com parametros diferentes do atual
    (ex.: time_cost mudou). Chamador deve re-hashear ao proximo login OK.
    """
    try:
        return _hasher.check_needs_rehash(hashed)
    except InvalidHash:
        return True


# ---------- validacao de senha ----------

MIN_PASSWORD_LENGTH = 8


def validate_password_strength(plain: str) -> Optional[str]:
    """
    Valida regras minimas: 8+ chars, 1 letra, 1 numero.
    Retorna mensagem de erro ou None se OK.
    """
    if not isinstance(plain, str):
        return "senha precisa ser texto"
    if len(plain) < MIN_PASSWORD_LENGTH:
        return f"senha precisa ter ao menos {MIN_PASSWORD_LENGTH} caracteres"
    has_letter = any(c.isalpha() for c in plain)
    has_digit = any(c.isdigit() for c in plain)
    if not has_letter:
        return "senha precisa ter ao menos 1 letra"
    if not has_digit:
        return "senha precisa ter ao menos 1 numero"
    return None


# ---------- sessao assinada ----------

_SESSION_SALT = "pdv-session-v1"


def _serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(get_settings().SECRET_KEY, salt=_SESSION_SALT)


def create_session_token(user_id: int) -> str:
    """
    Gera token assinado com timestamp. itsdangerous usa HMAC com SECRET_KEY.
    """
    if type(user_id) is not int:
        raise TypeError("user_id precisa ser int")
    if user_id <= 0:
        raise ValueError("user_id precisa ser positivo")
    return _serializer().dumps({"uid": user_id})


def verify_session_token(token: str, max_age_seconds: int) -> Optional[int]:
    """
    Verifica assinatura e expiracao. Retorna user_id ou None em qualquer
    falha. Nunca lanca.
    """
    if not isinstance(token, str) or not token:
        return None
    if type(max_age_seconds) is not int or max_age_seconds <= 0:
        return None
    try:
        payload = _serializer().loads(token, max_age=max_age_seconds)
    except (BadSignature, SignatureExpired):
        return None
    except Exception:
        return None
    if not isinstance(payload, dict):
        return None
    uid = payload.get("uid")
    if type(uid) is not int or uid <= 0:
        return None
    return uid


# ---------- CSRF double-submit ----------

CSRF_TOKEN_BYTES = 32  # ~43 chars url-safe
CSRF_HEADER = "X-CSRF-Token"
CSRF_COOKIE = "csrf_token"
SESSION_COOKIE = "session"


def generate_csrf_token() -> str:
    """Gera token aleatorio criptograficamente seguro."""
    return secrets.token_urlsafe(CSRF_TOKEN_BYTES)


def compare_csrf_tokens(a: Optional[str], b: Optional[str]) -> bool:
    """
    Comparacao constant-time. Rejeita vazios/nulos.
    """
    if not isinstance(a, str) or not isinstance(b, str):
        return False
    if not a or not b:
        return False
    # compare_digest exige mesmo tamanho; strings diferentes de tamanho
    # dao False imediatamente (sem leak de timing nesse caso trivial).
    if len(a) != len(b):
        return False
    return secrets.compare_digest(a.encode("utf-8"), b.encode("utf-8"))


# ---------- utilitario ----------


def utc_now() -> datetime:
    """
    Datetime UTC naive. SQLite nao preserva timezone; usar naive em todo
    lugar evita o erro 'can't compare offset-naive and offset-aware'.
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)
