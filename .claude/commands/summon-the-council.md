---
description: Summons The Council of Seven Sages to debate a project issue
---

The user wants to summon The Council of Seven Sages. The issue is in
$ARGUMENTS (if empty, briefly ask the user what to debate or default to
"General project improvement").

Run the council in mock + headless mode from `d:\consejo-7-sabios`:

```bash
cd d:/consejo-7-sabios && PYTHONPATH=src .venv/Scripts/python.exe -m consejo.cli "$ARGUMENTS" --mode mock --rounds 5 --speed 50 --no-ui
```

Then:
1. Find the most recent `consejo-report-*.md` generated in cwd
2. Read it and show the user:
   - Executive summary
   - The prioritized plan table (first 6 rows)
   - Any unresolved disagreements
3. Ask the user if they want to:
   a) Auto-execute SAFE tasks (re-run with `--execute auto`)
   b) See the full animation in terminal (re-run without `--no-ui`)
   c) Adjust rounds or atasco

DO NOT modify project code during this invocation — the council only
proposes and reports. Execution is opt-in via step 3a.

If the command fails (e.g. venv missing), inform the user and suggest
`python -m venv .venv && .venv\Scripts\pip install -e .`.
