---
description: Summons The Council of Seven Sages to debate a project issue
---

The user wants to summon The Council of Seven Sages. The issue is in
$ARGUMENTS (if empty, briefly ask the user what to debate or default to
"General project improvement").

## Before launching — warn the user

`claude-code --consensus` is the REAL debate (not mock):
- Spawns 9 `claude -p` subprocesses (semaphore caps at 3 concurrent)
- Round-robin turn-by-turn until unanimity or 20-round cap
- On serious issues, typically converges in ~11 rounds (~99 turns)
- Typical duration: 30-60+ minutes wall time
- Burns real tokens from the user's account; no cost cap

For trivial issues, suggest `--consensus-rounds 5` to shorten.
For serious issues, the default (20) is appropriate.

## Run the council

From `d:\consejo-7-sabios`, claude-code + consensus + headless (the
pygame animation does not render inside this chat — per-turn log lines
do show progress):

```bash
cd d:/consejo-7-sabios && PYTHONPATH=src .venv/Scripts/python.exe -m consejo.cli "$ARGUMENTS" --mode claude-code --consensus --consensus-rounds 20 --cc-model sonnet --no-ui
```

**Launch in background** (`run_in_background: true` on Bash) and arm a
Monitor on the log to report per-turn progress without blocking. Useful
event filter:

```
tail -F <log-path> 2>/dev/null | grep -E --line-buffered "turn [0-9]+ . r[0-9]|Consenso|reporte:|RuntimeError"
```

## After completion

1. Find the most recent `consejo-report-*.md` generated in cwd.
2. Read it and show the user:
   - Executive summary
   - Prioritized plan table
   - Strategic vision (headline + 1 paragraph of `where_to_take_it`)
   - Unresolved disagreements if any
3. Ask the user if they want to:
   a) Auto-execute SAFE tasks (`--execute auto`)
   b) Re-run with Opus for deeper synthesis (`--cc-model opus`)
   c) Adjust the issue or rounds

DO NOT modify project code during this invocation — the council only
proposes and reports. Execution is opt-in via step 3a.

If the command fails (e.g. venv missing, `claude` CLI not on PATH),
inform the user and suggest the appropriate fix.

## If the user wants the animation

Tell them that instead of the slash command they can use the VSCode task
"Consejo: invocar (claude-code, CONSENSUS conversacional)" (Ctrl+Shift+P
→ Tasks: Run Task) — that opens a new terminal panel in VSC with the TUI
animation running live during the debate.
