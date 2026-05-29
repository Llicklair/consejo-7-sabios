"""ClaudeCodeBackend — adapter around the existing `_spawn_claude` flow.

This is a thin wrapper, not a code move. The original `_spawn_claude` in
`claude_code_driver.py` (and its quirks: `--json-schema` retry,
DriverError mapping, _build_claude_args) stays put — we just expose it
through the `SageDriver` protocol so the orchestrator can be backend-agnostic.

A future refactor can pull the implementation in here; doing so now would
fight git diff readability for no functional gain.
"""

from __future__ import annotations

from pathlib import Path

from .. import claude_code_driver as _ccd


class ClaudeCodeBackend:
    name = "claude-code"

    def available(self) -> bool:
        return _ccd.claude_available()

    async def spawn(
        self,
        *,
        user_msg: str,
        system_prompt: str,
        schema: dict,
        repo: Path,
        model: str,
        allowed_tools: str = "Read,Glob,Grep",
        timeout_s: float = 300.0,
    ) -> dict:
        return await _ccd._spawn_claude(
            user_msg=user_msg,
            system_prompt=system_prompt,
            schema=schema,
            repo=repo,
            model=model,
            allowed_tools=allowed_tools,
            timeout_s=timeout_s,
        )
