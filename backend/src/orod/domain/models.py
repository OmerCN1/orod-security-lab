from __future__ import annotations

import re
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, HttpUrl, field_validator, model_validator


def utc_now() -> datetime:
    return datetime.now(UTC)


# Local fixture repositories are addressed as ``demo://<slug>``. The slug is a strict
# lowercase identifier so it can never escape the configured fixture root.
DEMO_REPOSITORY_RE = re.compile(r"demo://([a-z0-9][a-z0-9-]{0,63})")

# Model identifiers reach a subprocess-free code path, but they are still user input
# that ends up in prompts and reports, so keep them to the shape real ids have.
MODEL_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}")


class RunStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    AWAITING_REVIEW = "awaiting_review"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


TERMINAL_RUN_STATUSES = frozenset(
    {RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.CANCELLED}
)


class RunPhase(StrEnum):
    QUEUED = "queued"
    ARCHITECT = "architect"
    SECURITY = "security"
    DEVELOPER = "developer"
    VALIDATION = "validation"
    REVIEW = "review"
    PUBLISH = "publish"
    COMPLETE = "complete"
    FAILED = "failed"


class ReviewDecision(StrEnum):
    APPROVE = "approve"
    REJECT = "reject"
    REGENERATE = "regenerate"


class FindingSource(StrEnum):
    BANDIT = "bandit"
    SEMGREP = "semgrep"
    OSV = "osv"
    RUFF = "ruff"
    BUILTIN = "builtin"
    LLM = "llm"


class Severity(StrEnum):
    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class Confidence(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class FileEntry(BaseModel):
    path: str
    size: int
    language: str | None = None


class FileContent(BaseModel):
    path: str
    content: str
    language: str | None = None


class PackageDependency(BaseModel):
    name: str
    version: str | None = None
    source_file: str
    ecosystem: str = "PyPI"


class RepositorySnapshot(BaseModel):
    repository_url: str
    owner_repo: str | None = None
    base_branch: str = "main"
    workspace_path: str
    permission: str = "LOCAL"
    trusted: bool = False
    files: list[FileEntry] = Field(default_factory=list)
    dependencies: list[PackageDependency] = Field(default_factory=list)
    summary: str = ""


class Finding(BaseModel):
    id: str
    source: FindingSource
    rule_id: str
    severity: Severity
    confidence: Confidence = Confidence.MEDIUM
    title: str
    message: str
    file_path: str | None = None
    line: int | None = None
    evidence: str | None = None
    remediation: str | None = None
    cwe_ids: list[str] = Field(default_factory=list)
    advisory_ids: list[str] = Field(default_factory=list)
    references: list[str] = Field(default_factory=list)
    rag_context: list[str] = Field(default_factory=list)
    deterministic: bool = True
    # OSV findings only: the pinned dependency the advisory matched, and the versions
    # its affected ranges name as fixed for that package. Empty when no fix is known.
    dependency: PackageDependency | None = None
    fixed_versions: list[str] = Field(default_factory=list)


class FileEdit(BaseModel):
    """Replace one exact excerpt of an existing file with new text."""

    path: str = Field(description="Path of one of the supplied files, exactly as given.")
    search: str = Field(
        description=(
            "Text copied verbatim from that file, including indentation, long enough to "
            "occur exactly once in it."
        )
    )
    replace: str = Field(description="The text that takes the place of `search`.")


class EditProposal(BaseModel):
    """What a model returns: edits to existing files, never a diff.

    Models reliably copy and rewrite code but routinely emit unified diffs that do not
    parse or apply, so the application renders the diff from these edits itself.
    """

    edits: list[FileEdit]
    finding_ids: list[str]
    explanation: str


class PatchProposal(BaseModel):
    unified_diff: str
    changed_files: list[str]
    finding_ids: list[str]
    explanation: str
    validation_commands: list[list[str]] = Field(default_factory=list)
    # Set by model-backed providers. The diff is rendered from them against the
    # workspace before any safety gate runs; deterministic codemods supply a diff.
    edits: list[FileEdit] = Field(default_factory=list)


class DependencyUpgrade(BaseModel):
    """One pinned dependency moved to the version that clears every selected advisory."""

    name: str
    current_version: str
    target_version: str
    advisory_ids: list[str] = Field(default_factory=list)
    finding_ids: list[str] = Field(default_factory=list)


class CommandResult(BaseModel):
    argv: list[str]
    return_code: int
    stdout: str = ""
    stderr: str = ""
    duration_ms: int = 0
    timed_out: bool = False


class ScannerRun(BaseModel):
    """What one scanner contributed to a run's initial security scan."""

    name: str
    ok: bool
    findings: int = 0
    detail: str = ""


class CheckOutcome(BaseModel):
    """One fixed validation check, reduced to comparable failure identities.

    ``failures`` holds stable identities (failing file, diagnostic, test id) rather than
    raw output, so the same check on the base revision and on the patched tree can be
    compared without line numbers.
    """

    name: str
    return_code: int
    timed_out: bool = False
    failures: list[str] = Field(default_factory=list)
    passed_tests: int | None = None
    # False when the tool could not run meaningfully, e.g. pytest collected no tests.
    ran: bool = True
    # False when the output could not be interpreted; such a result is never trusted.
    parsed: bool = True


class ValidationBaseline(BaseModel):
    """The fixed checks as they came out on the base revision, before any patch."""

    checks: list[CheckOutcome] = Field(default_factory=list)

    def check(self, name: str) -> CheckOutcome | None:
        return next((item for item in self.checks if item.name == name), None)


class ValidationResult(BaseModel):
    passed: bool
    commands: list[CommandResult] = Field(default_factory=list)
    checks: list[CheckOutcome] = Field(default_factory=list)
    new_high_findings: int = 0
    # Failures that already existed on the base revision and were left unchanged.
    tolerated_failures: int = 0
    # None when no test run was attempted; False when pytest ran but executed no tests.
    tests_ran: bool | None = None
    summary: str = ""


class PullRequestResult(BaseModel):
    url: str
    number: int | None = None
    branch: str
    draft: bool = True


class ReviewRequest(BaseModel):
    """The decision a human is being asked to make about a generated patch."""

    changed_files: list[str] = Field(default_factory=list)
    explanation: str = ""
    validation_passed: bool = False
    validation_summary: str = ""
    can_approve: bool = False
    revision_count: int = 0
    requested_at: datetime = Field(default_factory=utc_now)


class ReviewSubmission(BaseModel):
    decision: ReviewDecision
    feedback: str | None = None

    @field_validator("feedback")
    @classmethod
    def normalise_feedback(cls, value: str | None) -> str | None:
        if value is None:
            return None
        collapsed = value.strip()
        if len(collapsed) > 2_000:
            raise ValueError("feedback is limited to 2000 characters")
        return collapsed or None

    @model_validator(mode="after")
    def require_feedback_for_regeneration(self) -> ReviewSubmission:
        if self.decision == ReviewDecision.REGENERATE and not self.feedback:
            raise ValueError("regeneration requires feedback describing the desired change")
        return self


class LLMUsage(BaseModel):
    """Token, latency and failure accounting for one provider over a window of calls."""

    provider: str = "none"
    model: str = ""
    calls: int = 0
    failed_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: int = 0

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    def merged_with(self, other: LLMUsage) -> LLMUsage:
        return LLMUsage(
            provider=self.provider or other.provider,
            model=self.model or other.model,
            calls=self.calls + other.calls,
            failed_calls=self.failed_calls + other.failed_calls,
            input_tokens=self.input_tokens + other.input_tokens,
            output_tokens=self.output_tokens + other.output_tokens,
            latency_ms=self.latency_ms + other.latency_ms,
        )


class RunMetrics(BaseModel):
    duration_ms: int
    total_findings: int
    findings_by_severity: dict[str, int] = Field(default_factory=dict)
    patch_generated: bool
    validation_passed: bool
    repair_attempts: int
    human_revisions: int = 0
    review_decision: str | None = None
    pull_request_created: bool
    scan_complete: bool = True


class RunCreate(BaseModel):
    repository_url: str
    base_branch: str | None = None
    trusted: bool = False
    model: str | None = None

    @field_validator("model")
    @classmethod
    def validate_model(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return None
        candidate = value.strip()
        if not MODEL_ID_RE.fullmatch(candidate):
            raise ValueError("unsupported model identifier")
        return candidate

    @field_validator("repository_url")
    @classmethod
    def validate_repository_url(cls, value: str) -> str:
        if DEMO_REPOSITORY_RE.fullmatch(value):
            return value
        parsed = HttpUrl(value)
        if parsed.scheme != "https" or parsed.host != "github.com":
            raise ValueError("only HTTPS github.com repositories or the demo URL are supported")
        return value.rstrip("/")


class RunRecord(BaseModel):
    id: str
    repository_url: str
    base_branch: str | None = None
    trusted: bool = False
    model: str | None = None
    status: RunStatus = RunStatus.QUEUED
    phase: RunPhase = RunPhase.QUEUED
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    error: str | None = None
    repository: RepositorySnapshot | None = None
    findings: list[Finding] = Field(default_factory=list)
    # Per-scanner outcome of the initial scan; empty until the scan has run.
    scanners: list[ScannerRun] = Field(default_factory=list)
    # None before scanning; False when any scanner failed, so "no findings" is not clean.
    scan_complete: bool | None = None
    patch: PatchProposal | None = None
    validation: ValidationResult | None = None
    review: ReviewRequest | None = None
    pull_request: PullRequestResult | None = None
    metrics: RunMetrics | None = None


class RunSummary(BaseModel):
    """Compact projection of a run for the history list."""

    id: str
    repository_url: str
    owner_repo: str | None = None
    model: str | None = None
    status: RunStatus
    phase: RunPhase
    created_at: datetime
    updated_at: datetime
    total_findings: int = 0
    scan_complete: bool | None = None
    validation_passed: bool | None = None
    pull_request_url: str | None = None

    @classmethod
    def from_run(cls, run: RunRecord) -> RunSummary:
        return cls(
            id=run.id,
            repository_url=run.repository_url,
            owner_repo=run.repository.owner_repo if run.repository else None,
            model=run.model,
            status=run.status,
            phase=run.phase,
            created_at=run.created_at,
            updated_at=run.updated_at,
            total_findings=len(run.findings),
            scan_complete=run.scan_complete,
            validation_passed=run.validation.passed if run.validation else None,
            pull_request_url=run.pull_request.url if run.pull_request else None,
        )


class AdvisorySyncRequest(BaseModel):
    packages: list[PackageDependency]


class AdvisorySyncResult(BaseModel):
    queried_packages: int
    matched_advisories: int
    cached_advisories: int
    errors: list[str] = Field(default_factory=list)
    # False when any OSV lookup failed, so the findings may be incomplete. Cache
    # failures do not count: they never hide a package/version match.
    complete: bool = True


class ModelOption(BaseModel):
    """A model the dashboard may offer for a run."""

    id: str
    provider: str
    available: bool
    detail: str = ""
    is_default: bool = False


class HealthComponent(BaseModel):
    ok: bool
    detail: str


class HealthResponse(BaseModel):
    status: str
    components: dict[str, HealthComponent]
    models: dict[str, str]
    version: str


JsonDict = dict[str, Any]
