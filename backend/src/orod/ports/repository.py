from __future__ import annotations

from typing import Protocol

from orod.domain.models import (
    FileEdit,
    PackageDependency,
    PatchProposal,
    RepositorySnapshot,
    ValidationBaseline,
    ValidationResult,
)


class RepositoryProvider(Protocol):
    async def prepare(
        self,
        repository_url: str,
        base_branch: str | None,
        run_id: str,
        trusted: bool,
    ) -> RepositorySnapshot: ...

    async def read_files(
        self, snapshot: RepositorySnapshot, paths: list[str], max_chars: int = 30_000
    ) -> dict[str, str]: ...

    async def read_base_files(
        self, snapshot: RepositorySnapshot, paths: list[str], max_chars: int = 100_000
    ) -> dict[str, str]: ...

    async def apply_patch(self, snapshot: RepositorySnapshot, patch: PatchProposal) -> str: ...

    async def render_edits(
        self, snapshot: RepositorySnapshot, edits: list[FileEdit], allowed_paths: list[str]
    ) -> tuple[str, list[str]]: ...

    async def revert_patch(self, snapshot: RepositorySnapshot, applied_diff: str) -> None: ...

    async def discover_dependencies(
        self, snapshot: RepositorySnapshot
    ) -> list[PackageDependency]: ...

    async def record_baseline(
        self, snapshot: RepositorySnapshot
    ) -> ValidationBaseline | None: ...

    async def validate(
        self, snapshot: RepositorySnapshot, baseline: ValidationBaseline | None = None
    ) -> ValidationResult: ...


class PullRequestPublisher(Protocol):
    async def publish(
        self,
        snapshot: RepositorySnapshot,
        patch: PatchProposal,
        validation: ValidationResult,
        run_id: str,
    ) -> object: ...
