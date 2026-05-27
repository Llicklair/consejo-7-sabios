---
description: Lanza al Consejo en un panel terminal nuevo del IDE con animación TUI
---

Convoca al Consejo de los 7 Sabios sobre el proyecto abierto. Tema
hardcodeado, sin prompts.

## Limitación técnica conocida

El sandbox Bash de Claude Code en Windows NO puede:
- Spawnear procesos detached (ventanas terminal nuevas)
- Disparar URL handlers (`vscode://`, `cursor://`)
- Ejecutar comandos del IDE programáticamente

Verificado con `Start-Process notepad` → falla con
"InvalidOperationException" típico de sesión no-interactiva.

Por eso este slash command NO ejecuta nada por ti — solo te muestra el
botón/atajo para que TÚ dispares la task con un keystroke o click.

## Lo que debes mostrar al usuario

Imprime exactamente este bloque (sin ejecutar ningún Bash):

> 🔮 **Lanza el debate desde tu IDE:**
>
> **Opción A (1 keystroke):** pulsa `Ctrl+Shift+B` — está configurada como
> default build task la `Consejo: mejorar este proyecto (auto)`.
>
> **Opción B (click):** haz click en este link:
> [▶ Ejecutar Consejo (consenso, opus, ~30-60 min)](command:workbench.action.tasks.runTask?%5B%22Consejo%3A%20mejorar%20este%20proyecto%20(auto)%22%5D)
>
> **Opción C (manual):** `Ctrl+Shift+P` → "Tasks: Run Task" → "Consejo:
> mejorar este proyecto (auto)".
>
> Cualquiera abre un panel terminal nuevo en el IDE con la animación TUI
> corriendo el debate consensus turn-by-turn (Opus, 20 rondas cap, tema
> "¿Cómo mejoramos este proyecto?"). Tardará ~30-60 min. Cuando termine,
> el reporte queda en `consejo-report-*.md`.

## Después

Cuando el usuario te diga que ya terminó (o tras el tiempo), si quiere
puedes leer el reporte más reciente y resumirle plan + visión.

## NO hagas

- NO intentes `code --open-url`, `start`, `Start-Process` o similares —
  todos fallan en este sandbox.
- NO ejecutes el python en background aquí (la animación no se ve en chat).
- NO modifiques código del proyecto durante esta invocación.
