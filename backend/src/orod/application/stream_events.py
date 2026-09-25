from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

from orod.domain.events import RunEvent
from orod.domain.models import RunStatus
from orod.ports.storage import RunStore


async def stream_run_events(
    store: RunStore,
    run_id: str,
    after: int,
    poll_interval: float,
) -> AsyncIterator[RunEvent]:
    cursor = after
    while True:
        events = await store.list_events(run_id, cursor)
        for event in events:
            cursor = event.sequence
            yield event
        run = await store.get_run(run_id)
        if run is None:
            return
        if run.status in {RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.CANCELLED}:
            trailing = await store.list_events(run_id, cursor)
            for event in trailing:
                cursor = event.sequence
                yield event
            return
        await asyncio.sleep(poll_interval)
