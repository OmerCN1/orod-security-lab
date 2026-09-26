from orod.domain.findings import introduced_high_risk_findings
from orod.domain.models import Finding, FindingSource, Severity

BEFORE_SOURCE = "import subprocess\nsubprocess.run(cmd, shell=True)\nvalue = eval(text)\n"


def finding(
    rule_id: str,
    line: int | None,
    severity: Severity = Severity.HIGH,
    *,
    source: FindingSource = FindingSource.BANDIT,
    path: str = "app.py",
) -> Finding:
    return Finding(
        id=f"{rule_id}-{line}",
        source=source,
        rule_id=rule_id,
        severity=severity,
        title=rule_id,
        message=rule_id,
        file_path=path,
        line=line,
    )


def test_swapping_one_high_finding_for_another_is_a_regression() -> None:
    # Totals are equal before and after; comparing counts reported this as clean.
    after_source = "import subprocess\nsubprocess.run(cmd, shell=False)\nvalue = eval(text)\n"
    before = [finding("B602", 2)]
    after = [finding("B307", 3)]

    introduced = introduced_high_risk_findings(
        before, after, {"app.py": BEFORE_SOURCE}, {"app.py": after_source}
    )

    assert [item.rule_id for item in introduced] == ["B307"]


def test_a_finding_moved_by_inserted_lines_is_not_new() -> None:
    after_source = "import shutil\n" + BEFORE_SOURCE
    before = [finding("B307", 3)]
    after = [finding("B307", 4)]

    assert (
        introduced_high_risk_findings(
            before, after, {"app.py": BEFORE_SOURCE}, {"app.py": after_source}
        )
        == []
    )


def test_a_second_instance_of_an_existing_rule_in_the_same_file_is_new() -> None:
    after_source = BEFORE_SOURCE + "other = eval(payload)\n"
    before = [finding("B307", 3)]
    after = [finding("B307", 3), finding("B307", 4)]

    introduced = introduced_high_risk_findings(
        before, after, {"app.py": BEFORE_SOURCE}, {"app.py": after_source}
    )

    assert [item.line for item in introduced] == [4]


def test_only_high_and_critical_findings_count() -> None:
    after = [finding("B311", 1, Severity.MEDIUM), finding("B324", 2, Severity.CRITICAL)]

    introduced = introduced_high_risk_findings([], after, {}, {})

    assert [item.rule_id for item in introduced] == ["B324"]


def test_a_finding_that_became_high_is_new() -> None:
    before = [finding("B602", 2, Severity.LOW)]
    after = [finding("B602", 2, Severity.HIGH)]

    assert len(introduced_high_risk_findings(before, after, {}, {})) == 1


def test_without_file_text_matching_falls_back_to_rule_and_file() -> None:
    before = [finding("B602", 2)]

    assert introduced_high_risk_findings(before, [finding("B602", 9)], {}, {}) == []
    elsewhere = [finding("B602", 9, path="b.py")]
    assert len(introduced_high_risk_findings(before, elsewhere, {}, {})) == 1


def test_dependency_advisories_are_matched_by_advisory_and_manifest() -> None:
    known = finding("GHSA-old", None, source=FindingSource.OSV, path="requirements.txt")
    added = finding("GHSA-new", None, source=FindingSource.OSV, path="requirements.txt")

    introduced = introduced_high_risk_findings([known], [known, added], {}, {})

    assert [item.rule_id for item in introduced] == ["GHSA-new"]
