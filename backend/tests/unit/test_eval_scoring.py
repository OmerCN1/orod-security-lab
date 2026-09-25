from evals.manifest import EvalCase
from evals.metrics import (
    CaseResult,
    aggregate,
    estimate_cost_usd,
    score_detection,
    score_outcome,
)
from orod.domain.models import LLMUsage


def make_case(**overrides: object) -> EvalCase:
    payload: dict[str, object] = {
        "id": "case",
        "title": "title",
        "cwe": "CWE-78",
        "expected_outcome": "fix",
        "expected_findings": [{"rule_id": "B602", "file_path": "app.py"}],
        "allowed_extra_rules": ["B404"],
    }
    payload.update(overrides)
    return EvalCase.model_validate(payload)


def make_result(**overrides: object) -> CaseResult:
    payload: dict[str, object] = {
        "case_id": "case",
        "title": "title",
        "cwe": "CWE-78",
        "expected_outcome": "fix",
        "run_status": "completed",
    }
    payload.update(overrides)
    return CaseResult.model_validate(payload)


def test_detection_counts_expected_tolerated_and_unexpected_rules() -> None:
    case = make_case()
    score = score_detection(case, [("B602", "app.py"), ("B404", "app.py"), ("B105", "app.py")])
    assert score.true_positives == ["B602"]
    assert score.false_negatives == []
    assert score.false_positives == ["B105"]


def test_detection_ignores_line_numbers_but_honours_file_paths() -> None:
    case = make_case()
    assert score_detection(case, [("B602", "other.py")]).false_negatives == ["B602"]


def test_clean_control_treats_any_finding_as_a_false_positive() -> None:
    case = make_case(expected_outcome="clean", expected_findings=[], allowed_extra_rules=[])
    score = score_detection(case, [("B105", "app.py")])
    assert score.false_positives == ["B105"]
    assert score.tp == 0


def test_a_rejected_diff_is_reported_as_such_rather_than_as_silence() -> None:
    """A malformed diff and an empty response need different fixes, so the report must
    not collapse them into one line."""
    case = make_case()
    met, detail = score_outcome(
        case,
        make_result(
            patch_generated=False,
            validation_summary="Patch rejected: error: corrupt patch at line 6",
        ),
    )
    assert not met
    assert "corrupt patch" in detail

    _, silent = score_outcome(case, make_result(patch_generated=False))
    assert silent == "no patch was produced"


def test_aggregate_counts_cases_lost_to_unusable_diffs() -> None:
    cases = [make_case(id="a"), make_case(id="b")]
    results = [
        make_result(case_id="a", validation_summary="Patch rejected: error: corrupt patch"),
        make_result(case_id="b", patch_generated=True, validation_passed=True, outcome_met=True),
    ]
    assert aggregate(cases, results).diff_rejected_cases == 1


def test_fix_outcome_requires_a_validated_patch_with_no_residual_finding() -> None:
    case = make_case()
    assert not score_outcome(case, make_result(patch_generated=False))[0]
    assert not score_outcome(case, make_result(patch_generated=True))[0]
    assert score_outcome(
        case, make_result(patch_generated=True, validation_passed=True)
    )[0]
    met, detail = score_outcome(
        case,
        make_result(
            patch_generated=True,
            validation_passed=True,
            residual_target_findings=["B602"],
        ),
    )
    assert not met
    assert "B602" in detail


def test_manual_review_outcome_fails_when_the_pipeline_patches_anyway() -> None:
    case = make_case(expected_outcome="manual_review")
    result = make_result(expected_outcome="manual_review", patch_generated=True)
    met, detail = score_outcome(case, result)
    assert not met
    assert "human" in detail


def test_incomplete_run_never_counts_as_a_met_outcome() -> None:
    case = make_case()
    met, detail = score_outcome(
        case, make_result(run_status="failed", patch_generated=True, validation_passed=True)
    )
    assert not met
    assert "failed" in detail


def test_local_models_cost_nothing_and_unknown_hosted_models_are_not_guessed() -> None:
    assert estimate_cost_usd(LLMUsage(provider="ollama", model="qwen2.5-coder:14b")) == 0.0
    assert (
        estimate_cost_usd(LLMUsage(provider="anthropic", model="claude-made-up-9")) is None
    )
    priced = estimate_cost_usd(
        LLMUsage(
            provider="anthropic",
            model="claude-opus-5",
            input_tokens=1_000_000,
            output_tokens=1_000_000,
        )
    )
    assert priced == 30.0


def test_aggregate_reports_unknown_cost_when_any_case_is_unpriced() -> None:
    cases = [make_case(id="a"), make_case(id="b")]
    results = [
        make_result(case_id="a", outcome_met=True, cost_usd=1.5, duration_ms=100),
        make_result(case_id="b", outcome_met=False, cost_usd=None, duration_ms=300),
    ]
    totals = aggregate(cases, results)
    assert totals.cost_usd is None
    assert totals.fix_cases == 2
    assert totals.fix_successes == 1
    assert totals.fix_rate == 0.5
    assert totals.median_duration_ms == 200
