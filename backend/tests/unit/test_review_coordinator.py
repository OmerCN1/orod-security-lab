import asyncio
from typing import Any

import pytest

from orod.application.run_analysis import RunCoordinator
from orod.domain.errors import ReviewNotAllowedError, ReviewNotPendingError, RunNotFoundError
from orod.domain.events import RunEvent
from orod.domain.models import (
    ReviewSubmission,
    RunRecord,
    RunStatus,
    ValidationResult,
)


class StubStore:
    """Minimal RunStore double; the coordinator only needs get/append here."""

    def __init__(self, run: RunRecord | None = None) -> None:
        self.run = run
        self.events: list[RunEvent] = []

    async def get_run(self, run_id: str) -> RunRecord | None:
        return self.run if self.run and self.run.id == run_id else None

    async def append_event(self, event: RunEvent) -> RunEvent:
        self.events.append(event)
        return event


class StubGraph:
    def __init__(self) -> None:
        self.invocations: list[Any] = []

    async def ainvoke(self, payload: Any, config: Any) -> dict[str, Any]:
        self.invocations.append(payload)
        return {}


def make_coordinator(run: RunRecord | None) -> tuple[RunCoordinator, StubStore, StubGraph]:
    store = StubStore(run)
    graph = StubGraph()
    return RunCoordinator(graph, store), store, graph  # type: ignore[arg-type]


async def drain(coordinator: RunCoordinator) -> None:
    """Let the resume task the coordinator scheduled actually run to completion."""
    for _ in range(50):
        await asyncio.sleep(0)
        if all(task.done() for task in coordinator._tasks.values()):  # noqa: SLF001
            return
    raise AssertionError("resume task did not finish")


def paused_run(validation_passed: bool = True) -> RunRecord:
    return RunRecord(
        id="run-1",
        repository_url="demo://vulnerable-python",
        status=RunStatus.AWAITING_REVIEW,
        validation=ValidationResult(passed=validation_passed, summary="checked"),
    )


async def test_reject_resumes_the_graph_with_the_decision() -> None:
    coordinator, store, graph = make_coordinator(paused_run())

    await coordinator.submit_review("run-1", ReviewSubmission(decision="reject"))
    await drain(coordinator)

    assert graph.invocations, "the graph should have been resumed"
    assert graph.invocations[0].resume == {"decision": "reject", "feedback": None}
    assert any("reject" in event.message for event in store.events)


async def test_regeneration_forwards_the_reviewer_feedback() -> None:
    coordinator, _, graph = make_coordinator(paused_run())

    await coordinator.submit_review(
        "run-1", ReviewSubmission(decision="regenerate", feedback="use an ORM")
    )
    await drain(coordinator)

    assert graph.invocations[0].resume["feedback"] == "use an ORM"


async def test_approval_is_refused_when_validation_did_not_pass() -> None:
    """Mirrors the graph-level guard: a failed validation can never reach publish."""
    coordinator, _, graph = make_coordinator(paused_run(validation_passed=False))

    with pytest.raises(ReviewNotAllowedError):
        await coordinator.submit_review("run-1", ReviewSubmission(decision="approve"))
    assert graph.invocations == []


async def test_decisions_are_refused_for_runs_that_are_not_paused() -> None:
    running = paused_run()
    running.status = RunStatus.RUNNING
    coordinator, _, graph = make_coordinator(running)

    with pytest.raises(ReviewNotPendingError):
        await coordinator.submit_review("run-1", ReviewSubmission(decision="reject"))
    assert graph.invocations == []


async def test_unknown_run_is_reported_as_missing() -> None:
    coordinator, _, _ = make_coordinator(None)

    with pytest.raises(RunNotFoundError):
        await coordinator.submit_review("run-1", ReviewSubmission(decision="reject"))
