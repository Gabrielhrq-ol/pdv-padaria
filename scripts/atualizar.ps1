# ============================================================================
#  ATUALIZAR PDV — baixa o codigo mais recente do GitHub e aplica no cliente
# ----------------------------------------------------------------------------
#  Uso (no PC do cliente):
#     Duplo clique no atalho "Atualizar PDV" do desktop
#     OU: PowerShell -> cd C:\pdv-padaria-kit\pdv-padaria -> .\scripts\atualizar.ps1
#
#  O que faz:
#   1. Baixa https://github.com/Gabrielhrq-ol/pdv-padaria/archive/refs/heads/main.zip
#   2. Extrai pra pasta temporaria
#   3. Faz backup do codigo atual (pra rollback) em pdv-padaria\_backup_YYYYMMDD
#   4. Sobrepoe app/, alembic/, scripts/, docs/, templates, static
#      PRESERVANDO: .venv, data/, logs/, .env, backups/
#   5. Roda alembic upgrade head (pega migrations novas)
#   6. Reinicia o uvicorn se estiver rodando
#
#  NAO precisa git. NAO precisa reinstalar deps (so faz isso se
#  requirements.txt mudar — nesse caso avisa).
# ============================================================================

$ErrorActionPreference = 'Stop'

$PDV_DIR = "C:\pdv-padaria-kit\pdv-padaria"
$VENV_PY = Join-Path $PDV_DIR ".venv\Scripts\python.exe"
$ZIP_URL = "https://github.com/Gabrielhrq-ol/pdv-padaria/archive/refs/heads/main.zip"
$TEMP_DIR = Join-Path $env:TEMP "pdv-update-$(Get-Date -Format 'yyyyMMddHHmmss')"
$BACKUP_SUFFIX = "_backup_$(Get-Date -Format 'yyyyMMdd_HHmm')"

function Write-Step { param([string]$msg)
    Write-Host ""
    Write-Host "================================================================" -ForegroundColor Cyan
    Write-Host "  $msg" -ForegroundColor Cyan
    Write-Host "================================================================" -ForegroundColor Cyan
}

function Write-Err { param([string]$msg)
    Write-Host "ERRO: $msg" -ForegroundColor Red
}

function Write-Ok { param([string]$msg)
    Write-Host "OK: $msg" -ForegroundColor Green
}

# ----------------------------------------------------------------------------
# Pre-checks
# ----------------------------------------------------------------------------
Write-Step "ATUALIZAR PDV — Padaria Joao & Maria"

if (-not (Test-Path $PDV_DIR)) {
    Write-Err "Pasta do PDV nao encontrada: $PDV_DIR"
    Write-Host "Ajuste a variavel PDV_DIR no topo deste script se o caminho for outro."
    Read-Host "Enter pra sair"
    exit 1
}

if (-not (Test-Path $VENV_PY)) {
    Write-Err ".venv nao encontrada. Rode a instalacao do zero antes."
    Read-Host "Enter pra sair"
    exit 1
}

# ----------------------------------------------------------------------------
# 1. Download do codigo
# ----------------------------------------------------------------------------
Write-Step "1/5  Baixando codigo mais recente do GitHub"
Write-Host "URL: $ZIP_URL"
Write-Host "Isso leva uns 10 segundos..."

New-Item -ItemType Directory -Path $TEMP_DIR | Out-Null
$zipPath = Join-Path $TEMP_DIR "main.zip"

try {
    Invoke-WebRequest -Uri $ZIP_URL -OutFile $zipPath -UseBasicParsing
} catch {
    Write-Err "Falha ao baixar: $($_.Exception.Message)"
    Write-Host "Confere se tem internet no PC."
    Read-Host "Enter pra sair"
    exit 1
}

Write-Ok "ZIP baixado ($([math]::Round((Get-Item $zipPath).Length/1KB,0)) KB)"

# ----------------------------------------------------------------------------
# 2. Extrair
# ----------------------------------------------------------------------------
Write-Step "2/5  Extraindo"

Expand-Archive -Path $zipPath -DestinationPath $TEMP_DIR -Force
$EXTRACTED = Join-Path $TEMP_DIR "pdv-padaria-main"

if (-not (Test-Path $EXTRACTED)) {
    Write-Err "Pasta extraida nao encontrada: $EXTRACTED"
    exit 1
}

Write-Ok "Extraido em $EXTRACTED"

# ----------------------------------------------------------------------------
# 3. Backup do estado atual (pra rollback)
# ----------------------------------------------------------------------------
Write-Step "3/5  Backup do codigo atual (pra rollback se der problema)"

$backupDir = Join-Path (Split-Path $PDV_DIR -Parent) "pdv-padaria$BACKUP_SUFFIX"
# Copia so o codigo (nao .venv, data, logs, backups)
$FOLDERS_TO_BACKUP = @('app', 'alembic', 'scripts', 'docs')
$FILES_TO_BACKUP = @('requirements.txt', 'requirements-dev.txt', 'alembic.ini',
                     'pytest.ini', 'CLAUDE.md', 'README.md', 'CHANGELOG.md',
                     'AVISOS-ENTREGA.md', 'start_pdv.bat', 'abrir_pdv.vbs')

New-Item -ItemType Directory -Path $backupDir | Out-Null
foreach ($folder in $FOLDERS_TO_BACKUP) {
    $src = Join-Path $PDV_DIR $folder
    if (Test-Path $src) {
        Copy-Item -Recurse -Force $src $backupDir
    }
}
foreach ($file in $FILES_TO_BACKUP) {
    $src = Join-Path $PDV_DIR $file
    if (Test-Path $src) {
        Copy-Item -Force $src $backupDir
    }
}

Write-Ok "Backup em $backupDir"
Write-Host "Se der problema, restaure com: Copy-Item -Recurse -Force '$backupDir\*' '$PDV_DIR\'"

# ----------------------------------------------------------------------------
# 4. Checa se requirements mudou (precisa reinstalar deps)
# ----------------------------------------------------------------------------
Write-Step "4/5  Aplicando codigo novo"

$oldReq = Join-Path $PDV_DIR "requirements.txt"
$newReq = Join-Path $EXTRACTED "requirements.txt"
$reqChanged = $false

if ((Test-Path $oldReq) -and (Test-Path $newReq)) {
    $oldHash = (Get-FileHash $oldReq -Algorithm SHA256).Hash
    $newHash = (Get-FileHash $newReq -Algorithm SHA256).Hash
    if ($oldHash -ne $newHash) {
        $reqChanged = $true
    }
}

# Mata uvicorn se estiver rodando (vamos atualizar codigo)
$pdvProc = Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue
if ($pdvProc) {
    Write-Host "Parando PDV (porta 8000)..." -ForegroundColor Yellow
    Stop-Process -Id $pdvProc.OwningProcess -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 1
}

# Sobrepoe codigo
foreach ($folder in $FOLDERS_TO_BACKUP) {
    $src = Join-Path $EXTRACTED $folder
    $dst = Join-Path $PDV_DIR $folder
    if (Test-Path $src) {
        # Remove destino antigo pra garantir que arquivos deletados tambem saiam
        if (Test-Path $dst) { Remove-Item -Recurse -Force $dst }
        Copy-Item -Recurse -Force $src $dst
    }
}
foreach ($file in $FILES_TO_BACKUP) {
    $src = Join-Path $EXTRACTED $file
    $dst = Join-Path $PDV_DIR $file
    if (Test-Path $src) {
        Copy-Item -Force $src $dst
    }
}

Write-Ok "Codigo atualizado"

if ($reqChanged) {
    Write-Host ""
    Write-Host "ATENCAO: requirements.txt mudou. Reinstalando dependencias..." -ForegroundColor Yellow
    & $VENV_PY -m pip install --upgrade -r (Join-Path $PDV_DIR "requirements.txt") 2>&1 | Tee-Object -Variable pipOut | Out-Null
    if ($LASTEXITCODE -ne 0) {
        Write-Err "Falha ao reinstalar deps. Rollback com o backup em $backupDir"
        Write-Host $pipOut
        exit 1
    }
    Write-Ok "Dependencias atualizadas"
}

# ----------------------------------------------------------------------------
# 5. Migrations
# ----------------------------------------------------------------------------
Write-Step "5/5  Aplicando migrations do banco"

Push-Location $PDV_DIR
try {
    & $VENV_PY -m alembic upgrade head 2>&1 | ForEach-Object { Write-Host $_ }
    if ($LASTEXITCODE -ne 0) {
        Write-Err "Alembic falhou. Rollback com o backup em $backupDir"
        exit 1
    }
} finally {
    Pop-Location
}

Write-Ok "Migrations aplicadas"

# ----------------------------------------------------------------------------
# Final
# ----------------------------------------------------------------------------
Write-Step "ATUALIZACAO COMPLETA"

Write-Host ""
Write-Host "O PDV foi atualizado. Pra abrir, use o atalho PDV do desktop." -ForegroundColor Green
Write-Host "Backup do codigo anterior em: $backupDir" -ForegroundColor Gray
Write-Host ""
Write-Host "Se algo der errado:" -ForegroundColor Yellow
Write-Host "  Copy-Item -Recurse -Force '$backupDir\*' '$PDV_DIR\'"
Write-Host ""

# Limpa temp
Remove-Item -Recurse -Force $TEMP_DIR -ErrorAction SilentlyContinue

Read-Host "Enter pra fechar"
