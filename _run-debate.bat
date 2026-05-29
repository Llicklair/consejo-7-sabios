@echo off
chcp 65001 >nul
REM Corre el debate sobre el repo = directorio ACTUAL (lo fija wt -d "%REPO%").
REM Usa el python/consejo del TOOL (%~dp0), no del repo debatido.
set "PYTHONPATH=%~dp0src"

echo  Consejo en curso sobre: %CD%
echo  El plan ira a consejo-report-*.md (en esta carpeta). Cierra para abortar.
echo.

"%~dp0.venv\Scripts\python.exe" -m consejo.cli "¿Cómo mejoramos este proyecto?" --repo "%CD%" --mode claude-code --consensus --consensus-rounds 8 --consensus-min-rounds 5 --cc-model opus --speed 0.3

echo.
echo  Consejo finalizado. Plan:
dir /b /o-d consejo-report-*.md 2>nul
echo.
echo  Pulsa una tecla para cerrar.
pause >nul
