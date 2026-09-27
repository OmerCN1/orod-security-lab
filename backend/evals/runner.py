from __future__ import annotations

import asyncio
import shutil
import sys
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from fastapi import FastAPI

from evals.manifest import CASES_ROOT, EvalCase
from evals.metrics import (
    CaseResult,
    SuiteAggregate,
    SuiteResult,
    aggregate,
    estimate_cost_usd,
    score_detection,
    score_outcome,
)
from orod.application.finding_regressions import introduced_high_risk
from orod.application.run_analysis import RunCoordinator
from orod.config import Settings
from orod.domain.errors import RunAlreadyFinishedError
from orod.domain.findings import deduplicate_findings
from orod.domain.models import Finding, FindingSource, RunCreate, RunRecord
from orod.main import create_app
from orod.ports.llm import LLMProvider
from orod.ports.repository import RepositoryProvider
from orod.ports.scanners import SecurityScanner
from orod.ports.storage import RunStore

TERMINAL_STATUSES = {"completed", "failed", "cancelled"}
DEFAULT_CASE_TIMEOUT_SECONDS = 600


def build_settings(workspace: Path, model: str, use_llm: bool, command_timeout: int) -> Settings:
    """Isolated, hermetic settings for one suite.

    Every stateful path is redirected into a scratch directory, external scanners and
    publishing are off, and the fixture root points at the corpus so ``demo://<case-id>``
    resolves. The corpus declares no pinned dependencies, so the OSV adapter
    short-circuits and the suite never touches the network.
    """
    return Settings(
        database_path=workspace / "orod.sqlite3",
        checkpoint_path=workspace / "checkpoints.sqlite3",
        chroma_path=workspace / "chroma",
        workspace_root=workspace / "workspaces",
        fixture_root=CASES_ROOT,
        chat_model=model,
        use_llm=use_llm,
        # The harness is headless: the review node must decide automatically, or every
        # case would interrupt and sit until its timeout.
        require_human_approval=False,
        enable_external_scanners=False,
        enable_github_publish=False,
        command_timeout_seconds=command_timeout,
        event_poll_interval_seconds=0.01,
    )


@asynccontextmanager
async def running_app(settings: Settings) -> AsyncIterator[FastAPI]:
    """Start the real application graph in-process, without the HTTP transport."""
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        yield app


def _store(app: FastAPI) -> RunStore:
    return cast(RunStore, app.state.store)


def _coordinator(app: FastAPI) -> RunCoordinator:
    return cast(RunCoordinator, app.state.coordinator)


def _llm(app: FastAPI) -> LLMProvider:
    return cast(LLMProvider, app.state.llm)


def _repository(app: FastAPI) -> RepositoryProvider:
    return cast(RepositoryProvider, app.state.repository)


def _scanners(app: FastAPI) -> list[SecurityScanner]:
    return cast(list[SecurityScanner], app.state.scanners)


async def _await_terminal_run(
    app: FastAPI, run_id: str, timeout_seconds: float
) -> RunRecord:
    store = _store(app)
    deadline = time.monotonic() + timeout_seconds
    while True:
        record = await store.get_run(run_id)
        if record is not None and record.status.value in TERMINAL_STATUSES:
            return record
        if time.monotonic() >= deadline:
            try:
                await _coordinator(app).cancel(run_id)
            except RunAlreadyFinishedError:
                pass  # It finished at the deadline; report that result below.
            cancelled = await store.get_run(run_id)
            if cancelled is None:
                raise RuntimeError(f"run {run_id} vanished from the store")
            if cancelled.status.value != "cancelled":
                return cancelled
            cancelled.error = cancelled.error or f"case timed out after {timeout_seconds:.0f}s"
            return cancelled
        await asyncio.sleep(0.05)


async def _rescan(app: FastAPI, record: RunRecord) -> list[Finding]:
    """Independently rescan the post-run workspace.

    The graph performs its own residual check before allowing a pull request; scanning
    again here means the report never has to take the pipeline's word for it.
    """
    snapshot = record.repository
    if snapshot is None or not Path(snapshot.workspace_path).is_dir():
        return []
    findings: list[Finding] = []
    for scanner in _scanners(app):
        try:
            findings.extend(await scanner.scan(snapshot))
        except Exception as exc:  # a broken rescan must not mask the run's own result
            print(f"  rescan skipped {scanner.name}: {type(exc).__name__}: {exc}", file=sys.stderr)
    return deduplicate_findings(findings)


async def run_case(app: FastAPI, case: EvalCase, timeout_seconds: float) -> CaseResult:
    result = CaseResult(
        case_id=case.id,
        title=case.title,
        cwe=case.cwe,
        expected_outcome=case.expected_outcome,
        tags=list(case.tags),
    )
    llm = _llm(app)
    llm.reset_usage()
    started = time.monotonic()
    try:
        run = await _coordinator(app).start(
            RunCreate(repository_url=case.repository_url, trusted=True)
        )
        record = await _await_terminal_run(app, run.id, timeout_seconds)
    except Exception as exc:
        result.error = f"{type(exc).__name__}: {exc}"[:500]
        result.duration_ms = int((time.monotonic() - started) * 1000)
        result.llm_usage = llm.usage()
        result.cost_usd = estimate_cost_usd(result.llm_usage)
        result.outcome_met, result.outcome_detail = False, result.error
        return result

    result.run_id = record.id
    result.run_status = record.status.value
    result.error = record.error
    result.duration_ms = (
        record.metrics.duration_ms
        if record.metrics
        else int((time.monotonic() - started) * 1000)
    )
    result.detected_rules = sorted({item.rule_id for item in record.findings})
    result.detection = score_detection(
        case, [(item.rule_id, item.file_path) for item in record.findings]
    )
    result.patch_generated = record.patch is not None
    result.patch_attempts = record.metrics.repair_attempts if record.metrics else 0
    result.validation_passed = bool(record.validation and record.validation.passed)
    result.validation_summary = record.validation.summary if record.validation else ""

    post_patch = await _rescan(app, record)
    if case.expected_outcome == "fix" and result.patch_generated:
        remaining = {item.rule_id for item in post_patch}
        result.residual_target_findings = sorted(
            {item.rule_id for item in case.expected_findings} & remaining
        )
    if record.repository is not None:
        # The rescan runs code scanners only, so compare it with the code findings.
        before = [item for item in record.findings if item.source != FindingSource.OSV]
        introduced = await introduced_high_risk(
            _repository(app), record.repository, before, post_patch, max_chars=1_000_000
        )
        result.new_high_findings = len(introduced)

    result.llm_usage = llm.usage()
    result.cost_usd = estimate_cost_usd(result.llm_usage)
    result.outcome_met, result.outcome_detail = score_outcome(case, result)
    return result


async def run_suite(
    label: str,
    model: str,
    use_llm: bool,
    cases: list[EvalCase],
    *,
    scratch_root: Path,
    case_timeout: float = DEFAULT_CASE_TIMEOUT_SECONDS,
    command_timeout: int = 120,
    progress: Any | None = None,
) -> SuiteResult:
    """Replay the whole corpus against one model configuration."""
    started_at = datetime.now(UTC).isoformat()
    suite = SuiteResult(
        label=label,
        model=model,
        provider="deterministic" if not use_llm else "",
        use_llm=use_llm,
        started_at=started_at,
    )
    workspace = scratch_root / label.replace("/", "_").replace(":", "_")
    if workspace.exists():
        shutil.rmtree(workspace)
    workspace.mkdir(parents=True)

    settings = build_settings(workspace, model, use_llm, command_timeout)
    try:
        async with running_app(settings) as app:
            suite.provider = _llm(app).usage().provider
            try:
                healthy, detail = await _llm(app).health()
            except Exception as exc:  # an unusable provider skips its suite, not the report
                healthy, detail = False, f"health check failed: {type(exc).__name__}: {exc}"[:200]
            if not healthy:
                suite.skipped_reason = detail
                suite.finished_at = datetime.now(UTC).isoformat()
                return suite
            for index, case in enumerate(cases, start=1):
                if progress is not None:
                    progress(label, index, len(cases), case.id)
                suite.results.append(await run_case(app, case, case_timeout))
    finally:
        shutil.rmtree(workspace, ignore_errors=True)

    suite.totals = aggregate(cases, suite.results) if suite.results else SuiteAggregate()
    suite.finished_at = datetime.now(UTC).isoformat()
    return suite
