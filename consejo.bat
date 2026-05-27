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
echo  Rondas:  hasta 20 (duracion esperada 30-60 min)
echo.

.venv\Scripts\python.exe -m consejo.cli "¿Cómo mejoramos este proyecto?" --mode claude-code --consensus --consensus-rounds 20 --cc-model opus --speed 0.3

echo.
echo  Consejo finalizado. Pulsa una tecla para cerrar.
pause >nul
