"""Compare a fresh suite with a recorded report, so CI fails when the pipeline regresses."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from evals.metrics import EvalReport


def suite_drift(report: EvalReport, reference_path: Path, label: str) -> list[str]:
    """What got worse in suite ``label`` compared with the recorded report.

    A case that used to meet its expected outcome and no longer does, a case with more
    new high/critical findings, or a lower detection F1 is drift. Improvements are not:
    they only mean the recorded report should be refreshed.
    """
    reference = json.loads(reference_path.read_text(encoding="utf-8"))
    recorded = next((s for s in reference.get("suites", []) if s.get("label") == label), None)
    current = next((s for s in report.suites if s.label == label), None)
    if recorded is None or current is None:
        return [f"suite {label!r} is missing from the recorded or the current report"]
    if current.skipped_reason:
        return [f"suite {label!r} was skipped: {current.skipped_reason}"]

    recorded_cases: dict[str, dict[str, Any]] = {
        case["case_id"]: case for case in recorded.get("results", [])
    }
    problems: list[str] = []
    for result in current.results:
        before = recorded_cases.get(result.case_id)
        if before is None:
            continue
        if before.get("outcome_met") and not result.outcome_met:
            problems.append(f"{result.case_id}: outcome no longer met ({result.outcome_detail})")
        if result.new_high_findings > int(before.get("new_high_findings") or 0):
            problems.append(f"{result.case_id}: new high/critical findings introduced")
    recorded_f1 = float(recorded.get("totals", {}).get("f1") or 0.0)
    if current.totals.f1 + 1e-9 < recorded_f1:
        problems.append(f"detection F1 fell from {recorded_f1:.2f} to {current.totals.f1:.2f}")
    return problems
