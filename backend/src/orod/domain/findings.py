from __future__ import annotations

from collections.abc import Iterable

from orod.domain.models import Finding, FindingSource


def deduplicate_findings(findings: Iterable[Finding]) -> list[Finding]:
    """Collapse findings that several scanners report at the same location.

    Bandit's classification wins a tie because it carries the canonical rule metadata
    and severity. Every scan whose severity counts are later compared - the initial
    security scan and each post-patch rescan - must go through this function, otherwise
    a rule reported by two scanners is counted once before a patch and twice after it,
    which reads as a regression that never happened.
    """
    collapsed: dict[tuple[str, str | None, int | None], Finding] = {}
    for finding in findings:
        key = (finding.rule_id, finding.file_path, finding.line)
        current = collapsed.get(key)
        if current is None or finding.source == FindingSource.BANDIT:
            collapsed[key] = finding
    return list(collapsed.values())
