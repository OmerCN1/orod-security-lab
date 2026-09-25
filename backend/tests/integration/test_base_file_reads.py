import subprocess
from pathlib import Path

import pytest

from orod.adapters.execution.subprocess import SafeCommandRunner
from orod.adapters.repository.git import GitRepositoryAdapter
from orod.config import Settings
from orod.domain.errors import UnsafePathError
from orod.domain.models import RepositorySnapshot

# Comfortably above the command runner's 20k default output limit.
LARGE_FILE_LINES = 1500


def build_repository(root: Path, content: str) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "app.py").write_text(content)
    for argv in (
        ["git", "init", "-b", "main"],
        ["git", "config", "user.email", "orod@example.invalid"],
        ["git", "config", "user.name", "OROD Test"],
        ["git", "add", "."],
        ["git", "commit", "-m", "baseline"],
    ):
        # Fixed argv, test-owned directory, no interpolated input.
        subprocess.run(argv, cwd=root, check=True, capture_output=True)  # noqa: S603, S607


async def test_base_read_returns_the_head_of_a_large_file(tmp_path: Path) -> None:
    """The command runner truncates stdout from the tail, so an unbudgeted read would
    return a large file's ending while the working-tree read returned its beginning -
    the two sides of the diff would not line up."""
    workspace = tmp_path / "workspaces"
    repo = workspace / "run-1"
    original = "".join(
        f"ORIGINAL_LINE_{index:05d} = {index}\n" for index in range(LARGE_FILE_LINES)
    )
    build_repository(repo, original)
    (repo / "app.py").write_text(original.replace("ORIGINAL_LINE_00000", "PATCHED_LINE_00000"))

    settings = Settings(workspace_root=workspace)
    runner = SafeCommandRunner(
        allowed_executables={"git"}, workspace_root=workspace, default_timeout_seconds=30
    )
    adapter = GitRepositoryAdapter(settings, runner)
    snapshot = RepositorySnapshot(repository_url="demo://x", workspace_path=str(repo), trusted=True)

    assert len(original) > 20_000, "fixture must exceed the runner's default output limit"

    base = await adapter.read_base_files(snapshot, ["app.py"])
    working = await adapter.read_files(snapshot, ["app.py"], max_chars=100_000)

    assert base["app.py"].startswith("ORIGINAL_LINE_00000")
    assert working["app.py"].startswith("PATCHED_LINE_00000")
    assert base["app.py"] == original


async def test_base_read_refuses_to_escape_the_workspace(tmp_path: Path) -> None:
    workspace = tmp_path / "workspaces"
    repo = workspace / "run-1"
    build_repository(repo, "value = 1\n")
    settings = Settings(workspace_root=workspace)
    runner = SafeCommandRunner(
        allowed_executables={"git"}, workspace_root=workspace, default_timeout_seconds=30
    )
    adapter = GitRepositoryAdapter(settings, runner)
    snapshot = RepositorySnapshot(repository_url="demo://x", workspace_path=str(repo), trusted=True)

    with pytest.raises(UnsafePathError):
        await adapter.read_base_files(snapshot, ["../../etc/passwd"])
