"""Event-bus producers: each driver pushes a sequence of StateEvents.

The mock driver is purely visual (canned sequence). The real council
driver lives in `consejo.orchestrator.run_council`. The claude-code
driver lives in `consejo.claude_code_driver`.
"""

from .mock import mock_driver

__all__ = ["mock_driver"]
