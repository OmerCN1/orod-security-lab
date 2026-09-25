"""One-shot structured-output smoke test for OROD's configured Ollama model."""

from __future__ import annotations

import asyncio
import json
from tempfile import TemporaryDirectory

from orod.adapters.llm.ollama import OllamaLLMProvider
from orod.domain.models import (
    Confidence,
    Finding,
    FindingSource,
    RepositorySnapshot,
    Severity,
)


async def main() -> None:
    provider = OllamaLLMProvider("http://127.0.0.1:11434", "qwen2.5-coder:14b")
    ready, detail = await provider.health()
    if not ready:
        raise SystemExit(detail)
    finding = Finding(
        id="smoke-b602",
        source=FindingSource.BUILTIN,
        rule_id="B602",
        severity=Severity.HIGH,
        confidence=Confidence.HIGH,
        title="Subprocess call uses shell=True",
        message="Untrusted input may reach a command shell.",
        file_path="app.py",
        line=5,
        remediation="Pass an argv list and set shell=False.",
        cwe_ids=["CWE-78"],
    )
    source = (
        "import subprocess\n\n"
        "def echo(value: str) -> str:\n"
        "    return subprocess.run([\"echo\", value], shell=True, check=True).stdout\n"
    )
    with TemporaryDirectory(prefix="orod-smoke-") as workspace:
        snapshot = RepositorySnapshot(
            repository_url="smoke://local",
            workspace_path=workspace,
            trusted=True,
            summary="One-file Python smoke test.",
        )
        patch = await provider.propose_patch(snapshot, [finding], {"app.py": source})
    if patch is None:
        raise SystemExit("model returned no patch")
    print(json.dumps(patch.model_dump(), indent=2))


if __name__ == "__main__":
    asyncio.run(main())
