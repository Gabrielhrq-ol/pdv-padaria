"""
Configuracao do PDV lida do .env via pydantic-settings.

Regras de seguranca aplicadas aqui:
- SECRET_KEY obrigatoria, nao-vazia, nao pode ser o placeholder do .env.example.
- HOST deve ser 127.0.0.1 ou localhost (bind local-only).
- ENVIRONMENT = "development" | "production".
- is_development controla docs automaticos do FastAPI.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

Environment = Literal["development", "production"]

PLACEHOLDER_SECRET = "change-me-generate-with-python-secrets"
PROJECT_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    """Settings carregadas do .env."""

    model_config = SettingsConfigDict(
        env_file=str(PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    SECRET_KEY: str = Field(
        ...,
        description="Chave de sessao. Gere com secrets.token_urlsafe(32).",
    )
    DB_PATH: str = Field(default="./data/pdv.db")
    ENVIRONMENT: Environment = Field(default="development")
    HOST: str = Field(default="127.0.0.1")
    PORT: int = Field(default=8000, ge=1, le=65535)

    @field_validator("SECRET_KEY")
    @classmethod
    def _secret_key_must_be_real(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("SECRET_KEY nao pode estar vazia.")
        if v.strip() == PLACEHOLDER_SECRET:
            raise ValueError(
                "SECRET_KEY esta com o valor placeholder. "
                "Gere com: python -c \"import secrets; print(secrets.token_urlsafe(32))\""
            )
        if len(v) < 32:
            raise ValueError("SECRET_KEY deve ter ao menos 32 caracteres.")
        return v

    @field_validator("HOST")
    @classmethod
    def _host_must_be_local(cls, v: str) -> str:
        allowed = {"127.0.0.1", "localhost"}
        if v not in allowed:
            raise ValueError(
                f"HOST deve ser um de {sorted(allowed)}. Recebido: {v!r}."
            )
        return v

    @property
    def is_development(self) -> bool:
        return self.ENVIRONMENT == "development"

    @property
    def db_absolute_path(self) -> Path:
        p = Path(self.DB_PATH)
        if not p.is_absolute():
            p = PROJECT_ROOT / p
        return p.resolve()

    @property
    def database_url(self) -> str:
        return f"sqlite:///{self.db_absolute_path.as_posix()}"


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
