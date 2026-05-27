"""Mock event-bus driver — canned sequence for visual smoke tests.

This driver knows nothing about the project being reviewed; it just emits
the state machine in order so the animator can be exercised in isolation.
For real debate output, use `orchestrator.run_council` or the claude-code
mode driver.
"""

from __future__ import annotations

import asyncio
import random
from typing import TYPE_CHECKING

from ..states import DEFAULT_DEBATE_ROUNDS, DEFAULT_TIMINGS, State, StateEvent

if TYPE_CHECKING:
    from ..bus import Publisher


async def mock_driver(
    bus: "Publisher",
    timings: dict[State, float] = DEFAULT_TIMINGS,
    speed: float = 1.0,
    debate_rounds: int = DEFAULT_DEBATE_ROUNDS,
    seed: int | None = None,
) -> None:
    """Emite la secuencia completa al bus respetando `timings / speed`.

    Simula la mecánica de firmas: cada ronda, algunos sabios firman la
    premisa. La última ronda fuerza que todos firmen → ACUERDO.
    """
    rng = random.Random(seed)
    n_sages = 7
    signed: set[int] = set()

    async def emit(state: State, **kwargs) -> None:
        await bus.publish(StateEvent(state=state, **kwargs))
        await asyncio.sleep(timings.get(state, 1.0) / speed)

    await emit(State.ENTRANDO)
    await emit(State.SENTANDOSE)
    await emit(State.ANALIZANDO)

    for r in range(1, debate_rounds + 1):
        remaining = [i for i in range(n_sages) if i not in signed]
        if r == debate_rounds:
            new_signers = remaining
        else:
            k = min(len(remaining), rng.randint(1, 3))
            new_signers = rng.sample(remaining, k) if remaining else []
        signed.update(new_signers)
        await emit(State.DEBATE, round_num=r, payload={
            "signed_this_round": new_signers,
            "total_signed": sorted(signed),
        })

    await emit(State.JUEZ)
    await emit(State.ACUERDO)
    await emit(State.LEVANTANDOSE)
    await emit(State.SALIENDO)
    await emit(State.REPORTE)
