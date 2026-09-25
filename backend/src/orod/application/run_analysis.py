from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from langgraph.types import Command

from orod.domain.errors import ReviewNotAllowedError, ReviewNotPendingError, RunNotFoundError
from orod.domain.events import EventLevel, EventType, RunEvent
from orod.domain.models import (
    ReviewDecision,
    ReviewSubmission,
    RunCreate,
    RunPhase,
    RunRecord,
    RunStatus,
    utc_now,
)
from orod.graph.state import TeamState
from orod.ports.storage import RunStore


class RunCoordinator:
    def __init__(self, graph: object, store: RunStore) -> None:
        self._graph = graph
        self._store = store
        self._tasks: dict[str, asyncio.Task[None]] = {}

    async def start(self, request: RunCreate) -> RunRecord:
        run_id = str(uuid4())
        run = RunRecord(
            id=run_id,
            repository_url=request.repository_url,
            base_branch=request.base_branch,
            trusted=request.trusted,
            model=request.model,
        )
        await self._store.create_run(run)
        await self._store.append_event(
            RunEvent(run_id=run_id, message="Run queued", event_type=EventType.RUN)
        )
        self._tasks[run_id] = asyncio.create_task(
            self._execute(run, self._initial_state(run)), name=f"orod-run-{run_id}"
        )
        return run

    async def submit_review(self, run_id: str, submission: ReviewSubmission) -> RunRecord:
        """Resume a paused run with a human decision.

        Approval is refused here as well as in the graph's routing, so no request path can
        open a pull request for a patch that did not pass validation.
        """
        run = await self._store.get_run(run_id)
        if run is None:
            raise RunNotFoundError(run_id)
        if run.status != RunStatus.AWAITING_REVIEW:
            raise ReviewNotPendingError(f"run is {run.status.value}, not awaiting review")
        existing = self._tasks.get(run_id)
        if existing is not None and not existing.done():
            raise ReviewNotPendingError("a decision for this run is already being applied")
        if submission.decision == ReviewDecision.APPROVE and not (
            run.validation is not None and run.validation.passed
        ):
            raise ReviewNotAllowedError("approval requires a patch that passed validation")

        await self._store.append_event(
            RunEvent(
                run_id=run_id,
                message=f"Reviewer submitted: {submission.decision.value}",
                event_type=EventType.REVIEW,
                agent="reviewer",
            )
        )
        command: Command[Any] = Command(
            resume={"decision": submission.decision.value, "feedback": submission.feedback}
        )
        self._tasks[run_id] = asyncio.create_task(
            self._execute(run, command), name=f"orod-review-{run_id}"
        )
        return run

    async def cancel(self, run_id: str) -> RunRecord | None:
        task = self._tasks.get(run_id)
        if task is not None and not task.done():
            task.cancel()
        run = await self._store.get_run(run_id)
        if run is None:
            return None
        run.status = RunStatus.CANCELLED
        run.updated_at = utc_now()
        await self._store.save_run(run)
        await self._store.append_event(
            RunEvent(
                run_id=run_id,
                message="Run cancelled",
                event_type=EventType.RUN,
                level=EventLevel.WARNING,
            )
        )
        return run

    async def shutdown(self) -> None:
        active = [task for task in self._tasks.values() if not task.done()]
        for task in active:
            task.cancel()
        if active:
            await asyncio.gather(*active, return_exceptions=True)

    @staticmethod
    def _initial_state(run: RunRecord) -> TeamState:
        return {
            "run_id": run.id,
            "repository_url": run.repository_url,
            "base_branch": run.base_branch,
            "trusted": run.trusted,
            "model": run.model,
            "phase": RunPhase.QUEUED.value,
            "findings": [],
            "selected_finding_ids": [],
            "errors": [],
            "attempt": 0,
            "revision_count": 0,
            "review_decision": None,
            "reviewer_feedback": None,
            "started_at": datetime.now(UTC).isoformat(),
        }

    async def _execute(self, run: RunRecord, payload: TeamState | Command[Any]) -> None:
        """Drive the graph until it finishes or pauses.

        A pause is not an error: when the review node interrupts, ``ainvoke`` returns
        normally and the node has already parked the run in ``awaiting_review``. The task
        simply ends, and ``submit_review`` starts a new one to resume.
        """
        try:
            await self._graph.ainvoke(  # type: ignore[attr-defined]
                payload,
                config={"configurable": {"thread_id": run.id}},
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            current = await self._store.get_run(run.id)
            if current is not None:
                current.status = RunStatus.FAILED
                current.phase = RunPhase.FAILED
                current.error = f"{type(exc).__name__}: {str(exc)[:500]}"
                current.updated_at = utc_now()
                await self._store.save_run(current)
            await self._store.append_event(
                RunEvent(
                    run_id=run.id,
                    message=f"Run failed: {type(exc).__name__}",
                    event_type=EventType.RUN,
                    level=EventLevel.ERROR,
                    payload={"detail": str(exc)[:500]},
                )
            )
        finally:
            self._tasks.pop(run.id, None)
