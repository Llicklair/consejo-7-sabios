---
description: Opens a new IDE terminal panel running the Council with TUI animation
---

Summon the Council of Seven Sages to debate the currently open project.
Topic hardcoded, no prompts.

## Known technical limitation

Claude Code's Bash sandbox on Windows CANNOT:
- Spawn detached processes (new terminal windows)
- Fire URL handlers (`vscode://`, `cursor://`)
- Execute IDE commands programmatically

Verified with `Start-Process notepad` → fails with the classic
"InvalidOperationException" of a non-interactive session.

So this slash command does NOT execute anything for you — it only shows
the button/shortcut so YOU fire the task with a keystroke or click.

## What to show the user

Print exactly this block (do NOT run any Bash):

> 🔮 **Launch the debate from your IDE:**
>
> **Option A (1 keystroke):** press `Ctrl+Shift+B` — it's set as the
> default build task: `Consejo: mejorar este proyecto (auto)`.
>
> **Option B (click):** click this link:
> [▶ Run the Council (consensus, opus, ~30-60 min)](command:workbench.action.tasks.runTask?%5B%22Consejo%3A%20mejorar%20este%20proyecto%20(auto)%22%5D)
>
> **Option C (manual):** `Ctrl+Shift+P` → "Tasks: Run Task" → "Consejo:
> mejorar este proyecto (auto)".
>
> Either opens a new terminal panel in the IDE with the TUI animation
> running the turn-by-turn consensus debate (Opus, 20-round cap, topic
> "¿Cómo mejoramos este proyecto?"). It will take ~30-60 min. When done,
> the report is at `consejo-report-*.md`.

## After

When the user says they're done (or after the wait), if they want, read
the latest report and summarize plan + vision.

## DO NOT

- DO NOT try `code --open-url`, `start`, `Start-Process` or similar —
  they all fail in this sandbox.
- DO NOT run the python in background here (animation does not render in chat).
- DO NOT modify project code during this invocation.
