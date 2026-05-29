@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo  Consejo en curso (opus, consenso, rondas 5-8). Cierra para abortar.
echo  El plan final ira a consejo-report-*.md
echo.

.venv\Scripts\python.exe -m consejo.cli "¿Cómo mejoramos este proyecto?" --mode claude-code --consensus --consensus-rounds 8 --consensus-min-rounds 5 --cc-model opus --speed 0.3

echo.
echo  Consejo finalizado. Plan:
dir /b /o-d consejo-report-*.md 2>nul
echo.
echo  Pulsa una tecla para cerrar.
pause >nul
