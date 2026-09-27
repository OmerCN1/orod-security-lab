"""The local API refuses foreign hosts, unauthenticated callers and cross-site writes."""

import stat
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from orod.api.security import load_or_create_api_token
from orod.config import Settings
from orod.main import create_app
from tests.api_auth import AUTH_HEADERS


def access_settings(tmp_path: Path) -> Settings:
    return Settings(
        database_path=tmp_path / "orod.sqlite3",
        checkpoint_path=tmp_path / "checkpoints.sqlite3",
        chroma_path=tmp_path / "chroma",
        workspace_root=tmp_path / "workspaces",
        use_llm=False,
        enable_external_scanners=False,
    )


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    with TestClient(create_app(access_settings(tmp_path))) as test_client:
        yield test_client


@pytest.mark.parametrize("headers", [{}, {"Authorization": "Bearer wrong"}])
def test_requests_without_the_token_are_refused(
    client: TestClient, headers: dict[str, str]
) -> None:
    for method, path in (("GET", "/api/v1/runs"), ("POST", "/api/v1/runs/x/cancel")):
        response = client.request(method, path, headers=headers)
        assert response.status_code == 401
        assert response.headers["www-authenticate"] == "Bearer"


def test_the_token_grants_access(client: TestClient) -> None:
    assert client.get("/api/v1/runs", headers=AUTH_HEADERS).status_code == 200


def test_a_foreign_host_is_refused_even_with_the_token(client: TestClient) -> None:
    # What a DNS-rebinding page produces: its own hostname resolving to 127.0.0.1.
    response = client.get("/api/v1/runs", headers={**AUTH_HEADERS, "Host": "evil.example"})
    assert response.status_code == 400


def test_cross_site_writes_are_refused(client: TestClient) -> None:
    # The dashboard's proxy adds the token to whatever reaches it, so the browser's
    # Origin decides whether a write came from the dashboard.
    foreign = {**AUTH_HEADERS, "Origin": "https://evil.example"}
    assert client.post("/api/v1/runs/missing/cancel", headers=foreign).status_code == 403

    own = {**AUTH_HEADERS, "Origin": "http://localhost:5173"}
    assert client.post("/api/v1/runs/missing/cancel", headers=own).status_code == 404
    # Reads stay possible: a cross-site page cannot read the response anyway.
    assert client.get("/api/v1/runs", headers=foreign).status_code == 200


def test_the_schema_and_docs_stay_reachable_without_a_token(client: TestClient) -> None:
    assert client.get("/openapi.json").status_code == 200


def test_a_token_file_is_created_private_and_reused(tmp_path: Path) -> None:
    settings = access_settings(tmp_path).model_copy(
        update={"api_token": SecretStr(""), "api_token_path": tmp_path / "data" / "api-token"}
    )

    first = load_or_create_api_token(settings)
    second = load_or_create_api_token(settings)

    assert first == second and len(first) >= 32
    assert stat.S_IMODE(settings.api_token_path.stat().st_mode) == 0o600


def test_a_readable_token_file_is_made_private(tmp_path: Path) -> None:
    path = tmp_path / "api-token"
    path.write_text("x" * 40 + "\n")
    path.chmod(0o644)
    settings = access_settings(tmp_path).model_copy(
        update={"api_token": SecretStr(""), "api_token_path": path}
    )

    assert load_or_create_api_token(settings) == "x" * 40
    assert stat.S_IMODE(path.stat().st_mode) == 0o600


@pytest.mark.parametrize("kind", ["symlink", "short"])
def test_an_unusable_token_file_is_refused(tmp_path: Path, kind: str) -> None:
    path = tmp_path / "api-token"
    if kind == "symlink":
        (tmp_path / "elsewhere").write_text("y" * 40)
        path.symlink_to(tmp_path / "elsewhere")
    else:
        path.write_text("short")
    settings = access_settings(tmp_path).model_copy(
        update={"api_token": SecretStr(""), "api_token_path": path}
    )

    with pytest.raises(RuntimeError):
        load_or_create_api_token(settings)
