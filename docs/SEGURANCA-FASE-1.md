# Relatorio de seguranca - Fase 1

Data: 2026-10-12
Escopo: esqueleto, banco, CRUD de produtos, impressora Dummy.
Metodo: revisao do codigo + `pip-audit` do venv.

> IMPORTANTE: NAO corrigi nada antes de voce ler, conforme CLAUDE.md.
> Decisao de upgrade/correcao fica com voce. Correcoes viram Issues/PRs.

## Resumo

- `pip-audit`: 11 vulnerabilidades em 3 pacotes (jinja2, pytest, starlette).
- Codigo da Fase 1: nenhum achado critico. Observacoes de medio/baixo.
- Headers de seguranca, TrustedHost, CSP, Pydantic `extra="forbid"`, erro
  handler sem stack trace e docs condicionados a dev estao em producao.

---

## Dependencias (saida do pip-audit)

### CRITICO
Nenhum.

### ALTO
Nenhum na configuracao atual da Fase 1 (ver notas em "MEDIO" sobre
mitigacoes do nosso bind local + TrustedHost).

### MEDIO
1. **starlette 0.41.3 - CVE-2026-48818 (GHSA-wqp7-x3pw-xc5r) - fix: 1.1.0**
   - StaticFiles no Windows e vulneravel a SSRF via UNC path
     (`\\\\attacker.com\\share`).
   - Nosso risco: usamos StaticFiles (`/static/*`) em Windows. **Mitigado**
     por bind em `127.0.0.1` e `TrustedHostMiddleware` com whitelist
     `['127.0.0.1','localhost']`. Mesmo assim recomendo upgrade do
     starlette na proxima janela.
2. **jinja2 3.1.4 - CVE-2025-27516 / CVE-2024-56326 / CVE-2024-56201 - fix: 3.1.6**
   - Bypass de sandbox do Jinja via `|attr`, `str.format` e compilador.
   - Nosso risco: templates sao SEMPRE do nosso codigo
     (`app/templates/*.html`); nunca sao renderizados a partir de entrada
     do usuario. Mitigado por design. Vale upgrade por higiene.
3. **starlette 0.41.3 - CVE-2026-48710 (GHSA-86qp-5c8j-p5mr) - fix: 1.0.1**
   - Reconstrucao de URL sem validar `Host`. **Mitigado** por
     TrustedHostMiddleware.
4. **starlette 0.41.3 - CVE-2026-54282 (GHSA-jp82-jpqv-5vv3) - fix: 1.3.0**
   - Path nao validado em `request.url`. **Mitigado** por TrustedHost +
     bind local.
5. **starlette 0.41.3 - CVE-2026-54283 (GHSA-82w8-qh3p-5jfq) - fix: 1.3.1**
   - Limites de form (`max_fields`, `max_part_size`) burlaveis.
   - Nosso risco: Fase 1 nao aceita multipart. Sera relevante quando a Fase 2
     tiver login via form ou quando houver upload (CSV).

### BAIXO
6. **starlette 0.41.3 - CVE-2025-62727 - fix: 0.49.1**: Range header DoS em
   `FileResponse`. Fase 1 nao usa FileResponse (static files e diferente).
7. **starlette 0.41.3 - CVE-2025-54121 - fix: 0.47.2**: multipart DoS com
   arquivos grandes. Fase 1 nao aceita multipart.
8. **starlette 0.41.3 - CVE-2026-48817 - fix: 1.1.0**: HTTPEndpoint dispatch.
   Nao usamos `HTTPEndpoint`; nossos routers sao `APIRouter`.
9. **pytest 8.3.4 - CVE-2025-71176 - fix: 9.0.3**: `/tmp/pytest-of-{user}` em
   UNIX. Dev-only, Windows, nao afeta o cliente.

### Dificuldade pratica de upgrade imediato
- `fastapi==0.115.6` exige `starlette >=0.40, <0.42`. Upgrade do starlette
  para 1.3.1 exige upgrade do fastapi tambem. Isso e uma decisao sua: faco
  numa Issue/PR separado se voce autorizar.

---

## Codigo da Fase 1

### CRITICO
Nenhum.

### ALTO
1. **Rotas de produto sem autorizacao.**
   - Qualquer um que conseguir fazer requisicao em `127.0.0.1:8000` pode
     criar, editar e desativar produto.
   - Mitigacao atual: bind local + TrustedHost. Em maquina compartilhada
     (navegador do operador aberto), qualquer processo local alcanca.
   - Correcao prevista: Fase 2 adiciona `require_admin` dependency. Deixei
     o `TODO Fase 2` em `app/routers/products.py`.

### MEDIO
2. **CSRF nao esta ligado.**
   - Fase 1 nao tem sessao, entao nao ha token CSRF.
   - Correcao prevista: Fase 2 (CSRF + cookie HttpOnly + SameSite=Strict).
3. **Logs em arquivo nao tem rotacao.**
   - `logs/pdv.log` cresce sem limite.
   - Correcao prevista: Fase 9 (RotatingFileHandler).

### BAIXO
4. **`check_same_thread=False` no SQLite.**
   - Necessario para SQLAlchemy pool em FastAPI. Mitigado por `SessionLocal`
     que ja isola transacoes por request.
5. **Falta rate limit.**
   - Nao aplicavel na Fase 1 (sem login). Fase 2 adiciona bloqueio apos 5
     tentativas de login.
6. **`permissions-policy` deliberadamente desligou geolocation, microphone,
   camera.** Suficiente para o escopo do PDV. Se um dia quiser scanner via
   webcam, releva.

---

## Pontos positivos aplicados (checklist que ja atende)

- [x] Servidor so em `127.0.0.1`
- [x] `TrustedHostMiddleware` com whitelist local
- [x] Nenhum CORS (`CORSMiddleware` nao foi adicionado)
- [x] `/docs`, `/redoc`, `/openapi.json` so em `development`
- [x] `Content-Security-Policy` restrita a `'self'` (sem `unsafe-inline`)
- [x] `X-Content-Type-Options: nosniff`
- [x] `X-Frame-Options: DENY`
- [x] `Referrer-Policy: no-referrer`
- [x] `Permissions-Policy` restritivo
- [x] Pydantic v2 com `extra="forbid"` em TODOS os schemas
- [x] Limites de tamanho + teto em preco/estoque
- [x] Unidade restrita a UN/KG/L
- [x] `price_cents >= 0`, `stock_milli >= 0`, `cost_cents >= 0`
- [x] Codigo de barras: somente digitos
- [x] Codigo interno: somente alfanumericos
- [x] CheckConstraints no banco espelham a validacao Pydantic (defesa em
      profundidade)
- [x] SECRET_KEY real no `.env`, placeholder em `.env.example`, validacao
      que rejeita placeholder e strings < 32 chars
- [x] `.env`, `data/`, `*.db*`, `logs/`, `backups/` no `.gitignore`
- [x] Jinja2 com autoescape (default do FastAPI)
- [x] `products.js` usa `textContent`/`createElement` - nunca `innerHTML`
      com dado do backend ou do usuario
- [x] Erro handler global: nunca retorna stack trace, loga internamente
- [x] 86 testes passando (money + products + headers + TrustedHost)
- [x] Produto nao e apagado - `active=False` so

---

## Recomendacoes (nao aplicadas; aguardando decisao)

1. **Upgrade fastapi + starlette.** Resolve 7 CVEs. Precisa testar
   compatibilidade com Pydantic/pytest.
2. **Upgrade jinja2 para 3.1.6.** Resolve 3 CVEs. Impacto esperado: nenhum.
3. **Fase 2 (dependencia logica, nao emergencial):** autorizacao em rotas
   de produto + CSRF + bloqueio de login.
4. **Pre-commit hook** para rodar `pip-audit` e `git grep` por segredos.
   Pode entrar na Fase 10.
