"""Selected advisories are cleared by a pin change and verified by the OSV rescan."""

from pathlib import Path
from typing import Any

from langgraph.checkpoint.memory import InMemorySaver

from orod.adapters.persistence.sqlite import SQLiteRunStore
from orod.agents.base import AgentServices
from orod.application.run_analysis import RunCoordinator
from orod.config import Settings
from orod.domain.models import (
    AdvisorySyncResult,
    DependencyUpgrade,
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

CODE_DIFF = "--- a/app.py\n+++ b/app.py\n@@ -1 +1 @@\n-bad\n+good\n"
Advisories = dict[str, list[tuple[str, Severity, list[str]]]]


def pinned(version: str) -> PackageDependency:
    return PackageDependency(name="PyYAML", version=version, source_file="requirements.txt")


class FakeRepository:
    def __init__(self, workspace: Path) -> None:
        self.workspace = workspace
        self.version = "5.3.1"
        self.pending: str | None = None
        self.applied: list[PatchProposal] = []

    async def prepare(self, *args: object) -> RepositorySnapshot:
        return RepositorySnapshot(
            repository_url="demo://fake",
            workspace_path=str(self.workspace),
            trusted=True,
            files=[FileEntry(path="app.py", size=4, language="python")],
            dependencies=[pinned("5.3.1")],
        )

    async def read_files(self, snapshot: object, paths: list[str], **_: object) -> dict[str, str]:
        return {path: "bad\n" for path in paths}

    async def read_base_files(
        self, snapshot: object, paths: list[str], **_: object
    ) -> dict[str, str]:
        return {path: "bad\n" for path in paths}

    async def upgrade_dependencies(
        self, snapshot: object, upgrades: list[DependencyUpgrade]
    ) -> tuple[str, list[str]]:
        self.pending = upgrades[0].target_version
        diff = (
            "--- a/requirements.txt\n+++ b/requirements.txt\n@@ -1 +1 @@\n"
            f"-PyYAML=={self.version}\n+PyYAML=={self.pending}\n"
        )
        return diff, ["requirements.txt"]

    async def apply_patch(self, snapshot: object, patch: PatchProposal) -> str:
        self.applied.append(patch)
        if "requirements.txt" in patch.changed_files and self.pending is not None:
            self.version = self.pending
        return patch.unified_diff

    async def revert_patch(self, snapshot: object, applied_diff: str) -> None:
        self.version = "5.3.1"

    async def discover_dependencies(self, snapshot: object) -> list[PackageDependency]:
        return [pinned(self.version)]

    async def record_baseline(self, snapshot: object) -> None:
        return None

    async def validate(self, snapshot: object, baseline: object = None) -> ValidationResult:
        return ValidationResult(passed=True, summary="All fixed validation commands passed.")


class FakeAdvisories:
    """OSV as a table: version -> (advisory id, severity, fixed versions)."""

    def __init__(self, table: Advisories, complete: bool = True) -> None:
        self.table = table
        self.complete = complete
        self.queries: list[str | None] = []

    async def scan_dependencies(
        self, dependencies: list[PackageDependency]
    ) -> tuple[list[Finding], AdvisorySyncResult]:
        dependency = dependencies[0]
        self.queries.append(dependency.version)
        findings = [
            Finding(
                id=f"{dependency.version}-{advisory_id}",
                source=FindingSource.OSV,
                rule_id=advisory_id,
                severity=severity,
                title=advisory_id,
                message=advisory_id,
                file_path=dependency.source_file,
                dependency=dependency,
                fixed_versions=fixed,
            )
            for advisory_id, severity, fixed in self.table.get(dependency.version or "", [])
        ]
        return findings, AdvisorySyncResult(
            queried_packages=1,
            matched_advisories=len(findings),
            cached_advisories=0,
            errors=[] if self.complete else ["OSV query failed: ConnectError"],
            complete=self.complete,
        )


class CodeScanner:
    """Reports B602 in app.py until a code patch is applied, when ``active``."""

    name = "fake"

    def __init__(self, repository: FakeRepository, active: bool) -> None:
        self.repository = repository
        self.active = active

    async def scan(self, snapshot: object) -> list[Finding]:
        fixed = any("app.py" in patch.changed_files for patch in self.repository.applied)
        if not self.active or fixed:
            return []
        return [
            Finding(
                id="b602",
                source=FindingSource.BANDIT,
                rule_id="B602",
                severity=Severity.HIGH,
                title="B602",
                message="B602",
                file_path="app.py",
                line=1,
            )
        ]


class RecordingProvider:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    async def propose_patch(
        self, snapshot: object, findings: list[Finding], *args: object
    ) -> PatchProposal:
        self.calls.append([item.rule_id for item in findings])
        return PatchProposal(
            unified_diff=CODE_DIFF,
            changed_files=["app.py"],
            finding_ids=["b602"],
            explanation="Disabled the shell.",
        )


class Registry:
    def __init__(self, provider: RecordingProvider) -> None:
        self.provider = provider

    def for_model(self, model: str | None) -> RecordingProvider:
        return self.provider


async def run_graph(
    tmp_path: Path,
    table: Advisories,
    *,
    complete: bool = True,
    code_finding: bool = False,
) -> tuple[RunRecord, FakeRepository, FakeAdvisories, RecordingProvider]:
    store = SQLiteRunStore(tmp_path / "orod.sqlite3")
    await store.initialize()
    repository = FakeRepository(tmp_path)
    advisories = FakeAdvisories(table, complete)
    provider = RecordingProvider()
    services = AgentServices(
        settings=Settings(require_human_approval=False, enable_github_publish=False),
        store=store,  # type: ignore[arg-type]
        repository=repository,  # type: ignore[arg-type]
        scanners=[CodeScanner(repository, code_finding)],
        vulnerabilities=advisories,
        vector_store=None,  # type: ignore[arg-type]
        llm=provider,  # type: ignore[arg-type]
        llms=Registry(provider),  # type: ignore[arg-type]
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
    return record, repository, advisories, provider


VULNERABLE: Advisories = {
    "5.3.1": [
        ("GHSA-8q59-q68h-6hv4", Severity.CRITICAL, ["5.4"]),
        ("PYSEC-2021-142", Severity.MEDIUM, ["5.4"]),
    ],
    "5.4": [],
}


async def test_a_pin_upgrade_clears_the_selected_advisories(tmp_path: Path) -> None:
    record, repository, advisories, provider = await run_graph(tmp_path, VULNERABLE)

    assert record.validation is not None
    assert record.validation.passed is True, record.validation.summary
    assert record.patch is not None
    assert record.patch.changed_files == ["requirements.txt"]
    assert "PyYAML 5.3.1 -> 5.4" in record.patch.explanation
    assert repository.version == "5.4"
    # Initial lookup, then the rescan of the changed manifest.
    assert advisories.queries == ["5.3.1", "5.4"]
    # No code finding was selected, so no model was asked.
    assert provider.calls == []


async def test_an_upgrade_the_rescan_still_matches_is_unresolved(tmp_path: Path) -> None:
    table: Advisories = {
        "5.3.1": [("GHSA-a", Severity.HIGH, ["5.4"])],
        # OSV is authoritative: the chosen version turns out to be affected too.
        "5.4": [("GHSA-a", Severity.HIGH, ["5.4"])],
    }
    record, *_ = await run_graph(tmp_path, table)

    assert record.validation is not None
    assert record.validation.passed is False
    assert (
        record.validation.summary
        == "Patch did not resolve selected findings: GHSA-a in requirements.txt"
    )


async def test_an_upgrade_into_a_new_high_advisory_is_refused(tmp_path: Path) -> None:
    table: Advisories = {
        "5.3.1": [("GHSA-a", Severity.HIGH, ["5.4"])],
        "5.4": [("GHSA-b", Severity.CRITICAL, ["5.5"])],
    }
    record, *_ = await run_graph(tmp_path, table)

    assert record.validation is not None
    assert record.validation.passed is False
    assert "new high/critical security findings: GHSA-b in requirements.txt" in (
        record.validation.summary
    )


async def test_advisories_from_an_incomplete_lookup_are_not_remediated(tmp_path: Path) -> None:
    record, repository, _, _ = await run_graph(tmp_path, VULNERABLE, complete=False)

    assert {item.rule_id for item in record.findings} == {
        "GHSA-8q59-q68h-6hv4",
        "PYSEC-2021-142",
    }
    assert record.patch is None
    assert repository.applied == []


async def test_a_code_fix_and_a_pin_upgrade_form_one_patch(tmp_path: Path) -> None:
    record, repository, _, provider = await run_graph(tmp_path, VULNERABLE, code_finding=True)

    # The provider sees the code finding only, never the advisories.
    assert provider.calls == [["B602"]]
    assert record.validation is not None
    assert record.validation.passed is True, record.validation.summary
    assert record.patch is not None
    assert record.patch.changed_files == ["app.py", "requirements.txt"]
    assert record.patch.unified_diff.startswith(CODE_DIFF)
    assert "+PyYAML==5.4\n" in record.patch.unified_diff
    assert record.patch.explanation.startswith("Disabled the shell. Upgraded PyYAML")
    assert len(repository.applied) == 1
