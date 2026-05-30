@echo off
chcp 65001 >nul
REM Corre el debate sobre el repo = directorio ACTUAL (lo fija wt -d "%REPO%").
REM Usa el python/consejo del TOOL (%~dp0), no del repo debatido.
set "PYTHONPATH=%~dp0src"

echo  Consejo en curso sobre: %CD%
echo  El plan ira a consejo-report-*.md (en esta carpeta). Cierra para abortar.
echo.

REM Convergencia: si los 6 sabios firman el mismo plan, el debate PARA (a partir
REM de la ronda 2 — la ronda 1 tiene la firma suprimida, es solo proponer). Si no
REM hay unanimidad, sigue hasta el techo de 8 rondas. min=2 evita las rondas
REM muertas que forzaba min=8 (firmaban en la r3 y daban vueltas en vacio hasta la 8).
"%~dp0.venv\Scripts\python.exe" -m consejo.cli "¿Cómo mejoramos este proyecto?" --repo "%CD%" --mode claude-code --consensus --consensus-rounds 8 --consensus-min-rounds 2 --cc-model opus --speed 0.3

echo.
echo  Consejo finalizado. Plan:
dir /b /o-d consejo-report-*.md 2>nul
echo.
echo  Pulsa una tecla para cerrar.
pause >nul
