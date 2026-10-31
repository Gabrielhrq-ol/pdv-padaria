# ⚠️ LEIA ANTES DE INSTALAR

Avisos atualizados em **2026-10-31**, depois da primeira instalação real.
**O que estiver aqui tem prioridade sobre o resto da documentação.**

---

## 1. Checar a versão do Windows ANTES de começar

Python 3.12 **não roda em Windows 7**. Antes de qualquer passo:

```powershell
(Get-ItemProperty "HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion").ProductName
```

- **Windows 10 / 11 / 8.1** → segue a instalação normal.
- **Windows 7** → PARAR. O kit não funciona nele: os pacotes são para
  Python 3.12. A solução é atualizar o Windows do PC.

---

## 2. Dados do cliente

Abrir, preencher e renomear:

```powershell
notepad C:\pdv-padaria-kit\pdv-padaria\data\cliente.json.PREENCHER
Rename-Item "C:\pdv-padaria-kit\pdv-padaria\data\cliente.json.PREENCHER" "cliente.json"
```

Se CNPJ, endereço ou telefone não forem conhecidos, deixar o campo vazio
(`""`). O cupom omite a linha. **Nunca** deixar `PREENCHER_...`, pois sairia
impresso. Não existe tela para esses dados: para mudar depois, editar
`data\cliente.json` e rodar `07-seed-cliente.bat` de novo.

---

## 3. Instalação limpa NÃO usa `trocar_admin.py`

O kit não traz banco nem usuário de desenvolvimento. O banco nasce vazio e
o script 06 cria o dono.

**Não rodar `scripts\trocar_admin.py` em instalação limpa.** Ele cria mais
um admin e desativa usuários chamados `gabriel`, `admin`, `teste` e `dev`,
o que pode desativar o próprio dono.

---

## 4. Entrada sem senha e operador obrigatório

- **Painel do dono:** tela com a lista de admins; clicar no nome entra sem
  senha. A senha do script 06 só existe porque o banco exige. Decisão do
  cliente; ver `docs/AUDITORIA-SEGURANCA.md`.
- **PDV e caixa:** só funcionam com **operador aberto**. Sem operador, o
  sistema mostra a tela "Abrir operador" (setas + Enter). Vale 12 horas.
- Abrindo um operador diferente de quem está no painel, a sessão do painel
  é encerrada e as vendas saem no nome do operador.

---

## 5. Abrir o sistema

O atalho **PDV** do script 09 usa `abrir_pdv.vbs`: janela própria, sem abas
e sem janela preta, com o servidor em segundo plano. Precisa de Chrome ou
Edge instalado, mas não de internet. O `start_pdv.bat` fica como reserva
(navegador comum + janela preta).

---

## 6. Atalhos do PDV (passar pro operador)

| Atalho | Ação |
|---|---|
| **Enter** com código | Adiciona o produto (cada bipada é uma linha nova) |
| `3*101` + Enter | 3 unidades do código 101 em uma linha só |
| **Enter** vazio | Abre o pagamento |
| **Setas** + **Enter** | Escolhem a forma de pagamento; Enter vai ao valor; Enter finaliza e imprime |
| **F1** ou **F12** | Menu de funções (sangria, suprimento, fechar caixa) |
| **F2** | Busca por nome |
| **F3** ou **F4** | Lista os itens para escolher qual cancelar |
| **F8** | Cancela a venda em andamento; sem itens, cancela o último cupom do caixa aberto |
| **F9** ou **H** | Consulta preço sem adicionar |
| **F10** | Reimprime o último cupom |
| **F11** | Cupom em tela cheia (conferência) |
| **Ctrl+Q** | Muda a quantidade do item selecionado |
| **Tab** ou **Esc** | Volta para a tela anterior |
| **F6** | SEM AÇÃO (reservado para gaveta eletrônica futura) |

---

## 7. Impressora POS-5890U-L

Testada e funcionando na instalação real: 58 mm, 32 colunas, CP850, sem
guilhotina. Configurar **depois** de imprimir pelo Windows:

- Painel do dono → **Impressora** → backend `win32raw`.
- Nome: cópia exata de "Impressoras e Scanners". Conferir se a fila aponta
  para a porta USB certa e não está com exclusão pendente.
- Enquanto estiver em `dummy`, **nada sai no papel**, mesmo com a mensagem
  "impressa".
- Acentos errados: testar CP850, CP858 e CP860.

---

## 8. Leitor de código de barras

Funciona como teclado, sem driver. Testar no Bloco de Notas: precisa sair o
número e descer a linha (Enter automático). Dois Enter abrem o pagamento
sozinho; nesse caso, configurar o leitor pelo manual dele.

---

## 9. Fechamento e backup

Fechar o caixa imprime e mostra o relatório, com cada venda e o total por
forma de pagamento. Sobra ou falta não pedem motivo. O backup roda ao fechar
e precisa do destino configurado em **Backup**. Se for pen drive, ele
precisa estar plugado. O agendamento das 23:30 (script 10) pede PowerShell
como administrador.

---

## Se der problema

Abrir o Claude Code em `C:\pdv-padaria-kit\pdv-padaria\` e colar o erro.
