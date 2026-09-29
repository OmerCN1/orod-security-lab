import re

import pytest

from evals.manifest import CASES_ROOT, load_cases
from evals.osv_replay import OSVRecording, load_recordings, pin_key, replay_transport
from orod.adapters.scanners.osv import OSVVulnerabilityAdapter
from orod.domain.models import PackageDependency

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


def test_every_pinned_dependency_has_a_recorded_osv_response() -> None:
    """The corpus must stay hermetic: an unrecorded pin would need a live OSV query."""
    for case in load_cases():
        repo = CASES_ROOT / case.id / "repo"
        pins = [
            match
            for manifest in [*repo.glob("*requirements*.txt"), *repo.glob("pyproject.toml")]
            for match in re.findall(r"([A-Za-z0-9_.-]+)\s*==\s*([^\s;\"']+)", manifest.read_text())
        ]
        if not pins:
            continue
        recording = load_recordings([case])
        for name, version in pins:
            assert pin_key(name, version) in recording.queries, f"{case.id}: {name}=={version}"


async def test_recorded_osv_responses_replay_through_the_real_adapter() -> None:
    cases = load_cases(only=["vulnerable-dependency"])
    adapter = OSVVulnerabilityAdapter(transport=replay_transport(load_recordings(cases)))

    findings, sync = await adapter.scan_dependencies(
        [PackageDependency(name="PyYAML", version="5.3.1", source_file="requirements.txt")]
    )
    fixed, fixed_sync = await adapter.scan_dependencies(
        [PackageDependency(name="PyYAML", version="5.4", source_file="requirements.txt")]
    )

    assert sync.complete and fixed_sync.complete
    assert {item.rule_id for item in findings} == {"GHSA-8q59-q68h-6hv4", "PYSEC-2021-142"}
    assert all("5.4" in item.fixed_versions for item in findings)
    assert fixed == []


async def test_an_unrecorded_osv_query_is_an_incomplete_lookup() -> None:
    adapter = OSVVulnerabilityAdapter(transport=replay_transport(OSVRecording()))

    findings, sync = await adapter.scan_dependencies(
        [PackageDependency(name="PyYAML", version="6.0", source_file="requirements.txt")]
    )

    assert findings == []
    assert sync.complete is False


def test_unknown_case_ids_are_rejected() -> None:
    with pytest.raises(ValueError, match="unknown case id"):
        load_cases(only=["does-not-exist"])
