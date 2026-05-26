"""Máquina de estados y bus de eventos del Consejo (v2 — rondas dinámicas).

Cambios respecto a v1:
- Nuevo estado `ANALIZANDO` (después de SENTANDOSE, antes del debate)
- `DEBATE` es ahora un solo estado con `round_num` dinámico (1..N)
- `JUEZ` se interpreta como momento de síntesis tras todas las rondas
- Cap duro: 30 rondas. Si las supera el orquestador real, el umbral de
  firmas baja: 7/7 (default) → 6/7 → 5/7 → aborta. (No implementado aún
  en el mock — sólo configura el número de rondas a emitir.)
"""

from __future__ import annotations

import argparse
import asyncio
from dataclasses import dataclass, field
from enum import StrEnum
from typing import AsyncIterator, Callable


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

DEFAULT_DEBATE_ROUNDS = 3        # cuántas rondas emite el mock por defecto
MAX_DEBATE_ROUNDS = 30           # cap duro antes del fallback de umbral


class EventBus:
    """Cola asíncrona. Un productor, uno o más consumidores secuenciales."""

    def __init__(self) -> None:
        self._queue: asyncio.Queue[StateEvent] = asyncio.Queue()
        self._closed = False

    async def publish(self, event: StateEvent) -> None:
        await self._queue.put(event)

    async def consume(self) -> AsyncIterator[StateEvent]:
        while True:
            event = await self._queue.get()
            yield event
            if event.state == State.REPORTE:
                self._closed = True
                return

    @property
    def closed(self) -> bool:
        return self._closed


async def mock_driver(
    bus: EventBus,
    timings: dict[State, float] = DEFAULT_TIMINGS,
    speed: float = 1.0,
    debate_rounds: int = DEFAULT_DEBATE_ROUNDS,
    seed: int | None = None,
) -> None:
    """Emite la secuencia completa al bus respetando `timings / speed`.

    Simula la mecánica de firmas: cada ronda, algunos sabios firman la
    premisa. La última ronda fuerza que todos firmen → ACUERDO.

    payload['signed_this_round']: lista de índices de sabios que firman
    en ESTA ronda. El animator acumula las firmas en un set global.
    """
    import random as _r
    rng = _r.Random(seed)
    n_sages = 7
    signed: set[int] = set()

    async def emit(state: State, **kwargs) -> None:
        await bus.publish(StateEvent(state=state, **kwargs))
        await asyncio.sleep(timings.get(state, 1.0) / speed)

    await emit(State.ENTRANDO)
    await emit(State.SENTANDOSE)
    await emit(State.ANALIZANDO)

    for r in range(1, debate_rounds + 1):
        # Cuántos firman esta ronda
        remaining = [i for i in range(n_sages) if i not in signed]
        if r == debate_rounds:
            # Última ronda: todos firman
            new_signers = remaining
        else:
            # 1-3 nuevos firmantes aleatorios
            k = min(len(remaining), rng.randint(1, 3))
            new_signers = rng.sample(remaining, k) if remaining else []
        signed.update(new_signers)
        payload = {
            "signed_this_round": new_signers,
            "total_signed": sorted(signed),
        }
        await emit(State.DEBATE, round_num=r, payload=payload)

    await emit(State.JUEZ)
    await emit(State.ACUERDO)
    await emit(State.LEVANTANDOSE)
    await emit(State.SALIENDO)
    await emit(State.REPORTE)


async def run_demo(
    speed: float = 10.0,
    rounds: int = DEFAULT_DEBATE_ROUNDS,
    on_event: Callable[[StateEvent], None] | None = None,
) -> list[StateEvent]:
    bus = EventBus()
    received: list[StateEvent] = []
    driver = asyncio.create_task(mock_driver(bus, speed=speed, debate_rounds=rounds))

    async for event in bus.consume():
        received.append(event)
        if on_event:
            on_event(event)

    await driver
    return received


def main() -> None:
    parser = argparse.ArgumentParser(description="Demo headless de la máquina de estados.")
    parser.add_argument("--speed", type=float, default=20.0)
    parser.add_argument("--rounds", type=int, default=DEFAULT_DEBATE_ROUNDS,
                        help=f"Número de rondas de debate (max {MAX_DEBATE_ROUNDS})")
    args = parser.parse_args()

    def _print(event: StateEvent) -> None:
        suf = f" (round {event.round_num})" if event.state == State.DEBATE else ""
        print(f"-> {event.state.value}{suf}")

    events = asyncio.run(run_demo(speed=args.speed, rounds=args.rounds, on_event=_print))
    print(f"\ntotal eventos: {len(events)}")


if __name__ == "__main__":
    main()
