# Instalação do PDV Padaria no PC do cliente

Guia passo-a-passo para instalar o sistema no PC do caixa (Dell Inspiron 620,
Windows 64 bits). Previsão: **~40 minutos** se tudo correr liso.

Pré-requisitos pra começar:
- Acesso ao PC do cliente (presencial ou AnyDesk)
- `data/cliente.json` real (nome fantasia, CNPJ, endereço, telefone)
- Senha definida pro admin do dono (não guardar no `.env`)
- Pendrive + conta Google Drive já logada no PC (opcional mas recomendado)

---

## 1. Instalar Python 3.12

1. Baixar de https://www.python.org/downloads/release/python-31210/
2. **IMPORTANTE:** no instalador marcar **"Add python.exe to PATH"** antes de "Install Now"
3. Após instalar, abrir `cmd` e confirmar:
   ```
   python --version
   ```
   Deve mostrar `Python 3.12.x`.

---

## 2. Copiar o código do PDV

Opção A — via Git (recomendado):

```powershell
cd C:\
git clone https://github.com/Gabrielhrq-ol/pdv-padaria.git
cd pdv-padaria
```

Opção B — sem Git: copiar a pasta `C:\Users\ghsol\pdv-padaria\` do seu PC
para o PC do cliente via pendrive. Colocar em `C:\pdv-padaria\`.

Verificar que a pasta tem:
```
pdv-padaria\
  app\
  alembic\
  scripts\
  start_pdv.bat
  requirements.txt
  .env.example
  ...
```

---

## 3. Criar o ambiente virtual

```powershell
cd C:\pdv-padaria
python -m venv .venv
.venv\Scripts\activate
```

O prompt deve mudar pra `(.venv) C:\pdv-padaria>`.

---

## 4. Instalar dependências

```powershell
pip install --upgrade pip
pip install -r requirements.txt
```

Vai demorar ~2 minutos. Checar que **não deu nenhum erro vermelho**. Warnings
amarelos sobre deprecação são OK.

---

## 5. Configurar `.env`

```powershell
copy .env.example .env
```

Abrir `.env` no Bloco de Notas e:

1. **Gerar SECRET_KEY nova:**
   ```powershell
   python -c "import secrets; print(secrets.token_urlsafe(32))"
   ```
   Copiar a string gerada e substituir `change-me-generate-with-python-secrets`
   em `SECRET_KEY=`.

2. **Mudar ENVIRONMENT:**
   ```
   ENVIRONMENT=production
   ```
   (Em produção, `/docs` e `/redoc` ficam desligados.)

3. Deixar o resto como está: `DB_PATH=./data/pdv.db`, `HOST=127.0.0.1`, `PORT=8000`.

Salvar e fechar.

---

## 6. Criar a estrutura do banco

```powershell
python -m alembic upgrade head
```

Deve criar `data/pdv.db` com todas as tabelas da Fase 1 à 9. Última mensagem
esperada: `Running upgrade ... -> d0b3bdd9d9e8, fase7 cash_sessions e cash_movements`.

---

## 7. Preencher dados confidenciais do cliente

1. Criar o arquivo `data/cliente.json` (ignorado pelo Git):

   ```json
   {
     "nome_fantasia": "Padaria do Zé",
     "cnpj": "00.000.000/0001-00",
     "endereco": "Rua X, 123 — Bairro Y — Araraquara/SP",
     "telefone": "(16) 90000-0000",
     "mensagem_rodape_cupom": "Obrigado e volte sempre!"
   }
   ```

2. Rodar o seed:
   ```powershell
   python scripts\seed_cliente.py
   ```
   O script lê o JSON e popula os settings do banco.

> **Importante:** `data/` está no `.gitignore`. **Nunca** commitar
> `cliente.json`.

---

## 8. Criar o admin do dono

```powershell
python scripts\create_admin.py
```

Vai perguntar nome, username e senha (não ecoa). Regras:
- Senha mínima 8 chars, com ao menos 1 letra e 1 número
- Username só `A-Z a-z 0-9 . _ -`
- Role = `admin`

**Dica:** anotar a senha em um lugar físico seguro. Perder significa precisar
rodar o script de novo (que cria outro user) e desativar o anterior.

---

## 9. (Opcional) Criar o operador caixa

Se o dono quiser um segundo usuário sem permissões de admin:

```powershell
python scripts\create_admin.py
```

Ao perguntar o papel, responder `caixa` em vez de `admin`.

---

## 10. (Opcional) Importar produtos de um CSV

Se o cliente já tem a lista de produtos em planilha:

1. Salvar como CSV com separador `;` e encoding UTF-8
2. Colunas esperadas: `name`, `barcode`, `internal_code`, `category`, `unit`,
   `price` (ou `price_cents`), `cost`, `stock`, `min_stock`
3. Rodar:
   ```powershell
   python scripts\import_products.py --dry-run data\produtos.csv
   ```
4. Se o dry-run estiver OK, repetir sem `--dry-run`:
   ```powershell
   python scripts\import_products.py data\produtos.csv
   ```

Ver `docs/IMPORTACAO-CSV.md` pra detalhes do formato.

---

## 11. Configurar backup externo

**Preparar as pastas:**
- Pendrive: criar `E:\pdv-backups\` (adaptar a letra ao pendrive do cliente)
- Google Drive: na pasta do Google Drive Desktop no PC, criar
  `C:\Users\<dono>\My Drive\pdv-backups\`

**No sistema:** abrir `http://127.0.0.1:8000/admin/backup` após login do admin:
1. Preencher `backup_dir_1` com `E:\pdv-backups`
2. Preencher `backup_dir_2` com `C:\Users\<dono>\My Drive\pdv-backups`
3. `backup_keep` = 30 (mantém 30 últimos)
4. **Deixar marcado** "Backup automático ao fechar caixa"
5. Deixar marcado "Comprimir (.db.gz)"
6. **Clicar "Fazer backup agora"** para validar que os destinos funcionam

---

## 12. Agendar backup diário via Task Scheduler

Mesmo com o hook no fechamento de caixa, agendar um backup diário às 23:30
como seguro adicional (caso o dono esqueça de fechar o caixa em um dia).

1. Abrir **"Agendador de Tarefas"** no Windows
2. Criar Tarefa Básica → nome: `PDV Backup Diário`
3. Disparador: Diariamente, 23:30
4. Ação: `Iniciar um programa`
   - Programa/script: `C:\pdv-padaria\.venv\Scripts\python.exe`
   - Argumentos: `scripts\do_backup.py --quiet`
   - Iniciar em: `C:\pdv-padaria`
5. Em "Condições" **desmarcar** "Iniciar a tarefa somente se o computador
   estiver na rede ligada" (precisa rodar mesmo sem internet)
6. Salvar

Alternativa via linha de comando (admin):
```powershell
schtasks /create /tn "PDV Backup Diario" /tr "C:\pdv-padaria\.venv\Scripts\python.exe C:\pdv-padaria\scripts\do_backup.py --quiet" /sc daily /st 23:30 /rl HIGHEST
```

**Validar:** rodar manualmente a tarefa pelo Task Scheduler e conferir
que o arquivo aparece nas duas pastas.

---

## 13. Criar atalho do PDV no desktop

1. Botão direito no desktop → Novo → Atalho
2. Localização: `C:\pdv-padaria\start_pdv.bat`
3. Nome: `PDV`
4. (Opcional) Botão direito no atalho → Propriedades → Alterar ícone
5. Testar: duplo-clique. Deve abrir uma janela cmd preta e, 3 segundos
   depois, o navegador em `http://127.0.0.1:8000`

---

## 14. Teste de impressora (quando POS-5890U-L estiver instalada)

> **Status 2026-10-16:** aguardando teste real via AnyDesk — ESC/POS da
> POS-5890U-L **não confirmado**. Até lá, deixar o backend em `dummy`.

Quando chegar a hora:

1. Instalar o driver da POS-5890U-L no Windows
2. Em "Impressoras e scanners", anotar o **nome exato** da impressora (ex: `POS-58 Printer`)
3. No PDV, logar como admin → `/admin/printer`
4. Trocar backend para `win32raw`
5. Preencher o nome exato
6. Clicar "Imprimir cupom de teste"
7. Testar acentos (pão, café, ação). Se vier errado, trocar codepage pra
   `CP850` → `CP858` → `CP860` nessa ordem
8. Se a impressora tiver guilhotina, marcar "corte automático"

---

## 15. Validação final

Rodar o checklist em `docs/CHECKLIST-TESTES-MANUAIS.md`.
**Não entregar sem checar todos os itens.**

---

## Troubleshooting rápido

**"Python não é reconhecido"**
→ Reinstalar Python marcando "Add to PATH". Reiniciar o cmd.

**`alembic.command.ERROR: Can't locate revision...`**
→ Deletar `data/pdv.db` e rodar `alembic upgrade head` de novo (**só** se
não houver dados de produção ainda).

**`SECRET_KEY nao pode estar vazia`**
→ O `.env` não foi editado. Gerar nova chave (passo 5).

**Browser abre mas dá erro de conexão**
→ Esperar mais 5 segundos (uvicorn demora pra iniciar).
→ Checar logs no cmd. Se tiver "Address already in use", já tem um PDV
rodando — fechar a janela cmd antiga.

**Firewall do Windows bloqueia**
→ Como o servidor é `127.0.0.1`, o firewall não deve interferir. Se
pedir permissão, negar "Rede pública" e aceitar "Rede privada".
