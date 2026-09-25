from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

from evals.manifest import EvalCase
from evals.metrics import EvalReport, SuiteResult

README_START = "<!-- EVAL_TABLE_START -->"
README_END = "<!-- EVAL_TABLE_END -->"

COMPARISON_HEADER = (
    "| Model | Detection F1 | Recall | Precision | Auto-fix rate | Patch validity | "
    "Policy | Regressions | Median run | Tokens | Cost |"
)
COMPARISON_DIVIDER = "|---|---|---|---|---|---|---|---|---|---|---|"


def git_commit(repo_root: Path) -> str:
    git = shutil.which("git")
    if git is None:
        return ""
    try:
        # Fixed argv, absolute executable, no interpolated input - the same contract the
        # runtime command adapter enforces.
        result = subprocess.run(  # noqa: S603
            [git, "rev-parse", "--short", "HEAD"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return result.stdout.strip() if result.returncode == 0 else ""


def _percent(value: float) -> str:
    return f"{value * 100:.0f}%"


def _seconds(milliseconds: int) -> str:
    return f"{milliseconds / 1000:.1f}s"


def _cost(value: float | None) -> str:
    if value is None:
        return "unknown"
    if value == 0:
        return "$0.00"
    return f"${value:.4f}"


def _comparison_row(suite: SuiteResult) -> str:
    if suite.skipped_reason:
        return f"| `{suite.label}` | _skipped: {suite.skipped_reason}_ |" + " |" * 9
    totals = suite.totals
    return (
        f"| `{suite.label}` "
        f"| {totals.f1:.2f} "
        f"| {_percent(totals.recall)} "
        f"| {_percent(totals.precision)} "
        f"| {_percent(totals.fix_rate)} ({totals.fix_successes}/{totals.fix_cases}) "
        f"| {_percent(totals.patch_validity_rate)} "
        f"| {totals.policy_successes}/{totals.policy_cases} "
        f"| {totals.regressions} "
        f"| {_seconds(totals.median_duration_ms)} "
        f"| {totals.input_tokens + totals.output_tokens:,} "
        f"| {_cost(totals.cost_usd)} |"
    )


def render_comparison_table(report: EvalReport) -> str:
    rows = [COMPARISON_HEADER, COMPARISON_DIVIDER]
    rows.extend(_comparison_row(suite) for suite in report.suites)
    return "\n".join(rows)


def _render_suite_detail(suite: SuiteResult, cases: list[EvalCase]) -> str:
    if suite.skipped_reason:
        return f"### `{suite.label}`\n\nSkipped: {suite.skipped_reason}\n"

    by_id = {case.id: case for case in cases}
    lines = [
        f"### `{suite.label}`",
        "",
        f"Provider `{suite.provider}` · {suite.totals.completed_runs}/{suite.totals.cases} runs "
        f"completed · {suite.totals.outcomes_met}/{suite.totals.cases} expected outcomes met."
        + (
            f" {suite.totals.diff_rejected_cases} case(s) failed because the generated "
            "diff would not apply."
            if suite.totals.diff_rejected_cases
            else ""
        ),
        "",
        "| Case | CWE | Expected | Detected | Met | Detail | Run | Tokens |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for result in suite.results:
        case = by_id[result.case_id]
        expected = ", ".join(item.rule_id for item in case.expected_findings) or "none"
        detected = ", ".join(result.detected_rules) or "none"
        met = "yes" if result.outcome_met else "no"
        tokens = result.llm_usage.input_tokens + result.llm_usage.output_tokens
        lines.append(
            f"| `{result.case_id}` | {case.cwe} | {expected} | {detected} | {met} "
            f"| {result.outcome_detail} | {_seconds(result.duration_ms)} | {tokens:,} |"
        )
    return "\n".join(lines) + "\n"


def render_markdown(report: EvalReport, cases: list[EvalCase]) -> str:
    header = [
        "# OROD evaluation report",
        "",
        f"Generated {report.generated_at}"
        + (f" · commit `{report.git_commit}`" if report.git_commit else "")
        + f" · {report.corpus_size} controlled cases"
        + f" · scanners: {', '.join(report.scanners)}",
        "",
        "The corpus is hermetic: no network access, no external scanners, and every case "
        "is a self-contained Python repository with a known vulnerability and a known "
        "expected outcome.",
        "",
        "## Model comparison",
        "",
        render_comparison_table(report),
        "",
        "`Auto-fix rate` counts cases that require a validated patch. `Policy` counts cases "
        "where the pipeline is expected to decline and defer to a human. `Regressions` counts "
        "cases where a patch introduced a new high or critical finding.",
        "",
        "## Per-case results",
        "",
    ]
    body = [_render_suite_detail(suite, cases) for suite in report.suites]
    return "\n".join(header) + "\n".join(body)


def write_report(report: EvalReport, cases: list[EvalCase], out_dir: Path) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "results.json"
    markdown_path = out_dir / "report.md"
    json_path.write_text(report.model_dump_json(indent=2) + "\n")
    markdown_path.write_text(render_markdown(report, cases))
    return json_path, markdown_path


def publish(report: EvalReport, cases: list[EvalCase], repo_root: Path) -> list[Path]:
    """Copy the report to the committed location and refresh the README table."""
    written: list[Path] = []
    docs_dir = repo_root / "docs" / "evals"
    docs_dir.mkdir(parents=True, exist_ok=True)

    latest_json = docs_dir / "latest.json"
    latest_json.write_text(report.model_dump_json(indent=2) + "\n")
    written.append(latest_json)

    latest_markdown = docs_dir / "latest.md"
    latest_markdown.write_text(render_markdown(report, cases))
    written.append(latest_markdown)

    readme = repo_root / "README.md"
    text = readme.read_text()
    if README_START in text and README_END in text:
        prefix = text[: text.index(README_START) + len(README_START)]
        suffix = text[text.index(README_END) :]
        table = render_comparison_table(report)
        readme.write_text(f"{prefix}\n\n{table}\n\n{suffix}")
        written.append(readme)
    return written


def load_report(path: Path) -> EvalReport:
    return EvalReport.model_validate(json.loads(path.read_text()))
