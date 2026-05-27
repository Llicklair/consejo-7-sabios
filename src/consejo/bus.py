"""Bus contract for council events.

Split from `states.py` (Phase D architecture: dependency-direction reform).
The orchestrator and any driver depend on `Publisher` rather than the
concrete `EventBus`, so testing/replay substitutes a list-collecting fake.
"""

from __future__ import annotations

import asyncio
from typing import AsyncIterator, Protocol

from .states import State, StateEvent


class Publisher(Protocol):
    """Minimal contract a producer needs to push events to a consumer."""

    async def publish(self, event: StateEvent) -> None: ...


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
