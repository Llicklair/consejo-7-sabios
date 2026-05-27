@echo off
chcp 65001 >nul
echo.
echo  Lanzando Consejo de los 7 Sabios en VSCode...
echo  (debate consensus, opus, ~30-60 min, animacion TUI)
echo.
echo  Si VSCode no responde, abre VSCode sobre d:\consejo-7-sabios
echo  y pulsa Ctrl+Shift+B como fallback.
echo.

start "" "vscode://command/workbench.action.tasks.runTask?args=%%5B%%22Consejo%%3A%%20mejorar%%20este%%20proyecto%%20(auto)%%22%%5D"

timeout /t 3 >nul
exit
