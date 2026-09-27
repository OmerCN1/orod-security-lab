from __future__ import annotations

from orod.adapters.llm.ollama import (
    DeterministicBanditPatchProvider,
    DeterministicDemoPatchProvider,
)
from orod.domain.models import Finding, LLMUsage, PatchProposal, RepositorySnapshot
from orod.ports.llm import LLMProvider


class RoutingLLMProvider:
    """Chooses which patch provider answers a request.

    With ``use_llm`` disabled the deterministic codemods answer everything, which is
    what keeps the demo and the test suite runnable with no model installed. With a
    model configured the model is always asked first - including for ``demo://``
    fixture repositories, so the evaluation harness measures the model rather than the
    fallback. Deterministic Bandit codemods only step in as a repair attempt after the
    model has already produced a patch that validation rejected, and only when they cover
    every selected finding.
    """

    def __init__(
        self,
        primary: LLMProvider,
        offline: DeterministicDemoPatchProvider,
        use_llm: bool,
    ) -> None:
        self._primary = primary
        self._offline = offline
        self._bandit_fallback = DeterministicBanditPatchProvider()
        self._use_llm = use_llm

    async def health(self) -> tuple[bool, str]:
        if not self._use_llm:
            return await self._offline.health()
        return await self._primary.health()

    async def propose_patch(
        self,
        snapshot: RepositorySnapshot,
        findings: list[Finding],
        source_files: dict[str, str],
        previous_error: str | None = None,
        reviewer_feedback: str | None = None,
    ) -> PatchProposal | None:
        if not self._use_llm:
            patch = await self._offline.propose_patch(
                snapshot, findings, source_files, previous_error, reviewer_feedback
            )
            if patch is not None:
                return patch
            return await self._bandit_fallback.propose_patch(
                snapshot, findings, source_files, previous_error, reviewer_feedback
            )
        # Every attempt starts from the base revision, so a codemod that covers only some
        # of the findings would undo the rest of the model's earlier fix. It steps in on a
        # repair only when it can resolve every selected finding on its own.
        if previous_error and not reviewer_feedback and self._bandit_fallback.covers(findings):
            fallback = await self._bandit_fallback.propose_patch(
                snapshot, findings, source_files, previous_error, reviewer_feedback
            )
            if fallback is not None:
                return fallback
        return await self._primary.propose_patch(
            snapshot, findings, source_files, previous_error, reviewer_feedback
        )

    def usage(self) -> LLMUsage:
        if not self._use_llm:
            return self._offline.usage().merged_with(self._bandit_fallback.usage())
        return self._primary.usage().merged_with(self._bandit_fallback.usage())

    def reset_usage(self) -> None:
        self._primary.reset_usage()
        self._offline.reset_usage()
        self._bandit_fallback.reset_usage()
