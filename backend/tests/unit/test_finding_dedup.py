from orod.domain.findings import deduplicate_findings
from orod.domain.models import Confidence, Finding, FindingSource, Severity


def make_finding(source: FindingSource, severity: Severity, line: int = 4) -> Finding:
    return Finding(
        id=f"{source.value}-{line}",
        source=source,
        rule_id="B307",
        severity=severity,
        confidence=Confidence.HIGH,
        title="Use of eval detected",
        message="eval can execute attacker-controlled Python code.",
        file_path="app.py",
        line=line,
    )


def test_two_scanners_at_one_location_collapse_to_the_bandit_finding() -> None:
    collapsed = deduplicate_findings(
        [
            make_finding(FindingSource.BUILTIN, Severity.HIGH),
            make_finding(FindingSource.BANDIT, Severity.MEDIUM),
        ]
    )
    assert len(collapsed) == 1
    assert collapsed[0].source == FindingSource.BANDIT
    assert collapsed[0].severity == Severity.MEDIUM


def test_bandit_wins_regardless_of_scan_order() -> None:
    ordered = deduplicate_findings(
        [
            make_finding(FindingSource.BANDIT, Severity.MEDIUM),
            make_finding(FindingSource.BUILTIN, Severity.HIGH),
        ]
    )
    assert ordered[0].source == FindingSource.BANDIT


def test_distinct_locations_are_preserved() -> None:
    assert len(
        deduplicate_findings(
            [
                make_finding(FindingSource.BANDIT, Severity.MEDIUM, line=4),
                make_finding(FindingSource.BANDIT, Severity.MEDIUM, line=9),
            ]
        )
    ) == 2


def test_severity_counts_match_before_and_after_a_rescan() -> None:
    """A rule seen by two scanners must not read as a new high finding after a patch."""
    initial = deduplicate_findings(
        [
            make_finding(FindingSource.BUILTIN, Severity.HIGH),
            make_finding(FindingSource.BANDIT, Severity.MEDIUM),
        ]
    )
    rescan = deduplicate_findings(
        [
            make_finding(FindingSource.BANDIT, Severity.MEDIUM),
            make_finding(FindingSource.BUILTIN, Severity.HIGH),
        ]
    )
    high = lambda items: sum(item.severity == Severity.HIGH for item in items)  # noqa: E731
    assert high(rescan) - high(initial) == 0
