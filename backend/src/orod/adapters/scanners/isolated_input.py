"""Filtered repository input for scanners that walk a directory themselves."""

from __future__ import annotations

import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from orod.adapters.repository.files import RepositoryFiles
from orod.domain.models import RepositorySnapshot


@contextmanager
def filtered_copy(
    snapshot: RepositorySnapshot, max_file_bytes: int, workspace_root: Path | None
) -> Iterator[Path]:
    """A temporary copy of the workspace holding only files the shared policy accepts.

    Bandit and Semgrep open whatever they find under their target: symlinks out of the
    workspace, oversized or binary files, and hidden configuration such as
    ``.semgrepignore`` that would let repository content decide what is scanned. They
    are pointed at this copy instead. It sits beside the run workspace, under the
    workspace root, because the command runner refuses any cwd outside it; the leading
    dot keeps it out of every repository inventory.
    """
    root = Path(snapshot.workspace_path)
    anchor = (workspace_root or root.parent).expanduser().resolve()
    with tempfile.TemporaryDirectory(prefix=".orod-scan-", dir=anchor) as directory:
        destination = Path(directory).resolve()
        RepositoryFiles(root, max_file_bytes, workspace_root=anchor).copy_to(destination)
        yield destination
