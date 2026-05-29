"""Backend-agnostic driver protocol for the council.

Each sage turn ultimately becomes a `driver.spawn(...)` call. The driver
encapsulates the subprocess CLI quirks of a specific backend (Claude Code,
Codex, future others). Callers only see normalized JSON output and a small
set of `DriverError` subclasses defined in `claude_code_driver`.

The active driver is set at orchestrator startup via `set_driver()` and
retrieved by the sage wrappers via `get_driver()`. This keeps the existing
`propose_one_sage` / `critique_one_sage` / `judge_synthesis` /
`consensus_dialogue` function signatures unchanged while letting us swap the
backend per session.
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


_active_driver: SageDriver | None = None


def set_driver(driver: SageDriver) -> None:
    global _active_driver
    _active_driver = driver


def get_driver() -> SageDriver:
    if _active_driver is None:
        raise RuntimeError(
            "No active SageDriver. Call set_driver(...) before invoking the council."
        )
    return _active_driver


def clear_driver() -> None:
    global _active_driver
    _active_driver = None
