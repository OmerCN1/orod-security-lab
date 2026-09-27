from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from langgraph.types import Command

from orod.domain.errors import (
    ReviewNotAllowedError,
    ReviewNotPendingError,
    RunAlreadyFinishedError,
    RunNotFoundError,
)
from orod.domain.events import EventLevel, EventType, RunEvent
from orod.domain.models import (
    TERMINAL_RUN_STATUSES,
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

INTERRUPTED_RUN_ERROR = "Interrupted: the backend stopped before this run finished."


class RunCoordinator:
    """Owns the in-process tasks that drive runs through the graph.

    Run state is shared between request handlers and those tasks, so every decision that
    checks a run and then acts on it - resuming a review, cancelling - happens under one
    lock. The lock is held only for store reads/writes and task bookkeeping, never while
    a run executes or while a cancelled run is being cleaned up. This assumes a single
    backend process owns the database, which is how `make backend` runs it.
    """

    def __init__(
        self,
        graph: object,
        store: RunStore,
        *,
        max_concurrent_runs: int = 2,
        cancel_grace_seconds: float = 15.0,
    ) -> None:
        self._graph = graph
        self._store = store
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._control = asyncio.Lock()
        self._cancelling: set[str] = set()
        # The review round each in-flight resume task answers, keyed by run id.
        self._answered_rounds: dict[str, datetime | None] = {}
        self._slots = asyncio.Semaphore(max_concurrent_runs)
        self._cancel_grace_seconds = cancel_grace_seconds

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
        self._launch(run, self._initial_state(run), f"orod-run-{run_id}")
        return run

    async def submit_review(self, run_id: str, submission: ReviewSubmission) -> RunRecord:
        """Resume a paused run with a human decision.

        Approval is refused here as well as in the graph's routing, so no request path can
        open a pull request for a patch that did not pass validation.

        Decisions are matched to the review round they answer (its ``requested_at``). A
        second decision for a round that already has one is refused; two submissions
        arriving together used to both pass the checks and resume the graph twice. The
        review node marks the run paused just before it interrupts, so the task that
        paused the round can still be parking the graph on its checkpoint when a quick
        decision arrives; that task is awaited rather than mistaken for a decision in
        progress.
        """
        for _ in range(2):
            async with self._control:
                run = await self._store.get_run(run_id)
                if run is None:
                    raise RunNotFoundError(run_id)
                if run.status != RunStatus.AWAITING_REVIEW or run_id in self._cancelling:
                    raise ReviewNotPendingError(f"run is {run.status.value}, not awaiting review")
                if submission.decision == ReviewDecision.APPROVE and not (
                    run.validation is not None and run.validation.passed
                ):
                    raise ReviewNotAllowedError("approval requires a patch that passed validation")
                review_round = run.review.requested_at if run.review is not None else None
                pausing = self._tasks.get(run_id) if self._is_active(run_id) else None
                if pausing is not None and (
                    review_round is None or self._answered_rounds.get(run_id) == review_round
                ):
                    raise ReviewNotPendingError("a decision for this run is already being applied")
                if pausing is None:
                    await self._store.append_event(
                        RunEvent(
                            run_id=run_id,
                            message=f"Reviewer submitted: {submission.decision.value}",
                            event_type=EventType.REVIEW,
                            agent="reviewer",
                        )
                    )
                    command: Command[Any] = Command(
                        resume={
                            "decision": submission.decision.value,
                            "feedback": submission.feedback,
                        }
                    )
                    self._answered_rounds[run_id] = review_round
                    self._launch(run, command, f"orod-review-{run_id}")
                    return run
            await asyncio.wait({pausing}, timeout=self._cancel_grace_seconds)
        raise ReviewNotPendingError("the run is still pausing for review; try again")

    async def cancel(self, run_id: str) -> RunRecord | None:
        """Stop a run and record it as cancelled.

        A finished run is never rewritten: cancelling one that already completed or failed
        raises ``RunAlreadyFinishedError``, and cancelling twice returns the same record. An
        executing run is cancelled and then awaited for up to ``cancel_grace_seconds`` so
        its process groups and validation containers are gone - and it can no longer write
        to the run - before the cancelled status is saved.
        """
        async with self._control:
            run = await self._store.get_run(run_id)
            if run is None:
                return None
            if run.status == RunStatus.CANCELLED:
                return run
            if run.status in TERMINAL_RUN_STATUSES:
                raise RunAlreadyFinishedError(f"run is already {run.status.value}")
            task = self._tasks.get(run_id)
            if task is None or task.done():
                # Nothing executes it: paused for review, or queued without a task.
                return await self._mark_cancelled(run, cleaned_up=True)
            self._cancelling.add(run_id)
            task.cancel()

        try:
            done, _ = await asyncio.wait({task}, timeout=self._cancel_grace_seconds)
            async with self._control:
                current = await self._store.get_run(run_id)
                if current is None:
                    return None
                if current.status in TERMINAL_RUN_STATUSES:
                    # It finished before the cancellation reached it; keep that result.
                    raise RunAlreadyFinishedError(f"run is already {current.status.value}")
                return await self._mark_cancelled(current, cleaned_up=bool(done))
        finally:
            self._cancelling.discard(run_id)

    async def reconcile_interrupted_runs(self) -> list[str]:
        """Fail runs that a previous backend process left queued or running.

        Their tasks died with that process, so nothing will ever move them on, and an SSE
        stream for them would poll forever. Runs paused for review are left alone: their
        graph is parked on a checkpoint and resumes normally. Call once at startup, before
        any run is started.
        """
        stranded = await self._store.list_runs_with_status({RunStatus.QUEUED, RunStatus.RUNNING})
        reconciled: list[str] = []
        for run in stranded:
            if self._is_active(run.id):
                continue
            run.status = RunStatus.FAILED
            run.phase = RunPhase.FAILED
            run.error = INTERRUPTED_RUN_ERROR
            run.updated_at = utc_now()
            await self._store.save_run(run)
            await self._store.append_event(
                RunEvent(
                    run_id=run.id,
                    message="Run interrupted by a backend restart",
                    event_type=EventType.RUN,
                    level=EventLevel.ERROR,
                )
            )
            reconciled.append(run.id)
        return reconciled

    async def shutdown(self) -> None:
        active = [task for task in self._tasks.values() if not task.done()]
        for task in active:
            task.cancel()
        if active:
            await asyncio.gather(*active, return_exceptions=True)

    def _is_active(self, run_id: str) -> bool:
        task = self._tasks.get(run_id)
        return task is not None and not task.done()

    def _launch(self, run: RunRecord, payload: TeamState | Command[Any], name: str) -> None:
        self._tasks[run.id] = asyncio.create_task(self._execute(run, payload), name=name)

    async def _mark_cancelled(self, run: RunRecord, *, cleaned_up: bool) -> RunRecord:
        run.status = RunStatus.CANCELLED
        run.updated_at = utc_now()
        await self._store.save_run(run)
        await self._store.append_event(
            RunEvent(
                run_id=run.id,
                message=(
                    "Run cancelled"
                    if cleaned_up
                    else "Run cancelled; its cleanup did not finish within the grace period"
                ),
                event_type=EventType.RUN,
                level=EventLevel.WARNING,
            )
        )
        return run

    @asynccontextmanager
    async def _run_slot(self, run_id: str) -> AsyncIterator[None]:
        if self._slots.locked():
            await self._store.append_event(
                RunEvent(
                    run_id=run_id,
                    message="Waiting for a free run slot; the concurrent-run limit is reached",
                    event_type=EventType.RUN,
                )
            )
        async with self._slots:
            yield

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
            async with self._run_slot(run.id):
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
            # Only forget this task; a later task for the same run must stay tracked.
            if self._tasks.get(run.id) is asyncio.current_task():
                del self._tasks[run.id]
                self._answered_rounds.pop(run.id, None)
