---
description: Lanza al Consejo en el panel terminal de VSCode (envía Ctrl+Shift+B vía SendKeys)
---

Convoca al Consejo de los 7 Sabios sobre el proyecto actualmente abierto
en VSCode. Tema hardcodeado, sin prompts.

## Cómo lo lanzo

El sandbox Bash de Claude Code en Windows PUEDE enviar keystrokes a la
ventana activa vía PowerShell SendKeys. La task default build de VSCode
es **"Consejo: mejorar este proyecto (auto)"** (con `--consensus`, opus,
20 rondas cap, animación TUI), atada a `Ctrl+Shift+B`. Por tanto enviar
`^+b` dispara el debate dentro del panel terminal de VSCode.

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
