from pathlib import Path

import pytest

from orod.adapters.github.cli import GitHubCLIPublisher
from orod.adapters.repository.patches import WORKING_DIFF_ARGV
from orod.domain.errors import OrodError
from orod.domain.models import (
    CommandResult,
    PatchProposal,
    RepositorySnapshot,
    ValidationResult,
)


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


class ScriptedRunner:
    """Answers the publisher's commands from a script and records what it ran."""

    def __init__(self, working_diff: str, changed_names: list[str]) -> None:
        self.working_diff = working_diff
        self.changed_names = changed_names
        self.commands: list[list[str]] = []

    async def run(self, argv: list[str], cwd: Path, **kwargs: object) -> CommandResult:
        self.commands.append(argv)
        if argv[:3] == ["gh", "pr", "view"]:
            return CommandResult(argv=argv, return_code=1)
        if tuple(argv) == WORKING_DIFF_ARGV:
            return CommandResult(argv=argv, return_code=0, stdout=self.working_diff)
        if argv[:3] == ["git", "diff", "--name-only"]:
            names = "".join(f"{name}\x00" for name in self.changed_names)
            return CommandResult(argv=argv, return_code=0, stdout=names)
        if argv[:3] == ["gh", "pr", "create"]:
            return CommandResult(
                argv=argv, return_code=0, stdout="https://github.com/example/project/pull/7\n"
            )
        return CommandResult(argv=argv, return_code=0)


VALIDATED_DIFF = "--- a/app.py\n+++ b/app.py\n@@ -1 +1 @@\n-value = 1\n+value = 2\n"


def writable_snapshot(tmp_path: Path) -> RepositorySnapshot:
    return RepositorySnapshot(
        repository_url="https://github.com/example/project",
        workspace_path=str(tmp_path),
        permission="WRITE",
        trusted=True,
    )


def validated_patch() -> PatchProposal:
    return PatchProposal(
        unified_diff=VALIDATED_DIFF,
        changed_files=["app.py"],
        finding_ids=["finding"],
        explanation="demo",
    )


@pytest.mark.parametrize(
    ("working_diff", "names", "reason"),
    [
        # An earlier attempt's change is still in the tree; only app.py would be staged.
        (VALIDATED_DIFF + "--- a/other.py\n+++ b/other.py\n", ["app.py", "other.py"], "patch"),
        ("", [], "patch"),
        (VALIDATED_DIFF, ["app.py", "other.py"], "changed files"),
    ],
)
async def test_publisher_refuses_a_workspace_that_differs_from_the_validated_patch(
    tmp_path: Path, working_diff: str, names: list[str], reason: str
) -> None:
    runner = ScriptedRunner(working_diff, names)
    publisher = GitHubCLIPublisher(runner)  # type: ignore[arg-type]

    with pytest.raises(OrodError, match=reason):
        await publisher.publish(
            writable_snapshot(tmp_path),
            validated_patch(),
            ValidationResult(passed=True),
            "run-id",
        )
    assert not any(argv[:2] in (["git", "checkout"], ["git", "push"]) for argv in runner.commands)


async def test_publisher_commits_a_workspace_that_matches_the_validated_patch(
    tmp_path: Path,
) -> None:
    runner = ScriptedRunner(VALIDATED_DIFF, ["app.py"])
    publisher = GitHubCLIPublisher(runner)  # type: ignore[arg-type]

    result = await publisher.publish(
        writable_snapshot(tmp_path), validated_patch(), ValidationResult(passed=True), "run-id"
    )

    assert result.number == 7
    assert ["git", "add", "--", "app.py"] in runner.commands
