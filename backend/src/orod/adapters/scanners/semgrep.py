from __future__ import annotations

import json
import sys
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from orod.adapters.scanners.isolated_input import filtered_copy
from orod.domain.errors import ScannerOutputError
from orod.domain.models import Confidence, Finding, FindingSource, RepositorySnapshot, Severity
from orod.ports.execution import CommandRunner


class SemgrepScanner:
    name = "semgrep"

    def __init__(
        self,
        runner: CommandRunner,
        max_file_bytes: int = 1_000_000,
        workspace_root: Path | None = None,
    ) -> None:
        self._runner = runner
        self._max_file_bytes = max_file_bytes
        self._workspace_root = workspace_root

    async def scan(self, snapshot: RepositorySnapshot) -> list[Finding]:
        if snapshot.repository_url.startswith("demo://"):
            return []
        semgrep_executable = str(Path(sys.executable).parent / "semgrep")
        with filtered_copy(snapshot, self._max_file_bytes, self._workspace_root) as root:
            result = await self._runner.run(
                [
                    semgrep_executable,
                    "scan",
                    "--config",
                    "p/python",
                    "--json",
                    "--metrics",
                    "off",
                    ".",
                ],
                root,
                max_output_chars=5_000_000,
            )
        if result.return_code != 0:
            raise ScannerOutputError(
                f"Semgrep failed with exit code {result.return_code}: {result.stderr[-500:]}"
            )
        try:
            payload = json.loads(result.stdout or "{}")
        except json.JSONDecodeError as exc:
            raise ScannerOutputError("Semgrep returned invalid or truncated JSON") from exc
        if payload.get("errors"):
            raise ScannerOutputError(f"Semgrep reported scan errors: {payload['errors'][:3]}")
        findings: list[Finding] = []
        for item in payload.get("results", []):
            extra = item.get("extra", {})
            metadata = extra.get("metadata", {})
            relative = str(item.get("path") or "")
            line = int(item.get("start", {}).get("line", 0) or 0)
            rule_id = str(item.get("check_id") or "semgrep")
            identity = f"{snapshot.repository_url}:{relative}:{line}:{rule_id}"
            severity = str(extra.get("severity") or "WARNING").upper()
            findings.append(
                Finding(
                    id=str(uuid5(NAMESPACE_URL, identity)),
                    source=FindingSource.SEMGREP,
                    rule_id=rule_id,
                    severity={"ERROR": Severity.HIGH, "WARNING": Severity.MEDIUM}.get(
                        severity, Severity.LOW
                    ),
                    confidence=Confidence.MEDIUM,
                    title=str(metadata.get("shortlink") or rule_id),
                    message=str(extra.get("message") or "Semgrep finding"),
                    file_path=relative,
                    line=line or None,
                    evidence=str(extra.get("lines") or "")[:500],
                    cwe_ids=[str(value) for value in metadata.get("cwe", [])],
                    references=[str(value) for value in metadata.get("references", [])[:5]],
                )
            )
        return findings
