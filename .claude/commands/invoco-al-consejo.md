---
description: Lanza al Consejo en un panel terminal nuevo de VSCode con animación TUI
---

Convoca al Consejo de los 7 Sabios para debatir cómo mejorar el proyecto
actualmente abierto en VSCode. Tema hardcodeado, sin prompts.

## Cómo funciona

El consejo necesita correr en un terminal real para que la animación TUI
(rich + rich_pixels) se renderice. Este chat NO es un terminal real, así
que disparamos una VSCode task vía su URL handler — eso abre un panel
terminal nuevo en VSC con la animación corriendo en directo.

## Lánzalo así

Ejecuta este Bash (NO en background — es solo para abrir el panel; el
debate corre dentro de VSC):

```bash
code --open-url 'cursor://command/workbench.action.tasks.runTask?args=%5B%22Consejo%3A%20mejorar%20este%20proyecto%20(auto)%22%5D'
```

(Si tu IDE es VSCode en vez de Cursor, cambia `cursor://` por `vscode://`.)

Esto le pide al IDE que ejecute la task **"Consejo: mejorar este
proyecto (auto)"** definida en `.vscode/tasks.json`, que a su vez:
- Abre un panel terminal nuevo en VSC (`presentation.panel: "new"`)
- Corre `python -m consejo.cli "¿Cómo mejoramos este proyecto?" --mode
  claude-code --consensus --consensus-rounds 20 --cc-model opus --speed 0.3`
- La animación TUI corre en ese panel
- El reporte se genera al final en `${workspaceFolder}/consejo-report-*.md`

## Después del comando

1. Confirma al usuario que el panel debería haberse abierto. Si no
   apareció, posibles causas:
   - VSCode no está abierto sobre `d:\consejo-7-sabios` → pide que lo abra
   - El URL handler de `code://` no está registrado → fallback: dile que
     use Ctrl+Shift+P → "Tasks: Run Task" → la misma task
2. Dile que el debate tardará ~30-60 min con Opus + consenso conversacional.
3. Cuando termine, el reporte queda en cwd; si el usuario quiere que lo
   leas y resumas, ofrécelo.

## NO hagas

- NO lances el python directamente con Bash + run_in_background aquí: la
  animación NO se renderiza en este chat (es lo que el usuario quiere
  evitar). El propósito de este slash command es disparar VSC, no
  ejecutar el debate dentro del chat.
- NO modifiques código del proyecto durante esta invocación.
