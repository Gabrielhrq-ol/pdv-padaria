# Manutenção remota — PDV João & Maria

Como atualizar o PDV e dar suporte sem precisar visita presencial.

## O setup

- **No PC do cliente:** AnyDesk instalado + PDV rodando
- **No notebook do Gabriel:** AnyDesk + Claude Code
- **GitHub público:** `github.com/Gabrielhrq-ol/pdv-padaria`

## Fluxo de atualização (sem precisar git no cliente)

Quando eu faço mudanças no código aqui e dou `git push`, pra chegar
no cliente:

### Via AnyDesk (recomendado)

1. Entro no PC do cliente via AnyDesk
2. Abro o Explorer em `C:\pdv-padaria-kit\pdv-padaria\`
3. Duplo-clique em **`atualizar_pdv.bat`**
4. O script faz tudo em ~15 segundos:
   - Baixa `main.zip` do GitHub (~2 MB)
   - Faz backup do código atual
   - Sobrepõe `app/`, `alembic/`, `scripts/`, `docs/`
   - Preserva: `.venv`, `data/`, `logs/`, `.env`, `backups/`
   - Roda `alembic upgrade head` (migrations novas)
   - Reinicia o uvicorn se estava rodando

### Alternativa: PowerShell direto

```powershell
cd C:\pdv-padaria-kit\pdv-padaria
.\scripts\atualizar.ps1
```

### Se o `requirements.txt` mudar

O script detecta e roda `pip install --upgrade -r requirements.txt`
automaticamente. **Precisa de internet** nesse caso. Avisa antes.

### Rollback (se algo quebrar)

O script cria um backup antes de aplicar em
`C:\pdv-padaria-kit\pdv-padaria_backup_YYYYMMDD_HHMM`. Pra reverter:

```powershell
Copy-Item -Recurse -Force "C:\pdv-padaria-kit\pdv-padaria_backup_YYYYMMDD_HHMM\*" "C:\pdv-padaria-kit\pdv-padaria\"
```

## Fluxo de suporte

### Cliente reporta um problema no WhatsApp

1. **Peço um print** da tela ou do erro
2. **Se não resolver remoto:** entro via AnyDesk
3. **Investigo pelos logs:**
   ```powershell
   Get-Content C:\pdv-padaria-kit\pdv-padaria\logs\pdv.log -Tail 50
   ```
4. **Audit log pela UI:** admin → Auditoria (filtros por data, operador, ação)
5. **Se eu precisar diagnosticar com código:**
   - Abro Claude Code no PC do cliente, em `C:\pdv-padaria-kit\pdv-padaria\`
   - Peço pra ler `AVISOS-ENTREGA.md` + log + descrevo o problema
6. **Se achar bug:** corrijo aqui no meu PC, pusho, no PC do cliente rodo `atualizar_pdv.bat`

### Backup trimestral (defensivo)

A cada 3 meses, entro via AnyDesk e baixo os `.db.gz` do cliente pra
minha pasta local:

```powershell
# No PC do cliente, via AnyDesk File Transfer ou copiando pelo clipboard
$dest = "C:\Users\dono\My Drive\pdv-backups"
Get-ChildItem $dest -Filter "*.db.gz" | Sort-Object LastWriteTime -Descending | Select-Object -First 1
```

Guardo pra garantir que se o Google Drive do cliente também pifar,
tenho uma cópia recente.

## Ciclo típico de deploy

```
Mudança aqui (notebook Gabriel)
  ↓
Edito código
  ↓
pytest (confirmar que passa)
  ↓
git commit + git push origin main
  ↓
AnyDesk → PC do cliente
  ↓
Duplo-clique em atualizar_pdv.bat
  ↓
Atualização aplicada em ~15 segundos
  ↓
Teste rápido no PDV lá
```

## O que NÃO atualiza automaticamente

- `data/cliente.json` (dados do negócio — intocado)
- `data/pdv.db` (banco de produção — intocado)
- `.env` (SECRET_KEY e configs locais — intocado)
- `backups/` (histórico de backups — intocado)
- `.venv/` (ambiente virtual — intocado, salvo se requirements mudar)

## O que o cliente precisa saber

Nada. Pra ele, o PDV simplesmente "ficou melhor" entre uma visita e outra.
Se precisar reiniciar, basta fechar o atalho PDV e abrir de novo.
