import asyncio
import sys
from pathlib import Path

import pytest

from orod.adapters.execution.container import ContainerCommandRunner
from orod.adapters.repository.git import GitRepositoryAdapter
from orod.config import Settings
from orod.domain.errors import CommandRejectedError, UnsafePathError
from orod.domain.models import CommandResult, RepositorySnapshot, RunCreate


class RecordingRunner:
    def __init__(self, *, fail: bool = False, cancel: bool = False) -> None:
        self.calls: list[list[str]] = []
        self.fail = fail
        self.cancel = cancel

    async def run(self, argv: list[str], cwd: Path, **_: object) -> CommandResult:
        self.calls.append(argv)
        if "run" in argv:
            mount = argv[argv.index("--mount") + 1]
            source = Path(mount.split("src=", 1)[1].split(",dst=", 1)[0])
            assert (source / "app.py").read_text() == "value = 1\n"
            assert not (source / ".env").exists()
            assert not (source / ".git").exists()
            assert not (source / "alias.py").exists()
            if self.cancel:
                raise asyncio.CancelledError
        return CommandResult(argv=argv, return_code=125 if self.fail else 0)


@pytest.mark.parametrize("trusted", [False, True])
async def test_remote_validation_requires_consent_and_only_uses_container(
    tmp_path: Path,
    trusted: bool,
) -> None:
    root = tmp_path / "repo"
    (root / "tests").mkdir(parents=True)
    host = RecordingRunner()
    sandbox = RecordingRunner()
    adapter = GitRepositoryAdapter(Settings(workspace_root=tmp_path), host, sandbox)
    snapshot = RepositorySnapshot(
        repository_url="https://github.com/example/project",
        workspace_path=str(root),
        trusted=trusted,
        permission="WRITE",
    )
    result = await adapter.validate(snapshot)
    assert result.passed is trusted
    assert not host.calls
    assert len(sandbox.calls) == (4 if trusted else 0)


async def test_container_failure_never_falls_back_to_host(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    host = RecordingRunner()
    sandbox = RecordingRunner(fail=True)
    adapter = GitRepositoryAdapter(Settings(workspace_root=tmp_path), host, sandbox)
    snapshot = RepositorySnapshot(
        repository_url="https://github.com/example/project",
        workspace_path=str(root),
        trusted=True,
    )
    assert not (await adapter.validate(snapshot)).passed
    assert len(sandbox.calls) == 1
    assert not host.calls


async def test_absent_isolation_runner_never_executes_remote_repo_locally(tmp_path: Path) -> None:
    host = RecordingRunner()
    adapter = GitRepositoryAdapter(Settings(workspace_root=tmp_path), host)
    result = await adapter.validate(
        RepositorySnapshot(
            repository_url="https://github.com/example/project",
            workspace_path=str(tmp_path),
            trusted=True,
        )
    )
    assert not result.passed
    assert "not configured" in result.summary
    assert not host.calls


@pytest.mark.parametrize("trusted", [False, True])
async def test_fixture_does_not_grant_itself_trust(tmp_path: Path, trusted: bool) -> None:
    source = tmp_path / "fixtures" / "sample"
    source.mkdir(parents=True)
    (source / "app.py").write_text("value = 1\n")
    workspace = tmp_path / "workspaces"
    workspace.mkdir()
    host = RecordingRunner()
    sandbox = RecordingRunner()
    adapter = GitRepositoryAdapter(
        Settings(workspace_root=workspace, fixture_root=source.parent), host, sandbox
    )
    snapshot = await adapter.prepare("demo://sample", None, "run", trusted)
    assert snapshot.trusted is trusted
    host.calls.clear()
    assert (await adapter.validate(snapshot)).passed is trusted
    assert len(host.calls) == (3 if trusted else 0)
    assert not sandbox.calls
    assert RunCreate(repository_url="demo://sample").trusted is False


@pytest.mark.parametrize("cancel", [False, True])
async def test_container_has_limits_and_cleans_up_even_on_cancellation(
    tmp_path: Path,
    cancel: bool,
) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    (root / "app.py").write_text("value = 1\n")
    (root / ".env").write_text("SYNTHETIC_TEST_DATA=1\n")
    (root / ".git").mkdir()
    (root / "alias.py").symlink_to(root / "app.py")
    host = RecordingRunner(cancel=cancel)
    runner = ContainerCommandRunner(Settings(workspace_root=tmp_path), host)
    if cancel:
        with pytest.raises(asyncio.CancelledError):
            await runner.run([sys.executable, "-m", "pytest", "-q"], root)
    else:
        assert (await runner.run([sys.executable, "-m", "pytest", "-q"], root)).return_code == 0
    command = host.calls[0]
    assert {
        "--network=none",
        "--read-only",
        "--cap-drop=ALL",
        "--pull=never",
        "--security-opt=no-new-privileges",
        "--user=65532:65532",
        "--pids-limit=128",
        "--memory=512m",
        "--memory-swap=512m",
        "--cpus=1",
    } <= set(command)
    assert command[command.index("--mount") + 1].endswith(",dst=/input,readonly")
    name = command[command.index("--name") + 1]
    assert host.calls[-1][1:] == ["rm", "--force", name]
    mount = command[command.index("--mount") + 1]
    assert not Path(mount.split("src=", 1)[1].split(",dst=", 1)[0]).exists()


async def test_container_rejects_unapproved_commands_and_workspace_escape(tmp_path: Path) -> None:
    root = tmp_path / "workspaces"
    root.mkdir()
    host = RecordingRunner()
    runner = ContainerCommandRunner(Settings(workspace_root=root), host)
    with pytest.raises(CommandRejectedError):
        await runner.run([sys.executable, "-c", "print('arbitrary')"], root)
    with pytest.raises(UnsafePathError):
        await runner.run([sys.executable, "-m", "pytest", "-q"], tmp_path)
    assert not host.calls
