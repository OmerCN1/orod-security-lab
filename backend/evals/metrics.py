from __future__ import annotations

from statistics import median

from pydantic import BaseModel, Field

from evals.manifest import EvalCase
from orod.domain.models import LLMUsage

# First-party Anthropic API list prices, USD per million tokens (input, output).
MODEL_PRICING_USD_PER_MTOK: dict[str, tuple[float, float]] = {
    "claude-fable-5": (10.00, 50.00),
    "claude-opus-5": (5.00, 25.00),
    "claude-opus-4-8": (5.00, 25.00),
    "claude-opus-4-7": (5.00, 25.00),
    "claude-opus-4-6": (5.00, 25.00),
    "claude-sonnet-5": (2.00, 10.00),
    "claude-sonnet-4-6": (3.00, 15.00),
    "claude-haiku-4-5": (1.00, 5.00),
}


def estimate_cost_usd(usage: LLMUsage) -> float | None:
    """Return the API spend for a window of calls.

    Locally hosted models have no per-token price, so they are reported as zero rather
    than as unknown. An unrecognised hosted model returns ``None`` so the report can say
    "unknown" instead of silently claiming it was free.
    """
    if usage.provider != "anthropic":
        return 0.0
    pricing = MODEL_PRICING_USD_PER_MTOK.get(usage.model)
    if pricing is None:
        return None
    input_price, output_price = pricing
    return (usage.input_tokens * input_price + usage.output_tokens * output_price) / 1_000_000


class DetectionScore(BaseModel):
    true_positives: list[str] = Field(default_factory=list)
    false_negatives: list[str] = Field(default_factory=list)
    false_positives: list[str] = Field(default_factory=list)

    @property
    def tp(self) -> int:
        return len(self.true_positives)

    @property
    def fn(self) -> int:
        return len(self.false_negatives)

    @property
    def fp(self) -> int:
        return len(self.false_positives)


def score_detection(case: EvalCase, detected: list[tuple[str, str | None]]) -> DetectionScore:
    """Compare reported findings with the corpus expectations for one case.

    Matching is on ``(rule_id, file_path)``; line numbers are deliberately ignored
    because a scanner upgrade may shift them without changing the verdict. Rules that
    are neither expected nor explicitly tolerated count as false positives, which is
    what makes the ``clean`` control meaningful.
    """
    detected_keys = set(detected)
    detected_rules = {rule_id for rule_id, _ in detected}

    true_positives: list[str] = []
    false_negatives: list[str] = []
    for expectation in case.expected_findings:
        matched = any(
            rule_id == expectation.rule_id
            and (expectation.file_path is None or file_path == expectation.file_path)
            for rule_id, file_path in detected_keys
        )
        (true_positives if matched else false_negatives).append(expectation.rule_id)

    false_positives = sorted(detected_rules - case.tolerated_rules)
    return DetectionScore(
        true_positives=sorted(true_positives),
        false_negatives=sorted(false_negatives),
        false_positives=false_positives,
    )


class CaseResult(BaseModel):
    case_id: str
    title: str
    cwe: str
    expected_outcome: str
    tags: list[str] = Field(default_factory=list)

    run_id: str | None = None
    run_status: str = "unknown"
    error: str | None = None

    detected_rules: list[str] = Field(default_factory=list)
    detection: DetectionScore = Field(default_factory=DetectionScore)

    patch_generated: bool = False
    patch_attempts: int = 0
    validation_passed: bool = False
    validation_summary: str = ""
    residual_target_findings: list[str] = Field(default_factory=list)
    new_high_findings: int = 0

    outcome_met: bool = False
    outcome_detail: str = ""

    duration_ms: int = 0
    llm_usage: LLMUsage = Field(default_factory=LLMUsage)
    cost_usd: float | None = None


def score_outcome(case: EvalCase, result: CaseResult) -> tuple[bool, str]:
    """Decide whether the pipeline did what this case demands of it."""
    if result.run_status != "completed":
        return False, f"run did not complete ({result.run_status})"

    if case.expected_outcome == "fix":
        if not result.patch_generated:
            # Distinguish "the model gave us nothing" from "the model's diff would not
            # apply" - they call for completely different fixes, and collapsing them into
            # one line hides the single most useful diagnostic in the report.
            return False, (
                f"no patch was applied: {result.validation_summary}"
                if result.validation_summary
                else "no patch was produced"
            )
        if not result.validation_passed:
            return False, f"validation failed: {result.validation_summary or 'unknown reason'}"
        if result.residual_target_findings:
            return False, (
                "post-patch rescan still reports "
                + ", ".join(sorted(result.residual_target_findings))
            )
        return True, "validated patch resolved the finding"

    if case.expected_outcome == "manual_review":
        if result.patch_generated:
            return False, "policy should have deferred to a human but a patch was applied"
        if result.detection.fn:
            return False, "finding was not detected"
        return True, "finding reported and correctly left for manual review"

    if case.expected_outcome == "clean":
        if result.detected_rules:
            return False, "false positives on a clean repository: " + ", ".join(
                result.detected_rules
            )
        if result.patch_generated:
            return False, "a patch was produced for a clean repository"
        return True, "no findings and no patch"

    # detect_only
    if result.detection.fn:
        return False, "finding was not detected"
    return True, "finding reported; remediation is out of scope for this case"


class SuiteAggregate(BaseModel):
    cases: int = 0
    completed_runs: int = 0

    expected_findings: int = 0
    true_positives: int = 0
    false_negatives: int = 0
    false_positives: int = 0
    precision: float = 0.0
    recall: float = 0.0
    f1: float = 0.0

    fix_cases: int = 0
    fix_successes: int = 0
    fix_rate: float = 0.0

    patch_attempted_cases: int = 0
    patch_applied_cases: int = 0
    patch_validity_rate: float = 0.0
    diff_rejected_cases: int = 0

    policy_cases: int = 0
    policy_successes: int = 0

    regressions: int = 0
    outcomes_met: int = 0
    outcome_rate: float = 0.0

    total_duration_ms: int = 0
    median_duration_ms: int = 0
    p95_duration_ms: int = 0

    llm_calls: int = 0
    failed_llm_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float | None = 0.0


def _ratio(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 4) if denominator else 0.0


def _percentile(values: list[int], fraction: float) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    index = min(len(ordered) - 1, int(round(fraction * (len(ordered) - 1))))
    return ordered[index]


def aggregate(cases: list[EvalCase], results: list[CaseResult]) -> SuiteAggregate:
    by_id = {case.id: case for case in cases}
    totals = SuiteAggregate(cases=len(results))
    durations: list[int] = []
    unknown_cost = False

    for result in results:
        case = by_id[result.case_id]
        totals.completed_runs += int(result.run_status == "completed")
        totals.expected_findings += len(case.expected_findings)
        totals.true_positives += result.detection.tp
        totals.false_negatives += result.detection.fn
        totals.false_positives += result.detection.fp

        if case.expected_outcome == "fix":
            totals.fix_cases += 1
            totals.fix_successes += int(result.outcome_met)
        if case.expected_outcome == "manual_review":
            totals.policy_cases += 1
            totals.policy_successes += int(result.outcome_met)

        if result.patch_attempts:
            totals.patch_attempted_cases += 1
        if result.patch_generated:
            totals.patch_applied_cases += 1
        elif "rejected" in result.validation_summary.lower():
            totals.diff_rejected_cases += 1

        totals.regressions += int(result.new_high_findings > 0)
        totals.outcomes_met += int(result.outcome_met)

        durations.append(result.duration_ms)
        totals.llm_calls += result.llm_usage.calls
        totals.failed_llm_calls += result.llm_usage.failed_calls
        totals.input_tokens += result.llm_usage.input_tokens
        totals.output_tokens += result.llm_usage.output_tokens
        if result.cost_usd is None:
            unknown_cost = True
        elif totals.cost_usd is not None:
            totals.cost_usd += result.cost_usd

    totals.precision = _ratio(totals.true_positives, totals.true_positives + totals.false_positives)
    totals.recall = _ratio(totals.true_positives, totals.true_positives + totals.false_negatives)
    if totals.precision + totals.recall:
        totals.f1 = round(
            2 * totals.precision * totals.recall / (totals.precision + totals.recall), 4
        )
    totals.fix_rate = _ratio(totals.fix_successes, totals.fix_cases)
    totals.patch_validity_rate = _ratio(totals.patch_applied_cases, totals.patch_attempted_cases)
    totals.outcome_rate = _ratio(totals.outcomes_met, totals.cases)

    totals.total_duration_ms = sum(durations)
    totals.median_duration_ms = int(median(durations)) if durations else 0
    totals.p95_duration_ms = _percentile(durations, 0.95)
    if unknown_cost:
        totals.cost_usd = None
    elif totals.cost_usd is not None:
        totals.cost_usd = round(totals.cost_usd, 6)
    return totals


class SuiteResult(BaseModel):
    label: str
    model: str
    provider: str
    use_llm: bool
    started_at: str
    finished_at: str = ""
    skipped_reason: str | None = None
    results: list[CaseResult] = Field(default_factory=list)
    totals: SuiteAggregate = Field(default_factory=SuiteAggregate)


class EvalReport(BaseModel):
    generated_at: str
    git_commit: str = ""
    corpus_size: int = 0
    scanners: list[str] = Field(default_factory=list)
    suites: list[SuiteResult] = Field(default_factory=list)
