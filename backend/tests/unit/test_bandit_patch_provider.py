from pathlib import Path

from orod.adapters.llm.ollama import DeterministicBanditPatchProvider
from orod.domain.models import Finding, FindingSource, RepositorySnapshot, Severity


async def test_b607_fallback_resolves_partial_executable_path(tmp_path: Path) -> None:
    source = (
        "import subprocess\n\n"
        "def probe(path: str) -> None:\n"
        "    subprocess.run(['ffprobe', path], check=True)\n"
    )
    snapshot = RepositorySnapshot(
        repository_url="https://github.com/example/project", workspace_path=str(tmp_path)
    )
    finding = Finding(
        id="finding",
        source=FindingSource.BANDIT,
        rule_id="B607",
        severity=Severity.LOW,
        title="partial path",
        message="partial path",
        file_path="app.py",
        line=4,
    )

    proposal = await DeterministicBanditPatchProvider().propose_patch(
        snapshot, [finding], {"app.py": source}
    )

    assert proposal is not None
    assert "import shutil" in proposal.unified_diff
    assert "_orod_require_executable('ffprobe')" in proposal.unified_diff
    assert proposal.changed_files == ["app.py"]
