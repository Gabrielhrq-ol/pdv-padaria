# Relatorio de seguranca - Fase 4

Data: 2026-10-13
Escopo: finalizacao atomica, pagamentos, baixa de estoque, cancelamento
de venda finalizada, reimpressao via Dummy.
Metodo: revisao de codigo + 271 testes passando + pip-audit.

> IMPORTANTE: NAO corrigi nada antes de voce ler.

## Resumo

- `pip-audit`: mesmas 11 CVEs herdadas das Fases 1-2 (nenhuma nova).
- 271 testes passando (218 + 53 novos: 29 finalize_service + 11 receipt
  + 13 integration).
- Transacao atomica validada por teste (`test_estoque_bate_com_movements`).

## Codigo

### CRITICO
Nenhum.

### ALTO
Nenhum.

### MEDIO
1. **`stock_milli` pode ir negativo** (decisao 9 do cliente).
   - Removi o `CheckConstraint ck_products_stock_non_negative` via migracao
     dedicada (`85a0a006e786`). O cliente explicitamente pediu: padaria
     produz propria mercadoria, nao faz sentido bloquear.
   - Relatorios futuros (Fase 8) devem destacar produtos com stock_milli
     negativo para auditoria.

2. **Rota `/reverse` acessivel por caixa (nao so admin).**
   - Decisao 3 do cliente: qualquer operador pode cancelar venda,
     com motivo + audit_log. Override do guia original.
   - Mitigacao: motivo obrigatorio, audit log registra tudo, nunca apaga.
   - Fase futura: setting `allow_reverse_by_cashier` para desligar quando
     o cliente quiser restringir.

3. **Multiplos pagamentos permitem distribuir troco so no ultimo dinheiro.**
   - Se operador coloca "dinheiro 500" + "dinheiro 1000" para total 1200,
     o troco (300) vai no segundo. Documentado em `calculate_change`.
   - Nao e vetor de ataque, mas vale lembrar que a UI permite varios
     pagamentos.

### BAIXO
4. **Reimpressao sem limite.** Qualquer caixa pode reimprimir qualquer
   venda sua (admin ve tudo). Audit registra `sale_reprinted` cada vez.
5. **`sale.number` ainda e `max+1` global.** Ja apontado na Fase 3; nao
   e critico para 1 caixa.
6. **Falha de impressao nao desfaz venda** (regra 6 do CLAUDE.md).
   Mensagem clara no retorno (`print_error`). Comportamento esperado.

## Pontos positivos aplicados

### Atomicidade (CLAUDE.md regra 3)
- [x] `finalize_sale`: payments + stock_milli + stock_movements no mesmo
      flush/commit do service; chamador faz UM commit no router
- [x] Erro no meio da finalize -> db.rollback() no router; nada e gravado
- [x] Teste `test_estoque_bate_com_movements`: invariante validado

### Preco (regra 4)
- [x] `sale_items` ja congelava preco; `payments` nao duplica preco
- [x] Receipt usa `item.unit_price_cents` do item (nao do produto atual)

### Impressao fora da venda (regra 6)
- [x] `print_job` chamado APOS `db.commit()`; nunca dentro da transacao
- [x] Falha de impressao: retorna `print_error` no payload, venda OK

### Validacao
- [x] Pydantic `extra="forbid"` em PaymentInput, FinalizeRequest,
      ReverseRequest, FinalizeResult
- [x] `method` regex `^[A-Za-z0-9_-]+$` (nao aceita injection)
- [x] Validacao de forma de pagamento contra setting `payment_methods`
- [x] Troco so sai de dinheiro (teste cobre cartao excedendo)
- [x] Discount >=0, discount <= subtotal, reason obrigatorio se > 0
- [x] CheckConstraints no banco: amount_cents >=0, change_cents >=0,
      method nao vazio, stock_movements.type em lista, qty_milli != 0

### Audit log
- [x] sale_finalized, sale_reversed, sale_reprinted gravados
- [x] Nunca armazena token, senha, numero de cartao, dados de PIX
- [x] IP e user_id em todos

### Permissoes
- [x] /finalize require_authenticated (caixa + admin)
- [x] /reverse require_authenticated (decisao 3) + motivo obrigatorio
- [x] /reprint require_authenticated
- [x] CSRF em TODAS as mutantes
- [x] Caixa so acessa suas vendas; admin ve todas (teste cobre)

### Frontend
- [x] Modal de pagamento usa textContent/createElement (nunca innerHTML)
- [x] Cookie CSRF enviado automaticamente nas mutantes
- [x] 401 em qualquer endpoint redireciona pra /login

### Testes novos (53)
- [x] calculate_change: exato, com troco, misto, cartao excedendo,
      insuficiente, multiplos dinheiros, vazio
- [x] finalize_sale: simples, troco, estoque abaixa, movements criados,
      misto, dupla finalizacao, sem itens, metodo invalido, desconto
      sem motivo, estoque negativo permitido
- [x] estoque_bate_com_movements: invariante critico
- [x] reverse_sale: estorno de estoque, movement estorno, so completed,
      motivo obrigatorio
- [x] get_last_completed
- [x] receipt: nome, disclaimer, cnpj, 32 colunas, desconto, troco,
      pagamento misto, marca "2a VIA"
- [x] endpoints: finaliza/reverse/reprint com CSRF, dupla finalizacao
      rejeitada, metodo invalido, cartao excedendo

## Decisoes do cliente aplicadas

- **Decisao 1**: cupom "DOCUMENTO SEM VALOR FISCAL" em destaque -> receipt.py
- **Decisao 3**: caixa pode cancelar venda com motivo + audit -> /reverse
- **Decisao 6**: formas de pagamento em setting -> `payment_methods` JSON
- **Decisao 7**: SEM TEF; sistema so registra forma + valor
- **Decisao 9**: estoque pode negativo -> constraint removida
- **Decisao 10**: operador escolhe imprimir -> botoes "finalizar imprimindo"
  e "finalizar sem imprimir"

## Recomendacoes (nao aplicadas)

1. **Upgrade fastapi + starlette + jinja2** (acumulado das fases).
2. **Fase 5 (proxima)**: substituir Dummy por `Win32Raw` apos teste
   da POS-5890U-L via AnyDesk. `receipt.py` ja esta validado.
3. **Fase 7**: linkar `sales.cash_session_id` ao caixa aberto.
4. **Fase 8**: relatorios devem destacar produtos com stock_milli
   negativo para auditoria do dono.
