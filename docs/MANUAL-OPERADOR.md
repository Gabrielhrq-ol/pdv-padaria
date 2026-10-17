# Manual do operador — PDV Padaria

Este manual é pra quem opera o caixa no dia a dia (dono ou operador).
Linguagem simples e direta.

**Dica:** imprimir e deixar perto do caixa.

---

## 1. Começar o dia

### 1.1. Ligar o PC e abrir o PDV

1. Ligar o computador normalmente.
2. Dar **duplo-clique** no atalho **PDV** no desktop.
3. Vai abrir uma janela preta (cmd) e, logo depois, o navegador com a
   tela de login.
4. **Não feche** a janela preta — ela é o sistema rodando. Só feche no
   fim do dia.

### 1.2. Fazer login

1. Digitar **usuário** e **senha**.
2. Depois de 5 senhas erradas em 15 minutos, a conta **bloqueia por 15 min**.
   Esperar e tentar de novo.

### 1.3. Abrir o caixa

Antes de qualquer venda, abrir o caixa:

1. Clicar em **Caixa** no topo da tela.
2. Contar o **dinheiro de troco** que está na gaveta.
3. Digitar esse valor em **"Fundo inicial"** (ex: `100,00`).
4. (Opcional) Em "Observações" escrever algo como "turno manhã Zé".
5. Clicar **Abrir caixa**.

Pronto, pode começar a vender.

---

## 2. Vender

### 2.1. Pelo código de barras (leitor)

1. Clicar no campo de código (fica em foco automático).
2. Passar o produto no leitor. O item aparece na lista com qtd 1.
3. Se vendeu mais de um do mesmo, **passar de novo** ou digitar `3*CODIGO`
   e Enter.

### 2.2. Pelo código interno (pães, salgados)

Pães e salgados não têm código de barras. Usar **código interno** (ex: `101`
pra pão francês):

1. Digitar `101` e Enter.
2. Se vender 3 pães: digitar `3*101` e Enter.

### 2.3. Produtos por peso (KG/L)

Para itens vendidos por peso (ex: bolo por kg):

1. Pesar o produto na balança (manual, por enquanto).
2. Digitar o código. O item entra com qtd 1,000 kg.
3. Apertar **F3** (ou botão "Qtd" no rodapé) e digitar a quantidade real:
   - `0,350` para 350 gramas
   - `1,500` para 1,5 kg
4. Enter.

### 2.4. Teclas úteis durante a venda

| Tecla | O que faz | Também disponível em notebook |
|-------|-----------|-------------------------------|
| F2 | Buscar produto por nome | `Ctrl+B` |
| F3 | Mudar quantidade do item selecionado | `Ctrl+Q` |
| F4 | Remover item selecionado | `Ctrl+D` |
| F6 | Finalizar venda e pagar | — (botão "Pagar") |
| F8 | Cancelar venda inteira | `Ctrl+X` |
| F9 | Consultar preço sem adicionar | `Ctrl+I` |
| F10 | Reimprimir última venda | — (botão) |

> No notebook do cliente, as teclas F2-F9 estão atrás da tecla **Fn**
> (brilho / volume). Use os atalhos `Ctrl+letra` acima ou os **botões no
> rodapé da tela do PDV**.

### 2.5. Finalizar e cobrar

1. Apertar **F6** (ou clicar "Pagar").
2. Escolher a forma de pagamento:
   - **Dinheiro** → digitar valor recebido. O sistema calcula o troco.
   - **Débito / Crédito / PIX** → digitar o valor exato (sem troco).
   - **Pagamento dividido** → somar várias formas até cobrir o total.
3. (Opcional) Marcar **Imprimir cupom** se o cliente quiser.
4. Clicar **Finalizar**.

Pronto. O sistema baixa o estoque automaticamente, registra o pagamento
no caixa e (se marcou) imprime o cupom.

### 2.6. Cancelar venda

1. **Antes de finalizar:** apertar **F8** e confirmar com motivo.
2. **Depois de finalizar:** chamar o admin. Só admin cancela venda
   finalizada (vai no histórico e faz estorno).

---

## 3. Movimentar dinheiro do caixa

### 3.1. Sangria (tirar dinheiro)

Exemplos: pagar fornecedor na mão, levar dinheiro pro cofre, dar troco
pro operador do caixa vizinho.

1. Clicar em **Caixa** no topo.
2. No bloco **Sangria**, digitar o valor (ex: `50,00`).
3. **Motivo é obrigatório.** Exemplo: "pagamento fornecedor farinha, nota 1234".
4. Clicar **Registrar sangria**.

### 3.2. Suprimento (colocar dinheiro)

Exemplos: reforço de troco no meio do dia.

1. No bloco **Suprimento**, digitar o valor.
2. Motivo é **opcional** mas ajuda ("reforço de troco").
3. Clicar **Registrar suprimento**.

---

## 4. Fechar o caixa (fim do dia)

Fazer isso **antes de fechar a padaria**:

1. Clicar em **Caixa** no topo.
2. Olhar o campo **Esperado em caixa** — é o que o sistema calculou.
   Fórmula: `fundo inicial + suprimentos + vendas em dinheiro − sangrias`.
3. **Contar o dinheiro físico** da gaveta.
4. Digitar o valor em **"Dinheiro contado"**.
5. Se bater com o esperado → clicar **Fechar caixa**.
6. Se **sobrar ou faltar** → o sistema mostra a diferença e pede
   **motivo obrigatório** (ex: "faltaram 50 centavos de troco").
7. Clicar **Fechar caixa**.

### 4.1. Importante antes de fechar

- **Nenhuma venda pode estar em aberto.** Se tiver, o sistema avisa.
  Finalizar ou cancelar antes.
- O **backup automático dispara** no fechamento. Ignorar — ele roda
  sozinho em segundo plano. Dá pra ver em `/admin/backup` (só admin) se
  deu certo.

### 4.2. Depois de fechar

Fechou o caixa, sistema registrou. Agora pode:
- Sair do sistema (botão **Sair** no topo direito)
- Fechar a janela preta do cmd
- Desligar o computador

---

## 5. Problemas comuns

### "Abra o caixa antes de iniciar uma venda"

Você entrou direto no PDV sem abrir o caixa. Clicar em **Caixa**,
abrir, voltar pro PDV.

### Produto não é encontrado pelo código

- O código pode não estar cadastrado. Chamar o admin.
- O código pode estar errado (passar de novo o leitor).
- O produto pode estar **inativo** (descontinuado). O admin reativa.

### Impressora não imprimiu

A venda **continua válida mesmo sem impressão** (regra do sistema).
Opções:
1. Em `/pdv`, clicar **F10 / Reimprimir** (ou botão "Reimprimir"). Vai
   sair como "2ª VIA".
2. Se persistir, verificar:
   - Cabo USB conectado
   - Papel na impressora
   - Impressora ligada
3. Admin pode trocar backend em `/admin/printer` → "Dummy" temporariamente
   enquanto resolve.

### Erro "conta temporariamente bloqueada"

Sua conta travou após 5 tentativas erradas. Esperar **15 minutos** e
tentar de novo. Se tem pressa, pedir pro admin desbloquear.

### Fechou a janela preta sem querer

O sistema parou. Abrir o PDV de novo pelo atalho. Suas vendas estão
seguras no banco.

### PC travou / desligou no meio de uma venda

- Se a venda **não foi finalizada**: ela fica em aberto. Ao religar e
  entrar no PDV, ela aparece lá. Finalizar normalmente.
- Se a venda **foi finalizada antes do travamento**: tudo salvo.

### Internet caiu

**Não interfere no PDV.** Ele roda 100% local. Só o sync do Google
Drive pros backups vai acumular até a internet voltar.

---

## 6. Papéis — o que cada um pode fazer

| Função | Caixa | Admin |
|--------|-------|-------|
| Vender | ✓ | ✓ |
| Abrir/fechar caixa | ✓ | ✓ |
| Sangria / Suprimento | ✓ | ✓ |
| Cancelar venda em aberto | ✓ | ✓ |
| Cadastrar produto | — | ✓ |
| Editar preço / estoque de produto | — | ✓ |
| Importar CSV de produtos | — | ✓ |
| Entrada / perda / ajuste de estoque | — | ✓ |
| Ver relatórios | — | ✓ |
| Fazer backup manual | — | ✓ |
| Configurar impressora / backup / caixa | — | ✓ |
| Ver histórico de movimentações | ✓ (só ver) | ✓ |
| Ver alertas de estoque baixo | ✓ | ✓ |

---

## 7. Rotina sugerida pro dono

**Diária:**
- No fim do dia, fechar caixa pelo PDV
- Conferir se o backup rodou (olhar notificação do Google Drive sync)
- Trocar o pendrive de backup de vez em quando (semanal) e guardar fora da padaria

**Semanal:**
- Ver `/admin/reports` → **Vendas por período** da semana
- Ver **Caixas fechados** — qualquer diferença grande merece atenção
- Ver **Top produtos** — orienta compra pra semana seguinte

**Mensal:**
- Ver **Vendas por operador** — como está o desempenho
- Ver **Descontos e cancelamentos** — se tem muito, investigar
- Fazer **ajuste de inventário** se os produtos físicos não baterem
  com o estoque do sistema

---

## 8. Em caso de dúvida ou problema

Entrar em contato com o Gabriel (desenvolvedor).

Antes de ligar, se possível:
1. Anotar a mensagem de erro exata
2. Lembrar o que estava fazendo
3. Tirar foto da tela (se ainda estiver aberta)

Isso acelera MUITO a resolução.
