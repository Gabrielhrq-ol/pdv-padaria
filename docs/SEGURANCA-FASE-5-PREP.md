# Relatorio de seguranca - Fase 5 preparatoria

Data: 2026-10-13
Escopo: factory de impressora, adapter Win32Raw, endpoints admin
`/api/admin/printer-settings` e `/printer-test`, pagina `/admin/printer`.
Metodo: revisao de codigo + 301 testes passando + pip-audit.

> IMPORTANTE: NAO corrigi nada antes de voce ler.

## Resumo

- `pip-audit`: 11 CVEs antigas (todas herdadas das Fases 1-2).
  `python-escpos==3.1` e `pywin32==308` estao LIMPOS (nenhuma CVE).
- 301 testes passando (271 + 30 novos: 16 factory + 14 admin endpoints).
- Fase 5 preparatoria: hardware real NAO foi conectado. Backend ativo
  continua Dummy ate o teste real via AnyDesk no PC do cliente.

## Codigo

### CRITICO
Nenhum.

### ALTO
1. **Lazy import de `python-escpos` nao protege 100% de ataque de
   dependencia envenenada.**
   - Mitigacao: pin exato (3.1), `pip-audit` em cada fase, instalacao
     num venv isolado.
   - A mesma logica se aplica a QUALQUER dep. Nao e especifico da Fase 5.

### MEDIO
2. **`/api/admin/printer-test` imprime em qualquer impressora salva no
   setting, sem confirmacao extra.**
   - Risco: admin configura `printer_name` com nome de impressora
     ERRADA (outra do escritorio) e envia o teste pra ela.
   - Mitigacao: nome e configuravel; audit log registra.
   - Baixo risco em padaria com 1 PC.

3. **`printer_name` aceita qualquer string (max 120 chars).**
   - Nao e injection: a string vai pro `Win32Raw(printer_name=...)`,
     que usa a Win32 API nativa com validacao propria.
   - Mitigacao: `strip_whitespace`, length <= 120.

### BAIXO
4. **Falha ao imprimir nao e logada em `logs/pdv.log`** (so no audit db).
   Fase 10 pode querer logar externamente para suporte remoto.

5. **Lazy import pode mascarar instalacao incompleta.**
   - Se `pywin32` nao esta instalado em producao e admin seleciona
     `win32raw`, o erro so aparece ao APERTAR "Testar". Melhorar: ao
     salvar settings, tentar inicializar o backend para validar.
   - Decisao: fica como esta por simplicidade. Fase 5 real (apos teste)
     pode adicionar validacao no PUT.

## Pontos positivos aplicados

### Arquitetura
- [x] `python-escpos` importado SO quando `backend != dummy`
  (teste `test_backend_desconhecido_lanca`, `test_default_e_dummy`)
- [x] `DummyPrinter` continua funcionando sem instalar python-escpos
- [x] `pywin32` com `; sys_platform == 'win32'` nao quebra em Linux CI
- [x] Factory `get_printer(db)` sem cache: le setting a cada chamada,
  trocar backend tem efeito imediato
- [x] `Win32RawPrinter` cria conexao por job e fecha (sem leak)
- [x] Erros encapsulados em `PrinterUnavailableError`
- [x] Impressao fora da transacao (regra 6 do CLAUDE.md) continua
  valendo: `get_printer(db).print_job()` depois do `db.commit()`

### Validacao
- [x] Pydantic `extra="forbid"` em `PrinterSettingsUpdate`,
  `PrinterSettingsOut`, `PrinterTestResult`
- [x] `printer_backend` em `Literal["dummy","win32raw"]` -> rejeita
  valores arbitrarios (teste `test_backend_invalido_rejeitado`)
- [x] `printer_codepage` em `Literal["","CP437","CP850","CP858","CP860"]`
  (teste `test_codepage_invalido_rejeitado`)
- [x] `win32raw` sem `printer_name` -> 422 (teste
  `test_win32raw_sem_nome_rejeitado`)
- [x] `strip_whitespace` em `printer_name`

### Autorizacao
- [x] `/api/admin/printer-settings` GET/PUT: `require_admin`
  (403 pra caixa; teste `test_caixa_403`)
- [x] `/api/admin/printer-test` POST: `require_admin`
  (teste `test_test_caixa_bloqueado`)
- [x] PUT e POST: CSRF obrigatorio
- [x] UI `/admin/printer` redireciona pra `/products` se nao admin

### Audit log
- [x] `printer_settings_updated` com `backend` e `name` nos details
- [x] `printer_test` com `backend` e `printed` nos details
- [x] Nenhum dado sensivel (senha, token) armazenado

### Frontend
- [x] `admin_printer.js` nunca usa `innerHTML` com dado do servidor
- [x] CSRF enviado em PUT e POST
- [x] 401 redireciona pra /login
- [x] Botao "Config" visivel SO pra admin (via `{% if user.role == 'admin' %}`
  no template)

### Falha segura
- [x] Impressora inexistente -> `print_error` no payload, venda nao
  afetada (teste `test_test_com_win32raw_e_nome_falha_graciosamente`)
- [x] `cut()` falhou (POS-58 sem guilhotina) -> ignora silenciosamente
  (teste `test_cut_falhou_nao_quebra`)
- [x] `python-escpos` ausente -> `PrinterUnavailableError` claro

## Decisoes do cliente aplicadas

- **Hardware pendente** (CLAUDE.md): nao escolhi conector nem codepage;
  admin configura pela UI. Dummy e o default seguro.
- **Decisao 10**: Operador escolhe imprimir ou nao em cada venda;
  backend NAO afeta esse fluxo.

## Checklist de teste manual (quando o AnyDesk rolar)

1. [ ] Admin loga em `/admin/printer`
2. [ ] Backend inicial = `Dummy`, label = `Dummy`
3. [ ] Troca pra `Win32Raw`, preenche nome exato, codepage `` (default)
4. [ ] Salva -> label atualiza pra `Win32Raw (NOME)`
5. [ ] Imprimir cupom de teste -> **confere o papel**
6. [ ] Se acentos saem errados: troca codepage pra CP850 -> salva -> testa
7. [ ] Se corte falha: desliga "corte auto" e testa de novo
8. [ ] Faz uma venda real pelo PDV, F6 finalizar imprimindo
9. [ ] F10 reimprime a venda com marca "2a VIA"

## Recomendacoes (nao aplicadas)

1. **Upgrade fastapi + starlette + jinja2 + pytest** (acumulado das fases).
2. **Fase 5 pos-teste real:** depois do teste no cliente, atualizar
   `docs/SEGURANCA-FASE-5-PREP.md` -> `SEGURANCA-FASE-5.md` consolidando
   o backend definitivo e o codepage escolhido.
3. **Fase 9:** backup do pdv.db + settings exportaveis (admin pode salvar
   configuracao de impressora para backup).
4. **Opcional:** adicionar validacao no PUT que tenta inicializar o
   backend selecionado (dry-run no `is_available()`). Util pra evitar
   salvar config inservivel.
