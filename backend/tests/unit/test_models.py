import pytest
from pydantic import ValidationError

from orod.domain.models import RunCreate


def test_run_create_accepts_demo_and_https_github() -> None:
    assert RunCreate(repository_url="demo://vulnerable-python").repository_url.startswith("demo://")
    request = RunCreate(repository_url="https://github.com/example/project.git/")
    assert request.repository_url == "https://github.com/example/project.git"


def test_run_create_rejects_non_github_url() -> None:
    with pytest.raises(ValidationError):
        RunCreate(repository_url="https://example.com/project")
