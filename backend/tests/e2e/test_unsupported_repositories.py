import json
import time
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from orod.config import Settings
from orod.main import create_app
from tests.api_auth import AUTH_HEADERS


def run_to_the_end(tmp_path: Path, repository_url: str) -> tuple[dict[str, Any], list[Any]]:
    settings = Settings(
        database_path=tmp_path / "orod.sqlite3",
        checkpoint_path=tmp_path / "checkpoints.sqlite3",
        chroma_path=tmp_path / "chroma",
        workspace_root=tmp_path / "workspaces",
        use_llm=False,
        require_human_approval=False,
        enable_external_scanners=False,
        command_timeout_seconds=30,
        event_poll_interval_seconds=0.01,
    )
    with TestClient(create_app(settings), headers=AUTH_HEADERS) as client:
        run_id = client.post("/api/v1/runs", json={"repository_url": repository_url}).json()["id"]
        deadline = time.monotonic() + 30
        payload = client.get(f"/api/v1/runs/{run_id}").json()
        while payload["status"] in {"queued", "running"} and time.monotonic() < deadline:
            time.sleep(0.05)
            payload = client.get(f"/api/v1/runs/{run_id}").json()
        stream = client.get(f"/api/v1/runs/{run_id}/events", headers={"Last-Event-ID": "0"}).text
        events = [json.loads(line[5:]) for line in stream.splitlines() if line.startswith("data:")]
        return payload, events


def test_a_repository_without_python_fails_with_a_clear_message(tmp_path: Path) -> None:
    run, events = run_to_the_end(tmp_path, "demo://javascript-repo")

    assert run["status"] == "failed"
    assert "No Python source files found" in run["error"]
    assert "JavaScript (1)" in run["error"]
    # It must not read as a clean scan: the security agent never ran.
    assert run["findings"] == [] and run["scan_complete"] is None
    architect = [event for event in events if event["agent"] == "architect"]
    assert architect[-1]["event_type"] == "agent_completed"
    assert architect[-1]["level"] == "error"
    assert not any(event["agent"] == "security" for event in events)


def test_a_mostly_foreign_repository_is_analysed_with_a_warning(tmp_path: Path) -> None:
    run, events = run_to_the_end(tmp_path, "demo://mostly-javascript-repo")

    assert run["status"] == "completed"
    warning = next(event for event in events if event["payload"].get("partial"))
    assert warning["level"] == "warning"
    assert "Mostly JavaScript" in warning["message"]
    assert "Only the 1 Python file(s) are analysed" in warning["message"]
