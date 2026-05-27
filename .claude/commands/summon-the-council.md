---
description: Launches the Council in VSCode's terminal panel (sends Ctrl+Shift+B via SendKeys)
---

Summon the Council of Seven Sages to debate the currently open VSCode
project. Topic hardcoded, no prompts.

## How I launch it

Claude Code's Bash sandbox on Windows CAN send keystrokes to the active
window via PowerShell SendKeys. The default build task in VSCode is
**"Consejo: mejorar este proyecto (auto)"** (with `--consensus`, opus,
20-round cap, TUI animation), bound to `Ctrl+Shift+B`. So sending `^+b`
fires the debate inside VSCode's terminal panel.

Run exactly this Bash:

```bash
powershell -Command "Add-Type -AssemblyName System.Windows.Forms; Start-Sleep -Milliseconds 300; [System.Windows.Forms.SendKeys]::SendWait('^+b')"
```

## Before launching

Tell the user in one line: "I'm going to send Ctrl+Shift+B — make sure
VSCode is focused (click on the window if unsure). I'll confirm once
sent."

After the bash, confirm: "Sent. If VSCode was focused you should see the
terminal panel with the TUI animation of the debate. If not, click on
VSCode and ask me /summon-the-council again."

## After

The debate takes ~30-60 min with Opus + consensus. When done, the report
is at `consejo-report-*.md` in cwd. If the user wants, you can read and
summarize plan + vision.

## Limitation

SendKeys sends to the foreground window. If the user has another app in
focus (not VSCode), the keystroke is consumed there and the task does
not fire. There's no reliable way from the sandbox to target a specific
window — depends on user focus.
