@echo off
chcp 65001 >nul
REM Lanza el Consejo sobre el directorio ACTUAL (no el del repo del consejo).
REM Copia este .bat en la raiz de cualquier proyecto Python/cualquiera y
REM dobla-click — el consejo debatira ese proyecto.
REM
REM Requiere consejo instalado en su venv original:
REM   d:\consejo-7-sabios\.venv\Scripts\consejo.exe
REM (si moviste el repo, edita CONSEJO_EXE abajo)

set CONSEJO_EXE=d:\consejo-7-sabios\.venv\Scripts\consejo.exe

if not exist "%CONSEJO_EXE%" (
    echo.
    echo [ERROR] No encuentro %CONSEJO_EXE%
    echo.
    echo Edita CONSEJO_EXE en este .bat con la ruta correcta del consejo.
    echo.
    pause
    exit /b 1
)

set "TEMA=%~1"
if "%TEMA%"=="" set "TEMA=¿Cómo mejoramos este proyecto?"

echo.
echo  Convocando al Consejo de los 7 Sabios
echo  --------------------------------------
echo  Tema:    %TEMA%
echo  Repo:    %CD%
echo  Modo:    claude-code . consenso . opus
echo  Rondas:  min 5, max 20 (duracion 60-120 min)
echo.

"%CONSEJO_EXE%" "%TEMA%" --repo "%CD%" --mode claude-code --consensus --consensus-rounds 20 --consensus-min-rounds 5 --cc-model opus --speed 0.3

echo.
echo  Consejo finalizado. Pulsa una tecla para cerrar.
pause >nul
