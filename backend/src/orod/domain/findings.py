from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping

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
    as neutral, so findings are matched one-to-one by identity instead. Line numbers are
    not part of the identity - a patch shifts every line below it - so the text of the
    flagged line stands in for the location. When a file's text is unavailable the
    identity degrades to source, rule and file, which still counts per file.

    Both lists must come from the same set of scanners, or findings that were simply
    not rescanned read as fixed.
    """
    available = Counter(
        _identity(item, before_sources) for item in before if item.severity in HIGH_RISK_SEVERITIES
    )
    introduced: list[Finding] = []
    for item in after:
        if item.severity not in HIGH_RISK_SEVERITIES:
            continue
        identity = _identity(item, after_sources)
        if available[identity] > 0:
            available[identity] -= 1
        else:
            introduced.append(item)
    return introduced


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
