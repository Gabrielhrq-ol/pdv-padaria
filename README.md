# PDV Padaria

Sistema de ponto de venda (PDV) local para padaria de bairro. Roda 100%
local no computador do caixa, sem depender de internet para vender.

> **Status:** em operação na João & Maria. Veja `AVISOS-ENTREGA.md` para
> instalar e `CLAUDE.md` para as regras inegociáveis.

## Documentação

- **[docs/INSTALACAO.md](docs/INSTALACAO.md)** — passo-a-passo pra instalar no PC do cliente
- **[docs/MANUAL-OPERADOR.md](docs/MANUAL-OPERADOR.md)** — manual pro padeiro/dono
- **[docs/CHECKLIST-TESTES-MANUAIS.md](docs/CHECKLIST-TESTES-MANUAIS.md)** — validação pré-entrega
- **[docs/AUDITORIA-SEGURANCA.md](docs/AUDITORIA-SEGURANCA.md)** — relatório de segurança
- **[docs/IMPORTACAO-CSV.md](docs/IMPORTACAO-CSV.md)** — formato do CSV de produtos
- **[CHANGELOG.md](CHANGELOG.md)** — histórico das 9 fases

## Stack

- Python 3.12
- FastAPI 0.133 + Uvicorn
- SQLite (WAL, foreign_keys ligados)
- SQLAlchemy 2 + Alembic
- Jinja2 autoescape + HTML/CSS/JS puro
- pytest + httpx + pip-audit
- argon2-cffi (senhas) + itsdangerous (sessão)
- python-escpos + pywin32 (impressora térmica)

## Rodar em desenvolvimento

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
# Gere SECRET_KEY e cole no .env:
python -c "import secrets; print(secrets.token_urlsafe(32))"
alembic upgrade head
python scripts\seed_demo.py           # dados de exemplo (opcional)
python scripts\create_admin.py        # cria o primeiro admin
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Abrir `http://127.0.0.1:8000` no navegador.

## Rodar em produção (PC do cliente)

Ler `docs/INSTALACAO.md`. Resumo: `start_pdv.bat` na raiz faz tudo.

## Rodar testes

```powershell
pytest
```

A suíte cobre autorização, CSRF, invariantes financeiros, cálculos de
estoque e caixa, hooks de backup, formato CSV, páginas HTML.

## Auditoria de dependências

```powershell
pip-audit
```

Status atual em `docs/AUDITORIA-SEGURANCA.md`.

## Capacidades por fase

| Fase | Capacidade | Status |
|------|------------|--------|
| 1 | Esqueleto, banco, CRUD de produtos | ✓ |
| 1-bis | Importação CSV de produtos | ✓ |
| 2 | Autenticação argon2id + sessão + CSRF + lockout | ✓ |
| 3 | Tela do PDV (abertura de venda, add/remove item, atalhos) | ✓ |
| 4 | Finalização atômica (pagamentos, estoque, cupom) | ✓ |
| 5-prep | Impressora configurável (dummy + win32raw) | ✓ (teste real da POS-5890U-L pendente) |
| 6 | Gestão de estoque (entrada, perda, ajuste, histórico, alerta) | ✓ |
| 7 | Caixa (abertura, sangria, suprimento, fechamento, guard) | ✓ |
| 8 | Relatórios (dashboard + 6 relatórios + CSV) | ✓ |
| 9 | Backup (SQLite nativo + hook pós-fechamento + CLI) + start_pdv.bat | ✓ |
| 10 | Auditoria + docs + checklist de testes manuais | em entrega |

## Estrutura

```
app/
  main.py                      # bootstrap FastAPI + segurança
  config.py                    # Settings (.env via pydantic-settings)
  db.py                        # engine SQLite (WAL + foreign_keys)
  models.py                    # SQLAlchemy 2.x
  schemas.py                   # Pydantic v2 (extra=forbid)
  money.py                     # centavos, milésimos, arredondamento, BRL
  security.py                  # argon2id + session token + CSRF
  dependencies.py              # auth guards (admin/caixa/csrf)
  routers/                     # auth, products, sales, admin, cash, reports, backup
  services/                    # sales_service, stock_service, cash_service, reports_service, backup_service, printer, receipt
  static/css,js/               # frontend puro, sem innerHTML
  templates/*.html             # Jinja2 autoescape
alembic/versions/              # migrações 1 → 7
scripts/                       # seed_cliente, seed_demo, create_admin, import_products, do_backup, test_printer
tests/                         # testes automatizados (pytest)
docs/                          # instalação, operador, checklist, auditoria, importação CSV
start_pdv.bat                  # script único pro cliente clicar
data/                          # pdv.db + cliente.json (fora do Git)
logs/                          # pdv.log (fora do Git)
```

## Regras inegociáveis

Ver `CLAUDE.md` completo. Pontos chave:

1. Dinheiro em **centavos (int)**; qty em **milésimos (int)**. Nunca float.
2. Todo total passa por `line_total_cents` em `app/money.py`
3. Finalização de venda é **1 transação atômica**
4. `sale_items` **copia nome e preço** do produto no momento da venda
5. Produto **nunca é apagado** — só `active=False`
6. **Venda nunca depende da impressora**. Falha de impressão não desfaz a venda
7. Servidor **só em `127.0.0.1`**
8. Autorização checada no backend em **toda** rota
9. Segredos no `.env` (fora do Git). Nunca commitar `.env`, `data/`, `*.db`, `backups/`
10. Pydantic `extra="forbid"` em todos os schemas
11. **Audit log** em ações sensíveis
12. Cupom traz **"CUPOM NAO FISCAL - SEM VALOR FISCAL"** em destaque
