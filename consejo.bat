@echo off
chcp 65001 >nul
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo.
    echo [ERROR] No encuentro .venv\Scripts\python.exe
    echo Crea el venv:  python -m venv .venv  ^&^&  .venv\Scripts\pip install -e .
    echo.
    pause
    exit /b 1
)

echo.
echo  Convocando al Consejo de los 7 Sabios
echo  -------------------------------------
echo  Se abren DOS ventanas: el debate (animado) y el watcher en vivo.
echo.

REM Ventana del watcher: sigue el debate formateado, turno a turno.
start "Consejo - debate en vivo" cmd /c "%~dp0watch-debate.bat"

REM El debate (con animacion) corre en Windows Terminal -> render fluido,
REM sin el parpadeo del cmd.exe legacy. Si no esta wt.exe, cae a cmd normal.
where wt.exe >nul 2>nul
if %errorlevel%==0 (
    wt.exe --title "Consejo" cmd /k "%~dp0_run-debate.bat"
) else (
    echo  [aviso] Windows Terminal no encontrado: uso cmd (la animacion parpadea).
    start "Consejo - debate" cmd /k "%~dp0_run-debate.bat"
)
