from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping

from orod.domain.models import Finding, FindingSource, Severity

HIGH_RISK_SEVERITIES = frozenset({Severity.HIGH, Severity.CRITICAL})

FindingIdentity = tuple[str, str, str | None, str | None]


def deduplicate_findings(findings: Iterable[Finding]) -> list[Finding]:
    """Collapse findings that several scanners report at the same location.

    Bandit's classification wins a tie because it carries the canonical rule metadata
    and severity. Every scan whose findings are later compared - the initial security
    scan and each post-patch rescan - must go through this function, otherwise a rule
    reported by two scanners is seen once before a patch and twice after it, which
    reads as a regression that never happened.
    """
    collapsed: dict[tuple[str, str | None, int | None], Finding] = {}
    for finding in findings:
        key = (finding.rule_id, finding.file_path, finding.line)
        current = collapsed.get(key)
        if current is None or finding.source == FindingSource.BANDIT:
            collapsed[key] = finding
    return list(collapsed.values())


def introduced_high_risk_findings(
    before: Iterable[Finding],
    after: Iterable[Finding],
    before_sources: Mapping[str, str],
    after_sources: Mapping[str, str],
) -> list[Finding]:
    """High/critical findings in ``after`` that no finding in ``before`` accounts for.

    Comparing totals lets a patch that removes one high finding and adds another pass
    as neutral, so findings are matched one-to-one instead, in two passes:

    1. By identity: source, rule, file and the text of the flagged line. Line numbers
       are not part of it - a patch shifts every line below it.
    2. What is left, by source, rule and file alone. This is a finding whose line the
       patch edited without resolving it, e.g. one insecure host-key policy swapped for
       another. It is unresolved, which the residual check reports, not introduced.

    A second finding of a rule in a file that had one is still introduced, as is any
    rule new to a file. When a file's text is unavailable, pass 1 degrades to pass 2.

    Both lists must come from the same set of scanners, or findings that were simply
    not rescanned read as fixed.
    """
    remaining_before = [item for item in before if item.severity in HIGH_RISK_SEVERITIES]
    remaining_after = [item for item in after if item.severity in HIGH_RISK_SEVERITIES]

    def same_line(new: Finding, old: Finding) -> bool:
        return _identity(new, after_sources) == _identity(old, before_sources)

    def same_location(new: Finding, old: Finding) -> bool:
        return _location(new) == _location(old)

    for matches in (same_line, same_location):
        remaining_after = _claim(remaining_after, remaining_before, matches)
    return remaining_after


def _claim(
    after: list[Finding], before: list[Finding], matches: Callable[[Finding, Finding], bool]
) -> list[Finding]:
    """Pair each finding in ``after`` with one in ``before``; return those left unpaired.

    Paired originals are removed from ``before``, so each accounts for one finding only.
    """
    unpaired: list[Finding] = []
    for item in after:
        index = next((index for index, old in enumerate(before) if matches(item, old)), None)
        if index is None:
            unpaired.append(item)
        else:
            del before[index]
    return unpaired


def _location(finding: Finding) -> tuple[str, str, str | None]:
    return (finding.source.value, finding.rule_id, finding.file_path)


def _identity(finding: Finding, sources: Mapping[str, str]) -> FindingIdentity:
    return (finding.source.value, finding.rule_id, finding.file_path, _line_text(finding, sources))


def _line_text(finding: Finding, sources: Mapping[str, str]) -> str | None:
    if not finding.file_path or not finding.line:
        return None
    text = sources.get(finding.file_path)
    if text is None:
        return None
    lines = text.splitlines()
    if not 1 <= finding.line <= len(lines):
        return None
    return " ".join(lines[finding.line - 1].split())
