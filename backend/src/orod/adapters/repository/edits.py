"""Turn search/replace edits into a unified diff against the real file contents.

The diff that results goes through exactly the same gates as any other patch - strict
target parsing, the repository file policy, size limits and `git apply --check` - so
this module only has to be precise, not trusted.
"""

from __future__ import annotations

import difflib
from collections.abc import Mapping, Sequence

from orod.domain.errors import PatchRejectedError
from orod.domain.models import FileEdit

NO_NEWLINE_MARKER = "\\ No newline at end of file\n"


def apply_edits(originals: Mapping[str, str], edits: Sequence[FileEdit]) -> dict[str, str]:
    """Apply edits in order and return the files they changed.

    Each ``search`` must occur exactly once in the file as it stands after the edits
    before it. An exact match is tried first; failing that, a whole-line match that
    ignores trailing whitespace, which is the most common way a model's copy drifts
    from the file. Anything missing or ambiguous rejects the whole proposal rather than
    guessing where an edit was meant to go.
    """
    if not edits:
        raise PatchRejectedError("proposal contains no edits")
    current = dict(originals)
    for number, edit in enumerate(edits, start=1):
        if edit.path not in current:
            raise PatchRejectedError(f"edit {number} targets a file that was not supplied")
        if not edit.search.strip():
            raise PatchRejectedError(f"edit {number} has an empty search text")
        text = current[edit.path]
        start, end, whole_lines = _locate(text, edit.search, number)
        replacement = edit.replace
        if whole_lines and replacement.endswith("\n"):
            # The span stops before the file's own line ending, which is kept.
            replacement = replacement[:-1]
        current[edit.path] = text[:start] + replacement + text[end:]
    changed = {path: text for path, text in current.items() if text != originals[path]}
    if not changed:
        raise PatchRejectedError("edits produce no repository changes")
    return changed


def render_diff(originals: Mapping[str, str], changed: Mapping[str, str]) -> str:
    return "".join(unified_diff(path, originals[path], changed[path]) for path in sorted(changed))


def unified_diff(path: str, original: str, updated: str) -> str:
    """A unified diff `git apply` accepts, including files without a final newline."""
    lines: list[str] = []
    for line in difflib.unified_diff(
        original.splitlines(keepends=True),
        updated.splitlines(keepends=True),
        fromfile=f"a/{path}",
        tofile=f"b/{path}",
    ):
        lines.append(line if line.endswith("\n") else f"{line}\n{NO_NEWLINE_MARKER}")
    return "".join(lines)


def _locate(text: str, search: str, number: int) -> tuple[int, int, bool]:
    """The span to replace, and whether it was found as whole lines."""
    occurrences = text.count(search)
    if occurrences == 1:
        start = text.index(search)
        return start, start + len(search), False
    if occurrences > 1:
        raise PatchRejectedError(
            f"edit {number} search text occurs {occurrences} times; include more context"
        )
    matches = _line_matches(text, search)
    if len(matches) == 1:
        return (*matches[0], True)
    if matches:
        raise PatchRejectedError(
            f"edit {number} search text occurs {len(matches)} times; include more context"
        )
    raise PatchRejectedError(f"edit {number} search text was not found in the file")


def _line_matches(text: str, search: str) -> list[tuple[int, int]]:
    """Spans of whole-line runs equal to ``search`` apart from trailing whitespace.

    A span runs from the start of its first line to the end of its last line's content,
    so the file's own line ending is kept and ``replace`` stands in for the lines alone.
    """
    wanted = [line.rstrip() for line in search.strip("\n").split("\n")]
    lines = text.splitlines(keepends=True)
    offsets = [0]
    for line in lines:
        offsets.append(offsets[-1] + len(line))
    stripped = [line.rstrip() for line in lines]
    size = len(wanted)
    spans: list[tuple[int, int]] = []
    for first in range(len(lines) - size + 1):
        if stripped[first : first + size] == wanted:
            last = lines[first + size - 1]
            content_end = offsets[first + size] - (len(last) - len(last.rstrip("\r\n")))
            spans.append((offsets[first], content_end))
    return spans
