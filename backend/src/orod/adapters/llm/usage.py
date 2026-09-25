from __future__ import annotations

import time
from collections.abc import Iterator
from contextlib import contextmanager

from orod.domain.models import LLMUsage


class UsageRecorder:
    """Cumulative token/latency accounting shared by every LLM provider.

    Providers are long-lived, so the evaluation harness resets the recorder before
    each case and reads it afterwards to attribute cost to a single run.
    """

    provider_name = "none"

    def __init__(self, model: str = "") -> None:
        # Distinct from any adapter attribute: concrete providers keep their own
        # ``_model`` client object.
        self._usage_model = model
        self._usage = LLMUsage(provider=self.provider_name, model=model)

    def usage(self) -> LLMUsage:
        return self._usage.model_copy(deep=True)

    def reset_usage(self) -> None:
        self._usage = LLMUsage(provider=self.provider_name, model=self._usage_model)

    def record(
        self,
        *,
        input_tokens: int = 0,
        output_tokens: int = 0,
        latency_ms: int = 0,
        failed: bool = False,
    ) -> None:
        self._usage.calls += 1
        self._usage.failed_calls += int(failed)
        self._usage.input_tokens += max(0, input_tokens)
        self._usage.output_tokens += max(0, output_tokens)
        self._usage.latency_ms += max(0, latency_ms)

    @contextmanager
    def timed(self) -> Iterator[dict[str, int]]:
        """Record one call, letting the body report token counts via the yielded dict.

        The call is recorded even when the body raises, so a provider crash still
        shows up as a failed call in the evaluation report instead of vanishing.
        """
        counters = {"input_tokens": 0, "output_tokens": 0}
        start = time.monotonic()
        failed = False
        try:
            yield counters
        except BaseException:
            failed = True
            raise
        finally:
            self.record(
                input_tokens=counters["input_tokens"],
                output_tokens=counters["output_tokens"],
                latency_ms=int((time.monotonic() - start) * 1000),
                failed=failed,
            )
