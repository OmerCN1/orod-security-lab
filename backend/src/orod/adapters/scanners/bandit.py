from __future__ import annotations

import json
import sys
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from orod.domain.errors import ScannerOutputError
from orod.domain.models import Confidence, Finding, FindingSource, RepositorySnapshot, Severity
from orod.ports.execution import CommandRunner

REMEDIATIONS = {
    "B607": (
        "Resolve the executable with shutil.which, fail closed when it is unavailable, "
        "and pass the resulting absolute path as argv[0]."
    ),
    "B603": (
        "Keep shell disabled and verify that every user-controlled argv value is "
        "strictly validated before execution."
    ),
}


class BanditScanner:
    name = "bandit"

    def __init__(self, runner: CommandRunner) -> None:
        self._runner = runner

    async def scan(self, snapshot: RepositorySnapshot) -> list[Finding]:
        root = Path(snapshot.workspace_path)
        result = await self._runner.run(
            [sys.executable, "-m", "bandit", "-r", ".", "-f", "json"],
            root,
            max_output_chars=5_000_000,
        )
        if result.return_code not in {0, 1}:
            raise ScannerOutputError(
                f"Bandit failed with exit code {result.return_code}: {result.stderr[-500:]}"
            )
        try:
            payload = json.loads(result.stdout or "{}")
        except json.JSONDecodeError as exc:
            raise ScannerOutputError("Bandit returned invalid or truncated JSON") from exc
        if payload.get("errors"):
            raise ScannerOutputError(f"Bandit reported scan errors: {payload['errors'][:3]}")
        findings: list[Finding] = []
        for item in payload.get("results", []):
            filename = str(item.get("filename", ""))
            try:
                candidate = Path(filename)
                if not candidate.is_absolute():
                    candidate = root / candidate
                relative = candidate.resolve().relative_to(root.resolve()).as_posix()
            except ValueError:
                relative = Path(filename).as_posix().removeprefix("./")
            rule_id = str(item.get("test_id", "B000"))
            if rule_id == "B101" and "tests" in Path(relative).parts:
                continue
            line = int(item.get("line_number", 0) or 0)
            identity = f"{snapshot.repository_url}:{relative}:{line}:{rule_id}:bandit"
            findings.append(
                Finding(
                    id=str(uuid5(NAMESPACE_URL, identity)),
                    source=FindingSource.BANDIT,
                    rule_id=rule_id,
                    severity=self._severity(item.get("issue_severity")),
                    confidence=self._confidence(item.get("issue_confidence")),
                    title=_title(item, rule_id),
                    message=str(item.get("issue_text") or "Bandit security finding"),
                    file_path=relative,
                    line=line or None,
                    evidence=str(item.get("code") or "")[:500],
                    remediation=REMEDIATIONS.get(rule_id),
                    cwe_ids=[f"CWE-{item['issue_cwe']['id']}"] if item.get("issue_cwe") else [],
                    references=[str(item["more_info"])] if item.get("more_info") else [],
                )
            )
        return findings

    @staticmethod
    def _severity(value: object) -> Severity:
        return Severity(str(value or "medium").lower())

    @staticmethod
    def _confidence(value: object) -> Confidence:
        return Confidence(str(value or "medium").lower())


def _title(item: dict[str, object], rule_id: str) -> str:
    """Build a title a person can read.

    Bandit's ``test_name`` is an internal slug - ``blacklist``,
    ``start_process_with_partial_path`` - which is what used to be shown. The human
    sentence lives in ``issue_text``, so that is the title, with the slug only as a
    fallback for output that omits it.
    """
    text = str(item.get("issue_text") or "").strip().rstrip(".")
    if text:
        return (text[0].upper() + text[1:])[:120]
    slug = str(item.get("test_name") or "").replace("_", " ").strip()
    return (slug[0].upper() + slug[1:]) if slug else rule_id
