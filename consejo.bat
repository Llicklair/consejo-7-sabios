@echo off
chcp 65001 >nul

REM Repo a debatir: argumento %1 (el workspace abierto) o, si no, esta carpeta.
set "REPO=%~1"
if "%REPO%"=="" set "REPO=%~dp0"
REM quita la barra final para que -d "...\" no rompa el parseo de wt.exe
if "%REPO:~-1%"=="\" set "REPO=%REPO:~0,-1%"

if not exist "%~dp0.venv\Scripts\python.exe" (
    echo [ERROR] No encuentro "%~dp0.venv\Scripts\python.exe"
    pause
    exit /b 1
)

echo.
echo  Convocando al Consejo de los 7 Sabios
echo  Repo: %REPO%
echo  Una sola ventana: animacion arriba, debate en vivo abajo.
echo.

where wt.exe >nul 2>nul && goto :wt
goto :fallback

:wt
wt.exe new-tab -d "%REPO%" --title "Consejo" cmd /k "%~dp0_run-debate.bat" ; split-pane -H --size 0.35 -d "%REPO%" cmd /k "%~dp0watch-debate.bat"
goto :eof

:fallback
echo  [aviso] Windows Terminal no encontrado: dos ventanas cmd (la animacion parpadea).
start "Consejo - en vivo" /D "%REPO%" cmd /c "%~dp0watch-debate.bat"
start "Consejo - debate" /D "%REPO%" cmd /k "%~dp0_run-debate.bat"
goto :eof
