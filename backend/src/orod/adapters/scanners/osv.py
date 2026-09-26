from __future__ import annotations

from typing import Any
from uuid import NAMESPACE_URL, uuid5

import httpx

from orod.domain.models import (
    AdvisorySyncResult,
    Confidence,
    Finding,
    FindingSource,
    PackageDependency,
    Severity,
)
from orod.ports.storage import VectorStore


class OSVVulnerabilityAdapter:
    API_ROOT = "https://api.osv.dev/v1"

    def __init__(self, vector_store: VectorStore | None = None) -> None:
        self._vector_store = vector_store

    async def scan_dependencies(
        self, dependencies: list[PackageDependency]
    ) -> tuple[list[Finding], AdvisorySyncResult]:
        versioned = [dependency for dependency in dependencies if dependency.version]
        if not versioned:
            return [], AdvisorySyncResult(
                queried_packages=0,
                matched_advisories=0,
                cached_advisories=0,
            )

        errors: list[str] = []
        complete = True
        cached = 0
        findings: list[Finding] = []
        queries = [
            {
                "version": dependency.version,
                "package": {
                    "ecosystem": dependency.ecosystem,
                    "name": dependency.name,
                },
            }
            for dependency in versioned
        ]
        async with httpx.AsyncClient(timeout=20.0) as client:
            try:
                response = await client.post(
                    f"{self.API_ROOT}/querybatch", json={"queries": queries}
                )
                response.raise_for_status()
                results = response.json().get("results", [])
            except (httpx.HTTPError, ValueError) as exc:
                return [], AdvisorySyncResult(
                    queried_packages=len(versioned),
                    matched_advisories=0,
                    cached_advisories=0,
                    errors=[f"OSV query failed: {type(exc).__name__}"],
                    complete=False,
                )

            if len(results) != len(versioned):
                errors.append("OSV returned a result count that does not match the query")
                complete = False
            for dependency, result in zip(versioned, results, strict=False):
                for match in result.get("vulns", []):
                    advisory_id = str(match.get("id") or "")
                    if not advisory_id:
                        continue
                    try:
                        detail_response = await client.get(f"{self.API_ROOT}/vulns/{advisory_id}")
                        detail_response.raise_for_status()
                        advisory = detail_response.json()
                    except (httpx.HTTPError, ValueError) as exc:
                        errors.append(f"{advisory_id}: {type(exc).__name__}")
                        # Without its detail the advisory's severity is only a default.
                        complete = False
                        advisory = {"id": advisory_id, "summary": "Known vulnerable dependency"}

                    findings.append(self._to_finding(dependency, advisory))
                    if self._vector_store is not None:
                        try:
                            if await self._vector_store.upsert_advisory(advisory):
                                cached += 1
                        # Cache failure must not hide a deterministic package/version match.
                        except Exception as exc:
                            errors.append(f"cache {advisory_id}: {type(exc).__name__}")

        return findings, AdvisorySyncResult(
            queried_packages=len(versioned),
            matched_advisories=len(findings),
            cached_advisories=cached,
            errors=errors,
            complete=complete,
        )

    def _to_finding(self, dependency: PackageDependency, advisory: dict[str, Any]) -> Finding:
        advisory_id = str(advisory.get("id") or "OSV")
        aliases = [str(value) for value in advisory.get("aliases", [])]
        references = [
            str(item.get("url"))
            for item in advisory.get("references", [])
            if isinstance(item, dict) and item.get("url")
        ][:5]
        identity = f"{dependency.name}:{dependency.version}:{advisory_id}"
        return Finding(
            id=str(uuid5(NAMESPACE_URL, identity)),
            source=FindingSource.OSV,
            rule_id=advisory_id,
            severity=self._severity(advisory),
            confidence=Confidence.HIGH,
            title=str(advisory.get("summary") or advisory_id),
            message=(
                f"{dependency.name}=={dependency.version} is affected by {advisory_id}. "
                f"{str(advisory.get('details') or '')[:600]}"
            ).strip(),
            file_path=dependency.source_file,
            remediation="Upgrade the dependency to a version outside the affected ranges.",
            advisory_ids=[advisory_id, *aliases],
            references=references,
        )

    @staticmethod
    def _severity(advisory: dict[str, Any]) -> Severity:
        database_specific = advisory.get("database_specific") or {}
        raw = str(database_specific.get("severity") or "medium").lower()
        return {
            "critical": Severity.CRITICAL,
            "high": Severity.HIGH,
            "moderate": Severity.MEDIUM,
            "medium": Severity.MEDIUM,
            "low": Severity.LOW,
        }.get(raw, Severity.MEDIUM)
