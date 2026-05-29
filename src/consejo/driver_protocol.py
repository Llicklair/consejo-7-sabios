"""Backend-agnostic driver protocol for the council.

Each sage turn ultimately becomes a `driver.spawn(...)` call. The driver
encapsulates the subprocess CLI quirks of a specific backend (Claude Code,
Codex, future others). Callers only see normalized JSON output and a small
set of `DriverError` subclasses defined in `claude_code_driver`.

The orchestrator builds one driver per session (`build_backend(...)`) and
passes it EXPLICITLY to `propose_one_sage` / `critique_one_sage` /
`judge_synthesis` / `consensus_dialogue` / `post_consensus_vision`. There is
no module-global active driver: the dependency is visible at every call site,
so a test or a second session can inject its own driver without mutating
shared state.
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable


@runtime_checkable
class SageDriver(Protocol):
    name: str

    def available(self) -> bool:
        ...

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
        ...
