# Relatorio de seguranca - Fase 2

Data: 2026-10-12
Escopo: login, sessao, CSRF, bloqueio por tentativas, papeis admin/caixa,
audit log, criacao do primeiro usuario.
Metodo: revisao de codigo + 147 testes automatizados + fluxo manual
end-to-end via curl + `pip-audit`.

> IMPORTANTE: NAO corrigi nada antes de voce ler, conforme CLAUDE.md.

## Resumo

- `pip-audit`: 11 vulnerabilidades, as MESMAS da Fase 1 (nenhuma nova
  introduzida pela Fase 2). argon2-cffi 23.1.0 e itsdangerous 2.2.0 estao
  limpos.
- 147 testes passando (86 da Fase 1 + 61 novos).
- Fluxo auth validado end-to-end: login OK, login falha, lockout, CSRF
  presente/ausente, logout, 401 apos logout, redirect de /products para
  /login quando anonimo.

---

## Dependencias novas da Fase 2

| Pacote | Versao | CVEs | Observacao |
|---|---|---|---|
| argon2-cffi | 23.1.0 | nenhum | OK |
| argon2-cffi-bindings | 26.1.0 | nenhum | OK |
| itsdangerous | 2.2.0 | nenhum | OK |
| cffi | 2.1.1 | nenhum | OK |

Dependencias herdadas da Fase 1 continuam com os 11 CVEs documentados em
`docs/SEGURANCA-FASE-1.md`.

---

## Codigo da Fase 2

### CRITICO
Nenhum.

### ALTO
Nenhum.

### MEDIO
1. **Rotas de criacao de usuario sao via script apenas.**
   - Nao ha API `POST /api/users`. Isso evita que um admin comprometido crie
     outros admins remotamente, mas tambem significa que trocar/criar
     usuarios exige CLI. Decisao do cliente (Fase 2 explicitamente nao
     pediu management via UI).
   - Correcao prevista: fase futura quando precisar (sem urgencia).

2. **Senhas trocadas pelo proprio usuario nao estao implementadas.**
   - Fase 2 pediu login/logout; nao pediu "trocar senha pelo painel".
   - Risco: se um admin esquecer a senha, so o acesso ao SQLite ou outro
     admin resolve.
   - Correcao prevista: fase futura.

3. **Nao ha rotacao de SECRET_KEY definida.**
   - Se SECRET_KEY vazar e for trocada, todas as sessoes atuais sao
     invalidadas (comportamento desejado). Mas nao ha procedure
     documentada.
   - Mitigacao: `config.py` falha se SECRET_KEY <32 chars ou placeholder.
   - Correcao prevista: documentar no manual de instalacao (Fase 10).

### BAIXO
4. **Lockout timing e por usuario, nao por IP.**
   - Em PDV local com 1 PC, isso e OK (atacante com acesso fisico ja
     ganhou).
   - Se um dia for exposto na rede, considerar bloquear por IP tambem.

5. **Nao ha captcha ou proof-of-work no login.**
   - Local, baixo risco de bot. Nao aplicavel.

6. **Audit log nao e append-only por constraint do banco.**
   - admin com SQL CLI pode editar/deletar. Nao e vetor realista em PDV
     local, mas em producao distribuida isso seria risco.
   - Mitigacao futura: backup diario + checksum.

---

## Pontos positivos da Fase 2 (checklist que ja atende)

### Autenticacao
- [x] Senhas hasheadas com argon2id (`argon2-cffi` 23.1.0)
- [x] Parametros argon2id: time_cost=3, memory_cost=64MiB, parallelism=4
- [x] `verify_password` NUNCA lanca - retorna False em qualquer falha
- [x] Nao loga senha em nenhum caso
- [x] `check_needs_rehash` disponivel para migrar hashes antigos
- [x] Validacao de senha: 8+ chars, 1 letra, 1 numero
- [x] `getpass` no `create_admin.py` - nao ecoa no terminal
- [x] Mensagem de erro de login e GENERICA ("Credenciais invalidas") -
      nao vaza se o username existe

### Sessao
- [x] Cookie `session` assinado via `itsdangerous.URLSafeTimedSerializer`
      com `SECRET_KEY`
- [x] Cookie **HttpOnly** (JS nao le)
- [x] Cookie **SameSite=Strict**
- [x] Cookie **Secure** em producao (desligado so em development HTTP local)
- [x] Expiracao de 8 horas (`SESSION_MAX_AGE_SECONDS`)
- [x] Token invalido/expirado/adulterado -> retorna None (nao lanca)

### CSRF
- [x] Double-submit cookie: `csrf_token` nao-HttpOnly + header `X-CSRF-Token`
- [x] Token gerado com `secrets.token_urlsafe(32)` por login
- [x] Comparacao com `secrets.compare_digest` (constant-time)
- [x] Rejeita vazios/nulos/tamanhos diferentes
- [x] GET/HEAD/OPTIONS passam sem CSRF (metodos seguros)
- [x] Quando nao ha sessao, deixa 401 ser retornado em sequencia (nao
      vaza 403 CSRF para anonimo)
- [x] CSRF renovado a cada login

### Lockout
- [x] 5 tentativas erradas em 15 min -> `locked_until = now + 15min`
- [x] Sucesso zera `failed_login_count` e `locked_until`
- [x] `locked_until` checado antes de verificar senha (lockout honrado)
- [x] Lockout tambem bloqueia sessao ja autenticada (checado em
      `get_current_user`)
- [x] Audit log `account_locked` com contador de tentativas

### Autorizacao
- [x] `require_authenticated` em todas as rotas de leitura de produtos
- [x] `require_admin` em TODAS as rotas mutantes de produtos
- [x] `require_csrf` em TODAS as rotas mutantes de produtos
- [x] Caixa recebe 403 em POST/PUT/PATCH de produtos (testes confirmam)
- [x] Anonimo recebe 401 em GET/POST de /api/products (testes confirmam)
- [x] Usuario inativo nao consegue autenticar nem usar sessao velha
- [x] Papel validado via `CheckConstraint` no banco e via `Role` Literal
      no Pydantic (defesa em profundidade)

### Audit log
- [x] Tabela `audit_log` com user_id, action, entity, entity_id,
      details, ip, created_at + indices
- [x] `login_ok`, `login_fail`, `login_fail_unknown_user`,
      `login_fail_inactive`, `login_blocked_locked`, `account_locked`,
      `logout` gravados
- [x] `product_created`, `product_updated`, `product_deactivated`,
      `product_reactivated` gravados
- [x] `user_created` gravado pelo script
- [x] Nenhum campo armazena senha nem token

### Frontend
- [x] `auth.js` nao usa `innerHTML`
- [x] `products.js` le cookie CSRF e envia no header `X-CSRF-Token`
- [x] 401 em qualquer API chama redirect automatico para /login
- [x] Botao "Sair" chama /auth/logout com CSRF e redireciona
- [x] Jinja autoescape (default) nos templates

### Testes
- [x] 32 de security (hash, session, CSRF)
- [x] 15 de auth (login, lockout, logout, me, audit)
- [x] 14 de products com autorizacao (anonimo, caixa, admin)
- [x] CSP, X-Frame, nosniff, Referrer-Policy continuam presentes
- [x] TrustedHost continua rejeitando hosts externos

---

## Validacao manual (fluxo end-to-end)

```
1) GET /products sem login              -> 302 /login             OK
2) GET /api/products sem login          -> 401                    OK
3) POST /auth/login credenciais erradas -> 401                    OK
4) POST /auth/login OK                   -> 200 + cookies setados  OK
   session com HttpOnly, csrf_token sem HttpOnly, ambos SameSite=Strict
5) GET /api/products com login          -> 200 (12 produtos)      OK
6) POST /api/products SEM X-CSRF-Token  -> 403 "CSRF invalido"    OK
7) POST /api/products COM X-CSRF-Token  -> 201 (produto criado)   OK
8) POST /auth/logout com CSRF           -> 204                    OK
9) GET /api/products apos logout real   -> 401                    OK
```

---

## Recomendacoes (nao aplicadas)

1. **Upgrade fastapi + starlette** (ainda vigente da Fase 1).
2. **Upgrade jinja2 para 3.1.6** (ainda vigente).
3. **Fase 10:** documentar procedure de rotacao de SECRET_KEY + reset de
   senha de admin via SQL em caso de perda.
4. **Fase 10:** adicionar pre-commit hook com `pip-audit` + varredura de
   segredos.
5. **Opcional:** mover `MAX_LOGIN_ATTEMPTS` e `LOCKOUT_MINUTES` para
   `settings` do banco, para permitir ajuste sem redeploy. Deixei
   constantes em `app/routers/auth.py` por simplicidade.
