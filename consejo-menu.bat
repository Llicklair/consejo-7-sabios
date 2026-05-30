@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

REM ============================================================
REM  Menu lanzador del Consejo de los 7 Sabios.
REM  Abre un selector de carpeta de Windows y convoca al consejo
REM  sobre el repositorio elegido (reusa consejo.bat = 2 panes).
REM ============================================================

echo.
echo  Consejo de los 7 Sabios
echo  -----------------------
echo  Elige en el dialogo la carpeta del repo a debatir...
echo.

REM Selector nativo "Examinar carpeta". Capturamos la ruta via archivo
REM temporal (mas fiable que for /f con PowerShell multilinea).
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

REM quita comillas/espacios y barra final sobrante
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

echo.
echo  Convocando al Consejo...
echo.
call "%~dp0consejo.bat" "%REPO%"

endlocal
