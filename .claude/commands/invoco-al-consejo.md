---
description: Lanza al Consejo en el panel terminal de VSCode (envía Ctrl+Shift+B vía SendKeys)
---

Convoca al Consejo de los 7 Sabios sobre el proyecto actualmente abierto
en VSCode. Tema hardcodeado, sin prompts.

## Cómo lo lanzo

El sandbox Bash de Claude Code en Windows PUEDE enviar keystrokes a la
ventana activa vía PowerShell SendKeys. En `%APPDATA%\Code\User\
keybindings.json` está atada **`Ctrl+Shift+B`** a la task user-level
**"Consejo: debatir el workspace abierto"** (en `%APPDATA%\Code\User\
tasks.json`), que invoca consejo con `--repo "${workspaceFolder}"` —
funciona en CUALQUIER proyecto que tengas abierto en VSCode. Opus,
--consensus, min 5 rondas, max 20, animación TUI. Enviar `^+b` (=
Ctrl+Shift+B en notación SendKeys) dispara el debate en el panel terminal
del workspace actual.

Ejecuta exactamente este Bash:

```bash
powershell -Command "Add-Type -AssemblyName System.Windows.Forms; Start-Sleep -Milliseconds 300; [System.Windows.Forms.SendKeys]::SendWait('^+b')"
```

## Antes de lanzar

Avisa al usuario en una línea: "Voy a enviar Ctrl+Shift+B — asegúrate de
que VSCode está en foco (haz click en la ventana si dudas). Te aviso
cuando lo lance."

Después del bash, confirma: "Enviado. Si VSCode estaba en foco deberías
ver el panel terminal con la animación TUI del debate. Si no, haz click
en VSCode y vuelve a pedirme /invoco-al-consejo."

## Después

El debate tarda ~30-60 min con Opus + consenso. Cuando termine, el
reporte queda en `consejo-report-*.md` en cwd. Si el usuario quiere,
puedes leerlo y resumir plan + visión.

## Limitación

SendKeys envía a la ventana en foreground. Si el usuario tiene otra app
en foco (no VSCode), el keystroke se lo come esa app y la task no se
dispara. No hay forma fiable desde el sandbox de targetear una ventana
específica — depende del foco del usuario.
