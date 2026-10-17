# Changelog

Histórico das 9 fases funcionais do PDV Padaria. Formato inspirado em
[Keep a Changelog](https://keepachangelog.com/).

## [10.0.0] — 2026-10-16 — Entrega

### Documentação de entrega
- `docs/AUDITORIA-SEGURANCA.md` — relatório final estruturado por gravidade (1 crítico, 2 altos, 4 médios, 5 baixos)
- `docs/INSTALACAO.md` — passo-a-passo pra instalar no PC do cliente
- `docs/MANUAL-OPERADOR.md` — manual pro padeiro/dono em linguagem simples
- `docs/CHECKLIST-TESTES-MANUAIS.md` — ~90 itens pra validar antes de entregar
- README e CHANGELOG atualizados
- `scripts/trocar_admin.py` — utilitário pra desativar credenciais de dev

### Commits
- `9612967` Auditoria de segurança
- `0a3d7d9` Doc de instalação
- `9557ba9` Manual do operador
- `4a58e1f` Checklist de testes manuais

## [9.0.0] — 2026-10-14 — Backup

### Adicionado
- `app/services/backup_service.py` — API nativa `sqlite3.Connection.backup()`, compressão gzip, multi-destino, rotação por mtime
- `app/services/backup_hook.py` — hook em `cash_service.close_session` dispara backup em thread daemon. Defesa em 4 camadas: falha de backup JAMAIS trava fechamento de caixa
- `scripts/do_backup.py` — CLI pra Task Scheduler (exit codes 0/1/2/3)
- `start_pdv.bat` — script `.bat` na raiz, pronto pra atalho no desktop
- Página `/admin/backup` — settings + botão manual + histórico
- 30 testes novos (11 service + 13 router + 6 hook)

### Settings
- `backup_dir_1`, `backup_dir_2`, `backup_keep` (default 30), `backup_on_cash_close` (default true), `backup_compress` (default true)

### Commit
- `99ef35a`

## [8.0.0] — 2026-10-14 — Relatórios

### Adicionado
- `app/services/reports_service.py` — funções puras: dashboard, sales_by_period, closed_cash_sessions, sales_by_operator, sales_by_method, top_products, discounts_and_cancellations
- `app/routers/reports.py` — endpoints JSON + CSV (streaming, BOM UTF-8, separador `;` BR). Admin-only em todas
- Página `/admin/reports` — dashboard do dia (5 cards) + filtros globais de data + 6 abas com botão Exportar CSV
- 49 testes novos (27 service + 22 router)

### Commit
- `f8e77f7`

## [7.0.0] — 2026-10-14 — Caixa

### Adicionado
- Modelos `CashSession` + `CashMovement` + migração com seed `cash_session_required=true` em produção
- `app/services/cash_service.py` — open/close/sangria/suprimento, calcular esperado, bloqueio por venda aberta no fechamento
- 1 sessão aberta por vez no sistema (padaria tem 1 caixa físico; validação em service)
- Fechamento permite diferença (declarado ≠ esperado) com motivo obrigatório ≥ 3 chars
- Guard em `sales_service.create_open_sale`: se setting on + sem caixa → `SalesError` 409. Carimba `cash_session_id` em toda venda
- `/pdv` redireciona pra `/caixa?msg=abra` quando setting on e sem sessão
- Página `/caixa` com fluxo completo + admin tem toggle do setting
- 74 testes novos (40 service + 24 router + 10 guard)

### Commit
- `f0e242a`

## [6.0.0] — 2026-10-14 — Gestão de estoque

### Adicionado
- `app/services/stock_service.py` — register_entry (motivo opcional, evolui decisão 9 do CLAUDE.md), register_loss (motivo obrigatório), register_adjustment (produto ATIVO + motivo obrigatório), list_movements, list_low_stock
- Rotas em `/api/admin/stock/`: entry|loss|adjustment (admin + CSRF), movements|low (admin+caixa, read-only)
- Página `/admin/stock` — 4 abas (Entrada/Perda/Ajuste/Histórico) + alerta de estoque baixo no header de `/products`
- Reusa `StockMovement` da Fase 4; invariante `product.stock_milli == sum(movements.qty_milli)` mantido pelos testes
- 68 testes novos (34 service + 34 router)

### Commit
- `902f254`

## [5-prep] — 2026-10-13 — Impressora configurável

### Adicionado
- `app/services/printer.py` com factory `get_printer(db)` que lê setting `printer_backend` em cada request
- Backends: `dummy` (default), `win32raw` (lazy import de python-escpos)
- Dependências: python-escpos==3.1, pywin32==308 (só Windows)
- Settings: `printer_backend`, `printer_name`, `printer_codepage`, `printer_auto_cut`
- UI `/admin/printer` (admin only) pra trocar backend sem redeploy
- Endpoint `/api/admin/printer-test` pra teste real
- 30 testes novos (301 total)

### Pendente
- Teste real da POS-5890U-L via AnyDesk no PC do cliente

### Commit
- `1e34bef`

## [4.0.0] — 2026-10-13 — Finalização atômica

### Adicionado
- Tabelas `payments` + `stock_movements` (migrações `224a49b53db9` e `85a0a006e786`)
- DROP ck_products_stock_non_negative (decisão 9: estoque pode ir negativo — padaria produz própria mercadoria)
- Service: `calculate_change` (puro) + `finalize_sale` (transação atômica) + `reverse_sale`
- `receipt.py` puro, 32 colunas, "DOCUMENTO SEM VALOR FISCAL", marca "2ª VIA" em reimpressão
- Endpoints: `/finalize`, `/reverse`, `/reprint`, `/last-completed`
- F6 modal de pagamento + F10 reimprimir
- Troco distribuído só no último pagamento dinheiro; cartão/PIX não pode exceder
- Impressão fora da transação (regra 6): falha não desfaz venda
- 53 testes novos (271 total)

### Commit
- `10366f1`

## [3.0.0] — 2026-10-12 — Tela do PDV

### Adicionado
- Modelos `sales` + `sale_items` com cópia de nome/preço/unidade no item
- Service `sales_service.py`: resolve_code (N*cod), add com agrupamento, change/remove/cancel; preço CONGELADO no item (regra 4)
- Router `/api/sales/*` + `/api/products/by-code/{code}`
- Tela `/pdv` dark, teclado-first: F2 busca, F3 qty, F4 remove, F6/F10 toast "Disponível na Fase X", F8 cancela, F9 preço
- Caixa só vê suas vendas; admin vê tudo
- Reload retoma venda em aberto automaticamente
- 48 testes novos (218 total)

### UX
- Botões clicáveis no rodapé + atalhos duplicados `Ctrl+B/Q/D/X/I` pra notebook (commit `0aad53b`)

### Commits
- `5f15a00`, `0aad53b`

## [2.0.0] — 2026-10-12 — Autenticação

### Adicionado
- argon2id + sessão itsdangerous (8h)
- Cookies: session HttpOnly + csrf_token (SameSite=Strict)
- CSRF double-submit em todas as rotas mutantes
- Lockout após 5 tentativas erradas em 15 min
- Papéis: admin (CRUD produto) / caixa (só leitura)
- Audit log (tabela nova): login_ok/fail, lockout, product_*
- `scripts/create_admin.py` interativo (getpass)
- 61 testes novos (147 total)

### Commit
- `5de7bee`

## [1-bis] — 2026-10-12 — Importação CSV

### Adicionado
- `app/services/csv_import.py` — parser + idempotência por barcode/internal_code
- `scripts/import_products.py` — CLI com `--dry-run` e `--strict`
- Reusa `app/money.py` e `app/schemas.py`
- Aceita UTF-8 com/sem BOM, separador `,` ou `;`, formatos BRL ou cents
- Categoria criada automaticamente se não existir
- `data/produtos.example.csv` versionado como template
- `docs/IMPORTACAO-CSV.md` manual pro instalador/cliente
- 23 testes novos (170 total)

### Commit
- `ef53e33`

## [1.0.0] — 2026-10-12 — Esqueleto

### Adicionado
- Python 3.12 + FastAPI + Uvicorn + SQLite WAL + foreign_keys ON
- SQLAlchemy 2 + Alembic (migração inicial `952458ce6b02`)
- Modelos: `users`, `categories`, `products`, `settings`
- Pydantic v2 com `extra="forbid"` em todos os schemas
- CRUD completo de produtos com validações
- Jinja2 autoescape + HTML/CSS/JS puro
- `TrustedHostMiddleware` restringe a 127.0.0.1/localhost
- Headers de segurança: CSP, X-Frame-Options DENY, X-Content-Type-Options nosniff
- `/docs` desligado em produção
- Impressora Dummy (texto no console)
- Função `line_total_cents` com arredondamento banker's half-up
- 86 testes

### Commit
- `9daec95`
