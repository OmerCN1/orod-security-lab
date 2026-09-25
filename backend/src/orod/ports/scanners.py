from __future__ import annotations

from typing import Protocol

from orod.domain.models import AdvisorySyncResult, Finding, PackageDependency, RepositorySnapshot


class SecurityScanner(Protocol):
    name: str

    async def scan(self, snapshot: RepositorySnapshot) -> list[Finding]: ...


class VulnerabilityProvider(Protocol):
    async def scan_dependencies(
        self, dependencies: list[PackageDependency]
    ) -> tuple[list[Finding], AdvisorySyncResult]: ...
