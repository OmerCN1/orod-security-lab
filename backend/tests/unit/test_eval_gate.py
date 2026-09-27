from pathlib import Path

from evals.gate import suite_drift
from evals.metrics import CaseResult, EvalReport, SuiteAggregate, SuiteResult

LABEL = "deterministic-baseline"


def case(case_id: str, met: bool, new_high: int = 0) -> CaseResult:
    return CaseResult(
        case_id=case_id,
        title=case_id,
        cwe="CWE-78",
        expected_outcome="fix",
        outcome_met=met,
        outcome_detail="ok" if met else "validation failed",
        new_high_findings=new_high,
    )


def report(*cases: CaseResult, f1: float = 1.0) -> EvalReport:
    return EvalReport(
        generated_at="2026-01-01T00:00:00+00:00",
        git_commit="abc",
        corpus_size=len(cases),
        scanners=[],
        suites=[
            SuiteResult(
                label=LABEL,
                model="deterministic",
                provider="deterministic",
                use_llm=False,
                started_at="2026-01-01T00:00:00+00:00",
                results=list(cases),
                totals=SuiteAggregate(f1=f1),
            )
        ],
    )


def recorded(tmp_path: Path, *cases: CaseResult, f1: float = 1.0) -> Path:
    path = tmp_path / "latest.json"
    path.write_text(report(*cases, f1=f1).model_dump_json())
    return path


def test_an_unchanged_or_better_suite_passes(tmp_path: Path) -> None:
    reference = recorded(tmp_path, case("a", True), case("b", False))

    assert suite_drift(report(case("a", True), case("b", False)), reference, LABEL) == []
    assert suite_drift(report(case("a", True), case("b", True)), reference, LABEL) == []


def test_a_case_that_stopped_meeting_its_outcome_is_drift(tmp_path: Path) -> None:
    reference = recorded(tmp_path, case("a", True))

    problems = suite_drift(report(case("a", False)), reference, LABEL)

    assert problems == ["a: outcome no longer met (validation failed)"]


def test_new_regressions_and_lower_detection_are_drift(tmp_path: Path) -> None:
    reference = recorded(tmp_path, case("a", False), f1=1.0)

    problems = suite_drift(report(case("a", False, new_high=1), f1=0.9), reference, LABEL)

    assert problems == [
        "a: new high/critical findings introduced",
        "detection F1 fell from 1.00 to 0.90",
    ]


def test_a_missing_suite_is_drift(tmp_path: Path) -> None:
    reference = recorded(tmp_path, case("a", True))

    assert suite_drift(report(case("a", True)), reference, "other") != []
