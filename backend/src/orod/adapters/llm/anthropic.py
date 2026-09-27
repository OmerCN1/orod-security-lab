from __future__ import annotations

import anthropic
from anthropic import AsyncAnthropic

from orod.adapters.llm.prompts import (
    PATCH_SYSTEM_PROMPT,
    build_patch_prompt,
    to_patch_proposal,
)
from orod.adapters.llm.usage import UsageRecorder
from orod.domain.models import EditProposal, Finding, PatchProposal, RepositorySnapshot

# Hosted models this adapter is wired for. Keep in step with the pricing table the
# evaluation harness uses to report cost.
SUPPORTED_MODELS: tuple[str, ...] = (
    "claude-opus-5",
    "claude-sonnet-5",
    "claude-haiku-4-5",
)


class AnthropicLLMProvider(UsageRecorder):
    """Claude-backed patch generation behind the same port as the local model.

    Structured outputs are used so the response is a validated ``EditProposal``
    rather than free text; the diff is rendered from its edits by the application.
    """

    provider_name = "anthropic"

    def __init__(
        self,
        api_key: str,
        model: str,
        max_output_tokens: int = 16_000,
        timeout_seconds: int = 180,
    ) -> None:
        super().__init__(model)
        self._model_name = model
        self._max_output_tokens = max_output_tokens
        self._client = AsyncAnthropic(
            api_key=api_key or None,
            timeout=float(timeout_seconds),
        )

    async def health(self) -> tuple[bool, str]:
        try:
            await self._client.models.retrieve(self._model_name)
        except anthropic.AuthenticationError:
            return False, "Anthropic API key is missing or invalid"
        except anthropic.NotFoundError:
            return False, f"unknown Anthropic model: {self._model_name}"
        except anthropic.APIConnectionError:
            return False, "Anthropic API is unreachable"
        except anthropic.APIStatusError as exc:
            return False, f"Anthropic API error: {exc.status_code}"
        except TypeError:
            # The SDK raises TypeError rather than an APIError when no credential
            # source resolves at all.
            return False, "no Anthropic credentials (set OROD_ANTHROPIC_API_KEY)"
        return True, "model ready"

    async def propose_patch(
        self,
        snapshot: RepositorySnapshot,
        findings: list[Finding],
        source_files: dict[str, str],
        previous_error: str | None = None,
        reviewer_feedback: str | None = None,
    ) -> PatchProposal | None:
        if not findings or not source_files:
            return None
        prompt = build_patch_prompt(
            snapshot, findings, source_files, previous_error, reviewer_feedback
        )
        with self.timed() as counters:
            response = await self._client.messages.parse(
                model=self._model_name,
                max_tokens=self._max_output_tokens,
                system=PATCH_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}],
                output_format=EditProposal,
            )
            counters["input_tokens"] = int(response.usage.input_tokens or 0)
            counters["output_tokens"] = int(response.usage.output_tokens or 0)
            # A safety decline or a truncated response yields no usable patch; the
            # graph treats that the same as any other "no safe patch" outcome.
            if response.stop_reason == "refusal":
                return None
            parsed = response.parsed_output
        if parsed is None:
            return None
        return to_patch_proposal(
            parsed if isinstance(parsed, EditProposal) else EditProposal.model_validate(parsed)
        )
