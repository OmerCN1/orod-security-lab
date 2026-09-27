import sqlite3
from pathlib import Path

from orod.adapters.persistence.sqlite import SQLiteRunStore
from orod.domain.events import RunEvent
from orod.domain.models import RunRecord, RunStatus, ValidationResult, utc_now


async def test_store_persists_runs_and_monotonic_events(tmp_path: Path) -> None:
    store = SQLiteRunStore(tmp_path / "events.sqlite3")
    await store.initialize()
    run = RunRecord(id="run-1", repository_url="demo://vulnerable-python")
    await store.create_run(run)

    first = await store.append_event(RunEvent(run_id=run.id, message="first"))
    second = await store.append_event(RunEvent(run_id=run.id, message="second"))

    assert first.sequence == 1
    assert second.sequence == 2
    assert [event.message for event in await store.list_events(run.id, after=1)] == ["second"]
    assert (await store.get_run(run.id)) == run


async def test_list_runs_returns_newest_first_and_paginates(tmp_path: Path) -> None:
    store = SQLiteRunStore(tmp_path / "runs.sqlite3")
    await store.initialize()
    base = utc_now()
    for index in range(3):
        await store.create_run(
            RunRecord(
                id=f"run-{index}",
                repository_url=f"demo://case-{index}",
                created_at=base.replace(microsecond=index * 1000),
            )
        )

    newest_first = [run.id for run in await store.list_runs()]
    assert newest_first == ["run-2", "run-1", "run-0"]
    assert [run.id for run in await store.list_runs(limit=1)] == ["run-2"]
    assert [run.id for run in await store.list_runs(limit=1, offset=1)] == ["run-1"]


async def test_list_runs_round_trips_review_state(tmp_path: Path) -> None:
    store = SQLiteRunStore(tmp_path / "runs.sqlite3")
    await store.initialize()
    run = RunRecord(
        id="run-review",
        repository_url="demo://vulnerable-python",
        status=RunStatus.AWAITING_REVIEW,
        model="claude-opus-5",
        validation=ValidationResult(passed=True, summary="ok"),
    )
    await store.create_run(run)

    stored = (await store.list_runs())[0]
    assert stored.status == RunStatus.AWAITING_REVIEW
    assert stored.model == "claude-opus-5"


async def test_initialize_migrates_a_database_created_before_the_created_at_column(
    tmp_path: Path,
) -> None:
    """Existing installations must keep their history when the schema gains a column."""
    path = tmp_path / "legacy.sqlite3"
    legacy = sqlite3.connect(path)
    legacy.execute("CREATE TABLE runs (id TEXT PRIMARY KEY, payload TEXT NOT NULL)")
    older = RunRecord(id="old", repository_url="demo://old")
    newer = RunRecord(
        id="new",
        repository_url="demo://new",
        created_at=older.created_at.replace(year=older.created_at.year + 1),
    )
    for run in (older, newer):
        legacy.execute("INSERT INTO runs VALUES (?, ?)", (run.id, run.model_dump_json()))
    legacy.commit()
    legacy.close()

    store = SQLiteRunStore(path)
    await store.initialize()

    assert [run.id for run in await store.list_runs()] == ["new", "old"]
    assert (await store.get_run("old")) is not None


async def test_migration_preserves_sub_second_ordering(tmp_path: Path) -> None:
    """Runs created inside the same second must still migrate in the right order.

    The ids are chosen so the `id DESC` tiebreaker would produce the *wrong* order: if
    the migration collapsed both timestamps to whole seconds, the tiebreaker would decide
    and this would fail.
    """
    path = tmp_path / "legacy-dense.sqlite3"
    legacy = sqlite3.connect(path)
    legacy.execute("CREATE TABLE runs (id TEXT PRIMARY KEY, payload TEXT NOT NULL)")
    older = RunRecord(
        id="zz-older",
        repository_url="demo://a",
        created_at=utc_now().replace(microsecond=100_000),
    )
    newer = RunRecord(
        id="aa-newer",
        repository_url="demo://b",
        created_at=older.created_at.replace(microsecond=900_000),
    )
    assert older.created_at.replace(microsecond=0) == newer.created_at.replace(microsecond=0)
    for run in (older, newer):
        legacy.execute("INSERT INTO runs VALUES (?, ?)", (run.id, run.model_dump_json()))
    legacy.commit()
    legacy.close()

    store = SQLiteRunStore(path)
    await store.initialize()

    assert [run.id for run in await store.list_runs()] == ["aa-newer", "zz-older"]


async def test_list_runs_with_status_selects_on_the_persisted_status(tmp_path: Path) -> None:
    store = SQLiteRunStore(tmp_path / "status.sqlite3")
    await store.initialize()
    for run_id, status in (
        ("running", RunStatus.RUNNING),
        ("queued", RunStatus.QUEUED),
        ("paused", RunStatus.AWAITING_REVIEW),
        ("done", RunStatus.COMPLETED),
    ):
        await store.create_run(
            RunRecord(id=run_id, repository_url="demo://vulnerable-python", status=status)
        )

    selected = await store.list_runs_with_status({RunStatus.RUNNING, RunStatus.QUEUED})

    assert sorted(run.id for run in selected) == ["queued", "running"]
    assert await store.list_runs_with_status(set()) == []
