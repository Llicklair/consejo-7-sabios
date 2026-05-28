"""Opt-in instrumentation for measuring token consumption during real debates.

The 20260527-183832 council report left this hilo de investigación open:

    "What is the actual token consumption distribution across sages and
    rounds in a real (non-mock) debate, and where do the budget blowouts
    happen? Items 1 and 4 set static caps based on worst-case math. The
    cap values should be evidence-based, not theoretical."

This module is the cheapest possible instrumentation that answers that
question. When `CONSEJO_METRICS=1` is set, every interesting boundary call
(subprocess spawn, scan, briefing build) appends a timestamped record to
an in-process list, and an `atexit` handler dumps the list to a JSON file
next to the report.

Default: disabled, zero overhead — `record()` returns immediately when the
env var isn't set. No imports leak, no files created.

To enable for one debate:
    CONSEJO_METRICS=1 python -m consejo ...

Output file: `consejo-metrics-<unix-timestamp>.json` in CWD.
"""

from __future__ import annotations

import atexit
import json
import os
import time
from pathlib import Path
from typing import Any

_ENABLED: bool = os.environ.get("CONSEJO_METRICS") == "1"
_START_TIME: float = time.time()
_RECORDS: list[dict[str, Any]] = []
_REGISTERED: bool = False


def is_enabled() -> bool:
    """True if metrics collection is on for this process."""
    return _ENABLED


def record(kind: str, **fields: Any) -> None:
    """Append a metrics record. No-op when disabled.

    `kind` is a short label ("subprocess", "scan", "briefing"). Extra
    fields are stored verbatim — keep them small and JSON-serializable.
    """
    if not _ENABLED:
        return
    _RECORDS.append({
        "t": round(time.time() - _START_TIME, 3),
        "kind": kind,
        **fields,
    })
    global _REGISTERED
    if not _REGISTERED:
        atexit.register(_dump)
        _REGISTERED = True


def snapshot() -> list[dict[str, Any]]:
    """Return a copy of the in-memory records. Used by tests."""
    return list(_RECORDS)


def reset_for_tests() -> None:
    """Clear records and unregister atexit. Test-only."""
    global _REGISTERED
    _RECORDS.clear()
    _REGISTERED = False


def _dump_path() -> Path:
    return Path.cwd() / f"consejo-metrics-{int(_START_TIME)}.json"


def _dump() -> None:
    if not _RECORDS:
        return
    try:
        _dump_path().write_text(
            json.dumps({
                "started_at_unix": int(_START_TIME),
                "records": _RECORDS,
            }, indent=2),
            encoding="utf-8",
        )
    except OSError:
        pass
