# PDV Padaria

Sistema de ponto de venda (PDV) local para padaria de bairro. Roda 100% local no computador do caixa, sem depender de internet para vender.

> **Status:** Fase 1 — Esqueleto, banco e CRUD de produtos.
> Veja `CLAUDE.md` para regras inegociáveis do projeto.

## Stack

- Python 3.12
- FastAPI + Uvicorn
- SQLite (WAL, foreign_keys ligados)
- SQLAlchemy 2 + Alembic
- Frontend em HTML + CSS + JavaScript puro
- pytest para testes

## Como rodar (primeira vez)

```powershell
# 1. Criar ambiente virtual
python -m venv .venv
.venv\Scripts\activate

# 2. Instalar dependências (produção + dev)
pip install -r requirements-dev.txt

# 3. Configurar .env
copy .env.example .env
# Gere um SECRET_KEY real e cole no .env:
python -c "import secrets; print(secrets.token_urlsafe(32))"

# 4. Aplicar migrações do banco
alembic upgrade head

# 5. Popular com dados de demo (opcional)
python scripts\seed_demo.py

# 6. Rodar o servidor
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Abra http://127.0.0.1:8000/products no navegador.

## Rodar testes

```powershell
pytest
```

## Auditoria de dependências

```powershell
pip-audit
```

## Estrutura

```
app/
  main.py              # bootstrap FastAPI + segurança (headers, TrustedHost)
  config.py            # Settings (lê .env via pydantic-settings)
  db.py                # engine SQLite (WAL + foreign_keys)
  models.py            # SQLAlchemy 2.x
  schemas.py           # Pydantic v2 (extra=forbid, validações rígidas)
  money.py             # centavos, milésimos, arredondamento, format BRL
  routers/products.py  # CRUD de produtos
  services/printer.py  # interface de impressão + Dummy
  static/              # CSS e JS puros
  templates/           # Jinja2 autoescape
alembic/               # migrações
scripts/seed_demo.py   # popula o banco com produtos de exemplo
tests/                 # pytest
data/                  # pdv.db (não vai pro Git)
```

## Segurança

Ver `CLAUDE.md` — seção **Segurança** é a fonte da verdade. Resumo:

- Servidor em `127.0.0.1` + `TrustedHostMiddleware`
- Headers: CSP self, nosniff, DENY, no-referrer
- Pydantic `extra="forbid"` em todos os schemas
- SECRET_KEY só no `.env` (fora do Git)
- Nenhum `innerHTML` com dado do banco/usuário no frontend
- Erros nunca retornam stack trace ao cliente
- `/docs`, `/redoc`, `/openapi.json` desligados fora de `development`
