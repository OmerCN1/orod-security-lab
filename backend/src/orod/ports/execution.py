from __future__ import annotations

from pathlib import Path
from typing import Protocol

from orod.domain.models import CommandResult


class CommandRunner(Protocol):
    async def run(
        self,
        argv: list[str],
        cwd: Path,
        *,
        input_text: str | None = None,
        timeout_seconds: int | None = None,
        max_output_chars: int | None = None,
    ) -> CommandResult: ...
