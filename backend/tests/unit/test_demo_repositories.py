from pathlib import Path

import pytest
from pydantic import ValidationError

from orod.adapters.repository.git import GitRepositoryAdapter
from orod.config import Settings
from orod.domain.errors import InvalidRepositoryError
from orod.domain.models import RunCreate


def adapter_for(fixture_root: Path, tmp_path: Path) -> GitRepositoryAdapter:
    settings = Settings(
        fixture_root=fixture_root,
        workspace_root=tmp_path / "workspaces",
        database_path=tmp_path / "orod.sqlite3",
        checkpoint_path=tmp_path / "checkpoints.sqlite3",
        chroma_path=tmp_path / "chroma",
    )
    settings.ensure_directories()
    return GitRepositoryAdapter(settings, runner=None)  # type: ignore[arg-type]


def test_run_create_accepts_any_demo_slug() -> None:
    assert RunCreate(repository_url="demo://shell-injection").repository_url == (
        "demo://shell-injection"
    )
    assert RunCreate(repository_url="demo://vulnerable-python").repository_url == (
        "demo://vulnerable-python"
    )


@pytest.mark.parametrize(
    "url",
    [
        "demo://../../etc",
        "demo://Upper-Case",
        "demo://with_underscore",
        "demo://",
        "demo://a/b",
    ],
)
def test_run_create_rejects_slugs_that_could_escape_the_fixture_root(url: str) -> None:
    with pytest.raises(ValidationError):
        RunCreate(repository_url=url)


def test_fixture_resolution_prefers_the_eval_corpus_layout(tmp_path: Path) -> None:
    fixtures = tmp_path / "cases"
    (fixtures / "shell-injection" / "repo").mkdir(parents=True)
    resolved = adapter_for(fixtures, tmp_path)._resolve_fixture("shell-injection")
    assert resolved == (fixtures / "shell-injection" / "repo").resolve()


def test_fixture_resolution_still_finds_the_original_test_fixture(tmp_path: Path) -> None:
    fixtures = tmp_path / "fixtures"
    (fixtures / "vulnerable_python_repo").mkdir(parents=True)
    resolved = adapter_for(fixtures, tmp_path)._resolve_fixture("vulnerable-python")
    assert resolved == (fixtures / "vulnerable_python_repo").resolve()


def test_missing_fixture_is_reported_rather_than_guessed(tmp_path: Path) -> None:
    fixtures = tmp_path / "fixtures"
    fixtures.mkdir()
    with pytest.raises(InvalidRepositoryError, match="demo fixture is missing"):
        adapter_for(fixtures, tmp_path)._resolve_fixture("nothing-here")
