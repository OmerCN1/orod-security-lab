from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from orod.api.dependencies import get_vulnerability_provider
from orod.application.sync_vulnerabilities import sync_vulnerabilities
from orod.domain.models import AdvisorySyncRequest, AdvisorySyncResult
from orod.ports.scanners import VulnerabilityProvider

router = APIRouter(prefix="/vulnerability-index", tags=["vulnerabilities"])


@router.post("/sync", response_model=AdvisorySyncResult)
async def sync_index(
    payload: AdvisorySyncRequest,
    provider: Annotated[VulnerabilityProvider, Depends(get_vulnerability_provider)],
) -> AdvisorySyncResult:
    return await sync_vulnerabilities(provider, payload)
