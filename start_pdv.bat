@echo off
REM =====================================================================
REM  PDV Padaria - script de start do dia
REM
REM  O que faz:
REM   1. Ativa o ambiente virtual (.venv)
REM   2. Roda migracoes de banco (idempotente - nao faz nada se ja esta ok)
REM   3. Inicia o servidor local em 127.0.0.1:8000
REM   4. Abre o navegador no PDV
REM
REM  Instalacao (uma unica vez, pelo instalador):
REM   - Criar atalho no desktop apontando pra este arquivo
REM   - (Opcional) Agendar backup diario via Task Scheduler, apontando pra
REM     scripts\do_backup.py (ver docs\INSTALACAO.md na Fase 10)
REM
REM  Operacao diaria do caixa:
REM   - Dar duplo-clique no atalho "PDV" do desktop
REM   - Esperar o navegador abrir e fazer login
REM   - No fim do dia: fechar o caixa pela tela /caixa, depois pode fechar
REM     esta janela com Ctrl+C ou com o botao X
REM =====================================================================

cd /d "%~dp0"

echo.
echo === PDV Padaria ===
echo Diretorio: %cd%
echo.

if not exist ".venv\Scripts\python.exe" (
    echo ERRO: ambiente virtual .venv nao encontrado em %cd%.
    echo Rode a instalacao primeiro.
    pause
    exit /b 1
)

echo [1/3] Ativando ambiente virtual...
call ".venv\Scripts\activate.bat"
if errorlevel 1 (
    echo ERRO ao ativar o venv.
    pause
    exit /b 1
)

echo [2/3] Atualizando banco de dados...
python -m alembic upgrade head
if errorlevel 1 (
    echo ERRO: falha na migracao do banco. Verifique logs\pdv.log.
    pause
    exit /b 1
)

echo [3/3] Iniciando servidor em http://127.0.0.1:8000 ...
echo.
echo    Para encerrar: feche esta janela ou aperte Ctrl+C
echo.

REM Abre o navegador em paralelo (espera 3s pro servidor subir)
start "" cmd /c "timeout /t 3 /nobreak >nul && start http://127.0.0.1:8000"

python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
