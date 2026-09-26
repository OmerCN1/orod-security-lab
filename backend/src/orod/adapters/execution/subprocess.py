from __future__ import annotations

import asyncio
import os
import signal
import time
from contextlib import suppress
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
            start_new_session=True,
        )
        output_limit = max_output_chars or 20_000

        async def read_tail(stream: asyncio.StreamReader | None) -> bytes:
            assert stream is not None
            output = bytearray()
            # Bound memory while draining, rather than truncating an unbounded communicate().
            byte_limit = output_limit * 4
            while chunk := await stream.read(65_536):
                output.extend(chunk)
                if len(output) > byte_limit:
                    del output[:-byte_limit]
            return bytes(output)

        async def write_input() -> None:
            if process.stdin is not None:
                with suppress(BrokenPipeError, ConnectionResetError):
                    process.stdin.write((input_text or "").encode())
                    await process.stdin.drain()
                process.stdin.close()

        async def communicate() -> tuple[bytes, bytes]:
            stdout, stderr, _, _ = await asyncio.gather(
                read_tail(process.stdout), read_tail(process.stderr), write_input(), process.wait()
            )
            return stdout, stderr

        def kill_group() -> None:
            with suppress(ProcessLookupError):
                os.killpg(process.pid, signal.SIGKILL)

        communication = asyncio.create_task(communicate())
        timed_out = False
        try:
            stdout, stderr = await asyncio.wait_for(
                asyncio.shield(communication),
                timeout=timeout_seconds or self._default_timeout,
            )
        except TimeoutError:
            timed_out = True
            kill_group()
            stdout, stderr = await communication
        except asyncio.CancelledError:
            kill_group()
            await communication
            raise

        duration_ms = int((time.monotonic() - start) * 1000)
        return CommandResult(
            argv=argv,
            return_code=process.returncode if process.returncode is not None else 124,
            stdout=stdout.decode(errors="replace")[-output_limit:],
            stderr=stderr.decode(errors="replace")[-output_limit:],
            duration_ms=duration_ms,
            timed_out=timed_out,
        )
