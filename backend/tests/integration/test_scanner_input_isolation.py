"""External scanners walk a filtered copy of the workspace, never the workspace itself."""

import sys
from pathlib import Path

import pytest

from orod.adapters.execution.subprocess import SafeCommandRunner
from orod.adapters.repository import files
from orod.adapters.scanners.bandit import BanditScanner
from orod.adapters.scanners.semgrep import SemgrepScanner
from orod.domain.errors import UnsafePathError
from orod.domain.models import CommandResult, RepositorySnapshot

EVAL = "value = eval(input())\n"


def repository(tmp_path: Path) -> tuple[Path, Path]:
    """A workspace whose unsafe entries each hold code Bandit reports."""
    workspace = tmp_path / "workspaces"
    root = workspace / "run"
    (root / "pkg").mkdir(parents=True)
    (root / "pkg" / "app.py").write_text(EVAL)
    outside = tmp_path / "outside.py"
    outside.write_text(EVAL)
    (root / "linked.py").symlink_to(outside)
    (root / "linked_dir").symlink_to(tmp_path, target_is_directory=True)
    (root / ".hidden").mkdir()
    (root / ".hidden" / "tool.py").write_text(EVAL)
    (root / "venv").mkdir()
    (root / "venv" / "vendored.py").write_text(EVAL)
    (root / "oversized.py").write_text(EVAL + "#" * 2_000)
    (root / ".semgrepignore").write_text("pkg/\n")
    return workspace, root


def snapshot(root: Path) -> RepositorySnapshot:
    return RepositorySnapshot(
        repository_url="https://github.com/example/project", workspace_path=str(root)
    )


async def test_bandit_reports_only_files_the_policy_accepts(tmp_path: Path) -> None:
    workspace, root = repository(tmp_path)
    runner = SafeCommandRunner({sys.executable}, workspace)

    findings = await BanditScanner(runner, 1_000, workspace).scan(snapshot(root))

    # Before: the file symlink (read from outside the workspace), the hidden and ignored
    # directories and the oversized file were all scanned, at paths no patch may touch.
    assert {(item.rule_id, item.file_path) for item in findings} == {("B307", "pkg/app.py")}
    assert [path.name for path in workspace.iterdir()] == ["run"]


class InspectingRunner:
    """Records what the scanner's working directory held when the command ran."""

    def __init__(self, stdout: str) -> None:
        self.stdout = stdout
        self.cwd: Path | None = None
        self.seen: list[str] = []

    async def run(self, argv: list[str], cwd: Path, **_: object) -> CommandResult:
        self.cwd = cwd
        self.seen = sorted(
            path.relative_to(cwd).as_posix() for path in cwd.rglob("*") if path.is_file()
        )
        return CommandResult(argv=argv, return_code=0, stdout=self.stdout)


async def test_semgrep_never_sees_repository_ignore_files_or_links(tmp_path: Path) -> None:
    workspace, root = repository(tmp_path)
    runner = InspectingRunner('{"results": [{"check_id": "r", "path": "pkg/app.py"}]}')

    findings = await SemgrepScanner(runner, 1_000, workspace).scan(snapshot(root))  # type: ignore[arg-type]

    # A .semgrepignore could otherwise decide which repository files are scanned.
    assert runner.seen == ["pkg/app.py"]
    assert runner.cwd is not None and runner.cwd.parent == workspace.resolve()
    assert not runner.cwd.exists()
    assert [item.file_path for item in findings] == ["pkg/app.py"]


async def test_a_repository_beyond_the_copy_limits_fails_the_scan(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace, root = repository(tmp_path)
    (root / "second.py").write_text("x = 1\n")
    monkeypatch.setattr(files, "COPY_MAX_FILES", 1)
    runner = InspectingRunner('{"results": []}')

    with pytest.raises(UnsafePathError, match="size limits"):
        await BanditScanner(runner, 1_000, workspace).scan(snapshot(root))  # type: ignore[arg-type]

    assert runner.cwd is None
    assert [path.name for path in workspace.iterdir()] == ["run"]
