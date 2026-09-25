import sys
from pathlib import Path

import pytest

from orod.adapters.execution.subprocess import SafeCommandRunner
from orod.adapters.repository.git import GitRepositoryAdapter
from orod.config import Settings
from orod.domain.errors import PatchRejectedError
from orod.domain.models import CommandResult, PatchProposal, RepositorySnapshot


def test_lockfile_version_wins_over_unpinned_manifest(tmp_path: Path) -> None:
    workspace = tmp_path / "workspaces"
    repository = workspace / "repo"
    repository.mkdir(parents=True)
    (repository / "pyproject.toml").write_text(
        '[project]\nname = "demo"\nversion = "0.1.0"\ndependencies = ["httpx>=0.27"]\n'
    )
    (repository / "uv.lock").write_text(
        'version = 1\n\n[[package]]\nname = "httpx"\nversion = "0.28.1"\n'
    )
    settings = Settings(workspace_root=workspace)
    runner = SafeCommandRunner({sys.executable}, workspace)
    adapter = GitRepositoryAdapter(settings, runner)

    dependencies = adapter._discover_dependencies(repository)

    assert len(dependencies) == 1
    assert dependencies[0].name == "httpx"
    assert dependencies[0].version == "0.28.1"
    assert dependencies[0].source_file == "uv.lock"


class NoChangeRunner:
    async def run(self, argv: list[str], cwd: Path, **_: object) -> CommandResult:
        return CommandResult(argv=argv, return_code=0, stdout="")


async def test_repository_rejects_patch_that_produces_no_change(tmp_path: Path) -> None:
    workspace = tmp_path / "workspaces"
    repository = workspace / "repo"
    repository.mkdir(parents=True)
    (repository / "app.py").write_text("print('before')\n")
    adapter = GitRepositoryAdapter(
        Settings(workspace_root=workspace),
        NoChangeRunner(),  # type: ignore[arg-type]
    )
    snapshot = RepositorySnapshot(
        repository_url="https://github.com/example/project",
        workspace_path=str(repository),
    )
    proposal = PatchProposal(
        unified_diff=(
            "--- a/app.py\n+++ b/app.py\n@@ -1 +1 @@\n-print('before')\n+print('after')\n"
        ),
        changed_files=["app.py"],
        finding_ids=["finding"],
        explanation="test",
    )

    with pytest.raises(PatchRejectedError, match="no repository changes"):
        await adapter.apply_patch(snapshot, proposal)
