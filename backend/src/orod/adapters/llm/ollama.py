from __future__ import annotations

import ast
import difflib
from typing import Any

import httpx
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_ollama import ChatOllama

from orod.adapters.llm.prompts import (
    PATCH_SYSTEM_PROMPT,
    build_patch_prompt,
    to_patch_proposal,
)
from orod.adapters.llm.usage import UsageRecorder
from orod.domain.models import EditProposal, Finding, PatchProposal, RepositorySnapshot


async def list_installed_models(base_url: str) -> list[str]:
    """Model names Ollama currently has pulled, or an empty list when it is unreachable."""
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            response = await client.get(f"{base_url.rstrip('/')}/api/tags")
            response.raise_for_status()
            payload = response.json()
    except (httpx.HTTPError, ValueError):
        return []
    names = {str(item.get("name")) for item in payload.get("models", []) if item.get("name")}
    return sorted(names)


class OllamaLLMProvider(UsageRecorder):
    provider_name = "ollama"

    def __init__(self, base_url: str, model: str) -> None:
        super().__init__(model)
        self._base_url = base_url.rstrip("/")
        self._model_name = model
        self._model = ChatOllama(
            base_url=self._base_url,
            model=model,
            temperature=0,
            validate_model_on_init=False,
        )

    async def health(self) -> tuple[bool, str]:
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                response = await client.get(f"{self._base_url}/api/tags")
                response.raise_for_status()
                names = {str(item.get("name")) for item in response.json().get("models", [])}
        except (httpx.HTTPError, ValueError):
            return False, "Ollama is unreachable"
        installed = any(
            name == self._model_name or name.startswith(f"{self._model_name}:") for name in names
        )
        return installed, "model ready" if installed else f"model not pulled: {self._model_name}"

    async def propose_patch(
        self,
        snapshot: RepositorySnapshot,
        findings: list[Finding],
        source_files: dict[str, str],
        previous_error: str | None = None,
        reviewer_feedback: str | None = None,
    ) -> PatchProposal | None:
        if not findings or not source_files:
            return None
        structured = self._model.with_structured_output(
            EditProposal, method="json_schema", include_raw=True
        )
        prompt = build_patch_prompt(
            snapshot, findings, source_files, previous_error, reviewer_feedback
        )
        with self.timed() as counters:
            envelope: Any = await structured.ainvoke(
                [SystemMessage(content=PATCH_SYSTEM_PROMPT), HumanMessage(content=prompt)]
            )
            raw = envelope.get("raw") if isinstance(envelope, dict) else None
            metadata = getattr(raw, "usage_metadata", None) or {}
            counters["input_tokens"] = int(metadata.get("input_tokens") or 0)
            counters["output_tokens"] = int(metadata.get("output_tokens") or 0)
            parsed = envelope.get("parsed") if isinstance(envelope, dict) else envelope
        # ``include_raw`` turns schema violations into a returned error rather than an
        # exception, so a malformed model response degrades to "no patch" instead of
        # failing the whole run.
        if parsed is None:
            return None
        return to_patch_proposal(
            parsed if isinstance(parsed, EditProposal) else EditProposal.model_validate(parsed)
        )


class DeterministicDemoPatchProvider(UsageRecorder):
    """Small offline fallback for the controlled shell=True demo fixture."""

    provider_name = "deterministic"

    async def health(self) -> tuple[bool, str]:
        return True, "deterministic demo provider ready"

    async def propose_patch(
        self,
        snapshot: RepositorySnapshot,
        findings: list[Finding],
        source_files: dict[str, str],
        previous_error: str | None = None,
        reviewer_feedback: str | None = None,
    ) -> PatchProposal | None:
        self.record()
        changed_files: list[str] = []
        diff_parts: list[str] = []
        finding_ids = [item.id for item in findings if item.rule_id in {"B602", "B607"}]
        if not finding_ids:
            return None
        for path, original in source_files.items():
            updated = original.replace("shell=True", "shell=False").replace(
                '["echo", value]', '["/bin/echo", value]'
            )
            if updated == original:
                continue
            changed_files.append(path)
            diff_parts.extend(
                difflib.unified_diff(
                    original.splitlines(keepends=True),
                    updated.splitlines(keepends=True),
                    fromfile=f"a/{path}",
                    tofile=f"b/{path}",
                )
            )
        if not changed_files:
            return None
        return PatchProposal(
            unified_diff="".join(diff_parts),
            changed_files=changed_files,
            finding_ids=finding_ids,
            explanation=(
                "Removed shell execution and replaced the partial executable path in the "
                "controlled demo."
            ),
            validation_commands=[
                ["python", "-m", "ruff", "check", "."],
                ["python", "-m", "pytest", "-q"],
            ],
        )


class DeterministicBanditPatchProvider(UsageRecorder):
    """AST-guided fallback for safe, mechanical Bandit remediations."""

    provider_name = "deterministic"

    @staticmethod
    def covers(findings: list[Finding]) -> bool:
        """Whether this codemod alone can resolve every one of ``findings``."""
        return bool(findings) and all(
            item.rule_id == "B607" and item.file_path and item.line for item in findings
        )

    async def propose_patch(
        self,
        snapshot: RepositorySnapshot,
        findings: list[Finding],
        source_files: dict[str, str],
        previous_error: str | None = None,
        reviewer_feedback: str | None = None,
    ) -> PatchProposal | None:
        del snapshot, previous_error, reviewer_feedback
        self.record()
        targets: dict[str, set[int]] = {}
        target_ids: list[str] = []
        for finding in findings:
            if finding.rule_id != "B607" or not finding.file_path or not finding.line:
                continue
            targets.setdefault(finding.file_path, set()).add(finding.line)
            target_ids.append(finding.id)
        if not targets:
            return None

        changed_files: list[str] = []
        diff_parts: list[str] = []
        for path, target_lines in targets.items():
            original = source_files.get(path)
            if original is None:
                continue
            updated = self._replace_partial_executables(original, target_lines)
            if updated == original:
                continue
            changed_files.append(path)
            diff_parts.extend(
                difflib.unified_diff(
                    original.splitlines(keepends=True),
                    updated.splitlines(keepends=True),
                    fromfile=f"a/{path}",
                    tofile=f"b/{path}",
                )
            )
        if not changed_files:
            return None
        return PatchProposal(
            unified_diff="".join(diff_parts),
            changed_files=changed_files,
            finding_ids=target_ids,
            explanation=(
                "Resolved subprocess executables to absolute paths with shutil.which and "
                "fail-closed handling."
            ),
            validation_commands=[
                ["python", "-m", "compileall", "-q", "."],
                ["python", "-m", "bandit", "-r", "."],
            ],
        )

    @staticmethod
    def _replace_partial_executables(source: str, target_lines: set[int]) -> str:
        try:
            tree = ast.parse(source)
        except SyntaxError:
            return source
        source_lines = source.splitlines(keepends=True)
        offsets = [0]
        for line in source_lines:
            offsets.append(offsets[-1] + len(line))
        replacements: list[tuple[int, int, str]] = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or node.lineno not in target_lines:
                continue
            function = node.func
            if not (
                isinstance(function, ast.Attribute)
                and isinstance(function.value, ast.Name)
                and function.value.id == "subprocess"
                and function.attr in {"run", "Popen", "call", "check_call", "check_output"}
                and node.args
                and isinstance(node.args[0], (ast.List, ast.Tuple))
                and node.args[0].elts
            ):
                continue
            executable = node.args[0].elts[0]
            if not (
                isinstance(executable, ast.Constant)
                and isinstance(executable.value, str)
                and executable.end_lineno is not None
                and executable.end_col_offset is not None
            ):
                continue
            start = offsets[executable.lineno - 1] + executable.col_offset
            end = offsets[executable.end_lineno - 1] + executable.end_col_offset
            replacements.append((start, end, f"_orod_require_executable({executable.value!r})"))
        if not replacements:
            return source
        updated = source
        for start, end, replacement in sorted(replacements, reverse=True):
            updated = updated[:start] + replacement + updated[end:]

        if "import shutil" not in updated:
            updated_lines = updated.splitlines(keepends=True)
            insertion = next(
                (
                    index
                    for index, line in enumerate(updated_lines)
                    if line.strip() == "import subprocess"
                ),
                0,
            )
            updated_lines.insert(insertion, "import shutil\n")
            updated = "".join(updated_lines)
        if "def _orod_require_executable(" not in updated:
            updated_tree = ast.parse(updated)
            last_import_line = max(
                (
                    int(node.end_lineno or node.lineno)
                    for node in updated_tree.body
                    if isinstance(node, (ast.Import, ast.ImportFrom))
                ),
                default=0,
            )
            updated_lines = updated.splitlines(keepends=True)
            helper = (
                "\n\ndef _orod_require_executable(name: str) -> str:\n"
                "    executable = shutil.which(name)\n"
                "    if executable is None:\n"
                "        raise RuntimeError(f'Required executable not found: {name}')\n"
                "    return executable\n"
            )
            updated_lines.insert(last_import_line, helper)
            updated = "".join(updated_lines)
        return updated
