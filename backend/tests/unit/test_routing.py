from orod.domain.models import Confidence, Finding, FindingSource, Severity
from orod.graph.routing import (
    after_review,
    after_security,
    after_validation,
    is_actionable_finding,
)


def finding(rule_id: str, severity: Severity, source: FindingSource) -> Finding:
    return Finding(
        id=rule_id,
        source=source,
        rule_id=rule_id,
        severity=severity,
        confidence=Confidence.HIGH,
        title=rule_id,
        message=rule_id,
    )


def test_actionable_finding_policy_keeps_fixable_low_findings() -> None:
    assert is_actionable_finding(finding("B607", Severity.LOW, FindingSource.BANDIT))
    assert not is_actionable_finding(finding("B311", Severity.LOW, FindingSource.BANDIT))
    assert not is_actionable_finding(finding("B603", Severity.LOW, FindingSource.BANDIT))
    assert is_actionable_finding(finding("B404", Severity.MEDIUM, FindingSource.BANDIT))
    assert not is_actionable_finding(finding("note", Severity.INFO, FindingSource.LLM))


def test_security_skips_patch_flow_without_actionable_findings() -> None:
    assert after_security({"selected_finding_ids": []}) == "complete"
    assert after_security({"selected_finding_ids": ["finding-id"]}) == "developer"


def test_validation_keeps_the_repair_budget_then_hands_off_to_review() -> None:
    assert after_validation({"patch": None}) == "review"
    assert after_validation({"patch": None, "errors": ["bad diff"], "attempt": 1}) == "developer"
    assert (
        after_validation({"patch": {"unified_diff": "x"}, "validation": {"passed": True}})
        == "review"
    )
    assert (
        after_validation(
            {"patch": {"unified_diff": "x"}, "validation": {"passed": False}, "attempt": 1}
        )
        == "developer"
    )
    assert (
        after_validation(
            {"patch": {"unified_diff": "x"}, "validation": {"passed": False}, "attempt": 2}
        )
        == "review"
    )


def test_an_untrusted_run_does_not_spend_a_repair_attempt() -> None:
    # Validation refuses every patch without consent; regenerating cannot change that.
    state = {
        "trusted": False,
        "patch": {"unified_diff": "x"},
        "validation": {"passed": False},
        "attempt": 1,
    }
    assert after_validation(state) == "review"  # type: ignore[arg-type]
    assert after_validation({**state, "trusted": True}) == "developer"  # type: ignore[arg-type]


def test_review_applies_the_decision() -> None:
    passed = {"validation": {"passed": True}}
    assert after_review({**passed, "review_decision": "approve"}) == "publish"
    assert after_review({**passed, "review_decision": "reject"}) == "complete"
    assert after_review({**passed, "review_decision": "regenerate"}) == "developer"


def test_approval_cannot_publish_an_unvalidated_patch() -> None:
    """Second gate on the invariant that a failed validation never opens a pull request."""
    failed = {"validation": {"passed": False}, "review_decision": "approve"}
    assert after_review(failed) == "complete"
    assert after_review({"review_decision": "approve"}) == "complete"


def test_missing_decision_completes_rather_than_publishing() -> None:
    assert after_review({"validation": {"passed": True}}) == "complete"
