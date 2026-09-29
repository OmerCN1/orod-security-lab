import sys
from pathlib import Path

from orod.adapters.scanners.semgrep import SemgrepScanner
from orod.domain.models import CommandResult, RepositorySnapshot


class CapturingRunner:
    def __init__(self) -> None:
        self.argv: list[str] | None = None

    async def run(self, argv: list[str], cwd: Path, **_: object) -> CommandResult:
        self.argv = argv
        return CommandResult(argv=argv, return_code=0, stdout='{"results": []}')


async def test_semgrep_uses_the_active_virtualenv_executable(tmp_path: Path) -> None:
    runner = CapturingRunner()
    (tmp_path / "run").mkdir()
    snapshot = RepositorySnapshot(
        repository_url="https://github.com/example/python-project",
        workspace_path=str(tmp_path / "run"),
    )

    findings = await SemgrepScanner(runner, workspace_root=tmp_path).scan(snapshot)

    assert findings == []
    assert runner.argv is not None
    assert runner.argv[0] == str(Path(sys.executable).parent / "semgrep")
