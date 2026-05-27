"""State machine data — enum, event dataclass, and tuning constants.

This module is the *data* layer of the state machine. The asyncio bus
(`EventBus`, `Publisher` contract) lives in `consejo.bus`; the mock
driver lives in `consejo.drivers.mock`. EventBus and Publisher are
re-exported here for backward compatibility with existing imports.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class State(StrEnum):
    ENTRANDO = "entrando"
    SENTANDOSE = "sentandose"
    ANALIZANDO = "analizando"
    DEBATE = "debate"
    JUEZ = "juez"
    ACUERDO = "acuerdo"
    LEVANTANDOSE = "levantandose"
    SALIENDO = "saliendo"
    REPORTE = "reporte"


@dataclass(frozen=True)
class StateEvent:
    state: State
    round_num: int = 0          # significativo sólo en DEBATE (1..N)
    sage_id: str | None = None
    payload: dict = field(default_factory=dict)


# Duración por defecto de cada estado (en segundos a velocidad 1x)
DEFAULT_TIMINGS: dict[State, float] = {
    State.ENTRANDO: 4.0,
    State.SENTANDOSE: 1.5,
    State.ANALIZANDO: 6.0,
    State.DEBATE: 3.5,           # por ronda
    State.JUEZ: 3.0,
    State.ACUERDO: 2.0,
    State.LEVANTANDOSE: 1.5,
    State.SALIENDO: 4.0,
    State.REPORTE: 2.0,
}

DEFAULT_DEBATE_ROUNDS = 3
MAX_DEBATE_ROUNDS = 30


def _reexport_bus():
    """Lazy re-export to avoid a top-level circular import (bus imports
    State/StateEvent from this module)."""
    from .bus import EventBus, Publisher  # noqa: F401
    return EventBus, Publisher


def __getattr__(name: str):
    """Backward-compat shim: `from consejo.states import EventBus` still works."""
    if name in ("EventBus", "Publisher"):
        EventBus, Publisher = _reexport_bus()
        return EventBus if name == "EventBus" else Publisher
    if name == "mock_driver":
        from .drivers.mock import mock_driver
        return mock_driver
    raise AttributeError(f"module 'consejo.states' has no attribute {name!r}")
