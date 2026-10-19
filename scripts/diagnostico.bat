@echo off
REM =============================================================
REM  DIAGNOSTICO PDV JOAO & MARIA
REM
REM  Rode SEMPRE que der problema no sistema.
REM  Gera um arquivo diagnostico-DATA-HORA.txt no desktop.
REM  Manda esse arquivo pelo WhatsApp pro Gabriel ((16) XXXXX-XXXX).
REM =============================================================

setlocal enabledelayedexpansion

REM Timestamp pro nome do arquivo
for /f "tokens=1-3 delims=/" %%a in ("%date%") do (
    set DIA=%%a
    set MES=%%b
    set ANO=%%c
)
for /f "tokens=1-2 delims=:" %%a in ("%time%") do (
    set HH=%%a
    set MM=%%b
)
set HH=%HH: =0%
set TS=%ANO%-%MES%-%DIA%_%HH%h%MM%

set OUT=%USERPROFILE%\Desktop\diagnostico-%TS%.txt
if not exist "%USERPROFILE%\Desktop" set OUT=%USERPROFILE%\OneDrive\Desktop\diagnostico-%TS%.txt

cd /d "%~dp0..\"

echo Gerando diagnostico em %OUT% ...
echo.

(
    echo ================================================================
    echo  DIAGNOSTICO PDV JOAO ^& MARIA
    echo  Data/Hora: %date% %time%
    echo ================================================================
    echo.
    echo [1] Sistema
    echo ----------------------------------------------------------------
    ver
    systeminfo 2>nul | findstr /B /C:"OS Name" /C:"OS Version" /C:"System Model" /C:"Total Physical Memory"
    echo.

    echo [2] Python
    echo ----------------------------------------------------------------
    where python
    python --version 2>^&1
    echo.

    echo [3] Projeto
    echo ----------------------------------------------------------------
    echo Pasta: %cd%
    if exist ".venv\Scripts\python.exe" (
        echo venv: OK
    ) else (
        echo venv: FALTANDO ^(.venv nao existe^)
    )
    if exist "data\pdv.db" (
        echo Banco: OK
        for %%a in ("data\pdv.db") do echo Tamanho do banco: %%~za bytes
    ) else (
        echo Banco: FALTANDO
    )
    if exist ".env" (echo .env: OK) else (echo .env: FALTANDO)
    if exist "data\cliente.json" (echo cliente.json: OK) else (echo cliente.json: FALTANDO)
    echo.

    echo [4] Versao do codigo
    echo ----------------------------------------------------------------
    if exist ".git" (
        git log -1 --oneline 2>nul
        git branch --show-current 2>nul
    ) else (
        echo .git nao existe. Instalacao via kit nao versionada.
    )
    echo.

    echo [5] Migracoes do banco
    echo ----------------------------------------------------------------
    if exist ".venv\Scripts\python.exe" (
        .venv\Scripts\python -m alembic current 2>^&1
    ) else (
        echo venv ausente, nao posso verificar.
    )
    echo.

    echo [6] Servidor em execucao?
    echo ----------------------------------------------------------------
    netstat -ano 2>nul | findstr ":8000"
    tasklist 2>nul | findstr /i python
    echo.

    echo [7] Backups recentes
    echo ----------------------------------------------------------------
    if exist ".venv\Scripts\python.exe" (
        .venv\Scripts\python -c "import sqlite3; c=sqlite3.connect('data/pdv.db'); r=c.execute(\"SELECT value FROM settings WHERE key='backup_dir_1'\").fetchone(); print('dir1:', r[0] if r else 'nao configurado')" 2>nul
        .venv\Scripts\python -c "import sqlite3; c=sqlite3.connect('data/pdv.db'); r=c.execute(\"SELECT value FROM settings WHERE key='backup_dir_2'\").fetchone(); print('dir2:', r[0] if r else 'nao configurado')" 2>nul
        .venv\Scripts\python -c "import sqlite3; c=sqlite3.connect('data/pdv.db'); r=c.execute(\"SELECT created_at, action, details FROM audit_log WHERE action LIKE 'backup%%' ORDER BY created_at DESC LIMIT 5\").fetchall(); [print(x) for x in r]" 2>nul
    )
    echo.

    echo [8] Caixa aberto?
    echo ----------------------------------------------------------------
    if exist ".venv\Scripts\python.exe" (
        .venv\Scripts\python -c "import sqlite3; c=sqlite3.connect('data/pdv.db'); r=c.execute(\"SELECT id, opened_at, opened_by FROM cash_sessions WHERE status='open'\").fetchall(); print('abertos:', r if r else 'NENHUM')" 2>nul
    )
    echo.

    echo [9] Usuarios ativos
    echo ----------------------------------------------------------------
    if exist ".venv\Scripts\python.exe" (
        .venv\Scripts\python -c "import sqlite3; c=sqlite3.connect('data/pdv.db'); r=c.execute(\"SELECT username, role, active FROM users ORDER BY username\").fetchall(); [print(x) for x in r]" 2>nul
    )
    echo.

    echo [10] Impressora
    echo ----------------------------------------------------------------
    if exist ".venv\Scripts\python.exe" (
        .venv\Scripts\python -c "import sqlite3; c=sqlite3.connect('data/pdv.db'); r=c.execute(\"SELECT key, value FROM settings WHERE key LIKE 'printer_%%'\").fetchall(); [print(x) for x in r]" 2>nul
    )
    echo.

    echo [11] Ultimas 50 linhas do log
    echo ----------------------------------------------------------------
    if exist "logs\pdv.log" (
        powershell -NoProfile -Command "Get-Content 'logs\pdv.log' -Tail 50"
    ) else (
        echo logs\pdv.log nao existe.
    )
    echo.

    echo [12] Teste de resposta do servidor
    echo ----------------------------------------------------------------
    powershell -NoProfile -Command "try { $r = Invoke-WebRequest -UseBasicParsing -TimeoutSec 3 http://127.0.0.1:8000/health; Write-Host 'HTTP' $r.StatusCode $r.Content } catch { Write-Host 'Servidor nao respondeu em 3s. Pode nao estar rodando.' }"
    echo.

    echo [13] Erros recentes no Windows Event Viewer ^(ultimos 5^)
    echo ----------------------------------------------------------------
    powershell -NoProfile -Command "Get-EventLog -LogName Application -EntryType Error -Newest 5 2>$null | Select-Object TimeGenerated, Source, Message | Format-List"

    echo.
    echo ================================================================
    echo  FIM DO DIAGNOSTICO
    echo ================================================================
) > "%OUT%" 2>&1

echo.
echo [OK] Diagnostico salvo em:
echo       %OUT%
echo.
echo PROXIMO PASSO:
echo   1. Abre o Explorer no Desktop
echo   2. Encontra o arquivo: diagnostico-%TS%.txt
echo   3. Manda esse arquivo pelo WhatsApp pro Gabriel
echo.
pause
