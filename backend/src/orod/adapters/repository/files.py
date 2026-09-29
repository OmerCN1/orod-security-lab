"""Shared, bounded text-file access for untrusted repository contents (POSIX)."""

from __future__ import annotations

import os
import re
import stat
from collections.abc import Iterator
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from orod.domain.errors import UnsafePathError

IGNORED_PARTS = {"venv", "node_modules", "dist", "build", "__pycache__"}
SECRET_NAMES = {"id_rsa", "id_ed25519", "id_dsa", "id_ecdsa"}
DIRECTORY_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
BINARY_CONTROL_BYTES = re.compile(rb"[\x00-\x08\x0b\x0e-\x1f\x7f]")
# An isolated copy stops here rather than silently leaving the rest of a repository out.
COPY_MAX_FILES = 2_000
COPY_MAX_BYTES = 100_000_000


@dataclass(frozen=True)
class RepositoryTextFile:
    relative: str
    content: str
    size: int


class RepositoryFiles:
    def __init__(
        self, root: Path, max_file_bytes: int, *, workspace_root: Path | None = None
    ) -> None:
        # Normalize '.' and '..' in the operator-owned anchor only. Never resolve
        # repository components: resolution would erase evidence of a symlink.
        self.anchor = (workspace_root or root.parent).expanduser().resolve()
        self.root = Path(os.path.abspath(root))
        if not self.root.is_relative_to(self.anchor):
            raise UnsafePathError("repository root is outside workspace")
        self._root_parts = self.root.relative_to(self.anchor).parts
        self.max_file_bytes = max_file_bytes

    @staticmethod
    def path_parts(relative: str) -> tuple[str, ...]:
        path = PurePosixPath(relative)
        if (
            not relative
            or path.is_absolute()
            or path.as_posix() != relative
            or not path.parts
            or "\\" in relative
            or any(ord(char) < 32 or ord(char) == 127 for char in relative)
            or any(
                part.startswith(".") or part in IGNORED_PARTS or part in SECRET_NAMES
                for part in path.parts
            )
        ):
            raise UnsafePathError("unsafe or excluded repository path")
        return path.parts

    def decode_text(self, data: bytes) -> str:
        if len(data) > self.max_file_bytes:
            raise UnsafePathError("file exceeds configured byte limit")
        if BINARY_CONTROL_BYTES.search(data):
            raise UnsafePathError("binary repository file")
        try:
            return data.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise UnsafePathError("repository file is not UTF-8 text") from exc

    @contextmanager
    def _root_directory(self) -> Iterator[int]:
        try:
            with ExitStack() as stack:
                descriptor = os.open(self.anchor, DIRECTORY_FLAGS)
                stack.callback(os.close, descriptor)
                for part in self._root_parts:
                    descriptor = os.open(part, DIRECTORY_FLAGS, dir_fd=descriptor)
                    stack.callback(os.close, descriptor)
                yield descriptor
        except OSError as exc:
            raise UnsafePathError("repository path is missing, unreadable or a symlink") from exc

    def read(self, relative: str) -> RepositoryTextFile:
        parts = self.path_parts(relative)
        with self._root_directory() as root_fd, ExitStack() as stack:
            directory_fd = root_fd
            for part in parts[:-1]:
                directory_fd = os.open(part, DIRECTORY_FLAGS, dir_fd=directory_fd)
                stack.callback(os.close, directory_fd)
            return self._read_at(directory_fd, parts[-1], relative)

    def _read_at(self, directory_fd: int, name: str, relative: str) -> RepositoryTextFile:
        # O_NOFOLLOW rejects the link at open time, including links pointing inside
        # the repo. Nonblocking open lets us reject FIFOs without waiting for a writer.
        descriptor = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory_fd)
        try:
            info = os.fstat(descriptor)
            if not stat.S_ISREG(info.st_mode):
                raise UnsafePathError("repository file is not a regular file")
            if info.st_size > self.max_file_bytes:
                raise UnsafePathError("file exceeds configured byte limit")
            with os.fdopen(descriptor, "rb", closefd=False) as stream:
                data = stream.read(self.max_file_bytes + 1)
        finally:
            os.close(descriptor)
        return RepositoryTextFile(relative, self.decode_text(data), len(data))

    def names(self) -> list[str]:
        """List root-level names without following entries or opening their contents."""
        with self._root_directory() as descriptor:
            return sorted(os.listdir(descriptor))

    def copy_to(self, destination: Path) -> None:
        """Write every file this policy accepts under ``destination``.

        A tool that walks a directory itself - a container's test run, an external
        scanner - is given this copy instead of the workspace, so it never follows a
        symlink or reads a hidden, binary or oversized file the policy rejects.
        """
        total_bytes = 0
        files = 0
        for item in self.iter_files():
            total_bytes += item.size
            files += 1
            if total_bytes > COPY_MAX_BYTES or files > COPY_MAX_FILES:
                raise UnsafePathError("repository exceeds the size limits of an isolated copy")
            target = destination / item.relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(item.content.encode("utf-8"))
            target.chmod(0o644)

    def iter_files(self) -> Iterator[RepositoryTextFile]:
        with self._root_directory() as descriptor:
            yield from self._walk(descriptor, "")

    def _walk(self, directory_fd: int, prefix: str) -> Iterator[RepositoryTextFile]:
        for name in sorted(os.listdir(directory_fd)):
            relative = f"{prefix}/{name}" if prefix else name
            try:
                self.path_parts(relative)
                info = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
                if stat.S_ISDIR(info.st_mode):
                    child = os.open(name, DIRECTORY_FLAGS, dir_fd=directory_fd)
                    try:
                        yield from self._walk(child, relative)
                    finally:
                        os.close(child)
                elif stat.S_ISREG(info.st_mode):
                    yield self._read_at(directory_fd, name, relative)
            except (UnsafePathError, OSError):
                # Inventory/discovery omit unsafe entries. Explicit reads reject them.
                continue
