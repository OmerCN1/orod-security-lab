import json
import time
from pathlib import Path

from fastapi.testclient import TestClient

from orod.config import Settings
from orod.main import create_app


def test_localhost_and_loopback_frontends_are_allowed(tmp_path: Path) -> None:
    settings = Settings(
        database_path=tmp_path / "orod.sqlite3",
        checkpoint_path=tmp_path / "checkpoints.sqlite3",
        chroma_path=tmp_path / "chroma",
        workspace_root=tmp_path / "workspaces",
    )
    with TestClient(create_app(settings)) as client:
        response = client.options(
            "/api/v1/runs",
            headers={
                "Origin": "http://127.0.0.1:5173",
                "Access-Control-Request-Method": "POST",
            },
        )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://127.0.0.1:5173"


def test_demo_run_finds_and_fixes_shell_true(tmp_path: Path) -> None:
    settings = Settings(
        database_path=tmp_path / "orod.sqlite3",
        checkpoint_path=tmp_path / "checkpoints.sqlite3",
        chroma_path=tmp_path / "chroma",
        workspace_root=tmp_path / "workspaces",
        use_llm=False,
        require_human_approval=False,
        enable_external_scanners=False,
        enable_github_publish=False,
        command_timeout_seconds=30,
        event_poll_interval_seconds=0.01,
    )
    with TestClient(create_app(settings)) as client:
        response = client.post(
            "/api/v1/runs",
            json={"repository_url": "demo://vulnerable-python", "trusted": True},
        )
        assert response.status_code == 202
        run_id = response.json()["id"]

        deadline = time.monotonic() + 30
        payload = response.json()
        while payload["status"] in {"queued", "running"} and time.monotonic() < deadline:
            time.sleep(0.1)
            payload = client.get(f"/api/v1/runs/{run_id}").json()

        assert payload["status"] == "completed", payload
        assert any(item["rule_id"] == "B602" for item in payload["findings"])
        assert payload["patch"] is not None
        assert payload["validation"]["passed"] is True
        assert payload["pull_request"] is None
        assert payload["metrics"]["total_findings"] >= 1
        assert payload["metrics"]["patch_generated"] is True
        assert payload["metrics"]["validation_passed"] is True

        file_response = client.get(
            f"/api/v1/runs/{run_id}/files/content", params={"path": "app.py"}
        )
        assert file_response.status_code == 200
        assert "shell=False" in file_response.json()["content"]
        traversal = client.get(
            f"/api/v1/runs/{run_id}/files/content", params={"path": "../../AGENTS.md"}
        )
        assert traversal.status_code == 400

        events = client.get(f"/api/v1/runs/{run_id}/events", headers={"Last-Event-ID": "0"})
        assert events.status_code == 200
        assert "agent_started" in events.text
        assert "validation" in events.text
        assert "osv completed" in events.text

        # Each stage must speak as itself. Validation used to be emitted as "developer",
        # which left the UI unable to show it as a distinct agent at all.
        emitted = [
            json.loads(line[len("data:") :])
            for line in events.text.splitlines()
            if line.startswith("data:")
        ]
        by_agent: dict[str, set[str]] = {}
        for event in emitted:
            by_agent.setdefault(event["agent"], set()).add(event["event_type"])
        assert {"architect", "security", "developer", "validator"} <= set(by_agent)
        # Every agent that starts must also finish, or a UI deriving state from the last
        # event shows it as permanently in-flight.
        for agent in ("architect", "security", "developer", "validator"):
            assert "agent_completed" in by_agent[agent], (agent, by_agent[agent])


def test_event_replay_honours_an_explicit_zero_last_event_id(tmp_path: Path) -> None:
    """`Last-Event-ID: 0` means replay everything, and must win over the query cursor."""
    settings = Settings(
        database_path=tmp_path / "orod.sqlite3",
        checkpoint_path=tmp_path / "checkpoints.sqlite3",
        chroma_path=tmp_path / "chroma",
        workspace_root=tmp_path / "workspaces",
        use_llm=False,
        require_human_approval=False,
        enable_external_scanners=False,
        enable_github_publish=False,
        command_timeout_seconds=30,
        event_poll_interval_seconds=0.01,
    )
    with TestClient(create_app(settings)) as client:
        run_id = client.post(
            "/api/v1/runs",
            json={"repository_url": "demo://vulnerable-python", "trusted": True},
        ).json()["id"]

        deadline = time.monotonic() + 30
        payload = client.get(f"/api/v1/runs/{run_id}").json()
        while payload["status"] in {"queued", "running"} and time.monotonic() < deadline:
            time.sleep(0.05)
            payload = client.get(f"/api/v1/runs/{run_id}").json()
        assert payload["status"] == "completed", payload

        def event_count(path: str, headers: dict[str, str] | None = None) -> int:
            return client.get(path, headers=headers or {}).text.count("event: ")

        everything = event_count(f"/api/v1/runs/{run_id}/events")
        assert everything > 4

        # Header present and zero: replay everything despite the query cursor.
        assert (
            event_count(f"/api/v1/runs/{run_id}/events?after=4", {"Last-Event-ID": "0"})
            == everything
        )
        # No header: the query cursor applies.
        assert event_count(f"/api/v1/runs/{run_id}/events?after=4") == everything - 4
