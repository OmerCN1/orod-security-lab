import asyncio
import time
from pathlib import Path

from fastapi.testclient import TestClient

from orod.adapters.persistence.sqlite import SQLiteRunStore
from orod.config import Settings
from orod.domain.models import RunPhase, RunRecord, RunStatus
from orod.main import create_app


def lifecycle_settings(tmp_path: Path) -> Settings:
    return Settings(
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


def test_startup_fails_runs_a_previous_process_left_running(tmp_path: Path) -> None:
    settings = lifecycle_settings(tmp_path)

    async def seed() -> None:
        store = SQLiteRunStore(settings.database_path)
        await store.initialize()
        await store.create_run(
            RunRecord(
                id="stranded",
                repository_url="demo://vulnerable-python",
                status=RunStatus.RUNNING,
                phase=RunPhase.SECURITY,
            )
        )

    asyncio.run(seed())
    with TestClient(create_app(settings)) as client:
        run = client.get("/api/v1/runs/stranded").json()
        assert run["status"] == "failed"
        assert run["phase"] == "failed"
        assert "backend stopped" in run["error"]
        # The stream ends instead of polling a run nothing will ever finish.
        events = client.get("/api/v1/runs/stranded/events").text
        assert "Run interrupted by a backend restart" in events


def test_cancelling_a_completed_run_is_refused_and_keeps_its_result(tmp_path: Path) -> None:
    with TestClient(create_app(lifecycle_settings(tmp_path))) as client:
        created = client.post(
            "/api/v1/runs", json={"repository_url": "demo://vulnerable-python", "trusted": True}
        )
        run_id = created.json()["id"]
        deadline = time.monotonic() + 30
        payload = created.json()
        while payload["status"] in {"queued", "running"} and time.monotonic() < deadline:
            time.sleep(0.05)
            payload = client.get(f"/api/v1/runs/{run_id}").json()
        assert payload["status"] == "completed", payload

        response = client.post(f"/api/v1/runs/{run_id}/cancel")

        assert response.status_code == 409
        assert client.get(f"/api/v1/runs/{run_id}").json()["status"] == "completed"
        assert client.post("/api/v1/runs/missing/cancel").status_code == 404
