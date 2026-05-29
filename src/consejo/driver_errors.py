"""Structured driver-boundary errors raised by SageDriver implementations.

Catching `DriverError` lets callers distinguish driver failures from
domain/logic errors without resorting to RuntimeError string matching.
These are backend-agnostic — both ClaudeCodeBackend and CodexBackend
raise them so the orchestrator handles failures uniformly.
"""

from __future__ import annotations


class DriverError(Exception):
    """Base class for errors raised at the Claude-CLI subprocess boundary.

    Catching `DriverError` lets callers distinguish driver failures from
    domain/logic errors without resorting to RuntimeError string matching.
    """


class DriverCLINotFoundError(DriverError):
    def __init__(self) -> None:
        super().__init__(
            "`claude` CLI not found on PATH. Install Claude Code to use this mode."
        )


class DriverTimeoutError(DriverError):
    def __init__(self, timeout_s: float) -> None:
        self.timeout_s = timeout_s
        super().__init__(f"claude CLI timed out after {timeout_s}s")


class DriverProcessError(DriverError):
    def __init__(self, returncode: int, stderr_head: str,
                 stdout_head: str, stderr_len: int, stdout_len: int) -> None:
        self.returncode = returncode
        self.stderr_head = stderr_head
        self.stdout_head = stdout_head
        rc_signed = returncode - 2**32 if returncode > 2**31 else returncode
        diag = (f"returncode={returncode} (signed={rc_signed}) "
                f"stderr_len={stderr_len} stdout_len={stdout_len}")
        super().__init__(
            f"claude CLI failed: {diag}\n"
            f"--stderr--\n{stderr_head}\n"
            f"--stdout_head--\n{stdout_head}"
        )


class DriverInvalidResponseError(DriverError):
    def __init__(self, response_head: str, kind: str = "wrapper") -> None:
        self.response_head = response_head
        self.kind = kind  # "wrapper" (CLI envelope) | "inner" (sage payload)
        label = ("claude CLI returned non-JSON"
                 if kind == "wrapper"
                 else "sage returned non-JSON inner text")
        super().__init__(f"{label}: {response_head}")


class DriverEmptyResultError(DriverError):
    def __init__(self, wrapper: dict) -> None:
        self.wrapper = wrapper
        super().__init__(f"claude CLI returned empty result: {wrapper}")

