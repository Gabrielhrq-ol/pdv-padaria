# ⚠️ LEIA ANTES DE INSTALAR

Avisos atualizados em **2026-10-31** — a documentação antiga (LEIA-ME.md,
00-INSTRUCOES.txt, INSTALAR-REMOTO.md) foi escrita antes dessas mudanças.
**O que estiver aqui tem prioridade sobre o resto da doc.**

---

## 1. Checar versão do Windows ANTES de começar

Python 3.12 **não roda em Windows 7**. Antes de qualquer passo:

```powershell
(Get-ItemProperty "HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion").ProductName
```

- **Windows 10 / 11 / 8.1** → segue a instalação normal
- **Windows 7** → PARAR. Avisar Gabriel. Soluções: Python 3.11.9 adaptado
  OU reinstalar Windows 10 no PC

---

## 2. Nome do arquivo de dados do cliente

O `00-INSTRUCOES.txt` manda abrir `cliente.json`, mas o arquivo no kit
chama `cliente.json.PREENCHER`. O passo correto:

```powershell
notepad C:\pdv-padaria-kit\pdv-padaria\data\cliente.json.PREENCHER
```

Preencher CNPJ, endereço, telefone. Salvar. Depois renomear:

```powershell
Rename-Item "C:\pdv-padaria-kit\pdv-padaria\data\cliente.json.PREENCHER" "cliente.json"
```

---

## 3. Painel do dono entra SEM senha

Documentação antiga menciona "logar com usuário e senha". **Ignorar.**

Fluxo real do painel do dono:

1. Abre `http://127.0.0.1:8000/`
2. Clica em **"Painel do dono"**
3. Aparece **dropdown** com os admins ativos
4. **Clica no nome do dono** → entra direto, sem digitar senha

A senha pedida pelo `06-criar-admin.bat` é só pra satisfazer o banco
(obrigatório ter hash). Pode anotar num papel e esquecer — ela não é
usada pra entrar.

**CRÍTICO antes de encerrar:** rodar `scripts/trocar_admin.py` pra
desativar o usuário de desenvolvimento que vem no banco inicial. Senão
ele aparece no dropdown junto com o dono e qualquer um clica.

---

## 4. Atalhos do PDV (passar pro operador)

| Atalho | Ação |
|---|---|
| **Enter** com código | Adiciona produto |
| **Enter** vazio | Modal de pagamento (finalizar venda) |
| `3*101` + Enter | 3 unidades do código 101 |
| **F1** ou **F12** | Menu de Operações (sangria, suprimento, fechar caixa) |
| **F2** | Busca por nome |
| **F3** | Cancela item selecionado |
| **F8** | Cancela cupom inteiro |
| **F10** | Reimprime último cupom |
| **F11** | Cupom em tela cheia (conferência) |
| **H** | Consulta preço sem adicionar |
| **F6** | SEM AÇÃO (reservado p/ gaveta eletrônica futura — gaveta de hoje é mecânica) |

No modal de pagamento: `1`=dinheiro, `2`=débito, `3`=crédito, `4`=pix, `5`=outros.

---

## 5. Impressora POS-5890U-L

Configurar **só depois** da impressora funcionar no Windows (teste uma
página normal pelo painel de impressoras):

- Painel do dono → **Impressora**
- Backend: `win32raw`
- Nome: cópia exata do nome em "Impressoras e Scanners"
- Clica "Imprimir cupom de teste"
- Se acentos saírem errados: codepage **CP850 → CP858 → CP860**,
  testando entre cada troca

Se não tem guilhotina, desligar "corte automático".

---

## Se der problema

Abre o Claude Code na pasta `C:\pdv-padaria-kit\pdv-padaria\` e cola o
erro. O Claude lê este arquivo e sabe o contexto da entrega.
