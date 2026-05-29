"""Backend drivers for the council (Claude Code, Codex, ...).

Each backend implements `consejo.driver_protocol.SageDriver` and
encapsulates the subprocess CLI quirks of a specific vendor.
"""

from .claude_code import ClaudeCodeBackend
from .codex import CodexBackend

__all__ = ["ClaudeCodeBackend", "CodexBackend"]


def build_backend(name: str):
    """Factory: return the SageDriver implementation for `name`.

    Raises ValueError for unknown names so the CLI can surface a clear
    error before the council starts.
    """
    if name == "claude-code":
        return ClaudeCodeBackend()
    if name == "codex":
        return CodexBackend()
    raise ValueError(f"Unknown backend: {name!r}. Expected 'claude-code' or 'codex'.")
