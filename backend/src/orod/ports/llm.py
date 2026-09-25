from __future__ import annotations

from typing import Protocol

from orod.domain.models import Finding, LLMUsage, PatchProposal, RepositorySnapshot


class LLMProvider(Protocol):
    async def health(self) -> tuple[bool, str]: ...

    async def propose_patch(
        self,
        snapshot: RepositorySnapshot,
        findings: list[Finding],
        source_files: dict[str, str],
        previous_error: str | None = None,
        reviewer_feedback: str | None = None,
    ) -> PatchProposal | None: ...

    def usage(self) -> LLMUsage: ...

    def reset_usage(self) -> None: ...


class LLMProviderRegistry(Protocol):
    """Resolves the provider a run should use, given an optional per-run model."""

    def default(self) -> LLMProvider: ...

    def for_model(self, model: str | None) -> LLMProvider: ...
