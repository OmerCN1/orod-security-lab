"""Post-patch validation compares findings by identity, including dependency advisories."""

from pathlib import Path
from typing import Any

import pytest
from langgraph.checkpoint.memory import InMemorySaver

from orod.adapters.persistence.sqlite import SQLiteRunStore
from orod.agents.base import AgentServices
from orod.application.run_analysis import RunCoordinator
from orod.config import Settings
from orod.domain.errors import ScanFailedError, ScannerOutputError
from orod.domain.events import EventType, RunEvent
from orod.domain.models import (
    AdvisorySyncResult,
    FileEntry,
    Finding,
    FindingSource,
    PackageDependency,
    PatchProposal,
    RepositorySnapshot,
    RunRecord,
    Severity,
    ValidationResult,
)
from orod.graph.builder import build_security_team

BASE_SOURCE = "import subprocess\nsubprocess.run(cmd, shell=True)\n"
PATCHED_SOURCE = "import subprocess\nsubprocess.run(cmd, shell=False)\nvalue = eval(text)\n"
PINNED = PackageDependency(name="demo", version="1.0", source_file="requirements.txt")
UPGRADED = PackageDependency(name="demo", version="2.0", source_file="requirements.txt")


def finding(rule_id: str, source: FindingSource, path: str, line: int | None) -> Finding:
    return Finding(
        id=f"{source.value}-{rule_id}-{path}-{line}",
        source=source,
        rule_id=rule_id,
        severity=Severity.HIGH,
        title=rule_id,
        message=rule_id,
        file_path=path,
        line=line,
    )


class FakeRepository:
    def __init__(self, workspace: Path, dependencies_after: list[PackageDependency]) -> None:
        self.workspace = workspace
        self.patched = False
        self.dependencies_after = dependencies_after

    async def prepare(self, *args: object) -> RepositorySnapshot:
        return RepositorySnapshot(
            repository_url="demo://fake",
            workspace_path=str(self.workspace),
            trusted=True,
            files=[FileEntry(path="app.py", size=len(BASE_SOURCE), language="python")],
            dependencies=[PINNED],
        )

    async def read_files(self, snapshot: object, paths: list[str], **_: object) -> dict[str, str]:
        return {path: PATCHED_SOURCE if self.patched else BASE_SOURCE for path in paths}

    async def read_base_files(
        self, snapshot: object, paths: list[str], **_: object
    ) -> dict[str, str]:
        return {path: BASE_SOURCE for path in paths}

    async def apply_patch(self, snapshot: object, patch: PatchProposal) -> str:
        self.patched = True
        return patch.unified_diff

    async def revert_patch(self, snapshot: object, applied_diff: str) -> None:
        self.patched = False

    async def discover_dependencies(self, snapshot: object) -> list[PackageDependency]:
        return self.dependencies_after if self.patched else [PINNED]

    async def record_baseline(self, snapshot: object) -> None:
        return None

    async def validate(self, snapshot: object, baseline: object = None) -> ValidationResult:
        return ValidationResult(passed=True, summary="All fixed validation commands passed.")


class FakeScanner:
    """Reports B602 on the base revision and, once patched, a new B307 instead."""

    name = "fake"

    def __init__(self, repository: FakeRepository) -> None:
        self._repository = repository

    async def scan(self, snapshot: object) -> list[Finding]:
        if self._repository.patched:
            return [finding("B307", FindingSource.BANDIT, "app.py", 3)]
        return [finding("B602", FindingSource.BANDIT, "app.py", 2)]


class FakeAdvisories:
    def __init__(self, complete: bool = True) -> None:
        self.complete = complete
        self.queries: list[list[PackageDependency]] = []

    async def scan_dependencies(
        self, dependencies: list[PackageDependency]
    ) -> tuple[list[Finding], AdvisorySyncResult]:
        self.queries.append(dependencies)
        advisory = "GHSA-new" if dependencies == [UPGRADED] else "GHSA-known"
        result = AdvisorySyncResult(
            queried_packages=len(dependencies),
            matched_advisories=1,
            cached_advisories=0,
            errors=[] if self.complete else ["OSV query failed: ConnectError"],
            complete=self.complete,
        )
        found = [finding(advisory, FindingSource.OSV, "requirements.txt", None)]
        return (found if self.complete else []), result


class FakeProvider:
    async def propose_patch(self, *args: object, **kwargs: object) -> PatchProposal:
        return PatchProposal(
            unified_diff="--- a/app.py\n+++ b/app.py\n",
            changed_files=["app.py"],
            finding_ids=[],
            explanation="Disabled the shell.",
        )


class FakeRegistry:
    def for_model(self, model: str | None) -> FakeProvider:
        return FakeProvider()


async def run_graph(
    tmp_path: Path,
    *,
    dependencies_after: list[PackageDependency],
    scanner_swaps_rule: bool = True,
    advisories: FakeAdvisories | None = None,
    extra_scanners: tuple[Any, ...] = (),
    keep_default_scanner: bool = True,
) -> tuple[RunRecord, FakeAdvisories]:
    store = SQLiteRunStore(tmp_path / "orod.sqlite3")
    await store.initialize()
    repository = FakeRepository(tmp_path, dependencies_after)
    scanner = FakeScanner(repository)
    if not scanner_swaps_rule:

        async def clean_after_patch(snapshot: object) -> list[Finding]:
            if repository.patched:
                return []
            return [finding("B602", FindingSource.BANDIT, "app.py", 2)]

        scanner.scan = clean_after_patch  # type: ignore[method-assign]
    vulnerabilities = advisories or FakeAdvisories()
    services = AgentServices(
        settings=Settings(require_human_approval=False, enable_github_publish=False),
        store=store,  # type: ignore[arg-type]
        repository=repository,  # type: ignore[arg-type]
        scanners=[*([scanner] if keep_default_scanner else []), *extra_scanners],
        vulnerabilities=vulnerabilities,
        vector_store=None,  # type: ignore[arg-type]
        llm=FakeProvider(),  # type: ignore[arg-type]
        llms=FakeRegistry(),  # type: ignore[arg-type]
        publisher=None,  # type: ignore[arg-type]
    )
    graph: Any = build_security_team(services, InMemorySaver())
    run = RunRecord(id="run-1", repository_url="demo://fake", trusted=True)
    await store.create_run(run)
    await graph.ainvoke(
        RunCoordinator._initial_state(run),  # noqa: SLF001
        config={"configurable": {"thread_id": run.id}},
    )
    record = await store.get_run(run.id)
    assert record is not None
    return record, vulnerabilities


async def test_a_vulnerable_dependency_no_longer_hides_a_new_high_code_finding(
    tmp_path: Path,
) -> None:
    # Before: B602 + a high advisory. After: B307 only from the code rescan. Counting
    # highs gave 2 before and 1 after, so the introduced eval() passed validation.
    record, advisories = await run_graph(tmp_path, dependencies_after=[PINNED])

    assert record.validation is not None
    assert record.validation.passed is False
    assert record.validation.new_high_findings == 1
    assert "B307 in app.py:3" in record.validation.summary
    # Unchanged manifests reuse the original match rather than querying OSV again.
    assert advisories.queries == [[PINNED]]


async def test_a_dependency_change_is_rechecked_against_osv(tmp_path: Path) -> None:
    record, advisories = await run_graph(
        tmp_path, dependencies_after=[UPGRADED], scanner_swaps_rule=False
    )

    # Initial scan, then one post-patch query per repair attempt.
    assert advisories.queries == [[PINNED], [UPGRADED], [UPGRADED]]
    assert record.validation is not None
    assert record.validation.passed is False
    assert "GHSA-new in requirements.txt" in record.validation.summary


async def test_an_incomplete_post_patch_osv_lookup_fails_closed(tmp_path: Path) -> None:
    record, _ = await run_graph(
        tmp_path,
        dependencies_after=[UPGRADED],
        scanner_swaps_rule=False,
        advisories=FakeAdvisories(complete=False),
    )

    assert record.validation is not None
    assert record.validation.passed is False
    assert record.validation.summary.startswith("Post-patch dependency check failed")


async def test_a_clean_patch_with_unchanged_dependencies_still_passes(tmp_path: Path) -> None:
    record, _ = await run_graph(tmp_path, dependencies_after=[PINNED], scanner_swaps_rule=False)

    assert record.validation is not None
    assert record.validation.passed is True, record.validation.summary
    assert record.validation.new_high_findings == 0


class BrokenScanner:
    name = "broken"

    async def scan(self, snapshot: object) -> list[Finding]:
        raise ScannerOutputError("Bandit returned invalid or truncated JSON")


async def events_of(tmp_path: Path) -> list[RunEvent]:
    return await SQLiteRunStore(tmp_path / "orod.sqlite3").list_events("run-1")


async def test_a_failed_scanner_marks_the_scan_incomplete(tmp_path: Path) -> None:
    record, _ = await run_graph(
        tmp_path,
        dependencies_after=[PINNED],
        scanner_swaps_rule=False,
        extra_scanners=(BrokenScanner(),),
    )

    assert record.scan_complete is False
    broken = next(item for item in record.scanners if item.name == "broken")
    assert broken.ok is False
    assert "truncated JSON" in broken.detail
    assert record.metrics is not None and record.metrics.scan_complete is False
    events = await events_of(tmp_path)
    failed = next(event for event in events if event.payload.get("scanner") == "broken")
    # The dashboard lists scanners by this payload; a failure used to carry none.
    assert failed.payload["ok"] is False
    assert any("scan was incomplete because broken failed" in event.message for event in events)


async def test_a_run_whose_every_scanner_failed_is_not_reported_clean(tmp_path: Path) -> None:
    with pytest.raises(ScanFailedError, match="No security scanner completed"):
        await run_graph(
            tmp_path,
            dependencies_after=[PINNED],
            extra_scanners=(BrokenScanner(),),
            keep_default_scanner=False,
        )

    record = await SQLiteRunStore(tmp_path / "orod.sqlite3").get_run("run-1")
    assert record is not None and record.scan_complete is False
    events = await events_of(tmp_path)
    # The security agent still closes its lifecycle, so it does not read as in flight.
    assert any(
        event.agent == "security" and event.event_type == EventType.AGENT_COMPLETED
        for event in events
    )


async def test_a_scan_where_every_scanner_worked_is_complete(tmp_path: Path) -> None:
    record, _ = await run_graph(tmp_path, dependencies_after=[PINNED], scanner_swaps_rule=False)

    assert record.scan_complete is True
    assert [item.name for item in record.scanners] == ["fake", "osv"]
    assert all(item.ok for item in record.scanners)
