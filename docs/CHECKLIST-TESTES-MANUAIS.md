# Checklist de testes manuais — antes da entrega

Este checklist cobre fluxos felizes e edge cases por fase. **Não entregar
sem marcar todos.** Marcar com `[x]` o que foi testado e passou.

Rodar no PC do cliente (ou máquina equivalente ao perfil Dell Inspiron 620)
depois de completar `docs/INSTALACAO.md`.

---

## 0. Pré-check

- [ ] `pytest` roda 100% verde no mesmo PC (`.venv\Scripts\activate && pytest`)
- [ ] `pip-audit` output anexado em `docs/pip-audit-pre-entrega.txt`
- [ ] `data/cliente.json` real criado e **não** aparece em `git status`
- [ ] `data/pdv.db` existe e `alembic current` mostra `d0b3bdd9d9e8`
- [ ] `.env` tem `SECRET_KEY` real (não placeholder) e `ENVIRONMENT=production`
- [ ] Credenciais de dev **DESATIVADAS** via `scripts/trocar_admin.py`
  (`SELECT username, active FROM users` mostra apenas o dono ativo)
- [ ] Atalho `PDV` existe no desktop e abre o navegador

---

## 1. Autenticação (Fase 2)

- [ ] Login com usuário/senha do admin do dono funciona
- [ ] Login com senha errada mostra erro genérico (não vaza se usuário existe)
- [ ] 5 senhas erradas seguidas bloqueiam a conta por 15 minutos
- [ ] Após o lockout expirar, login funciona de novo
- [ ] Logout sai e volta pra `/login`
- [ ] Tentar acessar `/products` sem logar redireciona pra `/login`
- [ ] Tentar `/admin/stock` logado como caixa redireciona pra `/products`
- [ ] Cookie `session` tem flag HttpOnly (DevTools → Application → Cookies)
- [ ] `/docs` responde 404 em produção (ENVIRONMENT=production)

---

## 2. Produtos (Fase 1)

- [ ] Admin cadastra produto novo UN com barcode (código de barras) 13 dígitos
- [ ] Admin cadastra produto KG com internal_code `101`
- [ ] Admin cadastra produto com estoque mínimo definido
- [ ] Lista de produtos mostra ativos por padrão
- [ ] Toggle "mostrar inativos" revela desativados
- [ ] Admin edita preço de produto (atualiza na lista)
- [ ] Admin desativa produto (fica inativo, não some)
- [ ] Admin reativa produto inativo
- [ ] Caixa NÃO consegue cadastrar/editar produto (botão oculto)
- [ ] Preço com 2 casas decimais funciona (`1,50`, `18,00`)
- [ ] Barcode duplicado é rejeitado com mensagem clara
- [ ] Internal_code duplicado é rejeitado

---

## 3. Importação CSV (Fase 1-bis — se usar)

- [ ] `--dry-run` mostra o que seria importado sem gravar
- [ ] Importação real cria produtos novos
- [ ] Re-importar o mesmo CSV é idempotente (atualiza por barcode)
- [ ] CSV com encoding Windows-1252 (Excel BR) é lido
- [ ] Categoria nova no CSV é criada automaticamente

---

## 4. Vendas no PDV (Fases 3-4)

### Fluxo feliz
- [ ] Caixa consegue abrir uma venda (ou PDV abre direto após abrir caixa)
- [ ] Passar barcode adiciona o produto com qtd 1
- [ ] Passar o mesmo barcode 3x acumula qtd 3
- [ ] `3*101` adiciona 3x do internal_code 101
- [ ] F2 abre busca por nome; selecionar adiciona o produto
- [ ] F3 muda a quantidade do item selecionado
- [ ] F4 remove o item selecionado
- [ ] F9 mostra preço de um código sem adicionar
- [ ] Produto por KG: digitar `0,350` em F3 vira 350 gramas
- [ ] F6 abre o modal de pagamento
- [ ] Pagamento em dinheiro calcula troco corretamente
- [ ] Pagamento em PIX/débito aceita valor exato
- [ ] Pagamento dividido (dinheiro + PIX) funciona
- [ ] Finalizar com "imprimir cupom" marcado dispara impressão
- [ ] Finalizar sem imprimir salva venda sem cupom
- [ ] Após finalizar, o estoque é baixado em `/products`
- [ ] F10 (ou botão) reimprime a última venda como "2ª VIA"

### Edge cases
- [ ] Vender produto com estoque 0 funciona (padaria pode ir negativo)
- [ ] Cancelar venda em aberto exige motivo e grava audit
- [ ] Fechar a janela do navegador durante a venda e reabrir retoma a venda
- [ ] Vender produto inativo é rejeitado com mensagem
- [ ] Qtd 0 ou negativa é rejeitada
- [ ] Pagar valor menor que o total é rejeitado

---

## 5. Caixa (Fase 7)

### Fluxo feliz
- [ ] Operador abre o caixa com fundo inicial
- [ ] Após abrir, PDV libera venda
- [ ] Registrar sangria com motivo funciona
- [ ] Sangria sem motivo é rejeitada
- [ ] Registrar suprimento sem motivo é aceito
- [ ] Resumo mostra fundo, suprimentos, sangrias, vendas em dinheiro, esperado
- [ ] Totais por forma de pagamento aparecem corretamente
- [ ] Fechar caixa com valor igual ao esperado funciona sem motivo
- [ ] Fechar com sobra pede motivo
- [ ] Fechar com falta pede motivo
- [ ] Após fechar, PDV volta a bloquear até abrir novo caixa

### Edge cases
- [ ] Tentar abrir 2º caixa simultâneo é rejeitado (409)
- [ ] Fechar caixa com venda em aberto é rejeitado
- [ ] Admin desliga toggle `cash_session_required`: PDV libera venda sem caixa
- [ ] Admin religa: PDV volta a exigir caixa aberto

---

## 6. Estoque (Fase 6)

- [ ] Entrada sem motivo é aceita e atualiza saldo
- [ ] Entrada com motivo salva o motivo
- [ ] Perda exige motivo obrigatório
- [ ] Ajuste exige motivo e define novo saldo absoluto
- [ ] Ajuste em produto inativo é rejeitado (400)
- [ ] Histórico mostra entradas de venda, perda, entrada, ajuste
- [ ] Filtro por produto no histórico funciona
- [ ] Filtro por tipo funciona
- [ ] Filtro por período (data de / data até) funciona
- [ ] Badge de alerta em `/products` mostra contagem de produtos abaixo do min
- [ ] Modal do alerta lista os produtos

---

## 7. Relatórios (Fase 8)

- [ ] Dashboard de hoje mostra números corretos
- [ ] Vendas por período agrupa por dia corretamente
- [ ] Caixas fechados lista o caixa fechado anterior com diferença
- [ ] Vendas por operador soma por usuário
- [ ] Vendas por forma soma por método (dinheiro líquido, PIX etc)
- [ ] Top produtos ordenável por faturamento e por quantidade
- [ ] Descontos e cancelamentos lista ambos
- [ ] Filtros de data globais aplicam em todas as abas
- [ ] **Botão CSV** em cada aba baixa arquivo
- [ ] CSV abre no Excel (separador `;`, BOM UTF-8, acentos corretos)
- [ ] Caixa NÃO consegue acessar `/admin/reports` (redireciona)

---

## 8. Impressora (Fase 5-prep — pular se ainda não testou POS-5890U-L)

- [ ] Backend `dummy` é default se nunca mudou
- [ ] Backend `win32raw` precisa de nome preenchido (422 sem nome)
- [ ] Imprimir cupom de teste chega na impressora real
- [ ] Acentos saem corretos (testar CP850, CP858, CP860 se necessário)
- [ ] Guilhotina só é enviada se "corte automático" marcado
- [ ] Falha de impressão **não** desfaz a venda

---

## 9. Backup (Fase 9)

### Config
- [ ] Admin consegue salvar `backup_dir_1` apontando pro pendrive
- [ ] Admin consegue salvar `backup_dir_2` apontando pra pasta Google Drive
- [ ] Toggle `backup_on_cash_close` persiste entre reloads
- [ ] Botão "Fazer backup agora" cria arquivo `.db.gz` nos destinos
- [ ] Histórico mostra a execução com `backup_run`

### Hook
- [ ] Fechar caixa dispara backup automático (`backup_run` aparece no histórico)
- [ ] Backup com um destino bom e um ruim mostra 1 ok / 1 fail
- [ ] Fechar caixa com destinos inválidos **não** aborta o fechamento
  (caixa fica `closed` mesmo com `backup_failed` no histórico)

### Rotação
- [ ] Após mais de 30 backups no mesmo destino, o mais antigo é apagado
- [ ] Setar `keep_last=5` e rodar 7 backups: fica com 5

### CLI
- [ ] `python scripts\do_backup.py` roda sem erro e exit code 0
- [ ] Task Scheduler agendado roda à noite e deixa arquivo na pasta

### Integridade
- [ ] Descomprimir um `.db.gz` e abrir com `sqlite3`: `PRAGMA integrity_check` → `ok`
- [ ] Tabelas e dados estão presentes no backup

---

## 10. Segurança operacional

- [ ] `data/pdv.db` tem permissão restrita ao usuário Windows do dono
- [ ] `.env` tem permissão restrita
- [ ] `data/cliente.json` **NÃO** está no git (confirmar com `git status`)
- [ ] `logs/pdv.log` existe e grava eventos
- [ ] `audit_log` tem entradas de login, cash_opened, cash_closed, etc.
- [ ] Rodar `pip-audit` final: nenhuma vulnerabilidade adicionada vs. relatório

---

## 11. Robustez

- [ ] Simular queda de energia: desligar o PC durante uma venda em aberto.
  Religar: venda ainda aparece em aberto
- [ ] Encerrar o servidor com `Ctrl+C` durante uma venda. Reiniciar o PDV:
  venda está lá (não foi finalizada)
- [ ] Fechar e reabrir o navegador sem reiniciar o servidor: sessão
  continua válida (dentro das 8h)
- [ ] Deixar o navegador aberto por mais de 8h: ao agir, redireciona
  pra `/login` (sessão expirou)

---

## 12. Documentação / entrega

- [ ] Dono recebeu `MANUAL-OPERADOR.md` impresso
- [ ] Senhas do admin e do caixa (se houver) anotadas em local físico seguro
- [ ] Senha do Google Drive (se usar) anotada separada
- [ ] Combinado quando o dono deve trocar o pendrive (ex: semanal)
- [ ] Dono sabe o que fazer se der problema (contato do Gabriel)

---

## Após completar

Se tudo marcado:
1. Commit `docs/pip-audit-pre-entrega.txt` com output limpo
2. Tag no git: `git tag v1.0.0 && git push --tags`
3. Entregar o PC + o manual impresso
4. Agendar check-in de 1 semana e 1 mês com o dono
