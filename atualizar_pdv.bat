@echo off
REM =====================================================================
REM  ATUALIZAR PDV - wrapper facil pro atalho de desktop
REM
REM  Dupla-clica aqui ou use via AnyDesk pra atualizar sem precisar git.
REM  Baixa o codigo mais recente do GitHub e aplica sobre a instalacao.
REM =====================================================================

cd /d "%~dp0"

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\atualizar.ps1"

if errorlevel 1 (
    echo.
    echo A atualizacao falhou. Veja a mensagem acima.
    pause
    exit /b 1
)
