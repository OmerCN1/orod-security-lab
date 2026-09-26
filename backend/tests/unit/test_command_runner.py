import asyncio
import os
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


async def test_output_is_drained_with_bounded_tails(tmp_path: Path) -> None:
    runner = SafeCommandRunner({sys.executable}, tmp_path)
    result = await runner.run(
        [
            sys.executable,
            "-c",
            "import sys; print('x' * 1000000 + 'END'); "
            "print('y' * 1000000 + 'ERR', file=sys.stderr)",
        ],
        tmp_path,
        max_output_chars=100,
    )
    assert result.return_code == 0
    assert result.stdout.endswith("END\n") and len(result.stdout) == 100
    assert result.stderr.endswith("ERR\n") and len(result.stderr) == 100


async def test_timeout_kills_child_holding_output_pipes(tmp_path: Path) -> None:
    runner = SafeCommandRunner({sys.executable}, tmp_path)
    result = await asyncio.wait_for(
        runner.run(
            [
                sys.executable,
                "-c",
                "import subprocess, sys; subprocess.Popen([sys.executable, '-c', "
                "'import time; time.sleep(60)']); print('started', flush=True)",
            ],
            tmp_path,
            timeout_seconds=1,
        ),
        timeout=5,
    )
    assert result.timed_out
    assert "started" in result.stdout


async def test_cancellation_reaps_the_process(tmp_path: Path) -> None:
    runner = SafeCommandRunner({sys.executable}, tmp_path)
    marker = tmp_path / "pid.txt"
    task = asyncio.create_task(
        runner.run(
            [
                sys.executable,
                "-c",
                "import os, pathlib, time; "
                "pathlib.Path('pid.txt').write_text(str(os.getpid())); time.sleep(60)",
            ],
            tmp_path,
        )
    )
    try:
        async with asyncio.timeout(5):
            while not marker.exists():  # noqa: ASYNC110 -- waiting for a child process file
                await asyncio.sleep(0.01)
    finally:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    with pytest.raises(ProcessLookupError):
        os.kill(int(marker.read_text()), 0)
