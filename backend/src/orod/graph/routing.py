from __future__ import annotations

from typing import Literal

from orod.domain.models import Finding, FindingSource, ReviewDecision, Severity
from orod.graph.state import TeamState

MANUAL_REVIEW_LOW_BANDIT_RULES = {"B101", "B311", "B404", "B603"}


def is_actionable_finding(finding: Finding) -> bool:
    if finding.severity == Severity.INFO:
        return False
    if (
        finding.severity == Severity.LOW
        and finding.source == FindingSource.BANDIT
        and finding.rule_id in MANUAL_REVIEW_LOW_BANDIT_RULES
    ):
        return False
    return True


def after_security(state: TeamState) -> Literal["developer", "complete"]:
    return "developer" if state.get("selected_finding_ids") else "complete"


def after_validation(state: TeamState) -> Literal["developer", "review"]:
    """Route to the automatic repair loop, or hand the outcome to the review node.

    The two-attempt repair budget is unchanged; what used to be a direct jump to
    ``publish``/``complete`` now always passes through ``review``, which is where the
    approve/reject decision is made - by a human when one is required, and automatically
    when the run is headless.
    """
    patch = state.get("patch")
    validation = state.get("validation") or {}
    if patch is None:
        if state.get("errors") and int(state.get("attempt", 0)) < 2:
            return "developer"
        return "review"
    if validation.get("passed"):
        return "review"
    if int(state.get("attempt", 0)) < 2:
        return "developer"
    return "review"


def after_review(state: TeamState) -> Literal["developer", "publish", "complete"]:
    """Apply the review decision.

    Approval can only reach ``publish`` when validation actually passed. The API rejects
    such a submission too; this is the second gate, so no code path can open a pull
    request for an unvalidated patch.
    """
    decision = state.get("review_decision")
    if decision == ReviewDecision.REGENERATE.value:
        return "developer"
    validation = state.get("validation") or {}
    if decision == ReviewDecision.APPROVE.value and validation.get("passed"):
        return "publish"
    return "complete"
