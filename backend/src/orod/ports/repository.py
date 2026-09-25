from __future__ import annotations

from typing import Protocol

from orod.domain.models import PatchProposal, RepositorySnapshot, ValidationResult


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

    async def validate(self, snapshot: RepositorySnapshot) -> ValidationResult: ...


class PullRequestPublisher(Protocol):
    async def publish(
        self,
        snapshot: RepositorySnapshot,
        patch: PatchProposal,
        validation: ValidationResult,
        run_id: str,
    ) -> object: ...
