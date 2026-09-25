from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from orod.agents.base import AgentServices
from orod.domain.errors import PatchRejectedError
from orod.domain.events import EventLevel, EventType, RunEvent
from orod.domain.findings import deduplicate_findings
from orod.domain.models import (
    Finding,
    PatchProposal,
    PullRequestResult,
    RepositorySnapshot,
    ReviewDecision,
    ReviewRequest,
    RunMetrics,
    RunPhase,
    RunStatus,
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
        for scanner in services.scanners:
            try:
                scanner_findings = await scanner.scan(snapshot)
                findings.extend(scanner_findings)
                await emit(
                    state,
                    "security",
                    EventType.RUN,
                    f"{scanner.name} completed with {len(scanner_findings)} finding(s)",
                    payload={"scanner": scanner.name, "count": len(scanner_findings)},
                )
            except Exception as exc:
                await emit(
                    state,
                    "security",
                    EventType.RUN,
                    f"{scanner.name} was unavailable: {type(exc).__name__}",
                    level=EventLevel.WARNING,
                )

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
                "queried": sync.queried_packages,
                "errors": sync.errors[:5],
            },
        )

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
        await mutate_run(state, findings=final_findings)
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
            f"Security analysis completed with {len(final_findings)} finding(s)",
            payload={
                "count": len(final_findings),
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
            return {"phase": RunPhase.DEVELOPER.value, "patch": None, "attempt": attempt}

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
            result = await services.repository.validate(snapshot)
            if result.passed:
                selected_ids = set(state.get("selected_finding_ids", []))
                original_findings = [
                    Finding.model_validate(value) for value in state.get("findings", [])
                ]
                selected_targets = {
                    (item.source, item.rule_id, item.file_path)
                    for item in original_findings
                    if item.id in selected_ids
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
                post_patch_findings = deduplicate_findings(raw_post_patch)
                residual_targets = {
                    (item.source, item.rule_id, item.file_path) for item in post_patch_findings
                } & selected_targets
                original_high = sum(
                    item.severity.value in {"high", "critical"} for item in original_findings
                )
                post_patch_high = sum(
                    item.severity.value in {"high", "critical"} for item in post_patch_findings
                )
                result.new_high_findings = max(0, post_patch_high - original_high)
                if scanner_errors:
                    result.passed = False
                    result.summary = "Post-patch security scan failed: " + ", ".join(scanner_errors)
                elif residual_targets:
                    result.passed = False
                    residual_rules = ", ".join(
                        sorted(f"{rule_id} in {path}" for _, rule_id, path in residual_targets)
                    )
                    result.summary = f"Patch did not resolve selected findings: {residual_rules}"
                elif result.new_high_findings:
                    result.passed = False
                    result.summary = "Patch introduced new high/critical security findings."
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
        )
        await mutate_run(
            state,
            status=status,
            phase=RunPhase.COMPLETE,
            metrics=metrics,
        )
        await emit(state, "system", EventType.RUN, message)
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
