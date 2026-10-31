# Instalação remota via AnyDesk — PDV João & Maria

Guia pra Gabriel instalar o PDV **sem sair de casa**, apenas via AnyDesk.
Zero pendrive, zero visita presencial.

---

## O que você precisa ter antes

- **AnyDesk** instalado no PC do cliente, com acesso não-assistido
  liberado (ou cliente aceita toda vez)
- **Internet** no PC do cliente (precisa só durante a instalação,
  pra baixar Python + o kit)
- **5 GB livres** no SSD do cliente
- **Credencial de admin do Windows** no PC do cliente
- **Dados da padaria** anotados num bloco de notas aberto:
  - CNPJ
  - Endereço completo com cidade/UF
  - Telefone
  - Nome e senha nova pro admin (dono) — mínimo 8 chars, 1 letra, 1 número

## Fluxo da instalação (~40 min)

### Passo 1 — Conectar via AnyDesk (1 min)

- Abre AnyDesk no seu notebook
- Digita o ID do PC do cliente
- Cliente aceita (ou já está em modo não-assistido)
- Deixa a janela do AnyDesk ocupando metade da tela
- Deixa o Claude Code (eu) na outra metade

### Passo 2 — Abrir PowerShell admin no PC do cliente (30 seg)

Dentro do AnyDesk, no PC do cliente:

- Botão iniciar → digita `powershell`
- **Clique DIREITO** em "Windows PowerShell" → "Executar como administrador"
- Confirma UAC

### Passo 3 — Colar o one-liner (1 min pra colar, ~5 min pra rodar)

Copia esse bloco e cola no PowerShell do PC do cliente:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force
iwr -useb https://raw.githubusercontent.com/Gabrielhrq-ol/pdv-padaria/main/scripts/instalar.ps1 | iex
```

Aperta Enter. **Aguarda ~5 min** enquanto o script:

- ✅ Verifica Python 3.12 (ou baixa e instala silenciosamente)
- ✅ Baixa o kit (27 MB) do GitHub Release
- ✅ Extrai em `C:\pdv-padaria-kit\`
- ✅ Cria `.venv` com Python 3.12
- ✅ Instala as 60+ bibliotecas **offline** (das wheels no kit)
- ✅ Gera `.env` de produção com `SECRET_KEY` aleatório
- ✅ Cria o banco de dados SQLite com todas as migrations

Se tudo der certo, aparece "INSTALACAO AUTOMATICA COMPLETA" em verde.

### Passo 4 — Passos interativos (10 min)

O script para antes dos passos que precisam de informação sua.
Ele imprime o que fazer. Resumo:

**A. Preencher dados da padaria**

```powershell
notepad C:\pdv-padaria-kit\pdv-padaria\data\cliente.json.PREENCHER
```

Substituir:
- `PREENCHER_CNPJ` → CNPJ real da padaria
- `PREENCHER_ENDERECO_COMPLETO_COM_CIDADE_UF` → endereço completo
- `PREENCHER_TELEFONE` → telefone

Salvar e fechar o Notepad. Depois renomear:

```powershell
Rename-Item "C:\pdv-padaria-kit\pdv-padaria\data\cliente.json.PREENCHER" "cliente.json"
```

**B. Criar admin do dono**

```powershell
cd C:\pdv-padaria-kit\pdv-padaria
.\.venv\Scripts\python.exe scripts\create_admin.py
```

Responde o que o script perguntar:
- Nome completo: `Maria da Silva` (o nome do dono)
- Username: `maria`
- Senha: a senha nova (NÃO ecoa na tela — digita sem ver)
- Papel: `admin`

**ANOTA A SENHA** em local físico seguro.

**C. Carregar dados da padaria pro banco**

```powershell
.\.venv\Scripts\python.exe scripts\seed_cliente.py
```

**D. Criar atalho no desktop**

```powershell
C:\pdv-padaria-kit\scripts-instalacao\09-criar-atalho-desktop.bat
```

Vai aparecer um ícone **PDV** no desktop do PC do cliente.

**E. (Opcional, recomendado) Agendar backup diário 23:30**

```powershell
C:\pdv-padaria-kit\scripts-instalacao\10-task-scheduler-backup.bat
```

### Passo 5 — Testar (10 min)

Peça pro cliente clicar no atalho **PDV** no desktop. Vai abrir uma
janela cmd preta + navegador em `http://127.0.0.1:8000`.

- Tela inicial com 2 cards aparece ✓
- Logue como admin com a senha nova ✓
- Entra no painel ✓
- Cadastra um produto de teste (Pão francês, código `101`, R$ 0,80) ✓
- Vai pro PDV, abre caixa (fundo R$ 50,00), passa o produto, finaliza em dinheiro ✓
- Volta pro painel, confirma a venda no histórico ✓

### Passo 6 — Trocar credenciais de dev (CRÍTICO antes de entregar)

**NÃO esquece disso.** Se o usuário de desenvolvimento ainda estiver no
banco (visível no dropdown do painel do dono), remove:

```powershell
cd C:\pdv-padaria-kit\pdv-padaria
.\.venv\Scripts\python.exe scripts\trocar_admin.py
```

### Passo 7 — Impressora (quando a POS-5890U-L estiver instalada)

Só depois da impressora funcionar no Windows (teste imprimir uma página
de teste do painel de impressoras do Windows), você entra no PDV,
vai em **Painel do dono → Impressora**, troca backend pra `win32raw`
e preenche o nome exato da impressora. Testa com "Imprimir cupom de teste".

Se os acentos saírem errados, troca a codepage na ordem: CP850 → CP858
→ CP860, testando entre cada troca.

---

## Se algo der errado

**Erro de rede baixando Python ou o kit**
→ Confirma internet no PC do cliente abrindo google.com no navegador.
   Se abrir, tenta rodar o one-liner de novo (pode ser instabilidade
   temporária do GitHub).

**"ExecutionPolicy" bloqueou o script**
→ Confirma que você digitou a primeira linha
   (`Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force`)
   antes do iwr.

**Python instalou mas 'python --version' dá erro**
→ Feche o PowerShell e abra de novo. O PATH só atualiza em sessão nova.

**Firewall do Windows pede permissão**
→ Permita só em "Rede privada". Negue "Rede pública". É pra uvicorn
   escutar em 127.0.0.1 (local, não aceita conexão externa).

**Qualquer outro erro**
→ Tira foto do PowerShell com o erro e me manda. Eu diagnostico
   em segundos.

---

## Depois da entrega

- Deixa o atalho **AnyDesk** visível no desktop do cliente — se precisar
  dar suporte, você entra remoto.
- Marca retornar em 1 semana e em 1 mês pra checar como está indo.
- Guarda o `C:\pdv-padaria-kit\pdv-padaria\.env` em local seguro
  (o `SECRET_KEY` é o segredo do sistema).
- O cliente só precisa saber: **duplo-clique no atalho PDV todo dia**.
