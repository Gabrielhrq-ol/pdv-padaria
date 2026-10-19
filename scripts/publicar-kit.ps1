# ============================================================================
#  REBUILD + REPUBLICAR O KIT NO GITHUB RELEASE
# ----------------------------------------------------------------------------
#  Rode SEMPRE que mexer no codigo e quiser que o one-liner remoto baixe
#  a versao nova. Ex: depois de qualquer git push importante.
#
#  Uso (PowerShell qualquer, nao precisa admin):
#     cd C:\Users\ghsol\pdv-padaria
#     .\scripts\publicar-kit.ps1
#
#  O que faz:
#   1. Confere git status (precisa estar limpo + sincronizado com origin)
#   2. Copia codigo atual pra C:\Users\ghsol\pdv-padaria-kit\pdv-padaria\
#   3. Baixa wheels de prod + dev de novo (pra pegar deps atualizadas)
#   4. Gera ZIP novo em C:\Users\ghsol\pdv-padaria-kit.zip
#   5. Deleta Release antigo no GitHub e cria novo com o ZIP
#   6. Imprime o one-liner atualizado pra voce copiar
# ============================================================================

$ErrorActionPreference = 'Stop'
$REPO_DIR = "C:\Users\ghsol\pdv-padaria"
$KIT_DIR = "C:\Users\ghsol\pdv-padaria-kit"
$ZIP_FILE = "C:\Users\ghsol\pdv-padaria-kit.zip"

function Write-Step {
    param([string]$msg)
    Write-Host ""
    Write-Host "================================================================" -ForegroundColor Cyan
    Write-Host "  $msg" -ForegroundColor Cyan
    Write-Host "================================================================" -ForegroundColor Cyan
}

# ----------------------------------------------------------------------------
# 1. git status
# ----------------------------------------------------------------------------
Write-Step "1/6  Checando git status"

Set-Location $REPO_DIR
$status = git status --porcelain
if ($status) {
    Write-Host "AVISO: existem mudancas nao commitadas:" -ForegroundColor Yellow
    git status --short
    Write-Host ""
    Write-Host "Faz git commit + git push ANTES de publicar o kit." -ForegroundColor Yellow
    Write-Host "Senao o kit vai ter codigo diferente do GitHub." -ForegroundColor Yellow
    Write-Host ""
    $r = Read-Host "Continuar mesmo assim? [s/N]"
    if ($r -ne 's') { exit 1 }
}

# ----------------------------------------------------------------------------
# 2. Copiar codigo atualizado
# ----------------------------------------------------------------------------
Write-Step "2/6  Atualizando kit com codigo atual"

$kitPdv = Join-Path $KIT_DIR "pdv-padaria"
if (Test-Path $kitPdv) {
    # Preserva .venv do kit se existir (so pra teste local, nao vai no ZIP)
    Remove-Item -Recurse -Force (Join-Path $kitPdv "app") -ErrorAction SilentlyContinue
    Remove-Item -Recurse -Force (Join-Path $kitPdv "alembic") -ErrorAction SilentlyContinue
    Remove-Item -Recurse -Force (Join-Path $kitPdv "scripts") -ErrorAction SilentlyContinue
    Remove-Item -Recurse -Force (Join-Path $kitPdv "docs") -ErrorAction SilentlyContinue
    Remove-Item -Recurse -Force (Join-Path $kitPdv "tests") -ErrorAction SilentlyContinue
}

Copy-Item -Recurse "$REPO_DIR\app" $kitPdv
Copy-Item -Recurse "$REPO_DIR\alembic" $kitPdv
Copy-Item -Recurse "$REPO_DIR\scripts" $kitPdv
Copy-Item -Recurse "$REPO_DIR\docs" $kitPdv
Copy-Item -Recurse "$REPO_DIR\tests" $kitPdv
Copy-Item "$REPO_DIR\requirements.txt" $kitPdv -Force
Copy-Item "$REPO_DIR\requirements-dev.txt" $kitPdv -Force
Copy-Item "$REPO_DIR\CLAUDE.md" $kitPdv -Force
Copy-Item "$REPO_DIR\README.md" $kitPdv -Force
Copy-Item "$REPO_DIR\CHANGELOG.md" $kitPdv -Force
Copy-Item "$REPO_DIR\alembic.ini" $kitPdv -Force
Copy-Item "$REPO_DIR\pytest.ini" $kitPdv -Force
Copy-Item "$REPO_DIR\start_pdv.bat" $kitPdv -Force
Copy-Item "$REPO_DIR\.env.example" $kitPdv -Force
Copy-Item "$REPO_DIR\.gitignore" $kitPdv -Force -ErrorAction SilentlyContinue

# Limpa caches
Get-ChildItem -Path $kitPdv -Recurse -Directory -Filter "__pycache__" | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue

Write-Host "OK: codigo copiado." -ForegroundColor Green

# ----------------------------------------------------------------------------
# 3. Rebuild wheels (pega deps atualizadas se requirements mudou)
# ----------------------------------------------------------------------------
Write-Step "3/6  Rebuildando wheels"

$wheelsDir = Join-Path $KIT_DIR "wheels"
Remove-Item -Recurse -Force $wheelsDir -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Path $wheelsDir | Out-Null

& "$REPO_DIR\.venv\Scripts\python.exe" -m pip download `
    -r "$REPO_DIR\requirements.txt" `
    -d $wheelsDir `
    --platform win_amd64 `
    --python-version 312 `
    --only-binary=:all: 2>&1 | Out-Null
if ($LASTEXITCODE -ne 0) { Write-Host "ERRO ao baixar wheels de producao." -ForegroundColor Red; exit 1 }

& "$REPO_DIR\.venv\Scripts\python.exe" -m pip download `
    pytest==8.3.4 httpx==0.28.1 pip-audit==2.7.3 `
    -d $wheelsDir `
    --platform win_amd64 `
    --python-version 312 `
    --only-binary=:all: 2>&1 | Out-Null
if ($LASTEXITCODE -ne 0) { Write-Host "ERRO ao baixar wheels dev." -ForegroundColor Red; exit 1 }

$wheelCount = (Get-ChildItem $wheelsDir -Filter *.whl).Count
Write-Host "OK: $wheelCount wheels baixadas." -ForegroundColor Green

# ----------------------------------------------------------------------------
# 4. Gerar ZIP
# ----------------------------------------------------------------------------
Write-Step "4/6  Compactando kit em ZIP"

Remove-Item -Force $ZIP_FILE -ErrorAction SilentlyContinue
Compress-Archive -Path "$KIT_DIR\*" -DestinationPath $ZIP_FILE -Force
$sizeMB = [math]::Round((Get-Item $ZIP_FILE).Length / 1MB, 1)
Write-Host "OK: $ZIP_FILE ($sizeMB MB)" -ForegroundColor Green

# ----------------------------------------------------------------------------
# 5. Republicar no GitHub Release
# ----------------------------------------------------------------------------
Write-Step "5/6  Republicando no GitHub Release"

# Pergunta versao
$lastTag = git describe --tags --abbrev=0 2>$null
if (-not $lastTag) { $lastTag = "v1.0.0" }
Write-Host "Ultima versao: $lastTag"
$newTag = Read-Host "Nova versao? [v1.0.1]"
if (-not $newTag) { $newTag = "v1.0.1" }

# Deleta release antigo com mesmo tag (se existir)
gh release delete $newTag --yes 2>$null
git push origin ":refs/tags/$newTag" 2>$null

# Cria tag + release
git tag -f $newTag
git push origin $newTag --force 2>&1 | Out-Null

$notes = @"
Kit atualizado em $(Get-Date -Format 'yyyy-MM-dd HH:mm').

**Instalacao remota num comando (PowerShell admin no PC do cliente):**

``````powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force
iwr -useb https://raw.githubusercontent.com/Gabrielhrq-ol/pdv-padaria/main/scripts/instalar.ps1 | iex
``````
"@

gh release create $newTag $ZIP_FILE --title "$newTag - Kit de instalacao" --notes $notes --latest
if ($LASTEXITCODE -ne 0) { Write-Host "ERRO ao criar release." -ForegroundColor Red; exit 1 }

Write-Host "OK: release $newTag publicado." -ForegroundColor Green

# ----------------------------------------------------------------------------
# 6. Final
# ----------------------------------------------------------------------------
Write-Step "PUBLICACAO COMPLETA"

Write-Host ""
Write-Host "Release:" -ForegroundColor Green
Write-Host "  https://github.com/Gabrielhrq-ol/pdv-padaria/releases/tag/$newTag"
Write-Host ""
Write-Host "One-liner pra copiar e colar no PC do cliente:" -ForegroundColor Yellow
Write-Host ""
Write-Host "  Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force" -ForegroundColor White
Write-Host "  iwr -useb https://raw.githubusercontent.com/Gabrielhrq-ol/pdv-padaria/main/scripts/instalar.ps1 | iex" -ForegroundColor White
Write-Host ""
