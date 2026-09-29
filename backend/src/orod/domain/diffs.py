"""Read-only views of unified diffs that OROD produced itself."""

from __future__ import annotations

import re

_GIT_HEADER = re.compile(r"diff --git a/(\S+) b/\S+")


def split_by_file(diff: str) -> dict[str, str]:
    """Split a unified diff into its per-file sections, keyed by path.

    Git's own headers are unambiguous: every content line starts with a space, ``+``,
    ``-`` or ``\\``, never with ``diff --git``. A diff without them (one rendered before
    it was applied) starts a section at a ``--- a/`` line followed by ``+++ b/``. This is
    for describing a diff, not for validating one; the patch gates parse strictly.
    """
    lines = diff.splitlines(keepends=True)
    git_format = any(_GIT_HEADER.match(line) for line in lines)
    sections: dict[str, list[str]] = {}
    current: list[str] | None = None
    for index, line in enumerate(lines):
        path: str | None = None
        if git_format:
            match = _GIT_HEADER.match(line)
            path = match[1] if match else None
        elif (
            line.startswith("--- a/")
            and index + 1 < len(lines)
            and lines[index + 1].startswith("+++ b/")
        ):
            path = line[len("--- a/") :].rstrip("\n")
        if path is not None:
            current = sections.setdefault(path, [])
        if current is not None:
            current.append(line)
    return {path: "".join(section) for path, section in sections.items()}
