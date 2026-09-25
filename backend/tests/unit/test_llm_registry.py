from orod.adapters.llm.factory import CachingLLMProviderRegistry, is_anthropic_model
from orod.config import Settings


def settings_for(model: str) -> Settings:
    return Settings(chat_model=model, use_llm=True, anthropic_api_key="test-key")


def test_default_provider_is_reused_for_the_configured_model() -> None:
    """The evaluation harness resets usage on the default provider, so it must be the
    same object the graph resolves for a run that names no model."""
    registry = CachingLLMProviderRegistry(settings_for("qwen2.5-coder:14b"))

    assert registry.for_model(None) is registry.default()
    assert registry.for_model("qwen2.5-coder:14b") is registry.default()


def test_a_named_model_gets_its_own_cached_provider() -> None:
    registry = CachingLLMProviderRegistry(settings_for("qwen2.5-coder:14b"))

    first = registry.for_model("claude-opus-5")
    assert first is not registry.default()
    assert registry.for_model("claude-opus-5") is first
    assert first.usage().model == "claude-opus-5"
    assert first.usage().provider == "anthropic"


def test_provider_is_chosen_from_the_model_identifier() -> None:
    assert is_anthropic_model("claude-opus-5")
    assert not is_anthropic_model("qwen2.5-coder:14b")
    registry = CachingLLMProviderRegistry(settings_for("claude-opus-5"))
    assert registry.default().usage().provider == "anthropic"
    assert registry.for_model("qwen2.5-coder:7b").usage().provider == "ollama"
