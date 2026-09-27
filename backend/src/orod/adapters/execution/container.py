"""Run fixed validation commands in a disposable, offline container."""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path
from uuid import uuid4

from orod.adapters.execution.subprocess import SafeCommandRunner
from orod.adapters.repository.files import RepositoryFiles
from orod.adapters.repository.validation_checks import CHECKS
from orod.config import Settings
from orod.domain.errors import CommandRejectedError, UnsafePathError
from orod.domain.models import CommandResult
from orod.ports.execution import CommandRunner

# The image's entrypoint keeps its own copy of this allowlist; a test keeps them equal.
VALIDATION_ARGS = frozenset(check.args for check in CHECKS)


class ContainerCommandRunner:
    def __init__(self, settings: Settings, host_runner: CommandRunner | None = None) -> None:
        self._settings = settings
        self._root = settings.workspace_root.expanduser().resolve()
        self._docker = shutil.which("docker") or "docker"
        self._host = host_runner or SafeCommandRunner(
            {self._docker}, self._root, settings.command_timeout_seconds
        )

    async def run(
        self,
        argv: list[str],
        cwd: Path,
        *,
        input_text: str | None = None,
        timeout_seconds: int | None = None,
        max_output_chars: int | None = None,
    ) -> CommandResult:
        if not argv or argv[0] != sys.executable or tuple(argv[1:]) not in VALIDATION_ARGS:
            raise CommandRejectedError("unsupported container validation command")
        if input_text is not None:
            raise CommandRejectedError("container validation does not accept stdin")
        root = Path(os.path.abspath(cwd))
        if not root.is_relative_to(self._root) or root == self._root:
            raise UnsafePathError("validation cwd escaped run workspace")
        name = f"orod-validation-{uuid4().hex}"
        try:
            with tempfile.TemporaryDirectory(prefix="orod-validation-") as directory:
                source = Path(directory).resolve()
                self._copy_input(root, source)
                source.chmod(0o755)
                command = [
                    self._docker,
                    "run",
                    "--rm",
                    "--log-driver=none",
                    "--pull=never",
                    "--name",
                    name,
                    "--network=none",
                    "--read-only",
                    "--cap-drop=ALL",
                    "--security-opt=no-new-privileges",
                    "--user=65532:65532",
                    "--pids-limit=128",
                    "--memory=512m",
                    "--memory-swap=512m",
                    "--cpus=1",
                    "--tmpfs",
                    "/tmp:rw,noexec,nosuid,size=64m",  # noqa: S108 -- private tmpfs
                    "--tmpfs",
                    "/workspace:rw,nosuid,size=128m,uid=65532,gid=65532,mode=0700",
                    "--mount",
                    f"type=bind,src={source},dst=/input,readonly",
                    self._settings.validation_image,
                    *argv[1:],
                ]
                try:
                    result = await self._host.run(
                        command,
                        root,
                        timeout_seconds=timeout_seconds,
                        max_output_chars=max_output_chars,
                    )
                finally:
                    # Also remove a running container after timeout/cancellation of the CLI.
                    await self._host.run(
                        [self._docker, "rm", "--force", name], root, timeout_seconds=10
                    )
                return result.model_copy(update={"argv": argv})
        except OSError:
            return CommandResult(
                argv=argv,
                return_code=125,
                stderr="Container validation unavailable; install Docker and build its image.",
            )

    def _copy_input(self, root: Path, destination: Path) -> None:
        """Never mount the original repo, credentials, symlinks or special files."""
        total_bytes = 0
        files = 0
        reader = RepositoryFiles(root, self._settings.max_file_bytes, workspace_root=self._root)
        for item in reader.iter_files():
            total_bytes += item.size
            files += 1
            if total_bytes > 100_000_000 or files > 2_000:
                raise CommandRejectedError("validation input exceeds workspace limits")
            target = destination / item.relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(item.content.encode("utf-8"))
            target.chmod(0o644)
