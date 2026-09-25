from __future__ import annotations

import asyncio
import os
import time
from pathlib import Path

from orod.domain.errors import CommandRejectedError, UnsafePathError
from orod.domain.models import CommandResult


class SafeCommandRunner:
    def __init__(
        self,
        allowed_executables: set[str],
        workspace_root: Path,
        default_timeout_seconds: int = 120,
    ) -> None:
        self._allowed = allowed_executables
        self._workspace_root = workspace_root.expanduser().resolve()
        self._default_timeout = default_timeout_seconds

    async def run(
        self,
        argv: list[str],
        cwd: Path,
        *,
        input_text: str | None = None,
        timeout_seconds: int | None = None,
        max_output_chars: int | None = None,
    ) -> CommandResult:
        if not argv or argv[0] not in self._allowed:
            raise CommandRejectedError(f"executable is not allowed: {argv[0] if argv else ''}")

        resolved_cwd = cwd.resolve()
        if not resolved_cwd.is_relative_to(self._workspace_root):
            raise UnsafePathError("command cwd escaped workspace root")

        safe_env = {
            key: value
            for key, value in os.environ.items()
            if key in {"PATH", "HOME", "TMPDIR", "LANG", "LC_ALL", "GIT_CONFIG_GLOBAL"}
        }
        safe_env.update({"PYTHONUNBUFFERED": "1", "PIP_DISABLE_PIP_VERSION_CHECK": "1"})

        start = time.monotonic()
        process = await asyncio.create_subprocess_exec(
            *argv,
            cwd=resolved_cwd,
            env=safe_env,
            stdin=asyncio.subprocess.PIPE if input_text is not None else asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        timed_out = False
        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(input_text.encode() if input_text is not None else None),
                timeout=timeout_seconds or self._default_timeout,
            )
        except TimeoutError:
            timed_out = True
            process.kill()
            stdout, stderr = await process.communicate()

        duration_ms = int((time.monotonic() - start) * 1000)
        output_limit = max_output_chars or 20_000
        return CommandResult(
            argv=argv,
            return_code=process.returncode if process.returncode is not None else 124,
            stdout=stdout.decode(errors="replace")[-output_limit:],
            stderr=stderr.decode(errors="replace")[-output_limit:],
            duration_ms=duration_ms,
            timed_out=timed_out,
        )
