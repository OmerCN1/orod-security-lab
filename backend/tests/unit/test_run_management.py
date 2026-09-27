"""Run lifecycle control: review races, cancellation, concurrency and restart recovery."""

import asyncio
from typing import Any

import pytest

from orod.application.run_analysis import INTERRUPTED_RUN_ERROR, RunCoordinator
from orod.domain.errors import ReviewNotPendingError, RunAlreadyFinishedError
from orod.domain.events import RunEvent
from orod.domain.models import (
    ReviewRequest,
    ReviewSubmission,
    RunCreate,
    RunPhase,
    RunRecord,
    RunStatus,
    ValidationResult,
)


class MemoryStore:
    """RunStore double whose awaits really yield, so interleavings can happen."""

    def __init__(self, *runs: RunRecord) -> None:
        self.runs = {run.id: run.model_copy(deep=True) for run in runs}
        self.events: list[RunEvent] = []

    async def create_run(self, run: RunRecord) -> None:
        await asyncio.sleep(0)
        self.runs[run.id] = run.model_copy(deep=True)

    async def get_run(self, run_id: str) -> RunRecord | None:
        await asyncio.sleep(0)
        run = self.runs.get(run_id)
        return run.model_copy(deep=True) if run else None

    async def save_run(self, run: RunRecord) -> None:
        await asyncio.sleep(0)
        self.runs[run.id] = run.model_copy(deep=True)

    async def append_event(self, event: RunEvent) -> RunEvent:
        await asyncio.sleep(0)
        self.events.append(event)
        return event

    async def list_runs_with_status(self, statuses: set[RunStatus]) -> list[RunRecord]:
        return [run.model_copy(deep=True) for run in self.runs.values() if run.status in statuses]

    def messages(self, run_id: str) -> list[str]:
        return [event.message for event in self.events if event.run_id == run_id]


class BlockingGraph:
    """A graph whose runs stay in flight until released."""

    def __init__(self) -> None:
        self.invocations: list[Any] = []
        self.release = asyncio.Event()
        self.cleaned_up: list[str] = []

    async def ainvoke(self, payload: Any, config: Any) -> dict[str, Any]:
        self.invocations.append(payload)
        try:
            await self.release.wait()
        except asyncio.CancelledError:
            # Stands in for killing a process group and removing a container.
            await asyncio.sleep(0.01)
            self.cleaned_up.append(config["configurable"]["thread_id"])
            raise
        return {}


def paused_run(run_id: str = "run-1") -> RunRecord:
    return RunRecord(
        id=run_id,
        repository_url="demo://vulnerable-python",
        status=RunStatus.AWAITING_REVIEW,
        validation=ValidationResult(passed=True, summary="checked"),
        review=ReviewRequest(validation_passed=True, can_approve=True),
    )


def record(run_id: str, status: RunStatus) -> RunRecord:
    return RunRecord(id=run_id, repository_url="demo://vulnerable-python", status=status)


def coordinator_for(
    store: MemoryStore, graph: Any, *, max_concurrent_runs: int = 2
) -> RunCoordinator:
    return RunCoordinator(
        graph,
        store,  # type: ignore[arg-type]
        max_concurrent_runs=max_concurrent_runs,
        cancel_grace_seconds=1.0,
    )


async def settle() -> None:
    for _ in range(20):
        await asyncio.sleep(0)


async def test_concurrent_review_submissions_resume_the_graph_once() -> None:
    store, graph = MemoryStore(paused_run()), BlockingGraph()
    coordinator = coordinator_for(store, graph)
    decision = ReviewSubmission(decision="reject")

    results = await asyncio.gather(
        coordinator.submit_review("run-1", decision),
        coordinator.submit_review("run-1", decision),
        return_exceptions=True,
    )
    await settle()

    assert sum(isinstance(item, RunRecord) for item in results) == 1
    assert sum(isinstance(item, ReviewNotPendingError) for item in results) == 1
    assert len(graph.invocations) == 1
    assert store.messages("run-1").count("Reviewer submitted: reject") == 1
    graph.release.set()
    await coordinator.shutdown()


class ParkingGraph:
    """Pauses for review the way the real review node does: status first, then return.

    Between the two, the task that paused the run is still alive, finishing its
    checkpoint write.
    """

    def __init__(self, store: MemoryStore) -> None:
        self.store = store
        self.invocations: list[Any] = []
        self.parked = asyncio.Event()

    async def ainvoke(self, payload: Any, config: Any) -> dict[str, Any]:
        self.invocations.append(payload)
        run_id = config["configurable"]["thread_id"]
        run = await self.store.get_run(run_id)
        assert run is not None
        run.status = RunStatus.AWAITING_REVIEW
        run.validation = ValidationResult(passed=True, summary="checked")
        run.review = ReviewRequest(validation_passed=True, can_approve=True)
        await self.store.save_run(run)
        await self.parked.wait()
        return {}


async def test_a_decision_arriving_while_the_run_is_still_pausing_is_applied() -> None:
    store = MemoryStore()
    graph = ParkingGraph(store)
    coordinator = coordinator_for(store, graph)
    run = await coordinator.start(RunCreate(repository_url="demo://vulnerable-python"))
    await settle()
    assert store.runs[run.id].status == RunStatus.AWAITING_REVIEW
    assert coordinator._is_active(run.id)  # noqa: SLF001 - still parking

    async def finish_parking() -> None:
        await asyncio.sleep(0.02)
        graph.parked.set()

    parking = asyncio.create_task(finish_parking())
    accepted = await coordinator.submit_review(run.id, ReviewSubmission(decision="reject"))
    await parking
    await settle()

    assert accepted.id == run.id
    assert len(graph.invocations) == 2
    assert graph.invocations[1].resume == {"decision": "reject", "feedback": None}
    await coordinator.shutdown()


async def test_a_new_review_round_is_not_mistaken_for_a_duplicate_decision() -> None:
    store = MemoryStore(paused_run())
    graph = ParkingGraph(store)
    coordinator = coordinator_for(store, graph)
    first = ReviewSubmission(decision="regenerate", feedback="use shlex")
    await coordinator.submit_review("run-1", first)
    await settle()
    # The regeneration paused again with a new request while its task is still alive.
    assert store.runs["run-1"].status == RunStatus.AWAITING_REVIEW
    assert coordinator._is_active("run-1")  # noqa: SLF001

    async def finish_parking() -> None:
        await asyncio.sleep(0.02)
        graph.parked.set()

    parking = asyncio.create_task(finish_parking())
    second = await coordinator.submit_review("run-1", ReviewSubmission(decision="reject"))
    await parking
    await settle()

    assert second.id == "run-1"
    assert [item.resume["decision"] for item in graph.invocations] == ["regenerate", "reject"]
    await coordinator.shutdown()


@pytest.mark.parametrize("status", [RunStatus.COMPLETED, RunStatus.FAILED])
async def test_cancelling_a_finished_run_keeps_its_result(status: RunStatus) -> None:
    store = MemoryStore(record("run-1", status))
    coordinator = coordinator_for(store, BlockingGraph())

    with pytest.raises(RunAlreadyFinishedError):
        await coordinator.cancel("run-1")

    assert store.runs["run-1"].status == status
    assert store.events == []


async def test_cancelling_twice_returns_the_cancelled_run_unchanged() -> None:
    store = MemoryStore(record("run-1", RunStatus.CANCELLED))
    coordinator = coordinator_for(store, BlockingGraph())

    cancelled = await coordinator.cancel("run-1")

    assert cancelled is not None and cancelled.status == RunStatus.CANCELLED
    assert store.events == []


async def test_cancel_waits_for_the_run_to_clean_up_before_reporting() -> None:
    store, graph = MemoryStore(), BlockingGraph()
    coordinator = coordinator_for(store, graph)
    run = await coordinator.start(RunCreate(repository_url="demo://vulnerable-python"))
    await settle()
    assert graph.invocations

    cancelled = await coordinator.cancel(run.id)

    assert cancelled is not None and cancelled.status == RunStatus.CANCELLED
    # Cleanup finished before cancel returned, so nothing still runs for this run.
    assert graph.cleaned_up == [run.id]
    assert not coordinator._is_active(run.id)  # noqa: SLF001
    assert store.messages(run.id)[-1] == "Run cancelled"


async def test_a_run_that_finishes_before_the_cancellation_lands_keeps_its_result() -> None:
    store = MemoryStore()

    class FinishingGraph:
        async def ainvoke(self, payload: Any, config: Any) -> dict[str, Any]:
            run_id = config["configurable"]["thread_id"]
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                # The final node's write landed; the cancellation arrived too late.
                finished = await store.get_run(run_id)
                assert finished is not None
                finished.status = RunStatus.COMPLETED
                await store.save_run(finished)
            return {}

    coordinator = coordinator_for(store, FinishingGraph())
    run = await coordinator.start(RunCreate(repository_url="demo://vulnerable-python"))
    await settle()

    with pytest.raises(RunAlreadyFinishedError):
        await coordinator.cancel(run.id)
    assert store.runs[run.id].status == RunStatus.COMPLETED


async def test_a_paused_run_can_be_cancelled_and_then_accepts_no_decision() -> None:
    store = MemoryStore(paused_run())
    coordinator = coordinator_for(store, BlockingGraph())

    cancelled = await coordinator.cancel("run-1")

    assert cancelled is not None and cancelled.status == RunStatus.CANCELLED
    with pytest.raises(ReviewNotPendingError):
        await coordinator.submit_review("run-1", ReviewSubmission(decision="reject"))


async def test_runs_beyond_the_limit_wait_for_a_free_slot() -> None:
    store, graph = MemoryStore(), BlockingGraph()
    coordinator = coordinator_for(store, graph, max_concurrent_runs=1)

    first = await coordinator.start(RunCreate(repository_url="demo://vulnerable-python"))
    await settle()
    second = await coordinator.start(RunCreate(repository_url="demo://vulnerable-python"))
    await settle()

    assert len(graph.invocations) == 1
    assert store.runs[second.id].status == RunStatus.QUEUED
    assert any("Waiting for a free run slot" in message for message in store.messages(second.id))

    graph.release.set()
    await settle()
    assert len(graph.invocations) == 2
    assert not coordinator._is_active(first.id)  # noqa: SLF001
    await coordinator.shutdown()


async def test_a_queued_run_can_be_cancelled_without_ever_starting() -> None:
    store, graph = MemoryStore(), BlockingGraph()
    coordinator = coordinator_for(store, graph, max_concurrent_runs=1)
    await coordinator.start(RunCreate(repository_url="demo://vulnerable-python"))
    await settle()
    queued = await coordinator.start(RunCreate(repository_url="demo://vulnerable-python"))
    await settle()

    cancelled = await coordinator.cancel(queued.id)
    graph.release.set()
    await settle()

    assert cancelled is not None and cancelled.status == RunStatus.CANCELLED
    assert len(graph.invocations) == 1
    await coordinator.shutdown()


async def test_restart_fails_runs_left_in_flight_and_keeps_paused_ones() -> None:
    store = MemoryStore(
        record("running", RunStatus.RUNNING),
        record("queued", RunStatus.QUEUED),
        paused_run("paused"),
        record("done", RunStatus.COMPLETED),
    )
    coordinator = coordinator_for(store, BlockingGraph())

    reconciled = await coordinator.reconcile_interrupted_runs()

    assert sorted(reconciled) == ["queued", "running"]
    for run_id in reconciled:
        assert store.runs[run_id].status == RunStatus.FAILED
        assert store.runs[run_id].phase == RunPhase.FAILED
        assert store.runs[run_id].error == INTERRUPTED_RUN_ERROR
        assert store.messages(run_id) == ["Run interrupted by a backend restart"]
    assert store.runs["paused"].status == RunStatus.AWAITING_REVIEW
    assert store.runs["done"].status == RunStatus.COMPLETED
