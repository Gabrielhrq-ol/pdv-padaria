# Relatorio de seguranca - Fase 3

Data: 2026-10-12
Escopo: tela do PDV, modelos `sales` + `sale_items`, routers `/api/sales/*`
e `/api/products/by-code/*`, `app/services/sales_service.py`.
Metodo: revisao de codigo + 218 testes passando + `pip-audit`.

> IMPORTANTE: NAO corrigi nada antes de voce ler.

## Resumo

- `pip-audit`: mesmas 11 CVEs herdadas da Fase 1 (nenhuma nova).
- 218 testes passando (170 anteriores + 48 novos: 28 sales_service + 20 router).
- Preco e copiado no item no momento do add (regra 4 do CLAUDE.md,
  validada por teste).

## Codigo

### CRITICO
Nenhum.

### ALTO
Nenhum.

### MEDIO
1. **Isolamento entre operadores por regra, nao por FK forte.**
   - Caixa so acessa suas proprias vendas (checado por `user_id`).
   - Admin ve tudo. Teste `test_caixa_nao_ve_venda_de_outro` confirma.
   - Se um dia houver mais de 1 caixa concorrente, confirmar que o
     controle por `user_id` segue valendo (sem race).

### BAIXO
2. **Numeracao de venda e `max+1` global.** Para 1 caixa isso basta.
   Para 2+ caixas em paralelo pode haver colisao - CheckConstraint
   `unique(number)` detectaria e retornaria 500 (nao corromperia dados).
   Correcao prevista: Fase 7 ou producao, substituir por sequencia
   nativa / tabela de contador.
3. **Favoritos buscam /api/products?limit=500 sem filtro.** Em padaria
   com 150 produtos nao e problema. Para catalogos grandes, criar
   endpoint dedicado `/api/products/favorites`.
4. **Confirmacao de remocao de item usa `confirm()` nativo.** OK pra
   PDV local; nao e vetor de ataque.

## Pontos positivos aplicados

### Autorizacao
- [x] Rotas /api/sales/* exigem `require_authenticated`
- [x] Mutantes exigem `require_csrf` adicionalmente
- [x] Caixa pode criar, add item, change, remove e cancelar venda
      (decisao 3 do cliente)
- [x] Caixa so acessa suas vendas; admin ve tudo
- [x] 403 em venda de outro operador (teste confirma)

### Validacao
- [x] `SaleItemAdd` com `extra="forbid"`, limites de qty
- [x] `SaleItemUpdate` com qty_milli >= 1
- [x] `SaleCancel` exige motivo com min_length=1
- [x] `code` validado por regex no `resolve_code`: `^(?:(\d{1,4})\s*\*\s*)?[A-Za-z0-9]+$`
- [x] Multiplicador limitado a 1..1000
- [x] CheckConstraints no banco: status valido, qty > 0, valores >= 0

### Integridade da venda
- [x] Preco COPIADO no item (CLAUDE.md regra 4)
- [x] Teste `test_preco_congelado_quando_produto_muda` valida
- [x] Agrupamento automatico por product_id (evita duas linhas)
- [x] Totais recalculados automaticamente no service
- [x] Status valida transicoes (so cancela quem esta open)

### Audit log (CLAUDE.md regra 11)
- [x] sale_opened, sale_item_added, sale_item_changed, sale_item_removed,
      sale_cancelled gravados
- [x] Inclui user_id, entity=product/sale, entity_id, details, ip

### Frontend
- [x] `pdv.js` nunca usa innerHTML (textContent/createElement sempre)
- [x] CSRF enviado automaticamente em POST/PUT/PATCH/DELETE
- [x] 401 em qualquer endpoint -> redirect pra /login
- [x] Templates herdam base.html com Jinja autoescape
- [x] Headers de seguranca continuam (CSP, nosniff, DENY)
- [x] Nao expoe stack trace em caso de erro

### Resiliencia
- [x] Reload da pagina retoma venda em aberto via GET /api/sales/open
- [x] 1 venda ativa por operador (idempotente em POST /api/sales)
- [x] Transacoes do SQLite (commit por operacao); erro mantem venda
      coerente

### Testes novos
- [x] 28 em test_sales_service (unit, sem HTTP)
- [x] 20 em test_sales (integration via TestClient)
- [x] Cobertura: resolve_code (todos os formatos), add/change/remove/cancel,
      preco congelado, agrupamento, isolamento entre operadores,
      permissoes

## Recomendacoes (nao aplicadas)

1. **Upgrade fastapi + starlette + jinja2** (acumulada das fases 1-2).
2. **Fase 4 (proxima):** finalizacao atomica da venda com baixa de
   estoque (ja planejado no guia).
3. **Fase 7:** ativar setting `require_cash_session` ligando sales ao
   cash_session_id.
4. **Fase 10:** considerar sequencia de `number` persistida em settings
   ou tabela dedicada para suportar multi-caixa no futuro.
