from __future__ import annotations

from orod.domain.models import AdvisorySyncRequest, AdvisorySyncResult
from orod.ports.scanners import VulnerabilityProvider


async def sync_vulnerabilities(
    provider: VulnerabilityProvider, request: AdvisorySyncRequest
) -> AdvisorySyncResult:
    _, result = await provider.scan_dependencies(request.packages)
    return result
