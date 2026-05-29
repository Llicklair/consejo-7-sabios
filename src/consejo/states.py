"""State machine data — enum, event dataclass, and tuning constants.

This module is the *data* layer of the state machine. The asyncio bus
(`EventBus`, `Publisher` contract) lives in `consejo.bus`; the mock
animation driver lives in `consejo.animation_drivers.mock`. EventBus
and Publisher are re-exported here for backward compatibility with
existing imports.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class State(StrEnum):
    """Fases del ciclo de un consejo, emitidas como `StateEvent` en el bus.

    Forma del `payload` (dict del StateEvent) por estado:

    - ``ENTRANDO`` / ``SENTANDOSE`` / ``ANALIZANDO``: ``{}`` — sin payload
      (beats puros de animación).
    - ``DEBATE``: snapshot de voto/orador del turno. Siempre incluye::

          signed_this_round: list[int]  # asientos que firmaron en este turno/ronda
          total_signed:      list[int]  # todos los asientos firmados ahora mismo

      En modo consenso añade además::

          turn: int            # nº de turno global
          speaker: str         # sage_id del que habla
          speaker_idx: int     # asiento del orador (-1 si es voice-only/off-table)
          plan_size: int       # nº de items en el plan actual
          voice_only: bool      # True si el orador no ocupa asiento

      ``round_num`` del StateEvent es la ronda 1..N (solo significativo aquí).
    - ``JUEZ`` / ``ACUERDO`` / ``LEVANTANDOSE`` / ``SALIENDO``: ``{}`` — sin payload.
    - ``REPORTE``: ``{"plan": dict}`` — el plan final (forma que consume
      ``render_plan_markdown``); en modo demo puede traer ``report_path``.
    """
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
    """Una transición de estado en el bus de animación.

    `payload` depende del estado — ver `State` para la forma que lleva cada uno.
    `round_num` solo es significativo en DEBATE (1..N); 0 en el resto.
    """
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
        from .animation_drivers.mock import mock_driver
        return mock_driver
    raise AttributeError(f"module 'consejo.states' has no attribute {name!r}")
