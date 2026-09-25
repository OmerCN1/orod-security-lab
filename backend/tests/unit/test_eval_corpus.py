import pytest

from evals.manifest import CASES_ROOT, load_cases

EXPECTED_OUTCOMES = {"fix", "manual_review", "detect_only", "clean"}


def test_every_case_manifest_loads_and_matches_its_directory() -> None:
    cases = load_cases()
    assert len(cases) >= 15, "the corpus is the headline artefact; keep it substantial"
    assert len({case.id for case in cases}) == len(cases)
    for case in cases:
        assert case.expected_outcome in EXPECTED_OUTCOMES
        assert (CASES_ROOT / case.id / "repo" / "app.py").is_file()
        assert case.rationale, f"{case.id} must explain why its outcome is expected"


def test_the_corpus_covers_every_outcome_kind() -> None:
    outcomes = {case.expected_outcome for case in load_cases()}
    assert outcomes == EXPECTED_OUTCOMES


def test_non_clean_cases_declare_at_least_one_expected_finding() -> None:
    for case in load_cases():
        if case.expected_outcome == "clean":
            assert case.expected_findings == []
        else:
            assert case.expected_findings, f"{case.id} declares no expected finding"


def test_case_repositories_declare_no_pinned_dependencies() -> None:
    """The corpus must stay hermetic: pinned versions would trigger live OSV queries."""
    for case in load_cases():
        assert not list((CASES_ROOT / case.id / "repo").glob("*requirements*.txt"))


def test_unknown_case_ids_are_rejected() -> None:
    with pytest.raises(ValueError, match="unknown case id"):
        load_cases(only=["does-not-exist"])
