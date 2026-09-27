from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from orod.agents.base import AgentServices
from orod.application.finding_regressions import introduced_high_risk
from orod.domain.errors import OrodError, PatchRejectedError, ScanFailedError
from orod.domain.events import EventLevel, EventType, RunEvent
from orod.domain.findings import deduplicate_findings
from orod.domain.models import (
    Finding,
    FindingSource,
    PatchProposal,
    PullRequestResult,
    RepositorySnapshot,
    ReviewDecision,
    ReviewRequest,
    RunMetrics,
    RunPhase,
    RunStatus,
    ScannerRun,
    ValidationBaseline,
    ValidationResult,
    utc_now,
)
from orod.graph.routing import (
    after_review,
    after_security,
    after_validation,
    is_actionable_finding,
)
from orod.graph.state import TeamState


def scanner_failure_detail(exc: Exception) -> str:
    """A short, log-safe reason: our own error messages, otherwise only the error type."""
    if isinstance(exc, OrodError) and str(exc):
        return f"{type(exc).__name__}: {str(exc)[:200]}"
    return type(exc).__name__


def build_security_team(services: AgentServices, checkpointer: Any) -> Any:
    async def emit(
        state: TeamState,
        agent: str,
        event_type: EventType,
        message: str,
        *,
        level: EventLevel = EventLevel.INFO,
        payload: dict[str, object] | None = None,
    ) -> None:
        await services.store.append_event(
            RunEvent(
                run_id=state["run_id"],
                agent=agent,
                event_type=event_type,
                level=level,
                message=message,
                payload=payload or {},
            )
        )

    async def mutate_run(state: TeamState, **changes: object) -> None:
        run = await services.store.get_run(state["run_id"])
        if run is None:
            return
        for key, value in changes.items():
            setattr(run, key, value)
        run.updated_at = utc_now()
        await services.store.save_run(run)

    async def rescan_dependencies(
        snapshot: RepositorySnapshot, original_findings: list[Finding]
    ) -> tuple[list[Finding], str | None]:
        """Post-patch OSV findings, plus an error when they cannot be trusted as complete."""
        current = await services.repository.discover_dependencies(snapshot)
        if [item.model_dump() for item in current] == [
            item.model_dump() for item in snapshot.dependencies
        ]:
            # Unchanged manifests: the original package/version matches still hold,
            # and the rescan needs no network access.
            return [item for item in original_findings if item.source == FindingSource.OSV], None
        findings, sync = await services.vulnerabilities.scan_dependencies(current)
        if not sync.complete:
            return findings, "; ".join(sync.errors[:3]) or "OSV lookup was incomplete"
        return findings, None

    async def architect(state: TeamState) -> dict[str, object]:
        await mutate_run(state, status=RunStatus.RUNNING, phase=RunPhase.ARCHITECT)
        await emit(state, "architect", EventType.AGENT_STARTED, "Repository inspection started")
        snapshot = await services.repository.prepare(
            state["repository_url"],
            state.get("base_branch"),
            state["run_id"],
            bool(state.get("trusted", False)),
        )
        await mutate_run(state, repository=snapshot)
        await emit(
            state,
            "architect",
            EventType.AGENT_COMPLETED,
            snapshot.summary,
            payload={"files": len(snapshot.files), "dependencies": len(snapshot.dependencies)},
        )
        return {
            "phase": RunPhase.ARCHITECT.value,
            "workspace_path": snapshot.workspace_path,
            "repository_summary": snapshot.model_dump(mode="json"),
            "dependencies": [item.model_dump(mode="json") for item in snapshot.dependencies],
        }

    async def security(state: TeamState) -> dict[str, object]:
        await mutate_run(state, phase=RunPhase.SECURITY)
        await emit(state, "security", EventType.AGENT_STARTED, "Security analysis started")
        snapshot = RepositorySnapshot.model_validate(state["repository_summary"])
        findings: list[Finding] = []
        scanner_runs: list[ScannerRun] = []
        for scanner in services.scanners:
            try:
                scanner_findings = await scanner.scan(snapshot)
            except Exception as exc:
                detail = scanner_failure_detail(exc)
                scanner_runs.append(ScannerRun(name=scanner.name, ok=False, detail=detail))
                # The payload names the scanner, so the dashboard lists a failed scanner
                # instead of silently counting only the ones that worked.
                await emit(
                    state,
                    "security",
                    EventType.RUN,
                    f"{scanner.name} failed: {detail}",
                    level=EventLevel.WARNING,
                    payload={"scanner": scanner.name, "count": 0, "ok": False, "error": detail},
                )
                continue
            findings.extend(scanner_findings)
            scanner_runs.append(
                ScannerRun(name=scanner.name, ok=True, findings=len(scanner_findings))
            )
            await emit(
                state,
                "security",
                EventType.RUN,
                f"{scanner.name} completed with {len(scanner_findings)} finding(s)",
                payload={"scanner": scanner.name, "count": len(scanner_findings), "ok": True},
            )

        if scanner_runs and not any(item.ok for item in scanner_runs):
            # Reporting this as a clean repository would be the one wrong answer.
            await mutate_run(state, scanners=scanner_runs, scan_complete=False)
            message = "No security scanner completed: " + ", ".join(
                f"{item.name} ({item.detail})" for item in scanner_runs
            )
            await emit(
                state,
                "security",
                EventType.AGENT_COMPLETED,
                message,
                level=EventLevel.ERROR,
                payload={"scan_complete": False},
            )
            raise ScanFailedError(message)

        dependency_findings, sync = await services.vulnerabilities.scan_dependencies(
            snapshot.dependencies
        )
        findings.extend(dependency_findings)
        osv_error_count = len(sync.errors)
        await emit(
            state,
            "security",
            EventType.RUN,
            (
                f"osv completed with {len(dependency_findings)} finding(s)"
                if not osv_error_count
                else (
                    f"osv completed with {len(dependency_findings)} finding(s) "
                    f"and {osv_error_count} error(s)"
                )
            ),
            level=EventLevel.WARNING if osv_error_count else EventLevel.INFO,
            payload={
                "scanner": "osv",
                "count": len(dependency_findings),
                "ok": sync.complete,
                "queried": sync.queried_packages,
                "errors": sync.errors[:5],
            },
        )
        scanner_runs.append(
            ScannerRun(
                name="osv",
                ok=sync.complete,
                findings=len(dependency_findings),
                detail="" if sync.complete else "; ".join(sync.errors[:2]),
            )
        )
        scan_complete = all(item.ok for item in scanner_runs)

        if sync.cached_advisories:
            for finding in findings:
                if finding.source.value == "osv":
                    continue
                try:
                    finding.rag_context = await services.vector_store.search(
                        f"{finding.rule_id} {finding.title} {finding.message}",
                        limit=2,
                    )
                except Exception:
                    finding.rag_context = []

        final_findings = deduplicate_findings(findings)
        await mutate_run(
            state, findings=final_findings, scanners=scanner_runs, scan_complete=scan_complete
        )
        for finding in final_findings[:100]:
            await emit(
                state,
                "security",
                EventType.FINDING,
                finding.title,
                payload=finding.model_dump(mode="json"),
            )
        await emit(
            state,
            "security",
            EventType.AGENT_COMPLETED,
            (
                f"Security analysis completed with {len(final_findings)} finding(s)"
                if scan_complete
                else (
                    f"Security analysis incomplete with {len(final_findings)} finding(s); "
                    "failed: " + ", ".join(item.name for item in scanner_runs if not item.ok)
                )
            ),
            level=EventLevel.INFO if scan_complete else EventLevel.WARNING,
            payload={
                "count": len(final_findings),
                "scan_complete": scan_complete,
                "osv_queried": sync.queried_packages,
                "osv_cached": sync.cached_advisories,
                "osv_errors": sync.errors[:5],
            },
        )
        selected = [finding.id for finding in final_findings if is_actionable_finding(finding)]
        review_only = len(final_findings) - len(selected)
        await emit(
            state,
            "security",
            EventType.RUN,
            (
                f"{len(selected)} finding(s) selected for automated remediation; "
                f"{review_only} require manual review"
            ),
            payload={
                "selected_count": len(selected),
                "review_only_count": review_only,
                "selected_finding_ids": selected,
            },
        )
        return {
            "phase": RunPhase.SECURITY.value,
            "findings": [item.model_dump(mode="json") for item in final_findings],
            "selected_finding_ids": selected,
            "scan_complete": scan_complete,
            "failed_scanners": [item.name for item in scanner_runs if not item.ok],
        }

    async def developer(state: TeamState) -> dict[str, object]:
        await mutate_run(state, phase=RunPhase.DEVELOPER)
        attempt = int(state.get("attempt", 0)) + 1
        await emit(
            state,
            "developer",
            EventType.AGENT_STARTED,
            f"Patch generation attempt {attempt} started",
        )
        snapshot = RepositorySnapshot.model_validate(state["repository_summary"])
        previous_patch = state.get("patch")
        if previous_patch is not None:
            # Every attempt starts from the base revision. Stacking attempts would
            # validate and show their union while publishing only the latest one.
            await services.repository.revert_patch(
                snapshot, str(previous_patch.get("unified_diff") or "")
            )
            await mutate_run(state, patch=None)
            await emit(
                state,
                "developer",
                EventType.PATCH,
                f"Previous patch reverted; attempt {attempt} starts from the base revision",
                payload={"attempt": attempt, "reverted": True},
            )
        baseline_update: dict[str, object] = {}
        if "validation_baseline" not in state:
            # Measured once, on the untouched base revision, so validation can tell a
            # failure the patch introduced from one the repository already had.
            baseline = await services.repository.record_baseline(snapshot)
            baseline_update["validation_baseline"] = (
                baseline.model_dump(mode="json") if baseline is not None else None
            )
            if baseline is not None:
                existing = sum(len(check.failures) for check in baseline.checks)
                await emit(
                    state,
                    "developer",
                    EventType.RUN,
                    f"Validation baseline recorded on the base revision: "
                    f"{existing} pre-existing failure(s)",
                    payload={
                        "baseline": [
                            {
                                "check": check.name,
                                "return_code": check.return_code,
                                "failures": len(check.failures),
                            }
                            for check in baseline.checks
                        ]
                    },
                )
        findings = [Finding.model_validate(value) for value in state.get("findings", [])]
        selected = set(state.get("selected_finding_ids", []))
        chosen = [item for item in findings if item.id in selected]
        paths = sorted(
            {item.file_path for item in chosen if item.file_path and item.file_path.endswith(".py")}
        )
        sources = await services.repository.read_files(snapshot, paths)
        previous_validation = state.get("validation") or {}
        previous_error = str(previous_validation.get("summary") or "") or None
        reviewer_feedback = state.get("reviewer_feedback") or None
        provider = services.llms.for_model(state.get("model"))
        proposal = await provider.propose_patch(
            snapshot, chosen, sources, previous_error, reviewer_feedback
        )
        if proposal is None:
            await emit(
                state,
                "developer",
                EventType.AGENT_COMPLETED,
                "No safe automatic patch was produced",
                level=EventLevel.WARNING,
            )
            return {
                "phase": RunPhase.DEVELOPER.value,
                "patch": None,
                "attempt": attempt,
                **baseline_update,
            }

        try:
            applied_diff = await services.repository.apply_patch(snapshot, proposal)
        except PatchRejectedError as exc:
            errors = [*state.get("errors", []), str(exc)[:500]]
            await emit(
                state,
                "developer",
                EventType.PATCH,
                f"Generated patch was rejected on attempt {attempt}",
                level=EventLevel.WARNING,
                payload={"reason": str(exc)[:500], "attempt": attempt},
            )
            return {
                "phase": RunPhase.DEVELOPER.value,
                "patch": None,
                "attempt": attempt,
                "errors": errors,
                **baseline_update,
            }
        proposal.unified_diff = applied_diff
        await mutate_run(state, patch=proposal)
        await emit(
            state,
            "developer",
            EventType.PATCH,
            proposal.explanation,
            payload={"changed_files": proposal.changed_files, "attempt": attempt},
        )
        await emit(
            state,
            "developer",
            EventType.AGENT_COMPLETED,
            f"Patch applied to {len(proposal.changed_files)} file(s)",
        )
        return {
            "phase": RunPhase.DEVELOPER.value,
            "patch": proposal.model_dump(mode="json"),
            "attempt": attempt,
            "reviewer_feedback": None,
            **baseline_update,
        }

    async def validate(state: TeamState) -> dict[str, object]:
        await mutate_run(state, phase=RunPhase.VALIDATION)
        await emit(state, "validator", EventType.AGENT_STARTED, "Validation started")
        if state.get("patch") is None:
            errors = state.get("errors", [])
            summary = f"Patch rejected: {errors[-1]}" if errors else "No patch to validate."
            result = ValidationResult(passed=False, summary=summary)
        else:
            snapshot = RepositorySnapshot.model_validate(state["repository_summary"])
            baseline_data = state.get("validation_baseline")
            baseline = ValidationBaseline.model_validate(baseline_data) if baseline_data else None
            result = await services.repository.validate(snapshot, baseline)
            if result.passed:
                selected_ids = set(state.get("selected_finding_ids", []))
                original_findings = [
                    Finding.model_validate(value) for value in state.get("findings", [])
                ]
                # Dependency remediation is not automated yet, so the residual check
                # covers code findings only; OSV findings still count as regressions.
                selected_targets = {
                    (item.source, item.rule_id, item.file_path)
                    for item in original_findings
                    if item.id in selected_ids and item.source != FindingSource.OSV
                }
                raw_post_patch: list[Finding] = []
                scanner_errors: list[str] = []
                for scanner in services.scanners:
                    try:
                        raw_post_patch.extend(await scanner.scan(snapshot))
                    except Exception as exc:
                        scanner_errors.append(f"{scanner.name}: {type(exc).__name__}")
                # The original findings were deduplicated before being stored, so the
                # rescan must be too or a rule seen by two scanners looks like a new one.
                post_patch_code_findings = deduplicate_findings(raw_post_patch)
                dependency_findings, dependency_error = await rescan_dependencies(
                    snapshot, original_findings
                )
                residual_targets = {
                    (item.source, item.rule_id, item.file_path) for item in post_patch_code_findings
                } & selected_targets
                # The original findings include OSV, so the rescan must too; otherwise a
                # vulnerable dependency hides a high finding the patch introduced.
                introduced = await introduced_high_risk(
                    services.repository,
                    snapshot,
                    original_findings,
                    [*post_patch_code_findings, *dependency_findings],
                    max_chars=services.settings.max_file_bytes,
                )
                result.new_high_findings = len(introduced)
                if scanner_errors:
                    result.passed = False
                    result.summary = "Post-patch security scan failed: " + ", ".join(scanner_errors)
                elif dependency_error is not None:
                    result.passed = False
                    result.summary = f"Post-patch dependency check failed: {dependency_error}"
                elif residual_targets:
                    result.passed = False
                    residual_rules = ", ".join(
                        sorted(f"{rule_id} in {path}" for _, rule_id, path in residual_targets)
                    )
                    result.summary = f"Patch did not resolve selected findings: {residual_rules}"
                elif introduced:
                    result.passed = False
                    introduced_rules = ", ".join(
                        sorted(
                            f"{item.rule_id} in {item.file_path}"
                            + (f":{item.line}" if item.line else "")
                            for item in introduced
                        )
                    )
                    result.summary = (
                        f"Patch introduced new high/critical security findings: {introduced_rules}"
                    )
        await mutate_run(state, validation=result)
        await emit(
            state,
            "validator",
            EventType.VALIDATION,
            result.summary,
            level=EventLevel.INFO if result.passed else EventLevel.WARNING,
            payload={
                "passed": result.passed,
                "commands": [
                    {"argv": command.argv, "return_code": command.return_code}
                    for command in result.commands
                ],
            },
        )
        await emit(
            state,
            "validator",
            EventType.AGENT_COMPLETED,
            "Validation passed" if result.passed else "Validation failed",
            level=EventLevel.INFO if result.passed else EventLevel.WARNING,
            payload={"passed": result.passed},
        )
        return {"phase": RunPhase.VALIDATION.value, "validation": result.model_dump(mode="json")}

    async def review(state: TeamState) -> dict[str, object]:
        validation_data = state.get("validation") or {}
        passed = bool(validation_data.get("passed"))
        patch_data = state.get("patch")

        if not services.settings.require_human_approval:
            decision = ReviewDecision.APPROVE if passed else ReviewDecision.REJECT
            return {"phase": RunPhase.REVIEW.value, "review_decision": decision.value}

        patch = PatchProposal.model_validate(patch_data) if patch_data is not None else None
        request = ReviewRequest(
            changed_files=list(patch.changed_files) if patch else [],
            explanation=patch.explanation if patch else "",
            validation_passed=passed,
            validation_summary=str(validation_data.get("summary") or ""),
            can_approve=bool(patch is not None and passed),
            revision_count=int(state.get("revision_count", 0)),
        )

        # `interrupt` re-executes this node from the top when the graph resumes, so the
        # announcement below must be idempotent. It is guarded on the run's own status:
        # it fires once per review round and is skipped on the resuming pass, because
        # only the code after `interrupt` moves the run out of AWAITING_REVIEW.
        run = await services.store.get_run(state["run_id"])
        if run is None or run.status != RunStatus.AWAITING_REVIEW:
            await mutate_run(
                state,
                status=RunStatus.AWAITING_REVIEW,
                phase=RunPhase.REVIEW,
                review=request,
            )
            await emit(
                state,
                "reviewer",
                EventType.AGENT_STARTED,
                "Waiting for a human decision on the generated patch",
                payload=request.model_dump(mode="json"),
            )

        answer = interrupt(request.model_dump(mode="json"))

        raw = answer if isinstance(answer, dict) else {}
        try:
            decision = ReviewDecision(str(raw.get("decision")))
        except ValueError:
            decision = ReviewDecision.REJECT
        feedback = raw.get("feedback")
        feedback_text = str(feedback) if isinstance(feedback, str) and feedback.strip() else None

        # Second gate on the publishing invariant; the API rejects this too.
        if decision == ReviewDecision.APPROVE and not passed:
            decision = ReviewDecision.REJECT

        await mutate_run(state, status=RunStatus.RUNNING, phase=RunPhase.REVIEW, review=None)
        await emit(
            state,
            "reviewer",
            EventType.AGENT_COMPLETED,
            f"Reviewer decision: {decision.value}",
            payload={"decision": decision.value, "has_feedback": feedback_text is not None},
        )

        updates: dict[str, object] = {
            "phase": RunPhase.REVIEW.value,
            "review_decision": decision.value,
        }
        if decision == ReviewDecision.REGENERATE:
            updates["reviewer_feedback"] = feedback_text
            updates["revision_count"] = int(state.get("revision_count", 0)) + 1
        return updates

    async def publish(state: TeamState) -> dict[str, object]:
        await mutate_run(state, phase=RunPhase.PUBLISH)
        if not services.settings.enable_github_publish:
            await emit(
                state,
                "reviewer",
                EventType.PULL_REQUEST,
                "Draft PR publishing is disabled by configuration",
                level=EventLevel.WARNING,
            )
            return {"phase": RunPhase.PUBLISH.value, "pull_request": None}
        snapshot = RepositorySnapshot.model_validate(state["repository_summary"])
        if snapshot.repository_url.startswith("demo://"):
            await emit(
                state,
                "reviewer",
                EventType.PULL_REQUEST,
                "Demo run validated; no remote PR is created",
            )
            return {"phase": RunPhase.PUBLISH.value, "pull_request": None}
        patch = PatchProposal.model_validate(state["patch"])
        validation = ValidationResult.model_validate(state["validation"])
        result = await services.publisher.publish(snapshot, patch, validation, state["run_id"])
        pull_request = PullRequestResult.model_validate(result)
        await mutate_run(state, pull_request=pull_request)
        await emit(
            state,
            "reviewer",
            EventType.PULL_REQUEST,
            "Draft pull request created",
            payload=pull_request.model_dump(mode="json"),
        )
        return {
            "phase": RunPhase.PUBLISH.value,
            "pull_request": pull_request.model_dump(mode="json"),
        }

    async def complete(state: TeamState) -> dict[str, object]:
        validation_data = state.get("validation")
        patch_data = state.get("patch")
        validation = ValidationResult.model_validate(validation_data) if validation_data else None
        status = RunStatus.COMPLETED
        message = "Run completed"
        if state.get("review_decision") == ReviewDecision.REJECT.value and patch_data is not None:
            message = "Run completed; the reviewer rejected the generated patch"
        elif patch_data is not None and validation is not None and not validation.passed:
            message = "Run completed without a pull request because validation failed"
        scan_complete = bool(state.get("scan_complete", True))
        if not scan_complete:
            failed = ", ".join(state.get("failed_scanners", [])) or "a scanner"
            message += f"; the scan was incomplete because {failed} failed"
        findings = [Finding.model_validate(value) for value in state.get("findings", [])]
        counts: dict[str, int] = {}
        for finding in findings:
            counts[finding.severity.value] = counts.get(finding.severity.value, 0) + 1
        started_at = datetime.fromisoformat(state["started_at"])
        duration_ms = int((datetime.now(UTC) - started_at).total_seconds() * 1000)
        metrics = RunMetrics(
            duration_ms=duration_ms,
            total_findings=len(findings),
            findings_by_severity=counts,
            patch_generated=patch_data is not None,
            validation_passed=bool(validation and validation.passed),
            repair_attempts=int(state.get("attempt", 0)),
            human_revisions=int(state.get("revision_count", 0)),
            review_decision=state.get("review_decision"),
            pull_request_created=state.get("pull_request") is not None,
            scan_complete=scan_complete,
        )
        await mutate_run(
            state,
            status=status,
            phase=RunPhase.COMPLETE,
            metrics=metrics,
        )
        await emit(
            state,
            "system",
            EventType.RUN,
            message,
            level=EventLevel.INFO if scan_complete else EventLevel.WARNING,
        )
        return {"phase": RunPhase.COMPLETE.value}

    graph = StateGraph(TeamState)
    graph.add_node("architect", architect)
    graph.add_node("security", security)
    graph.add_node("developer", developer)
    graph.add_node("validate", validate)
    graph.add_node("review", review)
    graph.add_node("publish", publish)
    graph.add_node("complete", complete)
    graph.add_edge(START, "architect")
    graph.add_edge("architect", "security")
    graph.add_conditional_edges("security", after_security)
    graph.add_edge("developer", "validate")
    graph.add_conditional_edges("validate", after_validation)
    graph.add_conditional_edges("review", after_review)
    graph.add_edge("publish", "complete")
    graph.add_edge("complete", END)
    return graph.compile(checkpointer=checkpointer)
