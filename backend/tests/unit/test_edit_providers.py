"""Model-backed providers ask for edits, never a diff, and carry them unrendered."""

from types import SimpleNamespace
from typing import Any

from orod.adapters.llm.anthropic import AnthropicLLMProvider
from orod.adapters.llm.ollama import OllamaLLMProvider
from orod.adapters.llm.prompts import PATCH_SYSTEM_PROMPT
from orod.domain.models import (
    EditProposal,
    FileEdit,
    Finding,
    FindingSource,
    RepositorySnapshot,
    Severity,
)

SNAPSHOT = RepositorySnapshot(repository_url="demo://fake", workspace_path="workspaces/fake")
FINDING = Finding(
    id="f1",
    source=FindingSource.BANDIT,
    rule_id="B602",
    severity=Severity.HIGH,
    title="shell",
    message="shell",
    file_path="app.py",
    line=2,
)
SOURCES = {"app.py": "import subprocess\nsubprocess.run(cmd, shell=True)\n"}
RESPONSE = EditProposal(
    edits=[
        FileEdit(path="app.py", search="shell=True", replace="shell=False"),
        FileEdit(path="app.py", search="import subprocess", replace="import subprocess"),
    ],
    finding_ids=["f1"],
    explanation="Disabled the shell.",
)


class FakeStructuredModel:
    def __init__(self, parsed: object) -> None:
        self.parsed = parsed
        self.schema: object = None

    def with_structured_output(self, schema: object, **_: object) -> "FakeStructuredModel":
        self.schema = schema
        return self

    async def ainvoke(self, messages: object) -> dict[str, Any]:
        raw = SimpleNamespace(usage_metadata={"input_tokens": 10, "output_tokens": 5})
        return {"parsed": self.parsed, "raw": raw}


def ollama_with(parsed: object) -> tuple[OllamaLLMProvider, FakeStructuredModel]:
    provider = OllamaLLMProvider("http://localhost:11434", "qwen2.5-coder:14b")
    model = FakeStructuredModel(parsed)
    provider._model = model  # type: ignore[assignment]  # noqa: SLF001
    return provider, model


def test_the_shared_prompt_asks_for_edits_not_a_diff() -> None:
    assert "Do not write a diff" in PATCH_SYSTEM_PROMPT
    assert "exactly once" in PATCH_SYSTEM_PROMPT


async def test_ollama_requests_edits_and_leaves_rendering_to_the_pipeline() -> None:
    provider, model = ollama_with(RESPONSE)

    proposal = await provider.propose_patch(SNAPSHOT, [FINDING], SOURCES)

    assert model.schema is EditProposal
    assert proposal is not None
    assert proposal.unified_diff == ""
    assert proposal.edits == RESPONSE.edits
    assert proposal.changed_files == ["app.py"]
    assert provider.usage().output_tokens == 5


async def test_ollama_accepts_a_plain_dict_and_treats_no_edits_as_no_patch() -> None:
    provider, _ = ollama_with(RESPONSE.model_dump())
    assert (await provider.propose_patch(SNAPSHOT, [FINDING], SOURCES)) is not None

    empty, _ = ollama_with({"edits": [], "finding_ids": [], "explanation": "nothing"})
    assert (await empty.propose_patch(SNAPSHOT, [FINDING], SOURCES)) is None


async def test_anthropic_requests_edits_with_structured_output() -> None:
    provider = AnthropicLLMProvider(api_key="test", model="claude-sonnet-5")
    captured: dict[str, Any] = {}

    async def parse(**kwargs: Any) -> SimpleNamespace:
        captured.update(kwargs)
        return SimpleNamespace(
            stop_reason="end_turn",
            parsed_output=RESPONSE,
            usage=SimpleNamespace(input_tokens=7, output_tokens=3),
        )

    provider._client = SimpleNamespace(messages=SimpleNamespace(parse=parse))  # type: ignore[assignment]  # noqa: SLF001

    proposal = await provider.propose_patch(SNAPSHOT, [FINDING], SOURCES)

    assert captured["output_format"] is EditProposal
    assert captured["system"] == PATCH_SYSTEM_PROMPT
    assert proposal is not None and proposal.edits == RESPONSE.edits
