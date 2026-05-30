@echo off
chcp 65001 >nul
REM ============================================================
REM  Consejo de los 7 Sabios — lanzador unico.
REM
REM  Doble-click: abre un selector de carpeta y convoca al consejo
REM  sobre el repo elegido, en Windows Terminal con 2 paneles
REM  (debate arriba, vista en vivo abajo via watch-debate.ps1).
REM
REM  Modo interno "run": este mismo .bat se re-invoca a si mismo como
REM  comando del panel de debate (`consejo-menu.bat run`). Pasar el
REM  comando por RUTA en vez de inline esquiva el quoting de wt.exe
REM  — por eso no hace falta un _run-debate.bat aparte.
REM ============================================================

REM --- Dispatch: modo "run" (lo invoca el panel de wt, CWD = repo diana) ---
if /I "%~1"=="run" goto :run

setlocal enabledelayedexpansion

REM Repo como argumento (Ctrl+Shift+B / linea de comandos) -> directo, sin picker.
set "REPO=%~1"
if defined REPO goto :launch

echo.
echo  Consejo de los 7 Sabios
echo  -----------------------
echo  Elige en el dialogo la carpeta del repo a debatir...
echo.

REM Selector nativo "Examinar carpeta". Captura la ruta via archivo temporal.
set "PSF=%TEMP%\consejo_pick_%RANDOM%.txt"
del "%PSF%" 2>nul

powershell -NoProfile -STA -Command "Add-Type -AssemblyName System.Windows.Forms; $f = New-Object System.Windows.Forms.FolderBrowserDialog; $f.Description = 'Elige el repositorio que debatira el Consejo'; $f.ShowNewFolderButton = $false; $f.SelectedPath = [Environment]::GetFolderPath('Desktop'); if ($f.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) { Set-Content -LiteralPath '%PSF%' -Value $f.SelectedPath -Encoding UTF8 }"

set "REPO="
if exist "%PSF%" set /p REPO=<"%PSF%"
del "%PSF%" 2>nul

if not defined REPO (
    echo  Cancelado: no se eligio ninguna carpeta.
    echo.
    pause
    exit /b 0
)

REM quita comillas y barra final sobrante
set "REPO=%REPO:"=%"
if "%REPO:~-1%"=="\" set "REPO=%REPO:~0,-1%"

if not exist "%REPO%\" (
    echo  [ERROR] La carpeta no existe: %REPO%
    pause
    exit /b 1
)

echo.
echo  Repo elegido:  %REPO%
echo.
choice /C SN /N /M "  Convocar al Consejo sobre este repo? [S/N] "
if errorlevel 2 (
    echo  Cancelado.
    exit /b 0
)

:launch
REM Normaliza y valida el repo (venga del picker o del argumento).
set "REPO=%REPO:"=%"
if "%REPO:~-1%"=="\" set "REPO=%REPO:~0,-1%"
if not exist "%REPO%\" (
    echo  [ERROR] La carpeta no existe: %REPO%
    pause
    exit /b 1
)

echo.
echo  Convocando al Consejo sobre: %REPO%
echo.

REM Lanza 2 paneles. El panel de debate re-invoca este .bat en modo "run"
REM (por ruta, sin comillas anidadas -> esquiva el quoting de wt.exe).
where wt.exe >nul 2>nul && goto :wt
goto :fallback

:wt
wt.exe new-tab -d "%REPO%" --title "Consejo" cmd /k call "%~dp0consejo-menu.bat" run ; split-pane -H --size 0.35 -d "%REPO%" powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0watch-debate.ps1"
endlocal & goto :eof

:fallback
echo  [aviso] Windows Terminal no encontrado: dos ventanas cmd (la animacion parpadea).
start "Consejo - en vivo" /D "%REPO%" powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0watch-debate.ps1"
start "Consejo - debate" /D "%REPO%" cmd /k call "%~dp0consejo-menu.bat" run
endlocal & goto :eof

REM ============================================================
REM  Modo "run": ejecuta el debate sobre el directorio ACTUAL
REM  (lo fija wt -d "%REPO%"). Usa el python/consejo del TOOL (%~dp0),
REM  no el del repo debatido.
REM ============================================================
:run
set "PYTHONPATH=%~dp0src"

echo  Consejo en curso sobre: %CD%
echo  El plan ira a consejo-report-*.md (en esta carpeta). Cierra para abortar.
echo.

REM Convergencia: si los 6 sabios firman el mismo plan, el debate PARA (desde la
REM ronda 2; la 1 tiene la firma suprimida). Si no, sigue hasta el techo de 8.
"%~dp0.venv\Scripts\python.exe" -m consejo.cli "¿Cómo mejoramos este proyecto?" --repo "%CD%" --mode claude-code --consensus --consensus-rounds 8 --consensus-min-rounds 2 --cc-model opus --speed 0.3

echo.
echo  Consejo finalizado. Plan:
dir /b /o-d consejo-report-*.md 2>nul
echo.
echo  Pulsa una tecla para cerrar.
pause >nul
goto :eof
