"""Strict parser for the supported subset of unified diffs: existing text files only."""

from __future__ import annotations

import re
from pathlib import PurePosixPath

from orod.domain.errors import PatchRejectedError

HUNK = re.compile(r"@@ -\d+(?:,(\d+))? \+\d+(?:,(\d+))? @@(?: .*)?")
INDEX = re.compile(r"index [0-9a-f]+\.\.[0-9a-f]+(?: 100(?:644|755))?")


def patch_targets(diff: str) -> set[str]:
    """Reject ambiguous headers, metadata operations and malformed/trailing content.

    Count hunk bodies before interpreting more headers: source lines that look like
    headers are data, not additional targets. Git still performs its own apply check.
    """
    if any(char in diff for char in ("\x00", "\r")) or not diff.endswith("\n"):
        raise PatchRejectedError("patch must be newline-terminated text")
    lines = diff.split("\n")[:-1]
    targets: set[str] = set()
    position = 0
    while position < len(lines):
        git_header: str | None = None
        if lines[position].startswith("diff --git "):
            git_header = lines[position]
            position += 1
            if position < len(lines) and INDEX.fullmatch(lines[position]):
                position += 1
        if position + 1 >= len(lines) or not lines[position].startswith("--- a/"):
            raise PatchRejectedError("unsupported patch header or metadata operation")
        relative = lines[position][6:]
        path = PurePosixPath(relative)
        if (
            not relative
            or path.is_absolute()
            or path.as_posix() != relative
            or any(part in {".", ".."} for part in path.parts)
            or any(ord(char) < 32 or ord(char) == 127 for char in relative)
            or '"' in relative
            or "\\" in relative
        ):
            raise PatchRejectedError("unsupported patch path")
        if lines[position + 1] != f"+++ b/{relative}":
            raise PatchRejectedError("patch must edit existing files without renaming")
        if git_header is not None and git_header != f"diff --git a/{relative} b/{relative}":
            raise PatchRejectedError("inconsistent diff headers")
        if relative in targets:
            raise PatchRejectedError("duplicate patch target")
        targets.add(relative)
        position += 2
        hunks = 0
        while position < len(lines) and (match := HUNK.fullmatch(lines[position])):
            hunks += 1
            old = int(match[1]) if match[1] is not None else 1
            new = int(match[2]) if match[2] is not None else 1
            position += 1
            while old or new:
                if position >= len(lines) or not lines[position]:
                    raise PatchRejectedError("truncated patch hunk")
                prefix = lines[position][0]
                if prefix not in {" ", "+", "-"}:
                    raise PatchRejectedError("invalid patch hunk")
                old -= prefix in {" ", "-"}
                new -= prefix in {" ", "+"}
                if old < 0 or new < 0:
                    raise PatchRejectedError("invalid patch hunk counts")
                position += 1
                if position < len(lines) and lines[position] == "\\ No newline at end of file":
                    position += 1
        if not hunks:
            raise PatchRejectedError("patch target has no text hunks")
    if not targets:
        raise PatchRejectedError("patch has no targets")
    return targets
