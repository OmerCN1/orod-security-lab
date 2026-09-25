from pathlib import Path

import pytest

from orod.adapters.github.cli import GitHubCLIPublisher
from orod.domain.errors import OrodError
from orod.domain.models import PatchProposal, RepositorySnapshot, ValidationResult


class NoopRunner:
    async def run(self, *args: object, **kwargs: object) -> object:
        raise AssertionError("publisher must reject before executing Git commands")


async def test_publisher_rejects_failed_validation(tmp_path: Path) -> None:
    publisher = GitHubCLIPublisher(NoopRunner())  # type: ignore[arg-type]
    snapshot = RepositorySnapshot(
        repository_url="https://github.com/example/project",
        workspace_path=str(tmp_path),
        permission="WRITE",
        trusted=True,
    )
    patch = PatchProposal(
        unified_diff="--- a/app.py\n+++ b/app.py\n",
        changed_files=["app.py"],
        finding_ids=["finding"],
        explanation="demo",
    )

    with pytest.raises(OrodError, match="unvalidated"):
        await publisher.publish(
            snapshot,
            patch,
            ValidationResult(passed=False),
            "run-id",
        )


async def test_publisher_rejects_missing_write_permission(tmp_path: Path) -> None:
    publisher = GitHubCLIPublisher(NoopRunner())  # type: ignore[arg-type]
    snapshot = RepositorySnapshot(
        repository_url="https://github.com/example/project",
        workspace_path=str(tmp_path),
        permission="READ",
        trusted=True,
    )
    patch = PatchProposal(
        unified_diff="--- a/app.py\n+++ b/app.py\n",
        changed_files=["app.py"],
        finding_ids=["finding"],
        explanation="demo",
    )

    with pytest.raises(OrodError, match="write permission"):
        await publisher.publish(
            snapshot,
            patch,
            ValidationResult(passed=True),
            "run-id",
        )
