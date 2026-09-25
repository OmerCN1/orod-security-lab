import httpx
import respx

from orod.adapters.scanners.osv import OSVVulnerabilityAdapter
from orod.domain.models import PackageDependency


@respx.mock
async def test_osv_matches_versioned_dependency() -> None:
    respx.post("https://api.osv.dev/v1/querybatch").mock(
        return_value=httpx.Response(200, json={"results": [{"vulns": [{"id": "GHSA-demo"}]}]})
    )
    respx.get("https://api.osv.dev/v1/vulns/GHSA-demo").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "GHSA-demo",
                "aliases": ["CVE-2099-0001"],
                "summary": "Demo advisory",
                "details": "Affected demo package",
                "database_specific": {"severity": "HIGH"},
                "references": [{"url": "https://example.invalid/advisory"}],
            },
        )
    )
    provider = OSVVulnerabilityAdapter()
    findings, result = await provider.scan_dependencies(
        [PackageDependency(name="demo", version="1.0.0", source_file="requirements.txt")]
    )

    assert result.queried_packages == 1
    assert result.matched_advisories == 1
    assert findings[0].rule_id == "GHSA-demo"
    assert findings[0].advisory_ids == ["GHSA-demo", "CVE-2099-0001"]
