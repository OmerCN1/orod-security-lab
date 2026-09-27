from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Header, HTTPException, status
from fastapi.sse import EventSourceResponse, ServerSentEvent

from orod.api.dependencies import get_coordinator, get_repository, get_settings, get_store
from orod.application.run_analysis import RunCoordinator
from orod.application.stream_events import stream_run_events
from orod.config import Settings
from orod.domain.errors import (
    ReviewNotAllowedError,
    ReviewNotPendingError,
    RunAlreadyFinishedError,
    RunNotFoundError,
    UnsafePathError,
)
from orod.domain.models import (
    FileContent,
    FileEntry,
    Finding,
    PatchProposal,
    PullRequestResult,
    ReviewSubmission,
    RunCreate,
    RunRecord,
    RunSummary,
)
from orod.ports.repository import RepositoryProvider
from orod.ports.storage import RunStore

router = APIRouter(prefix="/runs", tags=["runs"])


@router.post("", response_model=RunRecord, status_code=status.HTTP_202_ACCEPTED)
async def create_run(
    payload: RunCreate,
    coordinator: Annotated[RunCoordinator, Depends(get_coordinator)],
) -> RunRecord:
    return await coordinator.start(payload)


@router.get("", response_model=list[RunSummary])
async def list_runs(
    store: Annotated[RunStore, Depends(get_store)],
    limit: int = 50,
    offset: int = 0,
) -> list[RunSummary]:
    runs = await store.list_runs(limit=limit, offset=offset)
    return [RunSummary.from_run(run) for run in runs]


@router.get("/{run_id}", response_model=RunRecord)
async def get_run(
    run_id: str,
    store: Annotated[RunStore, Depends(get_store)],
) -> RunRecord:
    return await _require_run(store, run_id)


@router.get("/{run_id}/events", response_class=EventSourceResponse)
async def get_events(
    run_id: str,
    store: Annotated[RunStore, Depends(get_store)],
    settings: Annotated[Settings, Depends(get_settings)],
    last_event_id: Annotated[str | None, Header(alias="Last-Event-ID")] = None,
    after: int = 0,
) -> AsyncIterator[ServerSentEvent]:
    """Replay persisted events, then stream new ones.

    Browsers cannot set headers on an ``EventSource``, so the resume cursor is accepted
    as the ``after`` query parameter as well as the standard ``Last-Event-ID`` header.
    The header wins when both are present, because that is what an automatic browser
    reconnect sends.
    """
    await _require_run(store, run_id)
    if last_event_id is None:
        cursor = after
    else:
        # An explicit `Last-Event-ID: 0` means "replay from the beginning", so the header
        # is honoured even when it is zero rather than falling back to the query value.
        try:
            cursor = int(last_event_id)
        except ValueError:
            cursor = 0
    after = max(0, cursor)

    async for event in stream_run_events(
        store,
        run_id,
        after,
        settings.event_poll_interval_seconds,
    ):
        yield ServerSentEvent(
            data=event.model_dump(mode="json"),
            event=event.event_type.value,
            id=str(event.sequence),
        )


@router.get("/{run_id}/files", response_model=list[FileEntry])
async def get_files(
    run_id: str,
    store: Annotated[RunStore, Depends(get_store)],
) -> list[FileEntry]:
    run = await _require_run(store, run_id)
    return run.repository.files if run.repository else []


@router.get("/{run_id}/files/content", response_model=FileContent)
async def get_file_content(
    run_id: str,
    path: str,
    store: Annotated[RunStore, Depends(get_store)],
    repository: Annotated[RepositoryProvider, Depends(get_repository)],
    revision: Literal["working", "base"] = "working",
) -> FileContent:
    """Return a workspace file.

    ``revision=base`` returns the content as it was before any patch was applied, which
    is the left-hand side of the dashboard's side-by-side diff.
    """
    run = await _require_run(store, run_id)
    if run.repository is None:
        raise HTTPException(status_code=404, detail="repository is not ready")
    reader = repository.read_base_files if revision == "base" else repository.read_files
    try:
        contents = await reader(run.repository, [path], max_chars=100_000)
    except UnsafePathError as exc:
        raise HTTPException(status_code=400, detail="unsafe file path") from exc
    if path not in contents:
        raise HTTPException(status_code=404, detail="file is unavailable")
    entry = next((item for item in run.repository.files if item.path == path), None)
    return FileContent(
        path=path,
        content=contents[path],
        language=entry.language if entry else None,
    )


@router.get("/{run_id}/findings", response_model=list[Finding])
async def get_findings(
    run_id: str,
    store: Annotated[RunStore, Depends(get_store)],
) -> list[Finding]:
    return (await _require_run(store, run_id)).findings


@router.get("/{run_id}/patch", response_model=PatchProposal)
async def get_patch(
    run_id: str,
    store: Annotated[RunStore, Depends(get_store)],
) -> PatchProposal:
    run = await _require_run(store, run_id)
    if run.patch is None:
        raise HTTPException(status_code=404, detail="patch is not available")
    return run.patch


@router.get("/{run_id}/pull-request", response_model=PullRequestResult)
async def get_pull_request(
    run_id: str,
    store: Annotated[RunStore, Depends(get_store)],
) -> PullRequestResult:
    run = await _require_run(store, run_id)
    if run.pull_request is None:
        raise HTTPException(status_code=404, detail="pull request is not available")
    return run.pull_request


@router.post("/{run_id}/review", response_model=RunRecord, status_code=status.HTTP_202_ACCEPTED)
async def submit_review(
    run_id: str,
    submission: ReviewSubmission,
    coordinator: Annotated[RunCoordinator, Depends(get_coordinator)],
) -> RunRecord:
    try:
        return await coordinator.submit_review(run_id, submission)
    except RunNotFoundError as exc:
        raise HTTPException(status_code=404, detail="run not found") from exc
    except ReviewNotAllowedError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ReviewNotPendingError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/{run_id}/cancel", response_model=RunRecord)
async def cancel_run(
    run_id: str,
    coordinator: Annotated[RunCoordinator, Depends(get_coordinator)],
) -> RunRecord:
    try:
        run = await coordinator.cancel(run_id)
    except RunAlreadyFinishedError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if run is None:
        raise HTTPException(status_code=404, detail="run not found")
    return run


async def _require_run(store: RunStore, run_id: str) -> RunRecord:
    run = await store.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="run not found")
    return run
