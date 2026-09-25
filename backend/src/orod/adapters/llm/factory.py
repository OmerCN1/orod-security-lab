from __future__ import annotations

from orod.adapters.llm.anthropic import AnthropicLLMProvider
from orod.adapters.llm.ollama import DeterministicDemoPatchProvider, OllamaLLMProvider
from orod.adapters.llm.routing import RoutingLLMProvider
from orod.config import Settings
from orod.ports.llm import LLMProvider

ANTHROPIC_MODEL_PREFIX = "claude-"


def is_anthropic_model(model: str) -> bool:
    return model.startswith(ANTHROPIC_MODEL_PREFIX)


def build_primary_provider(settings: Settings) -> LLMProvider:
    """Pick the concrete model adapter for the configured chat model."""
    if is_anthropic_model(settings.chat_model):
        return AnthropicLLMProvider(
            api_key=settings.anthropic_api_key,
            model=settings.chat_model,
            max_output_tokens=settings.llm_max_output_tokens,
            timeout_seconds=settings.llm_timeout_seconds,
        )
    return OllamaLLMProvider(settings.ollama_base_url, settings.chat_model)


def build_llm_provider(settings: Settings) -> RoutingLLMProvider:
    return RoutingLLMProvider(
        build_primary_provider(settings),
        DeterministicDemoPatchProvider(),
        settings.use_llm,
    )


class CachingLLMProviderRegistry:
    """Implements ``LLMProviderRegistry`` by caching one instance per model identifier.

    Providers are expensive to build and hold usage counters, so the default provider is
    created once and reused. ``for_model(None)`` returns that same object, which is what
    keeps the evaluation harness's per-case usage accounting working: it resets and reads
    the default provider directly.
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._default = build_llm_provider(settings)
        self._by_model: dict[str, LLMProvider] = {settings.chat_model: self._default}

    def default(self) -> LLMProvider:
        return self._default

    def for_model(self, model: str | None) -> LLMProvider:
        if not model or model == self._settings.chat_model:
            return self._default
        provider = self._by_model.get(model)
        if provider is None:
            provider = build_llm_provider(self._settings.model_copy(update={"chat_model": model}))
            self._by_model[model] = provider
        return provider

    def known_models(self) -> list[str]:
        return sorted(self._by_model)
