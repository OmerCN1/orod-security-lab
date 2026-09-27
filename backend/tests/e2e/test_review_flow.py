import json
import time
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from orod.config import Settings
from orod.main import create_app
from tests.api_auth import AUTH_HEADERS


def review_settings(tmp_path: Path) -> Settings:
    return Settings(
        database_path=tmp_path / "orod.sqlite3",
        checkpoint_path=tmp_path / "checkpoints.sqlite3",
        chroma_path=tmp_path / "chroma",
        workspace_root=tmp_path / "workspaces",
        use_llm=False,
        require_human_approval=True,
        enable_external_scanners=False,
        enable_github_publish=False,
        command_timeout_seconds=30,
        event_poll_interval_seconds=0.01,
    )


def wait_for_status(client: TestClient, run_id: str, *wanted: str, timeout: float = 40) -> Any:
    deadline = time.monotonic() + timeout
    payload = client.get(f"/api/v1/runs/{run_id}").json()
    while payload["status"] not in wanted and time.monotonic() < deadline:
        time.sleep(0.05)
        payload = client.get(f"/api/v1/runs/{run_id}").json()
    assert payload["status"] in wanted, payload
    return payload


def start_run(client: TestClient) -> str:
    response = client.post(
        "/api/v1/runs",
        json={"repository_url": "demo://vulnerable-python", "trusted": True},
    )
    assert response.status_code == 202
    return str(response.json()["id"])


def test_run_pauses_for_review_and_reject_completes_without_a_pull_request(
    tmp_path: Path,
) -> None:
    with TestClient(create_app(review_settings(tmp_path)), headers=AUTH_HEADERS) as client:
        run_id = start_run(client)
        paused = wait_for_status(client, run_id, "awaiting_review")

        assert paused["review"] is not None
        assert paused["review"]["can_approve"] is True
        assert paused["review"]["validation_passed"] is True
        assert paused["review"]["changed_files"] == ["app.py"]
        assert paused["pull_request"] is None

        accepted = client.post(f"/api/v1/runs/{run_id}/review", json={"decision": "reject"})
        assert accepted.status_code == 202

        final = wait_for_status(client, run_id, "completed")
        assert final["pull_request"] is None
        assert final["review"] is None
        assert final["metrics"]["review_decision"] == "reject"


def test_approval_resumes_the_graph_through_the_publish_node(tmp_path: Path) -> None:
    with TestClient(create_app(review_settings(tmp_path)), headers=AUTH_HEADERS) as client:
        run_id = start_run(client)
        wait_for_status(client, run_id, "awaiting_review")

        assert (
            client.post(f"/api/v1/runs/{run_id}/review", json={"decision": "approve"}).status_code
            == 202
        )
        final = wait_for_status(client, run_id, "completed")

        assert final["metrics"]["review_decision"] == "approve"
        # Publishing is disabled in this configuration, so the node runs and declines.
        assert final["pull_request"] is None
        events = client.get(f"/api/v1/runs/{run_id}/events", headers={"Last-Event-ID": "0"}).text
        assert "Draft PR publishing is disabled by configuration" in events


def test_regeneration_returns_to_the_developer_and_asks_again(tmp_path: Path) -> None:
    with TestClient(create_app(review_settings(tmp_path)), headers=AUTH_HEADERS) as client:
        run_id = start_run(client)
        first = wait_for_status(client, run_id, "awaiting_review")
        assert first["review"]["revision_count"] == 0

        accepted = client.post(
            f"/api/v1/runs/{run_id}/review",
            json={"decision": "regenerate", "feedback": "prefer an absolute executable path"},
        )
        assert accepted.status_code == 202

        deadline = time.monotonic() + 40
        payload = client.get(f"/api/v1/runs/{run_id}").json()

        def asked_again(current: Any) -> bool:
            review = current.get("review")
            return current["status"] == "awaiting_review" and review["revision_count"] == 1

        while (
            not asked_again(payload)
            and payload["status"] not in {"completed", "failed"}
            and time.monotonic() < deadline
        ):
            time.sleep(0.05)
            payload = client.get(f"/api/v1/runs/{run_id}").json()

        assert payload["status"] == "awaiting_review", payload
        assert payload["review"]["revision_count"] == 1
        # The regenerated patch starts from the base revision rather than stacking on the
        # first one, so it is a complete, approvable patch of its own - the same one here,
        # because the offline provider is deterministic.
        assert payload["review"]["can_approve"] is True, payload["validation"]
        assert payload["review"]["changed_files"] == ["app.py"]
        assert payload["patch"]["unified_diff"] == first["patch"]["unified_diff"]

        # The event stream stays open while a run is paused, so finish the run first.
        client.post(f"/api/v1/runs/{run_id}/review", json={"decision": "reject"})
        wait_for_status(client, run_id, "completed")
        events = client.get(f"/api/v1/runs/{run_id}/events", headers={"Last-Event-ID": "0"}).text
        assert "Previous patch reverted" in events
        # The dashboard counts `patch` events as attempts; the revert must not be one.
        emitted = [
            json.loads(line[len("data:") :])
            for line in events.splitlines()
            if line.startswith("data:")
        ]
        reverted = next(item for item in emitted if "Previous patch reverted" in item["message"])
        assert reverted["event_type"] == "run"


def test_review_endpoint_rejects_decisions_for_runs_that_are_not_paused(tmp_path: Path) -> None:
    with TestClient(create_app(review_settings(tmp_path)), headers=AUTH_HEADERS) as client:
        run_id = start_run(client)
        wait_for_status(client, run_id, "awaiting_review")
        client.post(f"/api/v1/runs/{run_id}/review", json={"decision": "reject"})
        wait_for_status(client, run_id, "completed")

        conflict = client.post(f"/api/v1/runs/{run_id}/review", json={"decision": "reject"})
        assert conflict.status_code == 409

        missing = client.post("/api/v1/runs/missing/review", json={"decision": "reject"})
        assert missing.status_code == 404


def test_regeneration_requires_feedback(tmp_path: Path) -> None:
    with TestClient(create_app(review_settings(tmp_path)), headers=AUTH_HEADERS) as client:
        run_id = start_run(client)
        wait_for_status(client, run_id, "awaiting_review")
        response = client.post(f"/api/v1/runs/{run_id}/review", json={"decision": "regenerate"})
        assert response.status_code == 422


def test_omitted_consent_blocks_validation_and_approval_even_for_demo(tmp_path: Path) -> None:
    with TestClient(create_app(review_settings(tmp_path)), headers=AUTH_HEADERS) as client:
        response = client.post("/api/v1/runs", json={"repository_url": "demo://vulnerable-python"})
        assert response.status_code == 202
        assert response.json()["trusted"] is False
        run_id = response.json()["id"]
        paused = wait_for_status(client, run_id, "awaiting_review")
        assert paused["repository"]["trusted"] is False
        assert paused["validation"]["passed"] is False
        assert paused["validation"]["commands"] == []
        assert "not explicitly marked trusted" in paused["validation"]["summary"]
        assert paused["review"]["can_approve"] is False
        assert paused["pull_request"] is None
        assert (
            client.post(f"/api/v1/runs/{run_id}/review", json={"decision": "approve"}).status_code
            == 422
        )
