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
echo  Una sola ventana: arriba la animacion, abajo el debate en vivo.
echo.

REM Una ventana de Windows Terminal con panel dividido: animacion arriba,
REM watcher en vivo abajo (35%%). Render fluido, sin el flicker del cmd legacy.
REM Si no esta wt.exe, cae a dos ventanas cmd separadas.
where wt.exe >nul 2>nul && goto :wt
goto :fallback

:wt
wt.exe new-tab --title "Consejo" cmd /k "%~dp0_run-debate.bat" ; split-pane -H --size 0.35 cmd /k "%~dp0watch-debate.bat"
goto :eof

:fallback
echo  [aviso] Windows Terminal no encontrado: uso dos ventanas cmd (la animacion parpadea).
start "Consejo - debate en vivo" cmd /c "%~dp0watch-debate.bat"
start "Consejo - debate" cmd /k "%~dp0_run-debate.bat"
goto :eof
