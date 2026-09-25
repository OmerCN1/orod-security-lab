import sys
from pathlib import Path

import pytest

from orod.adapters.execution.subprocess import SafeCommandRunner
from orod.domain.errors import CommandRejectedError, UnsafePathError


async def test_command_runner_rejects_unknown_executable(tmp_path: Path) -> None:
    workspace = tmp_path / "workspaces"
    workspace.mkdir()
    runner = SafeCommandRunner({sys.executable}, workspace)

    with pytest.raises(CommandRejectedError):
        await runner.run(["sh", "-c", "echo unsafe"], workspace)


async def test_command_runner_rejects_cwd_escape(tmp_path: Path) -> None:
    workspace = tmp_path / "workspaces"
    workspace.mkdir()
    runner = SafeCommandRunner({sys.executable}, workspace)

    with pytest.raises(UnsafePathError):
        await runner.run([sys.executable, "--version"], tmp_path)


async def test_command_runner_allows_larger_structured_output_limit(tmp_path: Path) -> None:
    workspace = tmp_path / "workspaces"
    workspace.mkdir()
    runner = SafeCommandRunner({sys.executable}, workspace)
    result = await runner.run(
        [sys.executable, "-c", "print('x' * 30000)"],
        workspace,
        max_output_chars=40_000,
    )

    assert result.return_code == 0
    assert len(result.stdout.strip()) == 30_000
