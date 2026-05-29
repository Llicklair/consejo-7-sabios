@echo off
chcp 65001 >nul
cd /d "%~dp0"
set PYTHONPATH=src

if not exist ".venv\Scripts\python.exe" (
    echo.
    echo [ERROR] No encuentro .venv\Scripts\python.exe
    echo.
    echo Crea el venv primero:
    echo     python -m venv .venv
    echo     .venv\Scripts\pip install -e .
    echo.
    pause
    exit /b 1
)

echo.
echo  Convocando al Consejo de los 7 Sabios
echo  -------------------------------------
echo  Tema:    Como mejoramos este proyecto?
echo  Modo:    claude-code . consenso . opus
echo  Rondas:  min 5, max 8 (duracion esperada ~30-60 min)
echo  Schema:  OFF (los sabios leen el repo de verdad)
echo  En vivo: se abre otra ventana con el debate formateado
echo.

REM Abre una ventana aparte que sigue el debate en vivo (espera al .jsonl)
start "Consejo - debate en vivo" cmd /c "%~dp0watch-debate.bat"

.venv\Scripts\python.exe -m consejo.cli "¿Cómo mejoramos este proyecto?" --mode claude-code --consensus --consensus-rounds 8 --consensus-min-rounds 5 --cc-model opus --speed 0.3

echo.
echo  Consejo finalizado. El plan esta en consejo-report-*.md (este directorio).
dir /b /o-d consejo-report-*.md 2>nul
echo.
echo  Pulsa una tecla para cerrar.
pause >nul
