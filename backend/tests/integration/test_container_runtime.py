"""Opt-in runtime check: build the image and set OROD_TEST_CONTAINER=1."""

import os
import sys
from pathlib import Path

import pytest

from orod.adapters.execution.container import ContainerCommandRunner
from orod.adapters.execution.subprocess import SafeCommandRunner
from orod.adapters.repository.git import GitRepositoryAdapter
from orod.adapters.repository.validation_checks import CHECKS
from orod.config import Settings
from orod.domain.models import RepositorySnapshot


@pytest.mark.skipif(os.environ.get("OROD_TEST_CONTAINER") != "1", reason="requires Docker image")
async def test_real_container_boundaries(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    (root / "tests").mkdir(parents=True)
    (root / ".env").write_text("SYNTHETIC_TEST_DATA=1\n")
    (root / "tests" / "test_boundary.py").write_text("""
import os
import socket
from pathlib import Path

def test_isolation():
    assert os.geteuid() != 0
    assert not Path("/input/.env").exists()
    assert not Path("/workspace/.env").exists()
    assert not os.access("/opt/orod/entrypoint.py", os.W_OK)
    status = Path("/proc/self/status").read_text()
    assert "CapEff:\\t0000000000000000" in status
    with socket.socket() as connection:
        connection.settimeout(1)
        assert connection.connect_ex(("1.1.1.1", 443)) != 0
""")
    runner = ContainerCommandRunner(Settings(workspace_root=tmp_path))
    pytest_args = next(check.args for check in CHECKS if check.name == "pytest")
    result = await runner.run([sys.executable, *pytest_args], root)
    assert result.return_code == 0, result.stderr + result.stdout
    assert "1 passed" in result.stdout
    assert not (root / ".pytest_cache").exists()
    adapter = GitRepositoryAdapter(
        Settings(workspace_root=tmp_path), SafeCommandRunner({"git"}, tmp_path), runner
    )
    validation = await adapter.validate(
        RepositorySnapshot(
            repository_url="https://github.com/example/project",
            workspace_path=str(root),
            permission="WRITE",
            trusted=True,
        )
    )
    assert validation.passed, validation.model_dump()
    assert len(validation.commands) == len(CHECKS)
    assert validation.tests_ran is True
    assert not (root / "tests" / "__pycache__").exists()
