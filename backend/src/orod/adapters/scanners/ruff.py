from __future__ import annotations

from orod.domain.models import Finding, RepositorySnapshot


class RuffScanner:
    """Reserved adapter for maintainability findings after the security MVP."""

    name = "ruff"

    async def scan(self, snapshot: RepositorySnapshot) -> list[Finding]:
        return []
