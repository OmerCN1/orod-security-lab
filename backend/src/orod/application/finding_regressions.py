from __future__ import annotations

from collections.abc import Awaitable, Callable

from orod.domain.errors import UnsafePathError
from orod.domain.findings import HIGH_RISK_SEVERITIES, introduced_high_risk_findings
from orod.domain.models import Finding, RepositorySnapshot
from orod.ports.repository import RepositoryProvider

SourceReader = Callable[..., Awaitable[dict[str, str]]]


async def introduced_high_risk(
    repository: RepositoryProvider,
    snapshot: RepositorySnapshot,
    before: list[Finding],
    after: list[Finding],
    max_chars: int,
) -> list[Finding]:
    """High/critical findings a patch introduced, matched against the base revision.

    ``before`` was scanned on the base revision and ``after`` on the working tree, so the
    flagged line of each is read from the matching revision. The graph's validation and
    the evaluation harness both call this, so they cannot disagree about a regression.
    """
    paths = sorted(
        {
            item.file_path
            for item in (*before, *after)
            if item.file_path and item.line and item.severity in HIGH_RISK_SEVERITIES
        }
    )
    before_sources = await _read_each(repository.read_base_files, snapshot, paths, max_chars)
    after_sources = await _read_each(repository.read_files, snapshot, paths, max_chars)
    return introduced_high_risk_findings(before, after, before_sources, after_sources)


async def _read_each(
    reader: SourceReader, snapshot: RepositorySnapshot, paths: list[str], max_chars: int
) -> dict[str, str]:
    # One unreadable file must not drop the others: its findings simply fall back to
    # matching by source, rule and file.
    sources: dict[str, str] = {}
    for path in paths:
        try:
            sources.update(await reader(snapshot, [path], max_chars=max_chars))
        except UnsafePathError:
            continue
    return sources
