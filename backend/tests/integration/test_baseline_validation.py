"""Validation against the base revision, with the real compileall, Ruff and pytest."""

import difflib
import sys
from pathlib import Path

import pytest

from orod.adapters.execution.subprocess import SafeCommandRunner
from orod.adapters.repository.git import GitRepositoryAdapter
from orod.config import Settings
from orod.domain.errors import WorkspaceIntegrityError
from orod.domain.models import PatchProposal, RepositorySnapshot

APP = "import os\n\n\ndef add(a, b):\n    return a + b\n"
TESTS = (
    "from app import add\n\n\n"
    "def test_add():\n    assert add(1, 2) == 3\n\n\n"
    "def test_known_broken():\n    assert add(1, 1) == 3\n"
)


async def make_repository(
    tmp_path: Path, files: dict[str, str]
) -> tuple[GitRepositoryAdapter, RepositorySnapshot, Path]:
    root = tmp_path / "repo"
    for relative, content in files.items():
        (root / relative).parent.mkdir(parents=True, exist_ok=True)
        (root / relative).write_text(content)
    runner = SafeCommandRunner({sys.executable, "git"}, tmp_path)
    for argv in (
        ["git", "init", "-b", "main"],
        ["git", "add", "."],
        ["git", "-c", "user.name=T", "-c", "user.email=t@example.invalid", "commit", "-m", "b"],
    ):
        assert (await runner.run(argv, root)).return_code == 0
    adapter = GitRepositoryAdapter(Settings(workspace_root=tmp_path), runner)
    snapshot = RepositorySnapshot(
        repository_url="demo://baseline", workspace_path=str(root), trusted=True
    )
    return adapter, snapshot, root


def edit(root: Path, path: str, before: str, after: str) -> PatchProposal:
    original = (root / path).read_text()
    updated = original.replace(before, after, 1)
    assert updated != original
    diff = "".join(
        difflib.unified_diff(
            original.splitlines(keepends=True),
            updated.splitlines(keepends=True),
            fromfile=f"a/{path}",
            tofile=f"b/{path}",
        )
    )
    return PatchProposal(unified_diff=diff, changed_files=[path], finding_ids=[], explanation="t")


@pytest.fixture
async def legacy_repository(tmp_path: Path) -> tuple[GitRepositoryAdapter, RepositorySnapshot]:
    # An unused import and a failing test already exist before any patch.
    adapter, snapshot, _ = await make_repository(
        tmp_path, {"app.py": APP, "tests/test_app.py": TESTS}
    )
    return adapter, snapshot


async def test_pre_existing_failures_do_not_block_a_clean_patch(
    legacy_repository: tuple[GitRepositoryAdapter, RepositorySnapshot],
) -> None:
    adapter, snapshot = legacy_repository
    baseline = await adapter.record_baseline(snapshot)
    assert baseline is not None

    # Strict validation cannot pass this repository even without a patch.
    assert not (await adapter.validate(snapshot)).passed
    await adapter.apply_patch(
        snapshot,
        edit(Path(snapshot.workspace_path), "app.py", "import os", "import os  # noqa: F401"),
    )
    result = await adapter.validate(snapshot, baseline)

    assert result.passed, result.summary
    assert result.tolerated_failures == 1
    assert result.tests_ran is True
    assert "pre-existing failure" in result.summary


async def test_a_newly_failing_test_fails_validation(
    legacy_repository: tuple[GitRepositoryAdapter, RepositorySnapshot],
) -> None:
    adapter, snapshot = legacy_repository
    baseline = await adapter.record_baseline(snapshot)
    # Same length as the original line: the patched file keeps its size, which is what
    # let timestamp-validated bytecode from the baseline run hide this change.
    patch = edit(Path(snapshot.workspace_path), "app.py", "return a + b", "return a - b")
    await adapter.apply_patch(snapshot, patch)

    result = await adapter.validate(snapshot, baseline)

    assert not result.passed
    assert "pytest: failed tests/test_app.py::test_add" in result.summary


async def test_new_lint_fails_validation(
    legacy_repository: tuple[GitRepositoryAdapter, RepositorySnapshot],
) -> None:
    adapter, snapshot = legacy_repository
    baseline = await adapter.record_baseline(snapshot)
    await adapter.apply_patch(
        snapshot, edit(Path(snapshot.workspace_path), "app.py", "import os", "import os, sys")
    )

    result = await adapter.validate(snapshot, baseline)

    assert not result.passed
    assert "ruff: F401 app.py `sys` imported but unused" in result.summary


async def test_tests_outside_a_tests_directory_are_run(tmp_path: Path) -> None:
    adapter, snapshot, _ = await make_repository(
        tmp_path,
        {
            "app.py": "def add(a, b):\n    return a + b\n",
            "test_app.py": "from app import add\n\n\ndef test_add():\n    assert add(1, 2) == 3\n",
        },
    )

    result = await adapter.validate(snapshot, await adapter.record_baseline(snapshot))

    assert result.passed, result.summary
    assert result.tests_ran is True
    pytest_check = next(check for check in result.checks if check.name == "pytest")
    assert pytest_check.passed_tests == 1


async def test_a_repository_without_tests_says_so(tmp_path: Path) -> None:
    adapter, snapshot, _ = await make_repository(tmp_path, {"app.py": "value = 1\n"})

    result = await adapter.validate(snapshot, await adapter.record_baseline(snapshot))

    assert result.passed
    assert result.tests_ran is False
    assert "No tests were collected" in result.summary


async def test_the_baseline_requires_the_untouched_base_revision(
    legacy_repository: tuple[GitRepositoryAdapter, RepositorySnapshot],
) -> None:
    adapter, snapshot = legacy_repository
    await adapter.apply_patch(
        snapshot,
        edit(Path(snapshot.workspace_path), "app.py", "import os", "import os  # noqa: F401"),
    )

    with pytest.raises(WorkspaceIntegrityError, match="base revision"):
        await adapter.record_baseline(snapshot)


async def test_no_baseline_without_consent(tmp_path: Path) -> None:
    adapter, snapshot, _ = await make_repository(tmp_path, {"app.py": "value = 1\n"})

    assert await adapter.record_baseline(snapshot.model_copy(update={"trusted": False})) is None
