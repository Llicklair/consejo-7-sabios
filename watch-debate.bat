@echo off
REM Sigue en vivo el debate del Consejo mas reciente, formateado.
REM Doble clic, o ejecuta: watch-debate.bat
REM Esquiva la execution policy con -ExecutionPolicy Bypass.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0watch-debate.ps1"
pause
