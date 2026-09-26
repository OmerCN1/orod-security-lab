from __future__ import annotations

import ast
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from orod.adapters.repository.files import RepositoryFiles
from orod.domain.errors import UnsafePathError
from orod.domain.models import Confidence, Finding, FindingSource, RepositorySnapshot, Severity


class BuiltinPythonScanner:
    name = "builtin-python"

    def __init__(self, max_file_bytes: int = 1_000_000, workspace_root: Path | None = None) -> None:
        self._max_file_bytes = max_file_bytes
        self._workspace_root = workspace_root

    async def scan(self, snapshot: RepositorySnapshot) -> list[Finding]:
        reader = RepositoryFiles(
            Path(snapshot.workspace_path), self._max_file_bytes, workspace_root=self._workspace_root
        )
        findings: list[Finding] = []
        for entry in snapshot.files:
            if entry.language != "python":
                continue
            try:
                source = reader.read(entry.path).content
                tree = ast.parse(source)
            except (UnsafePathError, SyntaxError):
                continue
            lines = source.splitlines()
            for node in ast.walk(tree):
                if isinstance(node, ast.Call) and self._is_shell_true(node):
                    identity = f"{snapshot.repository_url}:{entry.path}:{node.lineno}:B602"
                    findings.append(
                        Finding(
                            id=str(uuid5(NAMESPACE_URL, identity)),
                            source=FindingSource.BUILTIN,
                            rule_id="B602",
                            severity=Severity.HIGH,
                            confidence=Confidence.HIGH,
                            title="Subprocess call uses shell=True",
                            message="Untrusted input may reach a command shell.",
                            file_path=entry.path,
                            line=node.lineno,
                            evidence=lines[node.lineno - 1].strip()[:500],
                            remediation="Pass an argv list and set shell=False.",
                            cwe_ids=["CWE-78"],
                        )
                    )
                if (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Name)
                    and node.func.id == "eval"
                ):
                    identity = f"{snapshot.repository_url}:{entry.path}:{node.lineno}:B307"
                    findings.append(
                        Finding(
                            id=str(uuid5(NAMESPACE_URL, identity)),
                            source=FindingSource.BUILTIN,
                            rule_id="B307",
                            severity=Severity.HIGH,
                            confidence=Confidence.HIGH,
                            title="Use of eval detected",
                            message="eval can execute attacker-controlled Python code.",
                            file_path=entry.path,
                            line=node.lineno,
                            evidence=lines[node.lineno - 1].strip()[:500],
                            remediation=(
                                "Use an explicit parser such as json.loads or ast.literal_eval."
                            ),
                            cwe_ids=["CWE-95"],
                        )
                    )
        return findings

    @staticmethod
    def _is_shell_true(node: ast.Call) -> bool:
        return any(
            keyword.arg == "shell"
            and isinstance(keyword.value, ast.Constant)
            and keyword.value.value is True
            for keyword in node.keywords
        )
