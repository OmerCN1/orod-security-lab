import sys
from pathlib import Path

from orod.adapters.execution.subprocess import SafeCommandRunner
from orod.adapters.scanners.bandit import BanditScanner
from orod.domain.models import RepositorySnapshot


async def test_scan_does_not_import_repository_bandit_module(tmp_path: Path) -> None:
    repository = tmp_path / "run"
    repository.mkdir()
    (repository / "bandit.py").write_text("raise RuntimeError('repository code executed')\n")
    (repository / "app.py").write_text("eval(input())\n")
    runner = SafeCommandRunner({sys.executable}, tmp_path)
    findings = await BanditScanner(runner, workspace_root=tmp_path).scan(
        RepositorySnapshot(
            repository_url="https://github.com/example/project",
            workspace_path=str(repository),
            trusted=False,
        )
    )
    assert any(finding.rule_id == "B307" for finding in findings)
