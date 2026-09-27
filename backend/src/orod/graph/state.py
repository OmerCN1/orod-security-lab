from __future__ import annotations

from typing import Any, TypedDict


class TeamState(TypedDict, total=False):
    run_id: str
    repository_url: str
    base_branch: str | None
    trusted: bool
    model: str | None
    workspace_path: str
    phase: str
    repository_summary: dict[str, Any]
    dependencies: list[dict[str, Any]]
    findings: list[dict[str, Any]]
    selected_finding_ids: list[str]
    scan_complete: bool
    failed_scanners: list[str]
    validation_baseline: dict[str, Any] | None
    patch: dict[str, Any] | None
    validation: dict[str, Any] | None
    pull_request: dict[str, Any] | None
    errors: list[str]
    attempt: int
    review_decision: str | None
    reviewer_feedback: str | None
    revision_count: int
    started_at: str
