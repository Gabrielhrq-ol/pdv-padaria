# Auditoria de Segurança — Entrega (Fase 10)

Relatório final estruturado por gravidade (crítico / alto / médio / baixo),
cobrindo todas as 9 fases implementadas. Conforme CLAUDE.md, **nada é
corrigido neste relatório** — Gabriel decide o que vira issue e o que
entra na entrega.

**Data da auditoria original:** 2026-10-16
**Última revisão:** 2026-10-17 (Fase 17 pagou A1/A2/B1/B5)
**Escopo:** Fases 1 → 9 (relatório original); Fase 17 fecha dívidas
**Suite:** 617 testes automatizados passando

> **Status pós-Fase 17:** 4 dos 11 CVEs do pip-audit foram corrigidos
> (jinja2 → 3.1.6, starlette → 1.3.1, fastapi upgradado junto para
> compatibilidade). Rotação de log e warning de path externo de backup
> implementados. Resta apenas 1 CVE: pytest (TOCTOU em `/tmp`, não
> aplicável no Windows).

---

## Sumário executivo

- **1 crítico** — credenciais de dev no banco (bloqueia entrega até trocar)
- **2 altos** — vulnerabilidades em `starlette` e `jinja2` (mitigadas por design, mas precisam upgrade)
- **4 médios** — backup não criptografado, sem rate-limit extra, pytest CVE (não aplicável), ausência de monitoramento
- **5 baixos** — logs sem rotação, audit log mutável, NFC-e pendente, outros

Nenhum achado crítico de código do próprio projeto; os críticos/altos são
operacionais (credenciais) ou de biblioteca. A **superfície de ataque é
intencionalmente mínima**: servidor só escuta em `127.0.0.1`, não há CORS
liberado, nem upload de arquivo, nem endpoint público.

---

## 🔴 CRÍTICOS

### C1. Credenciais de desenvolvimento ainda no banco antes da entrega

**Localização:** banco local atual (`data/pdv.db`)
**Risco:** usuário `gabriel` com senha `TesteSenha123` tem papel admin.
Se o PC do cliente for ligado em rede local sem segmentação (ou acessado
fisicamente), qualquer pessoa pode logar como admin.

**Mitigação necessária antes da entrega:**
1. Rodar `scripts/create_admin.py` pra criar o admin real (nome e senha do dono)
2. Desativar o usuário `gabriel` (`active=False`), **não apagar** (regra inegociável 5)
3. Validar com `SELECT username, active, role FROM users` que só o dono fica ativo

**Status:** operacional, não é bug de código. Está documentado em
`CHECKLIST-TESTES-MANUAIS.md`.

---

## 🟠 ALTOS

### ~~A1~~ `starlette==0.41.3` → `1.3.1` ✅ RESOLVIDO (Fase 17)

Upgradado para starlette 1.3.1 em 2026-10-17 (fastapi 0.115.6 → 0.133.1
pra compatibilidade). Zero regressão nos 617 testes.

### A1 (original). Detalhes dos CVEs corrigidos:

**Detalhes:**

| CVE | Severidade real no PDV | Mitigação atual |
|-----|------------------------|-----------------|
| CVE-2026-48710 (host header auth bypass) | Baixa | TrustedHostMiddleware restringe a `127.0.0.1`/`localhost` |
| CVE-2026-54283 (form urlencoded DoS) | Baixa | Só usuários autenticados; lockout após 5 tentativas |
| CVE-2026-54282 (request.url.hostname bypass) | Baixa | Idem C-48710 |
| CVE-2025-62727 (Range header DoS em FileResponse) | **Nula** | Não usamos Range em respostas |
| CVE-2025-54121 (multipart form DoS) | **Nula** | Não aceita upload |
| **CVE-2026-48818 (SSRF via UNC em StaticFiles Windows)** | **Média** | Mitigada por TrustedHostMiddleware mas afeta o PDV porque é Windows + StaticFiles |
| CVE-2026-48817 (HTTPEndpoint method bypass) | **Nula** | Não usamos `HTTPEndpoint` |

**Recomendação:**
- Atualizar `starlette` para `>=1.3.1` **após** rodar a suite completa.
- A atualização pode exigir ajustes em `fastapi` (checar matriz de compatibilidade).
- Virar issue antes de entrega **ou** aceitar o risco atual (todas as 6 têm impacto baixo-médio dado o contexto single-host 127.0.0.1).

**Severidade final no contexto:** **Média-alta**. Promovida a "alto" pela
quantidade (6 CVEs) e porque uma delas (CVE-2026-48818) é Windows-specific
e usamos StaticFiles.

### ~~A2~~ `jinja2==3.1.4` → `3.1.6` ✅ RESOLVIDO (Fase 17)

Upgradado em 2026-10-17. 3 CVEs de sandbox escape eliminados.

### A2 (original). Detalhes:

Todas as 3 vulnerabilidades são **sandbox escape para templates controlados
por atacante**. No PDV, templates são sempre do próprio código em
`app/templates/*.html` — nunca vêm de input do usuário.

**Severidade real: BAIXA** (mitigado por design).
**Recomendação:** atualizar mesmo assim; é uma linha no `requirements.txt`
e evita o alerta do pip-audit.

---

## 🟡 MÉDIOS

### M1. Backup não criptografado

**Localização:** `app/services/backup_service.py:85` (compressão sem cifra)
**Risco:** arquivos `.db.gz` vão pro pendrive e Google Drive em claro.
Contêm nomes de produtos, histórico de vendas, operadores e hashes de senha.

**Hashes de senha** são argon2id (resistente a cracking), então a exposição
é limitada. Mas um pendrive perdido vira um dump de histórico de vendas.

**Decisão deliberada da Fase 9** (fora de escopo). Pode entrar como
melhoria futura:
- Opção 1: cifrar com AES-GCM usando chave simétrica derivada da senha do admin
- Opção 2: usar `openssl enc` externo via subprocess
- Opção 3: aceitar (padaria pública, baixo valor dos dados)

### M2. Rate-limit em login além do lockout por usuário

**Localização:** `app/routers/auth.py` + `app/security.py`
**Mitigação atual:** lockout após 5 tentativas erradas em 15 min.
**Gap:** atacante pode rotacionar `username` (`admin1`, `admin2`, ...) e
consumir CPU com argon2id. Argon2 é CPU-intensivo por design (~100ms por
hash), então 10 req/s já é 100% de 1 core.

**Severidade real: BAIXA** no PDV porque:
- Rede do servidor é `127.0.0.1` apenas
- Para explorar, atacante precisa acesso ao próprio PC (e já ganhou)

**Recomendação:** aceitar o risco. Se um dia o PDV abrir pra outra máquina
na rede, adicionar `slowapi` ou similar.

### M3. `pytest==8.3.4` → recomendado 9.0.3

CVE-2025-71176: TOCTOU em `/tmp/pytest-of-{user}` no UNIX. **Não aplicável** —
PDV roda Windows com usuário único. Virar issue "quando atualizarmos deps".

### M4. Sem monitoramento de erros / alertas

**Risco:** erro em produção fica só em `logs/pdv.log`. Se o backup
automático começar a falhar, o dono só descobre quando precisar restaurar.

**Mitigação:** audit log registra `backup_failed` e aparece em
`/admin/backup` histórico. Dono tem que olhar.

**Recomendação:**
- Adicionar banner na `/products` quando houver `backup_failed` recente
- Opcional: email/SMS ao dono (fora de escopo, sem internet garantida)

---

## 🟢 BAIXOS

### ~~B1~~ Logs sem rotação ✅ RESOLVIDO (Fase 17)

Trocado `FileHandler` por `RotatingFileHandler(maxBytes=10MB,
backupCount=5)` em `app/main.py`. Agora `logs/pdv.log` nunca passa
de ~60MB total (6 arquivos × 10MB).

### B1 (original):

**Localização:** `app/main.py:46` (`logging.FileHandler`)
**Risco:** `logs/pdv.log` cresce sem limite. Em um ano de operação, pode
chegar a GBs no SSD de 112GB.

**Recomendação:** trocar para `RotatingFileHandler(maxBytes=10MB, backupCount=5)`.
Fix de 2 linhas, mas documentado no CLAUDE.md como "fase futura".

### B2. Audit log não imutável

Admin pode deletar linhas da tabela `audit_log` via SQL direto.
**Mitigação atual:** só o dono tem acesso ao PC do caixa; backup diário
preserva histórico.

**Recomendação:** aceitar. Para imutabilidade real seria preciso log
append-only em arquivo ou hash chain — overkill para o contexto.

### B3. NFC-e / contador pendente

Nota fiscal eletrônica ainda **não está no escopo**. Cliente foi
notificado. Cupom traz "DOCUMENTO SEM VALOR FISCAL" em destaque. Virar
dependência explícita no contrato com o cliente.

### B4. Falta `.env.example` versionado

**Localização:** raiz do projeto. Checar se existe.
**Risco:** novo dev clona o repo e não sabe quais variáveis preencher.
Pode acabar criando `.env` com `SECRET_KEY=` vazio e levar erro na
inicialização.

**Mitigação:** `config.py` já falha claramente se `SECRET_KEY` estiver
vazia ou com placeholder. Mensagem orienta como gerar.

**Recomendação:** verificar que `.env.example` existe e está versionado
com placeholders claros. Se não existir, criar.

### ~~B5~~ Backup pra pasta local não é bloqueado ✅ RESOLVIDO (Fase 17)

`BackupSettingsOut.warnings` agora traz avisos quando `backup_dir_1/2`
estão dentro da pasta do PDV ou no mesmo drive (SSD do caixa). UI
exibe no feedback. Não bloqueia (admin pode insistir), mas alerta.

### B5 (original):

**Localização:** `app/routers/backup.py:settings`
**Risco:** admin pode configurar `backup_dir_1 = C:\Users\...\Documents\backups`
que fica no MESMO PC. Se o SSD queimar, perde-se os backups junto.

**Recomendação:** validar no PUT de settings que o path começa com letra
de drive diferente de `C:\` ou está em pasta `OneDrive`/`Google Drive`
conhecida. Ou simplesmente avisar na UI. Virar issue "melhoria da UX".

---

## 🟩 PRÁTICAS BOAS APLICADAS

Para contrapor os achados acima, o sistema aplica consistentemente:

- Senhas: **argon2id** via `argon2-cffi` (resistente a GPU)
- Dinheiro: **int em centavos**, qty em milésimos (nunca float)
- Validação: **Pydantic v2 com `extra="forbid"`** em todos os schemas
- CSRF: **double-submit cookie** em todas as rotas mutantes
- Session: cookie **HttpOnly + Secure + SameSite=Strict**, assinado com `itsdangerous`
- Lockout: **5 tentativas / 15 min**
- Autorização: **checada no backend em toda rota** (papéis admin/caixa)
- Audit log: todas ações sensíveis (login, lockout, product_*, stock_*, cash_*, backup_*)
- Headers de segurança: **CSP (default-src 'self')**, X-Content-Type-Options, X-Frame-Options DENY, Referrer-Policy no-referrer, Permissions-Policy
- Rede: **só 127.0.0.1** + `TrustedHostMiddleware` restringindo Host header
- `/docs`, `/redoc`, `/openapi.json`: **desligados em produção**
- Erros: **nunca retorna stack trace** ao cliente (CSP + handler genérico 500)
- CORS: **nenhum** (`allow_origins` ausente)
- Dependências: **pinadas** com versão exata em `requirements.txt`
- JS: **zero `innerHTML`** com dado do servidor; sempre `textContent` / `createElement`
- SQL: **100% ORM/parametrizado**, zero concatenação de string em query
- Testes: **522 automatizados** cobrindo autorização, CSRF, validação, invariantes
- `SECRET_KEY`: validada no boot (≥32 chars, não placeholder, não vazia)
- `compare_digest` constant-time em CSRF (evita timing attacks)
- Backup: `sqlite3.Connection.backup()` (API nativa, não corrompe DB em uso)
- Hook de backup: defesa em 4 camadas garantindo que falha de backup JAMAIS
  trava fechamento de caixa

---

## Dependências — tabela completa

Rodado em 2026-10-16 com `pip-audit`.

| Pacote | Versão | Status | Ação sugerida |
|--------|--------|--------|---------------|
| fastapi | 0.115.6 | OK | manter |
| uvicorn | 0.32.1 | OK | manter |
| sqlalchemy | 2.0.36 | OK | manter |
| alembic | 1.14.0 | OK | manter |
| pydantic | 2.10.3 | OK | manter |
| **jinja2** | **3.1.4** | **3 CVEs** | atualizar para 3.1.6 |
| argon2-cffi | 23.1.0 | OK | manter |
| itsdangerous | 2.2.0 | OK | manter |
| python-escpos | 3.1 | OK | manter |
| pywin32 | 308 | OK | manter |
| **starlette** | **0.41.3** | **6 CVEs** | atualizar para 1.3.1+ (checar matriz com fastapi) |
| **pytest** | **8.3.4** | **1 CVE (não aplicável)** | opcional — atualizar quando for conveniente |

---

## Próximos passos recomendados

**Antes da entrega (obrigatório):**
1. **C1** — trocar credenciais do admin (bloqueia entrega)
2. Rodar `pytest` uma última vez
3. Rodar `pip-audit` e anexar output no commit de entrega
4. Validar com Gabriel: aceitar ou corrigir **A1** antes de entregar

**Pós-entrega (viram issues):**
- A1, A2 — upgrade de deps
- B1 — rotação de log
- B5 — validação de path externo no backup
- M4 — banner de backup falho na UI

**Fora do escopo deste contrato (dependem do cliente):**
- NFC-e / contador
- Teste real da POS-5890U-L via AnyDesk
- Multi-caixa / multi-loja
