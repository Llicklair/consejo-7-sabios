---
description: Opens a new VSCode terminal panel running the Council with TUI animation
---

Summon the Council of Seven Sages to debate how to improve the currently
open VSCode project. Topic is hardcoded; no prompts.

## How it works

The council needs a real terminal so the TUI animation (rich + rich_pixels)
renders. This chat is NOT a real terminal, so we fire a VSCode task via
its URL handler — that opens a new terminal panel inside VSC with the
animation running live.

## Launch like this

Run this Bash (NOT in background — it's just for opening the panel; the
debate runs inside VSC):

```bash
code --open-url 'cursor://command/workbench.action.tasks.runTask?args=%5B%22Consejo%3A%20mejorar%20este%20proyecto%20(auto)%22%5D'
```

(If your IDE is VSCode instead of Cursor, swap `cursor://` for `vscode://`.)

This asks the IDE to run the task **"Consejo: mejorar este proyecto
(auto)"** defined in `.vscode/tasks.json`, which:
- Opens a new terminal panel in VSC (`presentation.panel: "new"`)
- Runs `python -m consejo.cli "¿Cómo mejoramos este proyecto?" --mode
  claude-code --consensus --consensus-rounds 20 --cc-model opus --speed 0.3`
- The TUI animation runs in that panel
- Report is written to `${workspaceFolder}/consejo-report-*.md` at end

## After the command

1. Confirm to the user that the panel should have opened. If it didn't:
   - VSCode isn't open on `d:\consejo-7-sabios` → ask them to open it
   - The `code://` URL handler isn't registered → fallback: tell them to
     use Ctrl+Shift+P → "Tasks: Run Task" → the same task
2. Mention the debate will take ~30-60 min with Opus + consensus dialogue.
3. When it finishes the report is in cwd; if the user wants you to read
   and summarize it, offer.

## DO NOT

- DO NOT run python directly via Bash + run_in_background here: the
  animation does NOT render in this chat (that's what the user is trying
  to avoid). The point of this slash command is to fire VSC, not to run
  the debate inside the chat.
- DO NOT modify project code during this invocation.
