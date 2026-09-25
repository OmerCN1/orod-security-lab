from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

CASES_ROOT = Path(__file__).parent / "cases"

ExpectedOutcome = Literal["fix", "manual_review", "detect_only", "clean"]


class ExpectedFinding(BaseModel):
    """One finding the corpus asserts the security agent must report."""

    rule_id: str
    file_path: str | None = None
    severity: str | None = None

    def key(self) -> tuple[str, str | None]:
        return (self.rule_id, self.file_path)


class EvalCase(BaseModel):
    """A single controlled repository plus the outcome the pipeline owes it.

    ``expected_outcome`` separates what the pipeline is asked to do from what it is
    merely asked to see:

    ``fix``            a validated patch is required
    ``manual_review``  policy must decline to patch and hand the finding to a human
    ``detect_only``    detection is scored, remediation is not (no safe stdlib fix)
    ``clean``          a negative control - any finding is a false positive
    """

    id: str
    title: str
    cwe: str
    expected_outcome: ExpectedOutcome
    expected_findings: list[ExpectedFinding] = Field(default_factory=list)
    allowed_extra_rules: list[str] = Field(default_factory=list)
    has_tests: bool = False
    tags: list[str] = Field(default_factory=list)
    rationale: str = ""

    @property
    def repository_url(self) -> str:
        return f"demo://{self.id}"

    @property
    def tolerated_rules(self) -> set[str]:
        return {item.rule_id for item in self.expected_findings} | set(self.allowed_extra_rules)


def load_cases(root: Path = CASES_ROOT, only: Iterable[str] | None = None) -> list[EvalCase]:
    """Load every case manifest, optionally filtered to an explicit id list."""
    wanted = set(only) if only else None
    cases: list[EvalCase] = []
    for manifest_path in sorted(root.glob("*/case.json")):
        case = EvalCase.model_validate(json.loads(manifest_path.read_text()))
        if case.id != manifest_path.parent.name:
            raise ValueError(
                f"case id {case.id!r} does not match directory {manifest_path.parent.name!r}"
            )
        if not (manifest_path.parent / "repo").is_dir():
            raise ValueError(f"case {case.id!r} has no repo/ directory")
        if wanted is None or case.id in wanted:
            cases.append(case)
    if wanted:
        missing = wanted - {case.id for case in cases}
        if missing:
            raise ValueError(f"unknown case id(s): {', '.join(sorted(missing))}")
    return cases
