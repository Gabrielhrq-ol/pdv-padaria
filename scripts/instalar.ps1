# ============================================================================
#  INSTALADOR REMOTO - PDV Joao & Maria
# ----------------------------------------------------------------------------
#  Baixa Python 3.12 (se precisar), baixa o kit do GitHub Release, extrai
#  e roda a instalacao offline em sequencia.
#
#  Uso no PC do cliente (PowerShell como ADMINISTRADOR):
#
#     Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force
#     iwr -useb https://raw.githubusercontent.com/Gabrielhrq-ol/pdv-padaria/main/scripts/instalar.ps1 | iex
#
#  O que faz:
#   1. Confere Python 3.12. Se nao tiver, baixa instalador oficial e roda
#      silenciosamente com PATH ativado.
#   2. Baixa pdv-padaria-kit.zip do GitHub Release mais recente.
#   3. Extrai em C:\pdv-padaria-kit\.
#   4. Executa os scripts 02 a 05 em sequencia (venv, deps offline,
#      .env, migrations).
#   5. Para antes dos interativos (06-criar-admin, 07-seed-cliente,
#      09-atalho, 10-task-scheduler) - Gabriel + cliente conduzem via
#      AnyDesk.
# ============================================================================

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'Continue'

$REPO = "Gabrielhrq-ol/pdv-padaria"
$KIT_URL = "https://github.com/$REPO/releases/latest/download/pdv-padaria-kit.zip"
$KIT_DEST = "C:\pdv-padaria-kit"
$KIT_ZIP = "$env:TEMP\pdv-padaria-kit.zip"
$PY_URL = "https://www.python.org/ftp/python/3.12.10/python-3.12.10-amd64.exe"
$PY_INSTALLER = "$env:TEMP\python-3.12.10-amd64.exe"

function Write-Step {
    param([string]$msg)
    Write-Host ""
    Write-Host "================================================================" -ForegroundColor Cyan
    Write-Host "  $msg" -ForegroundColor Cyan
    Write-Host "================================================================" -ForegroundColor Cyan
}

function Test-Admin {
    $id = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal $id
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

if (-not (Test-Admin)) {
    Write-Host "ERRO: este script precisa de PowerShell COMO ADMINISTRADOR." -ForegroundColor Red
    Write-Host "Feche, abra PowerShell com clique direito -> Executar como admin." -ForegroundColor Red
    exit 1
}

# ----------------------------------------------------------------------------
# 1. Python 3.12
# ----------------------------------------------------------------------------
Write-Step "1/5  Verificando Python 3.12"

$pyOk = $false
try {
    $v = & python --version 2>&1
    if ($v -match 'Python 3\.12\.') {
        Write-Host "OK: $v ja instalado." -ForegroundColor Green
        $pyOk = $true
    } else {
        Write-Host "Python encontrado mas nao e 3.12: $v" -ForegroundColor Yellow
    }
} catch {
    Write-Host "Python nao encontrado no PATH." -ForegroundColor Yellow
}

if (-not $pyOk) {
    Write-Host "Baixando Python 3.12.10 (~27MB)..." -ForegroundColor Yellow
    Invoke-WebRequest -Uri $PY_URL -OutFile $PY_INSTALLER
    Write-Host "Instalando (silencioso, com PATH)..." -ForegroundColor Yellow
    Start-Process -FilePath $PY_INSTALLER `
        -ArgumentList "/quiet", "InstallAllUsers=1", "PrependPath=1", "Include_test=0", "Include_doc=0", "Include_launcher=1" `
        -Wait -NoNewWindow
    # Atualiza o PATH da sessao atual sem reiniciar
    $env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [Environment]::GetEnvironmentVariable("Path", "User")
    try {
        $v = & python --version 2>&1
        if ($v -match 'Python 3\.12\.') {
            Write-Host "OK: Python 3.12 instalado com sucesso." -ForegroundColor Green
        } else {
            Write-Host "AVISO: Python instalado mas 'python --version' deu '$v'. Pode precisar reiniciar o PowerShell." -ForegroundColor Yellow
        }
    } catch {
        Write-Host "AVISO: Python instalado mas nao esta no PATH ainda. Feche e reabra o PowerShell." -ForegroundColor Yellow
        exit 1
    }
}

# ----------------------------------------------------------------------------
# 2. Baixar o kit do GitHub Release
# ----------------------------------------------------------------------------
Write-Step "2/5  Baixando kit (pdv-padaria-kit.zip ~27MB)"

if (Test-Path $KIT_DEST) {
    Write-Host "AVISO: $KIT_DEST ja existe. Para forcar nova instalacao," -ForegroundColor Yellow
    Write-Host "        delete essa pasta manualmente e rode de novo." -ForegroundColor Yellow
    Write-Host "        Para seguir com a existente, pressione Enter." -ForegroundColor Yellow
    Read-Host
} else {
    Invoke-WebRequest -Uri $KIT_URL -OutFile $KIT_ZIP
    Write-Host "Download OK ($([math]::Round((Get-Item $KIT_ZIP).Length / 1MB, 1)) MB)." -ForegroundColor Green
    Write-Host "Extraindo em $KIT_DEST ..." -ForegroundColor Yellow
    Expand-Archive -Path $KIT_ZIP -DestinationPath $KIT_DEST -Force
    Remove-Item $KIT_ZIP
    Write-Host "OK: kit extraido." -ForegroundColor Green
}

# ----------------------------------------------------------------------------
# 3. Criar .venv + instalar deps offline
# ----------------------------------------------------------------------------
Write-Step "3/5  Criando .venv e instalando dependencias (offline)"

Set-Location "$KIT_DEST\pdv-padaria"

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    python -m venv .venv
    if ($LASTEXITCODE -ne 0) {
        Write-Host "ERRO ao criar .venv." -ForegroundColor Red
        exit 1
    }
}

& .\.venv\Scripts\python.exe -m pip install --upgrade --no-index --find-links "$KIT_DEST\wheels" pip 2>&1 | Out-Null
& .\.venv\Scripts\python.exe -m pip install --no-index --find-links "$KIT_DEST\wheels" -r requirements.txt
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERRO: install das deps de producao falhou." -ForegroundColor Red
    exit 1
}
& .\.venv\Scripts\python.exe -m pip install --no-index --find-links "$KIT_DEST\wheels" -r requirements-dev.txt
Write-Host "OK: deps instaladas." -ForegroundColor Green

# ----------------------------------------------------------------------------
# 4. Gerar .env de producao
# ----------------------------------------------------------------------------
Write-Step "4/5  Configurando .env"

if (Test-Path ".env") {
    Write-Host "OK: .env ja existe, mantendo." -ForegroundColor Green
} else {
    $secret = & .\.venv\Scripts\python.exe -c "import secrets; print(secrets.token_urlsafe(32))"
    @"
SECRET_KEY=$secret
DB_PATH=./data/pdv.db
ENVIRONMENT=production
HOST=127.0.0.1
PORT=8000
"@ | Set-Content -Path ".env" -Encoding utf8
    Write-Host "OK: .env criado com SECRET_KEY novo." -ForegroundColor Green
}

# ----------------------------------------------------------------------------
# 5. Rodar migrations
# ----------------------------------------------------------------------------
Write-Step "5/5  Criando banco de dados"

if (-not (Test-Path "data")) { New-Item -ItemType Directory -Path "data" | Out-Null }
if (-not (Test-Path "logs")) { New-Item -ItemType Directory -Path "logs" | Out-Null }

& .\.venv\Scripts\python.exe -m alembic upgrade head
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERRO ao rodar migrations." -ForegroundColor Red
    exit 1
}
Write-Host "OK: banco criado em data\pdv.db" -ForegroundColor Green

# ----------------------------------------------------------------------------
# Final: proximos passos manuais (interativos)
# ----------------------------------------------------------------------------
Write-Step "INSTALACAO AUTOMATICA COMPLETA"

Write-Host ""
Write-Host "Proximos passos (manuais, Gabriel conduz via AnyDesk):" -ForegroundColor White
Write-Host ""
Write-Host "  A) PREENCHER DADOS DA PADARIA:" -ForegroundColor Yellow
Write-Host "     notepad $KIT_DEST\pdv-padaria\data\cliente.json.PREENCHER"
Write-Host "     (preencher CNPJ, endereco, telefone; salvar; renomear"
Write-Host "      para cliente.json tirando o .PREENCHER)"
Write-Host ""
Write-Host "  B) CRIAR ADMIN DO DONO:" -ForegroundColor Yellow
Write-Host "     cd $KIT_DEST\pdv-padaria"
Write-Host "     .\.venv\Scripts\python.exe scripts\create_admin.py"
Write-Host "     (sera pedido nome, username, senha, papel=admin)"
Write-Host ""
Write-Host "  C) CARREGAR DADOS DA PADARIA:" -ForegroundColor Yellow
Write-Host "     .\.venv\Scripts\python.exe scripts\seed_cliente.py"
Write-Host ""
Write-Host "  D) (OPCIONAL) RODAR TESTES PRA CONFIRMAR AMBIENTE:" -ForegroundColor Yellow
Write-Host "     .\.venv\Scripts\python.exe -m pytest --tb=line"
Write-Host ""
Write-Host "  E) CRIAR ATALHO NO DESKTOP:" -ForegroundColor Yellow
Write-Host "     $KIT_DEST\scripts-instalacao\09-criar-atalho-desktop.bat"
Write-Host ""
Write-Host "  F) (OPCIONAL) AGENDAR BACKUP DIARIO 23:30:" -ForegroundColor Yellow
Write-Host "     $KIT_DEST\scripts-instalacao\10-task-scheduler-backup.bat"
Write-Host ""
Write-Host "Pra INICIAR o PDV agora pra testar:" -ForegroundColor Green
Write-Host "     $KIT_DEST\pdv-padaria\start_pdv.bat"
Write-Host ""
