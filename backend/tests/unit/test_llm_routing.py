from pathlib import Path

from orod.adapters.llm.ollama import DeterministicDemoPatchProvider
from orod.adapters.llm.routing import RoutingLLMProvider
from orod.adapters.llm.usage import UsageRecorder
from orod.domain.models import (
    Confidence,
    Finding,
    FindingSource,
    PatchProposal,
    RepositorySnapshot,
    Severity,
)

SHELL_SOURCE = (
    "import subprocess\n\n\n"
    "def run(value: str) -> None:\n"
    '    subprocess.run(f"echo {value}", shell=True, check=True)\n'
)


class RecordingProvider(UsageRecorder):
    """Stand-in for a real model so routing can be asserted without one."""

    provider_name = "recording"

    def __init__(self) -> None:
        super().__init__("recording-model")
        self.calls = 0
        self.last_feedback: str | None = None

    async def health(self) -> tuple[bool, str]:
        return True, "ready"

    async def propose_patch(
        self,
        snapshot: RepositorySnapshot,
        findings: list[Finding],
        source_files: dict[str, str],
        previous_error: str | None = None,
        reviewer_feedback: str | None = None,
    ) -> PatchProposal | None:
        self.calls += 1
        self.last_feedback = reviewer_feedback
        self.record(input_tokens=120, output_tokens=45, latency_ms=7)
        return PatchProposal(
            unified_diff="--- a/app.py\n+++ b/app.py\n",
            changed_files=["app.py"],
            finding_ids=[item.id for item in findings],
            explanation="recorded",
        )


def make_snapshot(tmp_path: Path, url: str) -> RepositorySnapshot:
    return RepositorySnapshot(repository_url=url, workspace_path=str(tmp_path), trusted=True)


def make_finding(rule_id: str, severity: Severity = Severity.HIGH) -> Finding:
    return Finding(
        id=f"finding-{rule_id}",
        source=FindingSource.BANDIT,
        rule_id=rule_id,
        severity=severity,
        confidence=Confidence.HIGH,
        title=rule_id,
        message=rule_id,
        file_path="app.py",
        line=5,
    )


async def test_fixture_repositories_reach_the_model_when_one_is_configured(
    tmp_path: Path,
) -> None:
    """Regression guard: routing on the URL scheme made fixture runs bypass the model,
    which would have made every model evaluation measure the fallback instead."""
    primary = RecordingProvider()
    router = RoutingLLMProvider(primary, DeterministicDemoPatchProvider(), use_llm=True)

    patch = await router.propose_patch(
        make_snapshot(tmp_path, "demo://shell-injection"),
        [make_finding("B602")],
        {"app.py": SHELL_SOURCE},
    )

    assert primary.calls == 1
    assert patch is not None and patch.explanation == "recorded"


async def test_offline_mode_never_calls_the_model(tmp_path: Path) -> None:
    primary = RecordingProvider()
    router = RoutingLLMProvider(primary, DeterministicDemoPatchProvider(), use_llm=False)

    patch = await router.propose_patch(
        make_snapshot(tmp_path, "demo://shell-injection"),
        [make_finding("B602")],
        {"app.py": SHELL_SOURCE},
    )

    assert primary.calls == 0
    assert patch is not None
    assert "shell=False" in patch.unified_diff


async def test_offline_mode_falls_through_to_the_ast_codemod(tmp_path: Path) -> None:
    """The demo codemod only knows shell=True; B607 must still reach the AST fallback."""
    primary = RecordingProvider()
    router = RoutingLLMProvider(primary, DeterministicDemoPatchProvider(), use_llm=False)
    source = (
        "import subprocess\n\n\n"
        "def probe(path: str) -> None:\n"
        "    subprocess.run(['ffprobe', path], check=True)\n"
    )

    patch = await router.propose_patch(
        make_snapshot(tmp_path, "demo://partial-executable-path"),
        [make_finding("B607", Severity.LOW)],
        {"app.py": source},
    )

    assert primary.calls == 0
    assert patch is not None
    assert "shutil.which" in patch.unified_diff


async def test_usage_is_aggregated_and_resettable(tmp_path: Path) -> None:
    primary = RecordingProvider()
    router = RoutingLLMProvider(primary, DeterministicDemoPatchProvider(), use_llm=True)
    await router.propose_patch(
        make_snapshot(tmp_path, "demo://shell-injection"),
        [make_finding("B602")],
        {"app.py": SHELL_SOURCE},
    )

    usage = router.usage()
    assert usage.provider == "recording"
    assert usage.calls == 1
    assert usage.input_tokens == 120
    assert usage.total_tokens == 165

    router.reset_usage()
    assert router.usage().calls == 0


async def test_reviewer_feedback_reaches_the_model(tmp_path: Path) -> None:
    primary = RecordingProvider()
    router = RoutingLLMProvider(primary, DeterministicDemoPatchProvider(), use_llm=True)

    await router.propose_patch(
        make_snapshot(tmp_path, "demo://sql-injection-format"),
        [make_finding("B608")],
        {"app.py": SHELL_SOURCE},
        None,
        "use an ORM instead of a bound parameter",
    )

    assert primary.last_feedback == "use an ORM instead of a bound parameter"
