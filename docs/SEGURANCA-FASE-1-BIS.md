# Relatorio de seguranca - Fase 1-bis (importacao CSV)

Data: 2026-10-12
Escopo: `app/services/csv_import.py`, `scripts/import_products.py`,
`data/produtos.example.csv`, `tests/test_csv_import.py`.
Metodo: revisao de codigo + 170 testes passando + CLI real validado.

## Resumo

- **Nenhuma dependencia nova.** `pip-audit` mantem as mesmas 11 CVEs
  herdadas da Fase 1 (nada novo introduzido).
- Importacao e via **CLI, sem endpoint HTTP**: sem risco de upload
  malicioso, sem necessidade de CSRF ou autenticacao via web.
- 23 testes novos cobrem: parser, idempotencia, dry-run, strict,
  categorias, formatos BRL/cents, separador `,` e `;`, BOM, limites,
  CSV malformado.

## Codigo

### CRITICO
Nenhum.

### ALTO
Nenhum.

### MEDIO
1. **Script roda com acesso total ao banco.**
   - Quem rodar `python scripts/import_products.py` escreve no DB como
     se fosse admin. Isso e esperado (operacao de setup, feita por voce
     via AnyDesk), mas vale documentar: NAO distribuir o script como
     binario para o cliente usar sem supervisao.
   - Mitigacao: Fase 2 ja protege a UI. CLI e ferramenta de instalacao.

### BAIXO
2. **Limite de 2 MB / 2000 linhas** evita CSV monstruoso ou com memoria
   descontrolada. Suficiente para padaria (150 produtos ~ 15 KB).
3. **CSV com separador exotico** (ex.: TAB) falhara no sniffer e cairia
   no fallback para virgula. Nao e vulnerabilidade - so UX ruim.
4. **Linhas com erro reportadas com `line_number`** mas sem o conteudo
   bruto (nao vaza possiveis dados sensiveis em logs).

## Pontos positivos aplicados

- [x] Validacao Pydantic reutilizada (`ProductCreate` com
      `extra="forbid"`, limites, regex)
- [x] Parsing de preco e quantidade via `app/money.py` (mesma funcao de
      arredondamento do resto do sistema)
- [x] Idempotencia: produto existente e PULADO, nao sobrescrito
- [x] Modo `--dry-run` permite auditar antes de gravar
- [x] Modo `--strict` para operacoes criticas (rollback no primeiro erro)
- [x] Erros reportados com numero de linha, sem vazar stacktrace
- [x] Transacao unica (ou tudo ou nada em caso de falha irrecuperavel)
- [x] Encoding `utf-8-sig` aceita BOM do Excel sem quebra
- [x] Separador auto-detectado (vazamento zero: nao executa codigo do CSV)
- [x] `data/produtos.example.csv` versionado como template, com
      exceção explicita no `.gitignore`
- [x] Documentacao operacional em `docs/IMPORTACAO-CSV.md`

## Recomendacoes (nao aplicadas)

- Fase futura: botao "Importar CSV" na UI de produtos (opcional; a
  importacao via CLI atende o caso real).
- Fase 10: documentar fluxo "backup antes do import" no manual de
  instalacao.
